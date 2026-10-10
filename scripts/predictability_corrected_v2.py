"""可预测性分析（修正世界 v2）：LOO R² 全段统一到修正编码口径

背景（双世界问题，2026-09-27 审计确诊）
----------------------------------------
论文 §predictability 原有 LOO R²=+0.340/+0.361 来自 predictability_corrected.py，
其 y/T 均取 **OLD 编码世界**（robustness_validation_5seeds.csv +
ablation_ts_components.OLD_ENCODING.csv）。而同节的判别报告
（sens=spec=1.0, 60/60）运行在**修正世界**（重训 checkpoint + 重建缓存）。
两个世界混用同一段落：审稿人用 OLD 世界复算符号一致性只得 59/60
（违反格 cpsc_ptbxl_inceptiontime_seed43: y=-0.0057, T_old=1.0908>1）。

本脚本把 LOO R² / bootstrap CI / 符号预测**全部重算到修正世界**，
与判别实验（counterexample_discrimination.csv）共用同一数据源，
实现 §predictability 单一数据世界。

口径（全部修正世界）
--------------------
y      = delta_obs_orig（results/rebuild_shapley_slopeT.csv）
         内置断言：delta_obs_orig == raw_ood_orig − cal_ood_orig（tol 1e-9）
T      = T_src（同文件；与 E2 重跑新表 T_global 逐格一致，已交叉验证）
wass   = Wasserstein-1（标签无关，编码无关）
ent    = 类间熵差（标签无关，编码无关）
         二者取自 results/strengthening_battle_corrected.json

三重交叉断言（任一失败即中止不出数）
------------------------------------
A1. y 自洽：delta_obs_orig == raw − cal（tol 1e-9，逐格）。
A2. 与判别 CSV 逐格一致：T_src、delta_obs_orig 与
    counterexample_discrimination.csv 完全相等（tol 1e-12）。
A3. 符号一致性复算 = 60/60（与论文判别报告互证）。

统计结构（与 predictability_corrected.py 完全一致，保证可比）
------------------------------------------------------------
岭回归 alpha=1.0；三种折单元（cell / pair / (arch,pair)）LOO R²；
(arch,pair) 聚类 bootstrap B=4000，seed=42。

输出
----
results/predictability_corrected_v2.csv
"""
from __future__ import annotations
import csv
import json
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent.parent

REBUILD_CSV = ROOT / "results/rebuild_shapley_slopeT.csv"
CORR_JSON = ROOT / "results/strengthening_battle_corrected.json"
DISC_CSV = ROOT / "results/counterexample_discrimination.csv"
OUT_CSV = ROOT / "results/predictability_corrected_v2.csv"

ALPHA = 1.0
N_BOOT = 4000
BOOT_SEED = 42
TOL_SELF = 1e-9
TOL_CROSS = 1e-12


