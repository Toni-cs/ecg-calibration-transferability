"""§real_shapley 口径修复版重建：slope = 1/T_src, intercept = 0。

背景（2026-09-27，闭合 REAL_SHAPLEY_AUDIT_VERDICT 与
_PROBS_CACHE_LABEL_REPAIR_NOTICE §6 的阻塞项）：
  论文 §real_shapley 引用的 delta_pred（+0.3015, ρ=+0.31）来源脚本在全部
  git 历史中不存在；旧 rebuild_shapley_crossfit.py 的 (slope=1.0,
  intercept=0.0) 是恒等注入，s/b 分量结构性为零（delta_pred 退化为纯
  prevalence 项），其干净缓存实测 ρ = −0.2184 与论文符号相反。

本脚本确立有来源、可复现、非退化的口径：
  slope = 1/T_src（源域 cal 上拟合的多分类温度的倒数），intercept = 0。
  语义：把"源域模型带入目标域"的校准变换参数化为 logit 空间斜率缩放
  （top-label 边际近似），缩放量由源域校准集实测——与论文正文
  "we estimate (ŝ, b̂) on the source calibration split" 的表述一致。
  该口径下注入非恒等（当且仅当 T≠1），s/b 分量有非平凡取值。

产出：
  results/rebuild_shapley_slopeT.csv / .json
  （delta_obs_orig 口径与 rebuild_shapley_crossfit.py 相同：已在干净缓存上
   逐格复现主表 60/60，max|Δ| = 4.7e-07。）

用法：
  C:/python/python.exe scripts/rebuild_shapley_slopeT.py
"""
import csv
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils.calibration import smooth_ece            # noqa: E402
from src.utils.decomposition import decompose_benefit   # noqa: E402
from src.utils.calibration_methods import (             # noqa: E402
    fit_temperature_multiclass, apply_temperature_multiclass)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "checkpoints", "e2_probs_cache")
OUT_CSV = os.path.join(ROOT, "results", "rebuild_shapley_slopeT.csv")
OUT_JSON = os.path.join(ROOT, "results", "rebuild_shapley_slopeT.json")

ARCHS = ("inceptiontime", "resnet1d")
SEEDS = (42, 43, 44, 45, 46)


def _toplabel_binary(probs, labels):
    pred = probs.argmax(axis=1)
    conf = probs.max(axis=1)
    correct = (pred == labels).astype(float)
    return conf, correct


def _parse_name(fname):
    base = fname[:-4]
    parts = base.split("_")
    if len(parts) < 4:
        return None
    seed_s = parts[-1]
    if not seed_s.startswith("seed"):
        return None
    try:
        seed = int(seed_s[4:])
    except ValueError:
        return None
    arch = "_".join(parts[2:-1])
    return parts[0], parts[1], arch, seed


def _spearman(a, b):
    """无 scipy 依赖的 Spearman 秩相关（平均秩处理并列）。"""
    ra = np.argsort(np.argsort(a)).astype(float)
    rb = np.argsort(np.argsort(b)).astype(float)
    if np.std(ra) < 1e-12 or np.std(rb) < 1e-12:
        return float("nan")
    return float(np.corrcoef(ra, rb)[0, 1])


