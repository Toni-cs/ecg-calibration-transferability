#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""完美校准噪声底曲线（**带符号**）—— 论文 §noise_floor 锚点表的唯一生成脚本。

=====================================================================
这个脚本解决什么问题
=====================================================================
论文 §noise_floor 的锚点表（$T=1.25\\to+0.014$--$+0.035$ 等）在 2026-09-17 之前
**在仓库里没有生成脚本**（从未提交），三个下游脚本各自硬编码这几个数，导致无法
复现、无法审计。本脚本是**唯一来源**，把曲线写成
``results/noise_floor_curve.csv``，下游读 CSV 而不再硬编码。

=====================================================================
为什么主实验改用**真实**置信分布（2026-09-17 设计变更）
=====================================================================
最初按论文原文用三种**合成**分布（uniform / normal-skewed / bimodal）。实测发现
底噪的**符号依赖置信分布形状**：平坦/宽分布（uniform、logit-normal）在
$T=1.1$--$1.5$ 给出**负**底噪（$-0.009$ / $-0.007$），即该情形下度量噪声反而会
把主终点推**正** —— 这会直接打穿论文的方向论证。

而本研究模型的真实 top-label 置信度是**高置信为主**的
（主网格 60 个 cell 合并：中位 0.793、均值 0.752、30% 的样本 >0.9），
在该分布下底噪干净单调且几乎处处为正。

因此主实验改为**用本研究主网格 60 个 cell 的真实置信分布**计算底噪：
每个 cell 取其 ``test_probs`` 的 top-label 置信度 $c$，用 $y\\sim\\mathrm{Bernoulli}(c)$
重采样标签构造完美校准数据，再测 floor。这样

* **没有人为选分布的空间**（消除了"挑分布凑结论"的质疑）；
* 直接对应本研究的数据，而不是合成代理；
* 得到 60 条曲线，报告跨 cell 的 min / median / max 带。

合成分布保留为**敏感性分析**（写入 CSV 的 uniform/normal_skewed/bimodal 行），
用于如实披露"底噪符号依赖分布形状"这一事实。

=====================================================================
符号约定（关键，易错）
=====================================================================
* 主终点（main_bspc.tex L72）：``ΔECE_OOD = ECE_raw − ECE_post``，**正 = TS 有益**。
* 本实验（main_bspc.tex L1203）：``ΔECE_noise = SmoothECE(TS) − SmoothECE(raw)``，
  即 **post − raw，与主终点相反**。

理想化设定下真实校准误差恒为 0，故测得的

    ΔECE_OOD = 真值(0) − floor(T) = **−floor(T)**

即本脚本算出的 ``dECE_noise`` 就是 floor，而它**进入主终点时带负号**。
CSV 里同时给出 ``dECE_primary = −dECE_noise`` 这一列，避免下游再错一次。

=====================================================================
用法
=====================================================================
    /c/python/python.exe scripts/noise_floor_signed.py
    /c/python/python.exe scripts/noise_floor_signed.py --no-synthetic   # 只跑真实分布
    /c/python/python.exe scripts/noise_floor_signed.py --out results/noise_floor_curve.csv