def read_csv(p: Path):
    if not p.exists():
        raise SystemExit(f"[致命] 缺少输入 {p} —— 不静默回退。")
    with open(p, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def build():
    """返回 keys, y, T, W, E, pair, arch（全部修正世界，n=60）。"""
    # --- 主源：rebuild_shapley_slopeT.csv ---
    main = {}
    for r in read_csv(REBUILD_CSV):
        k = (f'{r["source"]}_{r["target"]}', r["arch"], str(int(r["seed"])))
        y_, raw_, cal_ = (float(r["delta_obs_orig"]), float(r["raw_ood_orig"]),
                          float(r["cal_ood_orig"]))
        # A1: y 自洽断言
        if abs(y_ - (raw_ - cal_)) > TOL_SELF:
            raise SystemExit(f"[A1 致命] {k}: delta_obs_orig={y_:.12f} ≠ "
                             f"raw−cal={raw_ - cal_:.12f}")
        main[k] = (y_, float(r["T_src"]))

    # --- 标签无关特征 ---
    free = {}
    for r in json.loads(CORR_JSON.read_text(encoding="utf-8")):
        free[(f'{r["source"]}_{r["target"]}', r["arch"], str(r["seed"]))] = \
            (r["wasserstein"], r["entropy_diff"])

    # --- A2: 与判别 CSV 交叉断言 ---
    disc = {r["cell"]: r for r in read_csv(DISC_CSV)}
    if len(disc) != 60:
        raise SystemExit(f"[A2 致命] 判别 CSV 行数 {len(disc)} ≠ 60。")
    for k, (y_, t_) in main.items():
        cell = f"{k[0]}_{k[1]}_seed{k[2]}"
        if cell not in disc:
            raise SystemExit(f"[A2 致命] {cell} 不在判别 CSV。")
        if (abs(float(disc[cell]["T_src"]) - t_) > TOL_CROSS
                or abs(float(disc[cell]["delta_obs_orig"]) - y_) > TOL_CROSS):
            raise SystemExit(f"[A2 致命] {cell}: 与判别 CSV 数值不一致。")
    print(f"[A2] {len(main)} 格与判别 CSV 的 T_src / delta_obs_orig 逐格一致"
          f"（tol {TOL_CROSS:g}）")

    keys = sorted(k for k in main if k in free)
    if len(keys) != 60:
        raise SystemExit(f"[致命] 交集 cell 数 {len(keys)} ≠ 60 —— 口径已漂移。")

    y = np.array([main[k][0] for k in keys])
    T = np.array([main[k][1] for k in keys])
    W = np.array([free[k][0] for k in keys])
    E = np.array([free[k][1] for k in keys])
    pair = np.array([k[0] for k in keys])
    arch = np.array([k[1] for k in keys])
    return keys, y, T, W, E, pair, arch


def loo_r2(y, X, groups, alpha=ALPHA):
    """留一组外的岭回归 R²。X: (n, d)。"""
    pred = np.full(len(y), np.nan)
    for g in sorted(set(groups)):
        te, tr = groups == g, groups != g
        if tr.sum() < 2 or te.sum() == 0:
            continue
        Xa = np.hstack([X[tr], np.ones((tr.sum(), 1))])
        Xb = np.hstack([X[te], np.ones((te.sum(), 1))])
        A = Xa.T @ Xa + alpha * np.eye(X.shape[1] + 1)
        A[-1, -1] -= alpha
        try:
            pred[te] = Xb @ np.linalg.solve(A, Xa.T @ y[tr])
        except np.linalg.LinAlgError:
            continue
    ok = ~np.isnan(pred)
    if ok.sum() < 3:
        return np.nan
    return 1 - np.sum((y[ok] - pred[ok]) ** 2) / np.sum((y[ok] - y[ok].mean()) ** 2)


def boot_ci(y, X, ap, n_boot=N_BOOT, seed=BOOT_SEED):
    """按 (arch,pair) 聚类重采样的 LOO R² 95% CI（两种折单元）。"""
    rng = np.random.RandomState(seed)
    groups = sorted(set(ap))
    bc, ba = [], []
    for _ in range(n_boot):
        bg = [groups[rng.randint(0, len(groups))] for _ in groups]
        idx = np.concatenate([np.where(ap == g)[0] for g in bg])
        yy, XX, pp = y[idx], X[idx], ap[idx]
        c = loo_r2(yy, XX, np.arange(len(yy)))
        a = loo_r2(yy, XX, pp)
        if np.isfinite(c):
            bc.append(c)
        if np.isfinite(a):
            ba.append(a)
    out = {}
    for nm, b in (("cell", bc), ("arch_pair", ba)):
        b = np.array(b)
        out[nm] = (float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5))) if len(b) else (np.nan, np.nan)
    return out


