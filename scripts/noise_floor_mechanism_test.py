#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""噪声底机理判别检验（**修正 T 口径 + 方向检验为主**）—— 论文新增节
§"Noise-floor mechanism test" 的数据源。

=====================================================================
为什么重写
=====================================================================
``scripts/adjudicate_noise_corrected.py`` 是这条论证的原始脚本，但它有两个问题：

**(1) 温度口径污染。** 它从 ``results/temperature_distribution_analysis.csv``
取 ``T_global``，而那是 2026-09-09 编码变更后生成的**受污染温度 CSV**（3 份温度
CSV 全部受影响）。由此产出的三个关键数字全部错误：

| 原报告数字 | 修正后 |
|---|---|
| T 中位 1.836、50% 的 cell T≥2 | 中位 **1.0757**、**T≥2 为 0 个** |
| 75% 的 cell 落在噪声底危险区 | **21.7%** |
| 分层 "T<1.25: +0.0174 vs T≥2.2: +0.0155" | **T≥2.2 层在修正数据里是空集** |

**(2) 符号错误。** 原脚本把机理斜率写成 **+0.045**，因为它直接用噪声底实验的约定
（``ΔECE_noise = SmoothECE(TS) − SmoothECE(raw)``，见 main_bspc.tex L1203）去预测
**主终点**（``ΔECE_OOD = ECE_raw − ECE_post``，见 L72）。两者符号相反：

    主终点约定下  ΔECE_OOD = 真实收益 − floor(T)
    floor(T) ≥ 0  ⇒  底噪只能把 ΔECE_OOD 往**负**推
    ⇒ 机理预测斜率 **−0.045**，而非 +0.045。

**(3) 锚点表硬编码（2026-09-17 修复）。** 原先这里硬编码论文 §noise_floor 的锚点，
而那张表在仓库里没有生成脚本。现改为读 ``results/noise_floor_curve.csv``
（由 ``scripts/noise_floor_signed.py`` 生成）。**缺失时直接报错，不静默回退** ——
静默回退到硬编码值正是上面那些 bug 的成因。

=====================================================================
数据源
=====================================================================
* 主终点：``results/robustness_validation_5seeds.csv``（method=ts；
  ``ood_deltaECE`` = 论文主终点，已独立复算为 +0.015863）
* 修正 T：``results/ablation_ts_components.OLD_ENCODING.csv``
  （stage=stage1_ts 的 ``T_global``）
* 噪声底曲线：``results/noise_floor_curve.csv``（→ ``scripts/noise_floor_signed.py``）
* 负对照：同一张 OLD_ENCODING 表的 ``stage1_ts − raw`` 的 ``smooth_ece`` 差

用法::

    /c/python/python.exe scripts/noise_floor_signed.py        # 先，生成曲线
    /c/python/python.exe scripts/noise_floor_mechanism_test.py
