"""真实数据上的目标先验恢复检验（protocol §13 item 7 —— 把 MAPE_pi 从设计校验升级）

背景 / 动机
-----------
decompose_benefit 的 prev_hat 是**设计常量回读**：合成环境里重采样精确控制了正类
数，所以 MAPE_pi 只是 design check，不是估计量能力检验。论文（Honesty Declaration
item 1、Limitations）如实登记了这个缺口，并注明"independent pi recovery
(BBSE/EM) is a deferred item (protocol §13)"。

本脚本执行该 deferred item：在**真实 60 格**上，用 src/utils/prior_shift.py 的
BBSE / EM，**仅凭源域标签 + 目标域 soft-probabilities**（目标域零标签）恢复目标
类先验，并与真值比较。

数据来源
--------
checkpoints/e2_probs_cache/*.npz（62 个：60 正式网格 + 2 个附加），每格含：
    cal_probs   (n_cal, K)   源域（有标签）预测概率
    cal_labels  (n_cal,)     源域标签
    test_probs  (n_tgt, K)   目标域预测概率（无标签 —— 本检验的关键约束）
    test_labels (n_tgt,)     目标域标签（**仅用于事后评分**，不进入估计器）
    num_classes ()

对照与报告
----------
- BBSE、EM：两种无标签先验估计器
- 源先验基线：直接用源域先验当作目标先验（不做任何适应）—— 检验"估计器是否真的
  优于不估计"
- 判据：mean absolute error 到真值；以及每格是否优于基线

诚实性纪律（对齐论文基调）
--------------------------
- 估计器返回 None（不可辨识/条件数超限）时**如实记为失败**，不静默替换
- 同时报告 confusion 条件数，标注哪些格处于数值边界
- 结论不写成"BBSE 有效"，而写成"在真实 ECG 迁移网格上，BBSE 相对朴素的
  源先验基线降低误差 X%，但绝对误差 Y 仍不可忽略"这类限定表述

用法：
    python scripts/real_prior_recovery.py
输出：
    results/real_prior_recovery.csv    逐格明细
    stdout                             汇总（可直接引用到论文）
"""

from __future__ import annotations

import glob
import os
import sys
import warnings

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils.prior_shift import fit_bbse, fit_em  # noqa: E402

CACHE_GLOB = "checkpoints/e2_probs_cache/*.npz"
OUT_CSV = "results/real_prior_recovery.csv"


def recovery_error(pi_hat: np.ndarray, pi_true: np.ndarray) -> float:
    """mean absolute error 到真值先验。"""
    return float(np.abs(np.asarray(pi_hat) - np.asarray(pi_true)).mean())


