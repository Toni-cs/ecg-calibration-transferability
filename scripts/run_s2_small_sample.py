"""S2 本地小样本再校准（协议 §5 S2，预注册场景，eval-only / CPU）

协议定义（docs/EXPERIMENT_PROTOCOL.md §5:92）
---------------------------------------------
S2 本地小样本再校准（临床手册）：目标域 n_cal ∈ {50,100,250,500,1000} 有标签
样本，患者级抽样 × 20 重复 → "标注预算-收益挽回"剂量曲线。
规模：4 方法 × 5 n_cal × 20 重复（本实现另加 S1-TS 零样本对照，见下）。

设计决策（本脚本领先披露，写作时同步进论文）
---------------------------------------------
D1. 标注预算语义：按患者级无放回抽样累积记录至 ≥ n_cal，再截断到恰好
    n_cal 条（"买 n 条标注"预算语义；末位患者可部分纳入）。
D2. 评估集：拟合样本之外的**补集**（held-out complement），防止 n_cal 最大
    达 test 的 25-46% 时的 in-sample 污染。raw 与各方法在**同一补集**上
    配对评估，benefit = smooth_ece(raw, comp) − smooth_ece(post, comp)。
D3. 方法：协议 4 方法 = TS / per-class Platt / Dirichlet / Isotonic(OvR)。
    Isotonic 小样本防护（n_cal ≤ 10K 返回 None，协议预注册失效区间）
    如实记 NaN。另加对照 **ts_s1**：源 cal 拟合温度一次性应用到补集
    （与主终点 S1 范式一致），不参与"再校准"剂量语义，仅作零样本基线。
D4. 患者结构：Chapman 每患者 1 条记录（患者级=记录级，如实报告）；
    PTB-XL / CPSC 存在同患者多记录。
D5. SmoothECE：与主终点同估计量（src.utils.calibration.smooth_ece），
    带宽用其默认 n 缩放规则；GPU 实现（float64 与 CPU 数值一致）优先，
    CUDA 异常自动回退 CPU。
D6. provenance 守卫（硬断言，任一失败即中止不出数）：
    - 缓存必须携带编码戳且等于运行期推导值（K=4→SUBSPACE_CPSC 戳）；
    - clusters_test 长度 == 缓存 test_probs 行数；
    - 数据集 test 标签 == 缓存 test_labels（逐位）。
D7. 随机性：每 (pair, arch, seed, n_cal, repeat) 独立确定性
    Generator（PCG64 seed 序列），与循环顺序无关。

输出
----
results/s2_dose_response.csv          逐 (cell, method, n_cal, repeat) 行
results/s2_dose_response_summary.json 聚合（方法×n_cal：cell 级均值收益、
                                      正收益格占比、按 pair 分解）
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT / "scripts"))

from src.data.mapping import SUBSPACE_CPSC  # noqa: E402
from src.utils.calibration import smooth_ece, smooth_ece_gpu  # noqa: E402
from src.utils.calibration_methods import (  # noqa: E402
    CALIBRATION_METHODS,
    apply_temperature_multiclass,
    fit_temperature_multiclass,
)

CACHE_DIR = _PROJECT_ROOT / "checkpoints" / "e2_probs_cache"
RESULTS_DIR = _PROJECT_ROOT / "results"
CACHE_STAMP_KEY = "label_encoding"

PAIRS = [
    ("chapman", "cpsc"), ("chapman", "ptbxl"),
    ("cpsc", "chapman"), ("cpsc", "ptbxl"),
    ("ptbxl", "chapman"), ("ptbxl", "cpsc"),
]
ARCHS = ["inceptiontime", "resnet1d"]
SEEDS = [42, 43, 44, 45, 46]
DATASET_NUM_CLASSES = {"ptbxl": 5, "chapman": 5, "cpsc": 4}

N_CAL_GRID = [50, 100, 250, 500, 1000]
REPEATS = 20
S2_METHODS = ["ts", "platt", "dirichlet", "isotonic"]  # 协议 §5 S2 四方法
RNG_DOMAIN = 20260927  # 本实验专属 rng 域分隔符


def expected_stamp(num_classes: int) -> str:
    from src.utils.encoding_guard import encoding_stamp

    return encoding_stamp(num_classes, SUBSPACE_CPSC if num_classes == 4 else None)


def build_target(target: str, seed: int, subspace):
    """重建 target 数据集元数据（ECGNPZDataset 惰性加载，仅读 metadata CSV）。

    返回 (ds_dict, clusters_test)。clusters_test = test 记录的患者 ID，
    与数据集顺序（即缓存 test_probs 行序）对齐（train.py L393-394 契约）。
    """
    # 惰性导入：train.py 顶层较重；DATA_DIRS 与 run_e2 L124-128 保持一致
    from train import (build_chapman_datasets, build_cpsc_datasets,  # noqa: E402
                       build_ptbxl_datasets)

    data_dir = str((_PROJECT_ROOT / "data" / {
        "ptbxl": "ptbxl_processed",
        "chapman": "chapman_processed_v2",
        "cpsc": "cpsc_processed",
    }[target]))
    builders = {"ptbxl": build_ptbxl_datasets, "chapman": build_chapman_datasets,
                "cpsc": build_cpsc_datasets}
    if target == "cpsc":
        ds, clusters = builders[target](data_dir, seed, limit=None)
    elif subspace is not None:
        ds, clusters = builders[target](data_dir, seed, limit=None, subspace=subspace)
    else:
        ds, clusters = builders[target](data_dir, seed, limit=None)
    return ds, clusters


def smooth_ece_safe(probs: np.ndarray, labels: np.ndarray) -> float:
    """GPU 优先、CPU 回退的 SmoothECE（confidence 口径，与主终点同一换算）。

    全仓约定（tests/test_calibration_methods.py L51、diagnose_json_orig_fields.py L53）：
    smooth_ece 输入为 1-D 置信度与 0/1 正确性，即
    conf = max_c p_c，correct = (argmax_c p_c == y)。
    """
    conf = probs.max(axis=1)
    corr = (probs.argmax(axis=1) == labels).astype(np.float64)
    try:
        return float(smooth_ece_gpu(conf, corr))
    except Exception:
        return float(smooth_ece(conf, corr))


def sample_patient_budget(clusters: np.ndarray, n_cal: int,
                          rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    """患者级无放回抽样，累积至 ≥ n_cal 后截断到恰好 n_cal 条（决策 D1）。

    返回 (sample_idx, comp_idx)：补集保持数据集顺序。
    """
    pids = np.unique(clusters)
    order = rng.permutation(pids)
    by_pid = {p: np.flatnonzero(clusters == p) for p in order}
    chosen: list[int] = []
    for p in order:
        chosen.extend(by_pid[p].tolist())
        if len(chosen) >= n_cal:
            break
    sample_idx = np.sort(np.asarray(chosen[:n_cal], dtype=int))
    mask = np.ones(len(clusters), dtype=bool)
    mask[sample_idx] = False
    comp_idx = np.flatnonzero(mask)
    return sample_idx, comp_idx


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeats", type=int, default=REPEATS)
    ap.add_argument("--out", default="results/s2_dose_response.csv")
    args = ap.parse_args()

    t_start = time.time()
    rows: list[dict] = []
    n_cells_done = 0

    for pair_i, (src, tgt) in enumerate(PAIRS):
        num_classes = min(DATASET_NUM_CLASSES[src], DATASET_NUM_CLASSES[tgt])
        runtime_subspace = SUBSPACE_CPSC if num_classes == 4 else None
        exp_stamp = expected_stamp(num_classes)

        # 每 (target, seed) 只重建一次数据集元数据
        meta_cache: dict[int, tuple] = {}
        for seed in SEEDS:
            if tgt not in meta_cache:
                ds, clusters = build_target(tgt, seed, runtime_subspace)
                clusters = np.asarray(clusters)
                meta_cache[seed] = (ds, clusters)
            ds, clusters = meta_cache[seed]

            for arch in ARCHS:
                cell = f"{src}_{tgt}_{arch}_seed{seed}"
                cache_file = CACHE_DIR / f"{cell}.npz"
                if not cache_file.exists():
                    raise FileNotFoundError(f"[provenance] 缓存缺失: {cache_file}")
                z = np.load(cache_file, allow_pickle=True)
                if CACHE_STAMP_KEY not in z.files:
                    raise RuntimeError(f"[provenance] {cell}: 缓存无编码戳")
                if str(z[CACHE_STAMP_KEY]) != exp_stamp:
                    raise RuntimeError(
                        f"[provenance] {cell}: 戳不符 {z[CACHE_STAMP_KEY]} ≠ {exp_stamp}")
                test_probs = np.asarray(z["test_probs"], dtype=np.float64)
                test_labels = np.asarray(z["test_labels"])

                # D6 provenance 硬断言
                if len(clusters) != test_probs.shape[0]:
                    raise RuntimeError(
                        f"[provenance] {cell}: clusters_test {len(clusters)} ≠ "
                        f"test_probs {test_probs.shape[0]}")
                if not np.array_equal(np.asarray(ds["test"].y), test_labels):
                    raise RuntimeError(f"[provenance] {cell}: 数据集标签 ≠ 缓存标签")

                # S1 对照：源 cal 拟合温度（每格一次），应用到补集
                cal_probs = np.asarray(z["cal_probs"], dtype=np.float64)
                cal_labels = np.asarray(z["cal_labels"])
                ts_s1_params = fit_temperature_multiclass(cal_probs, cal_labels)

                for n_cal in N_CAL_GRID:
                    for rep in range(args.repeats):
                        rng = np.random.default_rng(
                            [RNG_DOMAIN, pair_i, ARCHS.index(arch), seed, n_cal, rep])
                        s_idx, c_idx = sample_patient_budget(clusters, n_cal, rng)
                        p_comp, y_comp = test_probs[c_idx], test_labels[c_idx]
                        ece_raw = smooth_ece_safe(p_comp, y_comp)

                        def add(method: str, ece_post):
                            rows.append({
                                "cell": cell, "pair": f"{src}->{tgt}",
                                "arch": arch, "seed": seed,
                                "n_cal": n_cal, "n_eff": int(len(s_idx)),
                                "repeat": rep, "method": method,
                                "ece_raw": ece_raw,
                                "ece_post": ece_post,
                                "benefit": ece_raw - ece_post,
                            })

                        add("ts_s1", smooth_ece_safe(
                            apply_temperature_multiclass(p_comp, ts_s1_params),
                            y_comp))

                        for m in S2_METHODS:
                            fit_fn, apply_fn, _ = CALIBRATION_METHODS[m]
                            params = fit_fn(test_probs[s_idx], test_labels[s_idx])
                            if params is None:  # isotonic 小样本防护
                                add(m, float("nan"))
                                continue
                            post = apply_fn(p_comp, params)
                            add(m, smooth_ece_safe(post, y_comp))

                n_cells_done += 1
                print(f"[{n_cells_done}/60] {cell} done "
                      f"({time.time() - t_start:.0f}s)", flush=True)

    out_path = _PROJECT_ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    df.to_csv(out_path, index=False)

    # ---------------- 聚合：剂量曲线 ----------------
    # cell 级：先对 repeat 求均值（NaN 自动跳过），再跨 60 格聚合
    cell_lvl = (df.dropna(subset=["benefit"])
                  .groupby(["pair", "arch", "seed", "method", "n_cal"],
                           as_index=False)["benefit"].mean())
    summary = {"design": {
        "n_cal_grid": N_CAL_GRID, "repeats": int(args.repeats),
        "methods": ["ts_s1"] + S2_METHODS,
        "evaluation": "held-out complement of the n_cal sample",
        "budget_semantics": "patient-level sampling truncated to exactly n_cal records",
        "metric": "SmoothECE (5-class confidence), bandwidth = default n-scaled",
        "provenance_guards": "stamp + clusters length + bit-exact labels",
    }, "dose_curve": [], "by_pair": []}
    for (m, n), g in cell_lvl.groupby(["method", "n_cal"]):
        summary["dose_curve"].append({
            "method": m, "n_cal": int(n), "n_cells": int(len(g)),
            "mean_benefit": float(g["benefit"].mean()),
            "sd_benefit": float(g["benefit"].std(ddof=1)),
            "frac_cells_positive": float((g["benefit"] > 0).mean()),
        })
    for (m, n, pr), g in cell_lvl.groupby(["method", "n_cal", "pair"]):
        summary["by_pair"].append({
            "method": m, "n_cal": int(n), "pair": pr,
            "mean_benefit": float(g["benefit"].mean()),
            "frac_cells_positive": float((g["benefit"] > 0).mean()),
        })
    json_path = out_path.with_name("s2_dose_response_summary.json")
    json_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False))

    print(f"\n完成：{len(df)} 行 → {out_path}")
    print(f"聚合 → {json_path}")
    dc = pd.DataFrame(summary["dose_curve"])
    pivot = dc.pivot(index="n_cal", columns="method", values="mean_benefit")
    pivot = pivot.reindex(columns=["ts_s1", "ts", "platt", "dirichlet", "isotonic"])
    print("\n剂量曲线（cell 级 mean benefit，ECE 点数）：")
    print(pivot.round(4).to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