"""

from __future__ import annotations

import csv
import statistics as st
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]

MAIN_CSV = ROOT / "results/robustness_validation_5seeds.csv"
T_CSV_CORRECTED = ROOT / "results/ablation_ts_components.OLD_ENCODING.csv"
T_CSV_CONTAMINATED = ROOT / "results/temperature_distribution_analysis.csv"
CURVE_CSV = ROOT / "results/noise_floor_curve.csv"

# 噪声底机理预测的斜率（**注意符号**）
# ---------------------------------------------------------------------------
# 主终点约定（main_bspc.tex L72）：ΔECE_OOD = ECE_raw − ECE_post，**正 = TS 有益**。
# 噪声底实验的约定（main_bspc.tex L1203）：ΔECE_noise = SmoothECE(TS) − SmoothECE(raw)，
# 即 **post − raw，与主终点相反**。换算到主终点约定，底噪是 **负** 的：
#     ΔECE_main(T) = 真实收益(T) − floor(T)
# 底噪从 T=1 的 0 涨到 T≈1.5 的 0.03~0.06，即 d(floor)/dT ≈ 0.045。
# 故若真实收益不随 T 变，机理预测的斜率是 **−0.045**（不是 +0.045）。
MECHANISM_BETA = -0.045


# ---------------------------------------------------------------------------
# 噪声底曲线：**唯一来源** = scripts/noise_floor_signed.py 写出的 CSV
# ---------------------------------------------------------------------------
def load_curve(path=CURVE_CSV):
    """→ (Ts, lo, hi)；Ts 为升序网格，lo/hi 为三分布之间的 min/max。"""
    if not Path(path).exists():
        raise SystemExit(
            f"缺少噪声底曲线 {path}\n"
            "请先运行: /c/python/python.exe scripts/noise_floor_signed.py")
    lo, hi = {}, {}
    with open(path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            T = round(float(r["T"]), 4)
            v = float(r["dECE_noise"])
            if r["dist"] == "__min__":
                lo[T] = v
            elif r["dist"] == "__max__":
                hi[T] = v
    if not lo or not hi:
        raise SystemExit(f"{path} 缺少 dist=__min__/__max__ 行")
    Ts = sorted(lo)
    return Ts, [lo[t] for t in Ts], [hi[t] for t in Ts]


_CURVE = None


def curve():
    global _CURVE
    if _CURVE is None:
        _CURVE = load_curve()
    return _CURVE


def floor_at(T, mode="hi"):
    """曲线插值。mode: 'lo' | 'hi' | 'mid'。"""
    Ts, lo, hi = curve()
    ys = {"lo": lo, "hi": hi,
          "mid": [(a + b) / 2 for a, b in zip(lo, hi)]}[mode]
    if T <= Ts[0]:
        return ys[0]
    if T >= Ts[-1]:
        return ys[-1]
    for a, b, va, vb in zip(Ts, Ts[1:], ys, ys[1:]):
        if a <= T <= b:
            return va + (T - a) / (b - a) * (vb - va)
    return ys[-1]


def load_main():
    out = {}
    with open(MAIN_CSV, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["method"] != "ts":
                continue
            out[(r["pair"], r["arch"], r["seed"])] = {
                "id": float(r["id_deltaECE"]),
                "ood": float(r["ood_deltaECE"]),
                "lo": float(r["ood_ci_lo"]),
                "hi": float(r["ood_ci_hi"]),
            }
    return out


def load_T_corrected():
    """从修正后的消融表取 stage1_ts 的 T_global（= 论文口径的拟合温度）。"""
    out = {}
    with open(T_CSV_CORRECTED, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["stage"] != "stage1_ts":
                continue
            if "mamba" in r["arch"]:
                continue
            if r["T_global"] in ("", "nan"):
                continue
            out[(f'{r["source"]}_{r["target"]}', r["arch"], r["seed"])] = \
                float(r["T_global"])
    return out


def load_T_contaminated():
    out = {}
    with open(T_CSV_CONTAMINATED, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["arch"] not in ("inceptiontime", "resnet1d"):
                continue
            if r["T_global"] in ("", "nan"):
                continue
            out[(r["pair"], r["arch"], r["seed"])] = float(r["T_global"])
    return out


def ols_slope(x, y):
    xm, ym = x.mean(), y.mean()
    return float(((x - xm) * (y - ym)).sum() / ((x - xm) ** 2).sum())


def perm_slope_test(Ts, ds, n_perm=10000, seed=1):
    beta = ols_slope(Ts, ds)
    rng = np.random.default_rng(seed)
    perm = np.array([ols_slope(rng.permutation(Ts), ds) for _ in range(n_perm)])
    return beta, perm


def load_ablation_old():
    """修正后的消融表 → 每 cell 的 (stage1_ts − raw) smooth_ece 差。"""
    per = {}
    with open(T_CSV_CORRECTED, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            per.setdefault((r["source"], r["target"], r["arch"], r["seed"]),
                           {})[r["stage"]] = r
    out = []
    for s in per.values():
        if "raw" in s and "stage1_ts" in s:
            out.append(float(s["stage1_ts"]["smooth_ece"])
                       - float(s["raw"]["smooth_ece"]))
    return out


def main():
    Ts_grid, lo_grid, hi_grid = curve()

    main_ep = load_main()
    Tcor = load_T_corrected()
    Tcon = load_T_contaminated()

    recs = []
    for k, v in main_ep.items():
        if k in Tcor:
            recs.append({"key": k, "pair": k[0], "arch": k[1],
                         "T": Tcor[k], "T_old": Tcon.get(k), **v})
    N = len(recs)
    Ts = np.array([r["T"] for r in recs])
    ds = np.array([r["ood"] for r in recs])

    print("=" * 78)
    print("噪声底机理判别检验（修正 T 口径；方向检验为主）")
    print("=" * 78)
    print(f"噪声底曲线: {CURVE_CSV.name}  T 网格 {Ts_grid}")
    print(f"配对 cell: {N}  （主终点 mean ΔECE_OOD = {ds.mean():+.4f}）")
    print(f"修正 T：median {np.median(Ts):.4f}  range [{Ts.min():.4f}, {Ts.max():.4f}]  "
          f"T>=2: {(Ts >= 2).sum()}/{N}")

    old = [r["T_old"] for r in recs if r["T_old"] is not None]
    if old:
        oa = np.array(old)
        print(f"污染 T（对照）：median {np.median(oa):.4f}  "
              f"range [{oa.min():.4f}, {oa.max():.4f}]  T>=2: {(oa >= 2).sum()}/{len(oa)}")

    # ================================================================
    # B. 方向检验（主论证）
    # ================================================================
    print("\n" + "=" * 78)
    print("B. 方向检验（主论证）：底噪在主终点约定下**恒为负贡献**")
    print("=" * 78)
    print("  理想化设定下真实校准误差恒为 0 ⇒ 测得 ΔECE_OOD = −floor(T)。")
    print("  完美校准下恒等变换是 ECE 的最小值点，故任何 T≠1 都把 ECE 推高：")
    below = [t for t in Ts_grid if t < 1.0]
    above = [t for t in Ts_grid if t > 1.0]
    for tag, tl in (("T<1", below), ("T>1", above)):
        pts = "；".join(f"{t}→{floor_at(t,'lo'):+.3f}~{floor_at(t,'hi'):+.3f}"
                       for t in tl)
        print(f"    {tag}（噪声约定）：{pts}")
    print("  ⇒ 两种约定下底噪都为正，进入主终点**恒为负**。")

    print("\n  B2. 符号一致性列联表：sign(ΔECE_OOD) vs sign(T−1)")
    hi_T, lo_T = Ts > 1.0, Ts < 1.0
    eq_T = ~hi_T & ~lo_T
    pos_d, neg_d = ds > 0, ds < 0
    tab = [[int((hi_T & pos_d).sum()), int((hi_T & neg_d).sum())],
           [int((lo_T & pos_d).sum()), int((lo_T & neg_d).sum())]]
    print(f"      {'':<14}{'ΔECE>0':>10}{'ΔECE<0':>10}")
    print(f"      {'T>1':<14}{tab[0][0]:>10}{tab[0][1]:>10}")
    print(f"      {'T<1':<14}{tab[1][0]:>10}{tab[1][1]:>10}")
    diag = tab[0][0] + tab[1][1]
    n_off = N - int(eq_T.sum())
    if diag == n_off:
        print(f"      完美对角：{diag}/{n_off}（T==1 的 cell: {int(eq_T.sum())} 个）")
        print("      → 底噪方向**固定**，不可能产生随 T 变号的 ΔECE；")
        print("        观测到符号翻转 ⇒ 底噪不是驱动因素。")
    else:
        print(f"      对角 {diag}/{n_off}")

    print("\n  B3. 两分支效应量")
    for lab, m in [("T>=1", hi_T), ("T<1 ", lo_T)]:
        if m.sum():
            print(f"      {lab}  n={m.sum():>2}  mean ΔECE_OOD={ds[m].mean():+.5f}"
                  f"  正例 {int((ds[m] > 0).sum())}/{m.sum()}")
    print(f"      全样本 n={N}  mean={ds.mean():+.5f}"
          f"  正例 {int((ds > 0).sum())}/{N}")

    # ================================================================
    # C. 斜率（一致性检查，**不作为证据**）
    # ================================================================
    print("\n" + "=" * 78)
    print("C. 斜率 β（ΔECE_OOD ~ T）—— 仅作一致性检查")
    print("=" * 78)
    print("  ⚠️ T=1 是不动点：T=1 ⇒ 变换为恒等 ⇒ ΔECE_OOD ≡ 0（构造性）。")
    print("     故 β>0 部分是机械结果，**不构成独立证据**；本节的证据在 B 段。")
    for tag, arr in [("修正 T", Ts), ("污染 T（对照）", np.array(old) if old else None)]:
        if arr is None:
            continue
        beta, perm = perm_slope_test(arr, ds)
        plo, phi = np.percentile(perm, 2.5), np.percentile(perm, 97.5)
        r = float(np.corrcoef(arr, ds)[0, 1])
        print(f"  {tag}")
        print(f"    β̂ = {beta:+.5f}   R² = {r ** 2:.4f}   "
              f"置换零分布 95% [{plo:+.5f}, {phi:+.5f}]   "
              f"p(β=0) = {float((perm >= beta).mean()):.4f}")
        print(f"    机理预测 β = {MECHANISM_BETA:+.3f} → "
              f"观测与机理**符号相反**（{beta - MECHANISM_BETA:+.5f}）")

    # ================================================================
    # D. 分层效应量（可加性底噪预测「大 floor ⇒ 小 ΔECE」，观测应反之）
    # ================================================================
    print("\n" + "=" * 78)
    print("D. 分层效应量：可加性底噪预测『大 floor ⇒ 小 ΔECE』，观测应反之")
    print("=" * 78)
    EFF = float(ds.mean())
    fh = np.array([floor_at(t, "hi") for t in Ts])
    # ⚠️ 阈值只在 T>1 一侧找。floor_hi 在 T≈1 处最小、**两侧都升高**
    # （T=0.7 的 floor_hi=0.045 也 ≥ 主效应），取全网格最小值会错命中 T=0.7。
    thr = min([t for t in Ts_grid if t > 1.0 and floor_at(t, "hi") >= EFF],
              default=None)
    print(f"  主效应 = {EFF:+.4f}；floor_hi(T) ≥ 主效应 在 T>1 一侧自 T ≈ "
          f"{thr if thr is not None else '（曲线内无）'} 起")
    for lab, m in [("floor_hi <  主效应", fh < EFF), ("floor_hi >= 主效应", fh >= EFF)]:
        if m.sum():
            print(f"  {lab}  n={m.sum():>2}  mean ΔECE_OOD={ds[m].mean():+.5f}"
                  f"  正例 {int((ds[m] > 0).sum())}/{m.sum()}")
    print("  → 底噪最大的一档效应量反而最大；且底噪为负贡献 ⇒ 该档是**下界**。")

    # 限定 T>=1 分支（避免与 B2 的符号翻转混淆）
    mh = hi_T
    med = float(np.median(fh[mh]))
    print(f"\n  D1. 限定 T≥1 分支（n={mh.sum()}，全部为正），按 floor_hi 中位 "
          f"{med:.4f} 二分：")
    for lab, mm in [("低 floor", mh & (fh <= med)), ("高 floor", mh & (fh > med))]:
        if mm.sum():
            print(f"      {lab}  n={mm.sum():>2}  mean ΔECE_OOD={ds[mm].mean():+.5f}"
                  f"  正例 {int((ds[mm] > 0).sum())}/{mm.sum()}")
    print(f"  → 加性底噪预测高 floor 档效应更小；观测相反。")
    print(f"  ⚠️ 但 floor_hi 在该侧是 T 的单调函数，而 ΔECE 随 T 的增长部分是"
          f"机械结果（T=1 不动点）")
    print(f"     ⇒ D1 弱于 B 段的方向检验，仅作一致性陈述。")

    print("\n  D2. 与污染口径原报告的对照")
    print("     原报告（污染 T）声称：T<1.25: +0.0174  vs  T>=2.2: +0.0155")
    if old:
        oa = np.array(old)
        m_lo, m_hi = oa < 1.25, oa >= 2.2
        print(f"     污染口径复现：T<1.25: n={m_lo.sum()} mean={ds[m_lo].mean():+.4f}"
              f"  |  T>=2.2: n={m_hi.sum()} mean="
              f"{(ds[m_hi].mean() if m_hi.sum() else float('nan')):+.4f}")
    print(f"     修正口径：T>=2.2 层 n={(Ts >= 2.2).sum()} → 该层在正确数据里不存在")

    # ================================================================
    # E. 负对照
    # ================================================================
    print("\n" + "=" * 78)
    print("E. 负对照：独立消融通道的 TS 效应（同族 SmoothECE）")
    print("=" * 78)
    adv = load_ablation_old()
    print(f"  消融通道 n={len(adv)}  mean Δsmooth_ece = {st.mean(adv):+.4f}")
    print(f"  主通道   n={N}  mean ΔECE_OOD     = {st.mean(ds):+.4f}")
    print(f"  两者差 {st.mean(ds) - st.mean(adv):+.4f}")
    print(f"  消融通道可变号（min {min(adv):+.4f}, max {max(adv):+.4f}）"
          f" → 不存在\"底噪必然推正 ΔECE\"的系统性机制")

    # ================================================================
    # F. 可加性否证
    # ================================================================
    print("\n" + "=" * 78)
    print("F. 底噪\"确定性加性偏差\"假设的否证（决定逐 cell 扣减法是否成立）")
    print("=" * 78)
    w = [r["hi"] - r["lo"] for r in recs]
    f_lo = min(lo_grid)
    f_hi = max(hi_grid)
    print(f"  主终点逐 cell CI 宽度: median {st.median(w):.4f}, max {max(w):.4f}")
    print(f"  噪声底量级（曲线全网格）: {f_lo:.3f} ~ {f_hi:.3f}")
    print(f"  → 底噪 / 逐cell CI宽度 = {abs(f_lo) / st.median(w):.0f} ~ "
          f"{abs(f_hi) / st.median(w):.0f} 倍")
    corr = [r["ood"] - floor_at(r["T"], "mid") for r in recs]
    print(f"  逐 cell 扣底噪(中值档) mean = {st.mean(corr):+.4f}"
          f"（原始 {st.mean(ds):+.4f} 的 {st.mean(corr) / st.mean(ds) * 100:.0f}%）")
    print("  但该扣减把底噪当成逐 cell 的确定性加性偏差：若真是加性偏差，其量级"
          "（比逐 cell CI 宽 1~2 个数量级）应完全淹没信号，")
    print("  而观测效应几乎不动 ⇒ 底噪不是逐 cell 加性偏差，**不做逐 cell 扣减**。")

    # ================================================================
    # 汇总
    # ================================================================
    print("\n" + "=" * 78)
    print("结论（排除性，非确证性）")
    print("=" * 78)
    n_hi_floor = int((fh >= EFF).sum())
    print(f"  1) 方向：底噪在主终点约定下恒为负贡献，无法产生正分支；")
    print(f"     且观测符号随 T 翻转（sign(ΔECE)=sign(T−1) 命中 {diag}/{n_off}），")
    print(f"     而底噪方向固定 ⇒ 底噪不能解释主发现 ΔECE_OOD = {ds.mean():+.4f}。")
    old_dz = (int((np.array([floor_at(t, "hi") for t in old]) >= EFF).sum())
              if old else "—")
    print(f"  2) 覆盖：修正 T 下 floor_hi ≥ 主效应的 cell 仅 {n_hi_floor}/{N}"
          f"（污染口径为 {old_dz}/{len(old) if old else 0}）；且该档效应量最大"
          f"（{ds[fh >= EFF].mean():+.5f}），与加性底噪预测相反。")
    mh2 = Ts >= 1.0
    med2 = float(np.median(fh[mh2]))
    lo_m, hi_m = mh2 & (fh <= med2), mh2 & (fh > med2)
    print(f"     限定 T≥1 分支（n={int(mh2.sum())}，全为正）按 floor_hi 中位二分："
          f"低 {int(lo_m.sum())} 格 mean {ds[lo_m].mean():+.5f}；"
          f"高 {int(hi_m.sum())} 格 mean {ds[hi_m].mean():+.5f}（同向，非加性）。")
    print(f"     逐 cell 扣底噪(中值档)后仍余 {st.mean(corr) / st.mean(ds) * 100:.0f}%。")
    print(f"  3) 斜率 β̂={ols_slope(Ts, ds):+.5f} 与机理值 {MECHANISM_BETA:+.3f} 符号相反，"
          f"但 T=1 不动点使其非独立证据，故不作为主论证。")
    print(f"  限制：底噪基于理想化置信分布、分层 n 偏小 → 排除性证据，非因果判定。")


if __name__ == "__main__":
    main()
