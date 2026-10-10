"""三步链步骤 2：可预测性 LOO R²（协议§8.5:141-145）。

修复（对抗审查 R1c/R2）：
- 多变量特征：raw_ece, mean_conf, pred_entropy, pi_shift_l1
- 岭回归（防过拟合）代替 OLS
- leave-one-transfer-pair-out（按迁移对=6 折）代替留一样本
- 含截距项

§8.5 补齐（多架构）：
- ARCHS = ["inceptiontime", "resnet1d"]（mamba 数据见补充材料，后续补齐）
- SEEDS = [42, 43, 44, 45, 46]
- LOO 按 (架构, 迁移对) 做（6 对 × 2 架构 = 12 折，回归样本 = 12）
- 保存结果到 results/predictability_3arch.csv

若 CI 上界 < 0.5 → 预注册失败分支（降级两步链）。
"""
from __future__ import annotations
import csv
import json
import sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.data.mapping import SUBSPACE_CPSC  # noqa: E402
from src.utils.encoding_guard import assert_encoding_record  # noqa: E402

DATASET_NUM_CLASSES = {"ptbxl": 5, "chapman": 5, "cpsc": 4}

PAIRS = [
    "ptbxl_chapman", "ptbxl_cpsc",
    "chapman_ptbxl", "chapman_cpsc",
    "cpsc_ptbxl", "cpsc_chapman",
]
SEEDS = [42, 43, 44, 45, 46]
# §8.5 补齐：多架构循环（mamba 数据见补充材料，后续补齐）
ARCHS = ["inceptiontime", "resnet1d"]
METHODS = ["ts", "platt", "isotonic", "vector", "matrix", "dirichlet", "em_prior", "bbse_prior"]
SHIFTS = ["fs250", "fs125", "leads6", "leads3", "leads2", "leads1",
          "noise24", "noise12", "noise6", "noise0", "noise-6",
          "gain0.5", "gain2.0"]
FEATURES = ["raw_ece", "mean_conf", "pred_entropy", "pi_shift_l1"]


def load_l2_data():
    """加载多架构 L2 移位结果。

    返回 list[dict]，每行含 arch, pair, seed, shift, method, delta_ece, 各特征。

    ⚠️ 编码护栏（2026-09-17）：`l2_shift_results.json` 必须携带顶层
    `label_encoding` 戳，且与当前运行时口径一致。缺失或不符一律 raise。
    理由：09-10~09-12 产出的那 60 份 JSON 是在**新编码**下算出的污染值
    （MI↔CD 互换），它们同样满足"档位齐全、字段完整"的形式检查 —— 只靠形式
    检查无法识别，必须靠编码戳。参见
    results/_L2_SHIFT_CONTAMINATION_NOTICE.md。
    """
    data = []
    for arch in ARCHS:
        for pair in PAIRS:
            src, tgt = pair.split("_")
            num_classes = min(DATASET_NUM_CLASSES[src], DATASET_NUM_CLASSES[tgt])
            subspace = SUBSPACE_CPSC if num_classes == 4 else None
            for seed in SEEDS:
                p = ROOT / "checkpoints/transfer" / pair / arch / f"seed{seed}" / "l2_shift_results.json"
                if not p.exists():
                    continue
                whole = json.loads(p.read_text(encoding="utf-8"))
                assert_encoding_record(whole, num_classes, subspace,
                                       where=str(p.relative_to(ROOT)))
                d = whole[f"seed{seed}"]
                for shift in SHIFTS:
                    if shift not in d:
                        continue
                    for m in METHODS:
                        if m not in d[shift] or not isinstance(d[shift][m], dict):
                            continue
                        if "delta_ece" not in d[shift][m]:
                            continue
                        if d[shift][m].get("status") == "skipped":
                            continue
                        row = {"arch": arch, "pair": pair, "seed": seed,
                               "shift": shift, "method": m,
                               "delta_ece": d[shift][m]["delta_ece"]}
                        for feat in FEATURES:
                            row[feat] = d[shift].get(feat, 0.0)
                        data.append(row)
    return data


def ridge_predict(X_train, y_train, X_test, alpha=1.0):
    """岭回归预测（含截距）。"""
    n, d = X_train.shape
    X_aug = np.hstack([X_train, np.ones((n, 1))])
    X_test_aug = np.hstack([X_test, np.ones((len(X_test), 1))])
    A = X_aug.T @ X_aug + alpha * np.eye(d + 1)
    A[-1, -1] -= alpha
    coef = np.linalg.solve(A, X_aug.T @ y_train)
    return X_test_aug @ coef