def main():
    if not os.path.isdir(CACHE):
        print("[FATAL] cache dir missing:", CACHE)
        return 1

    files = sorted(f for f in os.listdir(CACHE) if f.endswith(".npz"))
    rows, skipped = [], []
    for fname in files:
        meta = _parse_name(fname)
        if meta is None or meta[2] not in ARCHS or meta[3] not in SEEDS:
            skipped.append((fname, "filter"))
            continue
        src, tgt, arch, seed = meta
        d = np.load(os.path.join(CACHE, fname), allow_pickle=True)
        cal_p, cal_y = d["cal_probs"], d["cal_labels"]
        tgt_p, tgt_y = d["test_probs"], d["test_labels"]

        cal_conf, cal_correct = _toplabel_binary(cal_p, cal_y)
        tgt_conf, tgt_correct = _toplabel_binary(tgt_p, tgt_y)

        try:
            tp = fit_temperature_multiclass(cal_p, cal_y)
            T = float(tp["T"])
        except Exception as e:
            skipped.append((fname, "T fit failed: %s" % e))
            continue
        slope = 1.0 / T  # 口径：logit 斜率缩放 = 源域拟合温度的倒数

        raw_ood_orig = smooth_ece(tgt_conf, tgt_correct)
        tgt_p_ts = apply_temperature_multiclass(tgt_p, tp)
        ts_conf, ts_correct = _toplabel_binary(tgt_p_ts, tgt_y)
        cal_ood_orig = smooth_ece(ts_conf, ts_correct)
        delta_obs_orig = raw_ood_orig - cal_ood_orig

        rng = np.random.default_rng(seed)
        prev_true = float(tgt_correct.mean())
        try:
            dec = decompose_benefit(cal_conf, cal_correct,
                                    slope=slope, intercept=0.0,
                                    target_prev=prev_true, rng=rng)
        except Exception as e:
            skipped.append((fname, "decompose failed: %s" % e))
            continue

        sh = dec["shapley"]["values"]
        rows.append({
            "cell": fname[:-4],
            "source": src, "target": tgt, "arch": arch, "seed": seed,
            "T_src": T, "slope_used": slope,
            "raw_ood_orig": raw_ood_orig,
            "cal_ood_orig": cal_ood_orig,
            "delta_obs_orig": delta_obs_orig,
            "shap_s": float(sh["s"]),
            "shap_b": float(sh["b"]),
            "shap_pi": float(sh["pi"]),
            "delta_pred": float(sh["s"] + sh["b"] + sh["pi"]),
            "recovery_failed": bool(dec["recovery_failed"]),
            "entangled": bool(dec["entangled"]),
            "fisher_det": float(dec["fisher_det"]),
        })

    print("成功 cell 数: %d（跳过 %d）" % (len(rows), len(skipped)))
    for s in skipped[:8]:
        print("   skip:", s)
    if len(rows) < 60:
        print("[FATAL] 期望 60 格")
        return 1

    # 退化守卫：本口径下 shap_s 不得全为 0
    if max(abs(r["shap_s"]) for r in rows) < 1e-12:
        print("[FATAL] shap_s 全为 0 —— 注入仍是恒等（T 恒为 1？），口径未生效")
        return 1

    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    with open(OUT_CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)

    # ---------------- 指标（与旧脚本同口径，便于对照） ----------------
    import statistics as st
    import math

    dobs = [r["delta_obs_orig"] for r in rows]
    dprd = [r["delta_pred"] for r in rows]
    n = len(rows)

    print("\n" + "=" * 72)
    print("口径: slope=1/T_src, intercept=0  （y = delta_obs_orig, n=%d）" % n)
    print("=" * 72)
    print("delta_obs_orig mean %+.4f  median %+.4f" % (st.mean(dobs), st.median(dobs)))
    print("delta_pred     mean %+.4f  median %+.4f" % (st.mean(dprd), st.median(dprd)))
    print("pred 全正? %s   slope 范围 [%.4f, %.4f]"
          % (all(v > 0 for v in dprd),
             min(r["slope_used"] for r in rows),
             max(r["slope_used"] for r in rows)))

    pos = sum(1 for v in dobs if v > 0)
    sign_ok = sum(1 for a, b in zip(dprd, dobs) if (a > 0) == (b > 0))
    print("\n--- 方向 ---")
    print("obs 正值率       : %d/%d (%.1f%%)" % (pos, n, 100 * pos / n))
    print("常数恒正基线     : %d/%d (%.1f%%)"
          % (max(pos, n - pos), n, 100 * max(pos, n - pos) / n))
    print("分解模型         : %d/%d (%.1f%%)" % (sign_ok, n, 100 * sign_ok / n))
    kappa = 0.0 if sign_ok == max(pos, n - pos) else None
    print("→ vs 常数基线 κ: %s" % ("0.0000（逐位相等）" if kappa == 0.0 else "非零，见明细"))

    err = [a - b for a, b in zip(dprd, dobs)]
    rc = math.sqrt(st.mean([(v - st.mean(dobs)) ** 2 for v in dobs]))
    rm = math.sqrt(st.mean([(a - b) ** 2 for a, b in zip(dprd, dobs)]))
    print("\n--- 误差 ---")
    print("mean %+.4f  median %+.4f" % (st.mean(err), st.median(err)))
    print("RMSE pred %.4f vs 常数 %.4f = %.2fx" % (rm, rc, rm / rc))

    rho = _spearman(dprd, dobs)
    loo = []
    for i in range(n):
        keep = [j for j in range(n) if j != i]
        loo.append(_spearman([dprd[j] for j in keep], [dobs[j] for j in keep]))
    print("\n--- 秩关联 ---")
    print("Spearman rho = %+.4f（全 60 格）" % rho)
    print("LOO rho: min %+.4f  max %+.4f  符号为正 %d/%d"
          % (min(loo), max(loo), sum(1 for v in loo if v > 0), n))

    print("\n--- T 分层（主终点 T-不变性自检）---")
    for lo, hi in [(0, 1.25), (1.25, 1.5), (1.5, 3), (3, 5)]:
        s = [r["delta_obs_orig"] for r in rows if lo <= r["T_src"] < hi]
        if s:
            print("  T∈[%.2f,%.2f) n=%2d  mean %+.4f"
                  % (lo, hi, len(s), st.mean(s)))

    print("\n落盘: %s / %s" % (OUT_CSV, OUT_JSON))
    print("论文 §real_shapley 重写引用本文件数字，勿再引用无来源的 "
          "strengthening_battle_corrected.json delta_pred。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