def main():
    keys, y, T, W, E, pair, arch = build()
    ap = np.array([f"{a}|{p}" for a, p in zip(arch, pair)])
    cell = np.arange(len(y))

    print(f"\nn = {len(y)}   y mean = {y.mean():+.6f}   T median = {np.median(T):.4f} "
          f"range = [{T.min():.4f}, {T.max():.4f}]")

    feats = {
        "T": T.reshape(-1, 1),
        "wasserstein": W.reshape(-1, 1),
        "entropy_diff": E.reshape(-1, 1),
        "T+wass+ent": np.c_[T, W, E],
    }

    rows = []
    print("\n" + "=" * 92)
    print(f"{'特征集':<14} {'corr':>9} {'R²(corr²)':>10} {'LOO cell':>10} {'LOO pair':>10} "
          f"{'LOO (a,p)':>10} {'CI(a,p) lo':>11} {'CI(a,p) hi':>11}")
    print("=" * 92)
    for nm, X in feats.items():
        c = float(np.corrcoef(y, X[:, 0])[0, 1]) if X.shape[1] == 1 else np.nan
        r_cell = loo_r2(y, X, cell)
        r_pair = loo_r2(y, X, pair)
        r_ap = loo_r2(y, X, ap)
        ci = boot_ci(y, X, ap)
        print(f"{nm:<14} {c:>+9.4f} {c**2:>10.4f} {r_cell:>+10.4f} {r_pair:>+10.4f} "
              f"{r_ap:>+10.4f} {ci['arch_pair'][0]:>+11.4f} {ci['arch_pair'][1]:>+11.4f}")
        rows.append(dict(feature_set=nm, corr=c, r2_corr2=c ** 2, loo_cell=r_cell,
                         loo_pair=r_pair, loo_arch_pair=r_ap,
                         ci_arch_pair_lo=ci["arch_pair"][0], ci_arch_pair_hi=ci["arch_pair"][1],
                         ci_cell_lo=ci["cell"][0], ci_cell_hi=ci["cell"][1]))

    # 符号预测（A3 断言）
    acc = float((np.sign(y) == np.sign(T - 1.0)).mean())
    base = float((y > 0).mean())
    n_pos = int((y > 0).sum())
    print("\n" + "=" * 92)
    print("符号预测（T 为源侧拟合量，不需目标域标签）")
    print("=" * 92)
    print(f"  sign(ΔECE_OOD) == sign(T−1) : {int(acc*len(y))}/{len(y)} = {acc:.1%}")
    print(f"  常数恒正基线               : {n_pos}/{len(y)} = {base:.1%}")
    print(f"  T>=1 的 cell: {int((T>=1).sum())} 个, 其中 ΔECE>0: {int(((T>=1)&(y>0)).sum())}")
    print(f"  T< 1 的 cell: {int((T<1).sum())} 个, 其中 ΔECE<0: {int(((T<1)&(y<0)).sum())}")

    # A3: 与论文判别报告互证
    if int(acc * len(y)) != 60:
        raise SystemExit(f"[A3 致命] 符号一致性 {int(acc*len(y))}/60 ≠ 60/60，"
                         f"与判别报告矛盾 —— 停止出数。")
    print(f"[A3] 符号一致性 60/60 复算通过，与 counterexample_discrimination 一致。")

    verdict = "失败分支触发" if rows[0]["ci_arch_pair_hi"] < 0.5 else "失败分支【不】触发"
    print(f"\n预注册判据（(arch,pair) 折，CI 上界 < 0.5 → 失败分支）：{verdict}")
    print(f"  T 的 CI 上界 = {rows[0]['ci_arch_pair_hi']:+.4f}；"
          f"cell 折 CI 上界 = {rows[0]['ci_cell_hi']:+.4f}"
          f"（{'>= 0.5，会翻转判定' if rows[0]['ci_cell_hi'] >= 0.5 else '< 0.5'}）")

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_CSV, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["# ECG-Lab 可预测性分析（修正世界 v2，单一编码口径）"])
        w.writerow(["# y", "delta_obs_orig (corrected world, rebuild_shapley_slopeT.csv; 断言=raw-cal)"])
        w.writerow(["# T", "T_src (corrected world, rebuild_shapley_slopeT.csv; 与E2重跑新表一致)"])
        w.writerow(["# wass/ent", "strengthening_battle_corrected.json（标签无关）"])
        w.writerow(["# 交叉断言", "counterexample_discrimination.csv 逐格一致 (A2); sign=60/60 (A3)"])
        w.writerow(["# n", len(y)])
        w.writerow(["# ridge alpha", ALPHA, "# bootstrap B", N_BOOT, "# cluster", "(arch,pair)"])
        w.writerow(["# sign_accuracy", f"{acc:.6f}", "# const_positive_baseline", f"{base:.6f}"])
        w.writerow(["# verdict", verdict])
        w.writerow([])
        w.writerow(["feature_set", "corr", "r2_corr2", "loo_cell", "loo_pair",
                    "loo_arch_pair", "ci_arch_pair_lo", "ci_arch_pair_hi",
                    "ci_cell_lo", "ci_cell_hi"])
        for r in rows:
            w.writerow([r["feature_set"], f"{r['corr']:.6f}", f"{r['r2_corr2']:.6f}",
                        f"{r['loo_cell']:.6f}", f"{r['loo_pair']:.6f}",
                        f"{r['loo_arch_pair']:.6f}", f"{r['ci_arch_pair_lo']:.6f}",
                        f"{r['ci_arch_pair_hi']:.6f}", f"{r['ci_cell_lo']:.6f}",
                        f"{r['ci_cell_hi']:.6f}"])
    print(f"\n结果已保存到 {OUT_CSV}")


if __name__ == "__main__":
    main()