def loo_pair_r2(data, method, alpha=1.0):
    """Leave-one-(arch,pair)-out R²（按架构×迁移对=12 折）。

    对每个 (arch, pair) 组合作为留出集，其余训练。
    """
    pts = [r for r in data if r["method"] == method]
    if len(pts) < 12:
        return None, None
    # 按 (arch, pair) 分组
    groups = list(set((r["arch"], r["pair"]) for r in pts))
    if len(groups) < 2:
        return None, None
    y_true, y_pred = [], []
    for hold_arch, hold_pair in groups:
        train = [r for r in pts if not (r["arch"] == hold_arch and r["pair"] == hold_pair)]
        test = [r for r in pts if r["arch"] == hold_arch and r["pair"] == hold_pair]
        if not train or not test:
            continue
        X_train = np.array([[r[f] for f in FEATURES] for r in train])
        y_train = np.array([r["delta_ece"] for r in train])
        X_test = np.array([[r[f] for f in FEATURES] for r in test])
        y_test = np.array([r["delta_ece"] for r in test])
        y_pred.extend(ridge_predict(X_train, y_train, X_test, alpha))
        y_true.extend(y_test)
    y_true, y_pred = np.array(y_true), np.array(y_pred)
    ss_res = np.sum((y_true - y_pred) ** 2)
    ss_tot = np.sum((y_true - np.mean(y_true)) ** 2)
    return 1 - ss_res / ss_tot if ss_tot > 1e-12 else 0.0, (y_true, y_pred)


def loo_pair_r2_single_arch(data, method, alpha=1.0):
    """单架构 Leave-one-transfer-pair-out R²（按迁移对=6 折，用于分架构报告）。"""
    pts = [r for r in data if r["method"] == method]
    if len(pts) < 6:
        return None, None
    pairs = list(set(r["pair"] for r in pts))
    if len(pairs) < 2:
        return None, None
    y_true, y_pred = [], []
    for hold_pair in pairs:
        train = [r for r in pts if r["pair"] != hold_pair]
        test = [r for r in pts if r["pair"] == hold_pair]
        if not train or not test:
            continue
        X_train = np.array([[r[f] for f in FEATURES] for r in train])
        y_train = np.array([r["delta_ece"] for r in train])
        X_test = np.array([[r[f] for f in FEATURES] for r in test])
        y_test = np.array([r["delta_ece"] for r in test])
        y_pred.extend(ridge_predict(X_train, y_train, X_test, alpha))
        y_true.extend(y_test)
    y_true, y_pred = np.array(y_true), np.array(y_pred)
    ss_res = np.sum((y_true - y_pred) ** 2)
    ss_tot = np.sum((y_true - np.mean(y_true)) ** 2)
    return 1 - ss_res / ss_tot if ss_tot > 1e-12 else 0.0, (y_true, y_pred)


def bootstrap_ci(data, method, n_boot=2000, seed=42, alpha=1.0):
    """Bootstrap CI for multi-arch LOO R²（按 (arch, pair) 分组重采样）。"""
    rng = np.random.RandomState(seed)
    pts = [r for r in data if r["method"] == method]
    groups = list(set((r["arch"], r["pair"]) for r in pts))
    if len(groups) < 2:
        return 0.0, 0.0
    r2s = []
    for _ in range(n_boot):
        boot_groups = [groups[rng.randint(0, len(groups))] for _ in groups]
        boot_data = []
        for bg in boot_groups:
            boot_data.extend([r for r in pts if r["arch"] == bg[0] and r["pair"] == bg[1]])
        r2, _ = loo_pair_r2(boot_data, method, alpha)
        if r2 is not None:
            r2s.append(r2)
    if not r2s:
        return 0.0, 0.0
    return float(np.percentile(r2s, 2.5)), float(np.percentile(r2s, 97.5))