⚠️ 真实分布来自 ``checkpoints/e2_probs_cache/*.npz``，而 ``checkpoints/`` 在 lab
仓库里被 gitignore。故**曲线 CSV 本身必须提交**（``git add -f``），它才是可审计的
产物；probs 缺失时脚本会明确报错而不是静默降级。
"""

from __future__ import annotations

import argparse
import csv
import glob
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.utils.calibration import smooth_ece  # noqa: E402

PROBS_GLOB = ROOT / "checkpoints/e2_probs_cache/*.npz"
DEFAULT_OUT = ROOT / "results/noise_floor_curve.csv"

# T 网格：在数据实际所在的区间（0.93–1.50）加密
T_GRID = (0.7, 0.8, 0.9, 1.0, 1.1, 1.25, 1.4, 1.5, 2.0, 3.0, 4.5)
EMP_DRAWS = 3          # 每个 cell 的标签重采样次数
MIN_CELL_N = 500       # 排除过小 cell
# ⚠️ cell 集合必须**钉死**：BiMamba 30 格网格正在跑，会不断往 e2_probs_cache 里
# 加 cell。若不排除，曲线会随训练进度漂移，同一脚本两次运行给出不同结果。
# 主网格（论文主终点）只有 inceptiontime / resnet1d 两种架构，故排除 mamba。
EXCLUDE_ARCH = ("mamba",)
SYN_SEEDS = 15         # 合成敏感性分析的种子数


def sigmoid(z):
    return 1.0 / (1.0 + np.exp(-z))


def logit(p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def apply_T(p, T):
    return sigmoid(logit(p) / T)


def floor_curve_for_conf(c, T_grid, draws, rng):
    """给定置信度向量 c（已完美校准化：y~Bernoulli(c)），返回 {T: mean dECE_noise}。"""
    acc = {T: [] for T in T_grid}
    for _ in range(draws):
        y = (rng.uniform(size=len(c)) < c).astype(float)
        base = smooth_ece(c, y)
        for T in T_grid:
            acc[T].append(smooth_ece(apply_T(c, T), y) - base)
    return {T: float(np.mean(acc[T])) for T in T_grid}


# ---------------------------------------------------------------------------
# 合成敏感性分析用的三种分布（论文原文口径）
#   uniform        : p ~ U(0, 1)
#   normal_skewed  : logit(p) ~ N(0.5, 1.2²)
#   bimodal        : 50/50 混合 logit ~ N(2.0,0.6²) 与 N(-1.5,0.6²)
# ---------------------------------------------------------------------------
def _mk(kind, rng, n):
    if kind == "uniform":
        return rng.uniform(0.0, 1.0, n)
    if kind == "normal_skewed":
        return sigmoid(rng.normal(0.5, 1.2, n))
    if kind == "bimodal":
        h = n // 2
        return np.concatenate([sigmoid(rng.normal(2.0, 0.6, n - h)),
                               sigmoid(rng.normal(-1.5, 0.6, h))])
    raise ValueError(kind)


SYN_DISTS = ("uniform", "normal_skewed", "bimodal")


def empirical_curves():
    fs = sorted(glob.glob(str(PROBS_GLOB)))
    if not fs:
        raise SystemExit(
            f"找不到 {PROBS_GLOB}\n"
            "本实验需要本研究模型的真实置信分布。若 probs 缓存已清空，"
            "请先重跑 eval_transfer.py（见 docs/EXPERIMENT_PROTOCOL.md）。\n"
            "（不静默降级到合成分布——那正是本脚本要消除的问题。）")
    out = {}
    skipped = []
    for f in fs:
        stem = Path(f).stem
        if any(a in stem for a in EXCLUDE_ARCH):
            skipped.append((stem, "arch"))
            continue
        d = np.load(f, allow_pickle=True)
        c = d["test_probs"].max(axis=1).astype(float)
        if len(c) < MIN_CELL_N:
            skipped.append((stem, len(c)))
            continue
        rng = np.random.default_rng(0)
        out[stem] = floor_curve_for_conf(c, T_GRID, EMP_DRAWS, rng)
    return out, skipped


def synthetic_curves(n=2000):
    out = {}
    for kind in SYN_DISTS:
        per = {T: [] for T in T_GRID}
        for seed in range(SYN_SEEDS):
            rng = np.random.default_rng(seed)
            c = _mk(kind, rng, n)
            for T, v in floor_curve_for_conf(c, T_GRID, 1, rng).items():
                per[T].append(v)
        out[kind] = {T: float(np.mean(per[T])) for T in T_GRID}
    return out


def write_csv(path, emp, syn):
    rows = []
    for name, cur in emp.items():
        for T in T_GRID:
            rows.append({"T": f"{T:.4f}", "dist": f"empirical:{name}", "kind": "empirical",
                         "n_cells": len(emp), "dECE_noise": f"{cur[T]:.6f}",
                         "dECE_primary": f"{-cur[T]:.6f}"})
    # 跨 cell 带（下游读这三行）
    for label, fn in (("__min__", np.min), ("__median__", np.median), ("__max__", np.max)):
        for T in T_GRID:
            v = float(fn([cur[T] for cur in emp.values()]))
            rows.append({"T": f"{T:.4f}", "dist": label, "kind": "empirical",
                         "n_cells": len(emp), "dECE_noise": f"{v:.6f}",
                         "dECE_primary": f"{-v:.6f}"})
    for name, cur in syn.items():
        for T in T_GRID:
            rows.append({"T": f"{T:.4f}", "dist": f"synthetic:{name}", "kind": "synthetic",
                         "n_cells": SYN_SEEDS, "dECE_noise": f"{cur[T]:.6f}",
                         "dECE_primary": f"{-cur[T]:.6f}"})
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    return path, len(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--no-synthetic", action="store_true")
    args = ap.parse_args()

    print("=" * 96)
    print("完美校准噪声底曲线（带符号）—— 论文 §noise_floor 锚点表的唯一生成脚本")
    print("=" * 96)
    print("dECE_noise = SmoothECE(TS) − SmoothECE(raw)   [post − raw，与主终点相反]")
    print("dECE_primary = −dECE_noise                    [raw − post，主终点约定]")

    emp, skipped = empirical_curves()
    if skipped:
        print(f"\n[跳过 {len(skipped)} 个 cell（架构排除 {EXCLUDE_ARCH} 或 n<{MIN_CELL_N}）] "
              f"{', '.join(f'{s}({n})' for s, n in skipped)}")

    print(f"\n【主实验】真实置信分布：{len(emp)} 个 cell "
          f"（test_probs 的 top-label 置信度，标签重采样 ×{EMP_DRAWS}）")
    print(f"{'T':>6} | {'min':>9} {'median':>9} {'max':>9} | {'frac>0':>7}")
    print("-" * 96)
    band = {}
    for T in T_GRID:
        v = np.array([cur[T] for cur in emp.values()])
        band[T] = (float(v.min()), float(np.median(v)), float(v.max()))
        print(f"{T:>6.2f} | {v.min():>+9.4f} {np.median(v):>+9.4f} {v.max():>+9.4f} "
              f"| {(v > 0).mean():>7.3f}")

    syn = {} if args.no_synthetic else synthetic_curves()
    if syn:
        print(f"\n【敏感性分析】合成分布（n=2000, {SYN_SEEDS} 种子）"
              f"—— 如实披露底噪符号依赖分布形状")
        print(f"{'T':>6} | " + " | ".join(f"{k:>14}" for k in syn))
        print("-" * 96)
        for T in T_GRID:
            print(f"{T:>6.2f} | " + " | ".join(f"{syn[k][T]:>+14.4f}" for k in syn))
        neg = [(k, T) for k in syn for T in T_GRID if T != 1.0 and syn[k][T] < -0.001]
        print(f"\n  负底噪（T≠1）组合：{len(neg)} 个"
              + (f"，全部来自 {sorted({k for k, _ in neg})}" if neg else ""))
        print("  → 平坦/宽置信分布下底噪可为负 ⇒ 主实验**必须**用本研究真实分布，"
              "不能拿合成分布代替。")

    out, nrow = write_csv(args.out, emp, syn)
    print(f"\n[写出] {out}  （{nrow} 行；下游读 dist=__min__/__median__/__max__）")

    print("\n" + "-" * 96)
    print("符号检查：真实分布下 floor 应恒为正 ⇒ 进入主终点恒为负")
    print("-" * 96)
    bad = [T for T in T_GRID if T != 1.0 and band[T][0] <= 0.0]
    for T in T_GRID:
        lo, md, hi = band[T]
        print(f"  T={T:<5}  floor ∈ [{lo:+.4f}, {hi:+.4f}] (median {md:+.4f})"
              f"  → 主终点贡献 ∈ [{-hi:+.4f}, {-lo:+.4f}]")
    print(f"\n  min 带非正的 T：{bad if bad else '无'}")


if __name__ == "__main__":
    main()
