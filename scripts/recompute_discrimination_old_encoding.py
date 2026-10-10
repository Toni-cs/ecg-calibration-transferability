#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""在 OLD 编码下重算 results/discrimination_metrics_60exp.csv（P0 修复）。

=====================================================================
背景
=====================================================================
`results/discrimination_metrics_60exp.csv`（mtime 2026-09-10 12:45）由
`run_e2_ablation_discrimination.py` 产出，输入是 `checkpoints/e2_probs_cache/*.npz`
（全部 62 份，mtime 2026-09-10 12:30~12:40，**全部落在标签编码污染窗口内**）。

缓存里 probs 与 labels 来自**不同编码**：

* **probs** 来自 2026-09-08 训练、当时 ``SUBSPACE_CPSC=("NORM","CD","STTC","MI")``
  （OLD）的 checkpoint ⇒ 第 1 列 = CD、第 3 列 = MI。
* **labels** 是 2026-09-09 编码变更之后写入的，为 ``("NORM","MI","STTC","CD")``
  （NEW）⇒ 第 1 列 = MI、第 3 列 = CD。

于是 AUROC/AUPRC/F1/PPV/NPV/MCC 全部按错位标签算出，**判别力被系统性低估**。

=====================================================================
实证裁决（本脚本的立论依据）
=====================================================================
对 `chapman_cpsc/inceptiontime/seed42`、split=cal、variant=raw：

    缓存原样（NEW 标签） AUROC = 0.641959  ← 与 CSV 所载 0.641959 **逐位相同**（差 0.000000）
    swap13（OLD 标签）   AUROC = 0.861000  ← 正确值，比 CSV 高 **0.219**

即 CSV 确实是用错位标签算的，且修正量巨大（不是四舍五入级别）。

逐方向 OOD AUROC 均值（5 种子 × 2 架构）：

    方向            CSV(污染)   OLD(正确)     差
    chapman_cpsc      0.6743     0.7554    +0.0812
    cpsc_chapman      0.6312     0.8251    +0.1939
    cpsc_ptbxl        0.6419     0.8044    +0.1625
    ptbxl_cpsc        0.6290     0.8425    +0.2135
    （5 类的 chapman_ptbxl / ptbxl_chapman 不受影响）
    6 方向均值范围: 污染 0.629–0.792  →  正确 0.735–0.843

论文 L1840 引 "AUROC ranges from 0.629 (CPSC→Chapman) to 0.795"、L1974 引
"OOD AUROC means range 0.629--0.792"，**恰好复现污染表的 0.629–0.792** ⇒ 需改。

=====================================================================
本脚本产出
=====================================================================
`results/discrimination_metrics_60exp.OLD_ENCODING.csv`（schema 与原件一致），
每个 checkpoint 写 cal/test 两个 split × 两个 variant：

* `variant=raw` —— OLD 标签下的原始判别力。
* `variant=ts`  —— 用 OLD 编码温度表（`results/ablation_ts_components.
  OLD_ENCODING.csv` 的 stage1_ts `T_global`）做温度缩放后的判别力。
  TS 概率由 `src.utils.calibration.apply_temperature` 从缓存 probs 复原
  （多分类：`p^(1/T)` 逐行归一），无需重跑模型。

两个 variant 的 `auroc_ts_minus_raw` / `auprc_ts_minus_raw` 列都写同一个差值。

修复记录（2026-09-17 第三轮对抗审查 R3-E）：
    初版只写 `variant=raw`，并把 `auroc_ts_minus_raw` 硬编码为 `""`。
    于是该列 **124/124 全空**，且**表内不存在 ts 行** —— 结构上不可能
    支撑论文正文所引的 "mean ΔAUROC_TS−raw"。现补出 ts 行并真实填充。

用法:
    python scripts/recompute_discrimination_old_encoding.py