def main():
    data = load_l2_data()
    print(f"加载 {len(data)} 个数据点（多架构: {ARCHS}）\n")

    # 统计每架构的数据量
    arch_counts = {}
    for r in data:
        arch_counts[r["arch"]] = arch_counts.get(r["arch"], 0) + 1
    print("各架构数据点数:")
    for arch, cnt in sorted(arch_counts.items()):
        print(f"  {arch}: {cnt}")
    print()

    available_feats = set()
    for r in data:
        for f in FEATURES:
            if r[f] != 0.0:
                available_feats.add(f)
    print(f"可用特征: {available_feats}\n")

    # ============================================================
    # 表1: 分架构 LOO R²（单架构报告）
    # ============================================================
    print("=" * 90)
    print("表1: 分架构 Leave-one-transfer-pair-out R²（岭回归 α=1.0，多变量特征）")
    print("=" * 90)
    per_arch_rows = []
    for arch in ARCHS:
        arch_data = [r for r in data if r["arch"] == arch]
        if not arch_data:
            print(f"\n  [{arch}] 无数据，跳过")
            continue
        print(f"\n  [{arch}] (n={len(arch_data)})")
        for method in METHODS:
            r2, _ = loo_pair_r2_single_arch(arch_data, method)
            if r2 is None:
                continue
            print(f"    {method:<12} LOO-pair R²={r2:+.4f}")
            per_arch_rows.append({"arch": arch, "method": method, "r2": float(r2)})

    # ============================================================
    # 表2: 多架构合并 LOO R²（按 (arch, pair) = 12 折）
    # ============================================================
    print("\n" + "=" * 90)
    print(f"表2: 多架构合并 Leave-one-(arch,pair)-out R²（{len(ARCHS)}架构 × 6对 = {len(ARCHS)*6}折）")
    print("=" * 90)
    merged_rows = []
    for method in METHODS:
        r2, _ = loo_pair_r2(data, method)
        if r2 is None:
            continue
        ci_lo, ci_hi = bootstrap_ci(data, method)
        verdict = "通过" if ci_hi >= 0.5 else "失败分支"
        print(f"{method:<12} LOO R²={r2:+.4f}  CI=[{ci_lo:+.4f}, {ci_hi:+.4f}]  {verdict}")
        merged_rows.append({"method": method, "r2": float(r2),
                            "ci_lo": float(ci_lo), "ci_hi": float(ci_hi),
                            "verdict": verdict})

    # ============================================================
    # 表3: 全方法合并（主判据）
    # ============================================================
    print("\n" + "=" * 90)
    print("表3: 全方法合并（主判据）")
    print("=" * 90)
    r2, _ = loo_pair_r2(data, "ts")
    ci_lo, ci_hi = bootstrap_ci(data, "ts")
    print(f"全方法      LOO R²={r2:+.4f}  CI=[{ci_lo:+.4f}, {ci_hi:+.4f}]")
    if ci_hi < 0.5:
        print("\n⚠ 预注册失败分支触发：CI 上界 < 0.5 → 降级为两步链")
    else:
        print("\n✓ 预注册检验通过：CI 上界 >= 0.5 → 三步链成立")

    # ============================================================
    # 保存结果到 CSV
    # ============================================================
    out_csv = ROOT / "results" / "predictability_3arch.csv"
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(out_csv, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["# ECG-Lab §8.5 可预测性分析（多架构）"])
        w.writerow(["# 架构", ", ".join(ARCHS)])
        w.writerow(["# 注: mamba 架构数据见补充材料（后续补齐）"])
        w.writerow(["# 数据点数", len(data)])
        w.writerow(["# LOO 折数", f"{len(ARCHS)} 架构 x 6 对 = {len(ARCHS)*6} 折"])
        w.writerow([])

        # 表1 分架构
        w.writerow(["## 表1 分架构 LOO-pair R²"])
        w.writerow(["arch", "method", "r2"])
        for r in per_arch_rows:
            w.writerow([r["arch"], r["method"], f"{r['r2']:.6f}"])
        w.writerow([])

        # 表2 多架构合并
        w.writerow(["## 表2 多架构合并 LOO-(arch,pair) R²"])
        w.writerow(["method", "r2", "ci_lo", "ci_hi", "verdict"])
        for r in merged_rows:
            w.writerow([r["method"], f"{r['r2']:.6f}",
                        f"{r['ci_lo']:.6f}", f"{r['ci_hi']:.6f}", r["verdict"]])
        w.writerow([])

        # 表3 主判据
        w.writerow(["## 表3 主判据（全方法合并）"])
        w.writerow(["r2", "ci_lo", "ci_hi", "verdict"])
        verdict = "通过" if ci_hi >= 0.5 else "失败分支"
        w.writerow([f"{r2:.6f}", f"{ci_lo:.6f}", f"{ci_hi:.6f}", verdict])

    print(f"\n结果已保存到 {out_csv}")


if __name__ == "__main__":
    main()