def main() -> int:
    files = sorted(glob.glob(CACHE_GLOB))
    if not files:
        print(f"ERROR: 未找到 {CACHE_GLOB}")
        return 2

    # 只保留正式 60 格网格；排除 2 个 BiMamba 玩具运行（非正式网格，会污染统计）
    n_all = len(files)
    files = [f for f in files if "mamba" not in os.path.basename(f)]
    if len(files) != n_all:
        print(f"[过滤] 缓存 {n_all} 个 -> 正式网格 {len(files)} 格"
              f"（排除 {n_all - len(files)} 个 BiMamba 玩具运行）\n")

    rows = []
    n_bbse_fail = n_em_fail = 0

    for f in files:
        d = np.load(f)
        src_probs, src_labels = d["cal_probs"], d["cal_labels"]
        tgt_probs, tgt_labels = d["test_probs"], d["test_labels"]
        K = int(src_probs.shape[1])

        # 真值先验 —— 仅供事后评分
        pi_true = np.bincount(tgt_labels, minlength=K).astype(float)
        pi_true = pi_true / pi_true.sum()

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            res_bbse = fit_bbse(src_probs, src_labels, tgt_probs)
            res_em = fit_em(src_probs, src_labels, tgt_probs)

        # 朴素基线：不做任何适应，源先验直接当目标先验
        pi_src = np.bincount(src_labels, minlength=K).astype(float)
        pi_src = pi_src / pi_src.sum()

        name = os.path.basename(f).replace(".npz", "")
        row = {
            "cell": name,
            "K": K,
            "n_cal": int(len(src_labels)),
            "n_tgt": int(len(tgt_labels)),
            "err_baseline": recovery_error(pi_src, pi_true),
        }

        if res_bbse is None:
            n_bbse_fail += 1
            row.update(err_bbse="", cond_bbse="", rank_bbse="", bbse_failed=1)
        else:
            row.update(
                err_bbse=recovery_error(res_bbse["pi_hat"], pi_true),
                cond_bbse=res_bbse["confusion_cond"],
                rank_bbse=res_bbse["rank"],
                bbse_failed=0,
            )

        if res_em is None:
            n_em_fail += 1
            row.update(err_em="", em_failed=1)
        else:
            row.update(err_em=recovery_error(res_em["pi_hat"], pi_true), em_failed=0)

        rows.append(row)

    # ---------------- 写 CSV ----------------
    cols = ["cell", "K", "n_cal", "n_tgt", "err_baseline", "err_bbse",
            "err_em", "cond_bbse", "rank_bbse", "bbse_failed", "em_failed"]
    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    with open(OUT_CSV, "w", encoding="utf-8", newline="") as fh:
        fh.write(",".join(cols) + "\n")
        for r in rows:
            fh.write(",".join(str(r.get(c, "")) for c in cols) + "\n")

    # ---------------- 汇总 ----------------
    bb = np.array([r["err_bbse"] for r in rows if r["bbse_failed"] == 0])
    em = np.array([r["err_em"] for r in rows if r["em_failed"] == 0])
    base = np.array([r["err_baseline"] for r in rows])
    conds = np.array([r["cond_bbse"] for r in rows if r["bbse_failed"] == 0])

    n = len(rows)
    print("=" * 72)
    print("真实数据目标先验恢复检验（目标域零标签）")
    print("=" * 72)
    print(f"格子总数           : {n}")
    print(f"BBSE 可辨识        : {len(bb)}/{n}  (失败 {n_bbse_fail})")
    print(f"EM   可辨识        : {len(em)}/{n}  (失败 {n_em_fail})")
    print()
    print("mean absolute error 到真值先验:")
    print(f"  源先验基线       : {base.mean():.4f}  (median {np.median(base):.4f})")
    if len(bb):
        print(f"  BBSE             : {bb.mean():.4f}  (median {np.median(bb):.4f})")
    if len(em):
        print(f"  EM               : {em.mean():.4f}  (median {np.median(em):.4f})")
    print()
    if len(bb):
        n_beat_base = int((bb < base[: len(bb)]).sum())
        print(f"BBSE 优于基线      : {n_beat_base}/{len(bb)}")
        print(f"相对基线误差降低   : {(1 - bb.mean() / base.mean()) * 100:.1f}%")
        if len(em):
            print(f"BBSE 优于 EM       : {int((bb < em).sum())}/{min(len(bb), len(em))}")
        print()
        print("confusion 条件数（数值边界诊断）:")
        print(f"  min    {conds.min():.1f}")
        print(f"  median {np.median(conds):.1f}")
        print(f"  max    {conds.max():.1f}")
        print(f"  >1e4   {int((conds > 1e4).sum())}/{len(conds)} 格（近奇异区）")
    print()
    print(f"逐格明细 -> {OUT_CSV}")
    print()
    print("【论文可用表述（限定口径）】")
    print(f"  在真实 {n} 格上，BBSE 在目标域零标签条件下相对朴素的源先验基线")
    print(f"  将先验恢复误差降低约 {(1 - bb.mean() / base.mean()) * 100:.0f}%，但绝对误差")
    print(f"  仍有 {bb.mean():.3f}（mean abs），不可忽略；且 {int((conds > 1e4).sum())} 格")
    print("  的 confusion 条件数超 1e4，处于近奇异区 —— 恢复在这些格上数值边界敏感。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