"""
from __future__ import annotations

import csv
import os
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

CACHE_DIR = ROOT / "checkpoints" / "e2_probs_cache"
SRC_CSV = ROOT / "results" / "discrimination_metrics_60exp.csv"
OUT_CSV = ROOT / "results" / "discrimination_metrics_60exp.OLD_ENCODING.csv"

DATASET_NUM_CLASSES = {"ptbxl": 5, "chapman": 5, "cpsc": 4}
#: 需要重编码（4 类 CPSC 子空间）的方向
NEEDS_SWAP_K = 4
#: OLD 编码的温度表（stage1_ts 的 T_global = 源域标定温度）
ABL_OLD = ROOT / "results" / "ablation_ts_components.OLD_ENCODING.csv"


def swap13(labels):
    """MI↔CD 互换：NEW 编码 (NORM,MI,STTC,CD) → OLD 编码 (NORM,CD,STTC,MI)。"""
    out = np.asarray(labels, dtype=int).copy()
    m1 = out == 1
    m3 = out == 3
    out[m1] = 3
    out[m3] = 1
    return out


def load_temperatures(path=ABL_OLD):
    """读 OLD 编码温度表，返回 {(source,target,arch,seed_str): T_global}。

    只取 stage1_ts 行。该表由 scripts/recompute_ablation_old_encoding.py 产出，
    其 stage1_ts 的 smooth_ece 与主终点 delta_obs_orig 逐位一致（已验证
    max|Δ| = 0.000e+00，见 _attack_scratch/R3VERIFY/verify_r3b.py）。
    """
    import csv as _csv
    out = {}
    if not path.exists():
        return out
    with path.open(encoding="utf-8") as fh:
        for r in _csv.DictReader(fh):
            if r.get("stage") != "stage1_ts":
                continue
            try:
                T = float(r["T_global"])
            except (TypeError, ValueError):
                continue
            out[(r["source"], r["target"], r["arch"], f"seed{int(r['seed'])}")] = T
    return out


def main() -> int:
    from run_e2_ablation_discrimination import compute_discrimination_metrics
    from src.utils.calibration import apply_temperature

    temps = load_temperatures()
    rows = []
    n_swapped = n_kept = n_ts = 0
    for p in sorted(CACHE_DIR.glob("*.npz")):
        base = p.stem
        source, target, arch, seed = base.rsplit("_", 3)
        nc = min(DATASET_NUM_CLASSES[source], DATASET_NUM_CLASSES[target])
        d = np.load(p, allow_pickle=True)
        do_swap = (nc == NEEDS_SWAP_K)
        if do_swap:
            n_swapped += 1
        else:
            n_kept += 1
        T = temps.get((source, target, arch, seed))
        for split, (pk, lk) in {
            "cal": ("cal_probs", "cal_labels"),
            "test": ("test_probs", "test_labels"),
        }.items():
            probs = np.asarray(d[pk], dtype=np.float64)
            labels = np.asarray(d[lk], dtype=int)
            if do_swap:
                labels = swap13(labels)
            m_raw = compute_discrimination_metrics(probs, labels)
            m_ts = (compute_discrimination_metrics(apply_temperature(probs, T), labels)
                    if T is not None else None)
            if m_ts is not None:
                d_auroc = m_ts["auroc"] - m_raw["auroc"]
                d_auprc = m_ts["auprc"] - m_raw["auprc"]
                n_ts += 1
            else:
                d_auroc = d_auprc = None
            for variant, m in (("raw", m_raw), ("ts", m_ts)):
                if m is None:
                    continue
                rows.append({
                    "source": source, "target": target, "arch": arch, "seed": seed,
                    "split": split, "variant": variant,
                    "auroc": f"{m['auroc']:.6f}", "auprc": f"{m['auprc']:.6f}",
                    "f1": f"{m['f1']:.6f}", "ppv": f"{m['ppv']:.6f}",
                    "npv": f"{m['npv']:.6f}", "mcc": f"{m['mcc']:.6f}",
                    "auroc_ts_minus_raw": "" if d_auroc is None else f"{d_auroc:.6f}",
                    "auprc_ts_minus_raw": "" if d_auprc is None else f"{d_auprc:.6f}",
                })

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    # 注释行与 csv.writer 的数据行统一用 CRLF —— 否则文件行尾混杂，
    # 而该文件受 SHA256SUMS.txt 哈希校验、且要与同目录其它 CSV 一致。
    NL = "\r\n"
    with OUT_CSV.open("w", encoding="utf-8", newline="") as fh:
        fh.write("# discrimination_metrics_60exp —— OLD 编码修正版（variant=raw,ts）" + NL)
        fh.write("# 由 scripts/recompute_discrimination_old_encoding.py 生成。" + NL)
        fh.write("# 原 results/discrimination_metrics_60exp.csv（09-10）用 NEW 标签" + NL)
        fh.write("# 配 OLD probs，判别力被系统性低估；本表用 OLD 标签重算。" + NL)
        fh.write("# 逐方向 OOD AUROC 均值：污染 0.629–0.792 → 正确 0.735–0.843。" + NL)
        fh.write("# variant=ts 的温度取自 results/ablation_ts_components."
                 "OLD_ENCODING.csv 的 stage1_ts T_global。" + NL)
        fh.write("# auroc_ts_minus_raw = auroc(variant=ts) - auroc(variant=raw)，"
                 "同一 (cell, split) 内。" + NL)
        fh.write(f"# 重编码 cell 数,{n_swapped};未改动(5类)cell 数,{n_kept};"
                 f"TS 行数,{n_ts}" + NL)
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    print(f"已写出 {OUT_CSV.relative_to(ROOT)}（{len(rows)} 行；"
          f"重编码 {n_swapped} 个 cache，未改动 {n_kept} 个，TS 行 {n_ts}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
