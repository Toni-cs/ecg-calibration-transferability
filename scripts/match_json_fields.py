"""把 npz 双编码复现结果直接对上 strengthening_battle_corrected.json 的字段。

假设：
  delta_obs_orig  ≡ npz + OLD 编码（idx1=CD,idx3=MI）  ← 论文口径
  delta_obs       ≡ npz + NEW 编码（idx1=MI,idx3=CD）  ← 标签错位伪信号
  T               ≡ 用 NEW 编码拟合的温度（若 JSON 产于 09-10 之后）
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.utils.calibration import (  # noqa: E402
    apply_temperature, fit_temperature, smooth_ece,
)

CACHE = ROOT / "checkpoints" / "e2_probs_cache"
JSON_PATH = ROOT / "results" / "strengthening_battle_corrected.json"


def swap13(labels):
    out = labels.copy()
    out[labels == 1] = 3
    out[labels == 3] = 1
    return out


def onehot(y, k):
    m = np.zeros((len(y), k), dtype=float)
    m[np.arange(len(y)), y] = 1.0
    return m


def main() -> None:
    recs = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    print(f"JSON 记录数：{len(recs)}")
    print(f"字段样例：{sorted(recs[0].keys())}")

    # 建立 npz 索引
    npz_index = {}
    for p in CACHE.glob("*.npz"):
        parts = p.stem.split("_")
        src, tgt, arch, seed = parts[0], parts[1], "_".join(parts[2:-1]), parts[-1]
        npz_index[(src, tgt, arch, seed)] = p

    rows = []
    for r in recs:
        key = (r["source"], r["target"], r["arch"], f"seed{r['seed']}"
               if not str(r["seed"]).startswith("seed") else str(r["seed"]))
        key2 = (r["source"], r["target"], r["arch"], str(r["seed"]))
        p = npz_index.get(key) or npz_index.get(key2)
        if p is None:
            # 尝试 seed 为 int
            p = npz_index.get((r["source"], r["target"], r["arch"], f"seed{r['seed']}"))
        if p is None:
            print(f"  [no npz] {r['source']}->{r['target']} {r['arch']} seed={r['seed']}")
            continue
        d = np.load(p)
        tp, ty_new = d["test_probs"].astype(float), d["test_labels"].astype(int)
        cp, cy_new = d["cal_probs"].astype(float), d["cal_labels"].astype(int)
        k = tp.shape[1]
        is_cpsc = "cpsc" in (r["source"], r["target"])
        if is_cpsc:
            ty_old, cy_old = swap13(ty_new), swap13(cy_new)
        else:
            ty_old, cy_old = ty_new, cy_new

        def de(cy, ty):
            T = fit_temperature(cp, onehot(cy, k))
            ts = apply_temperature(tp, T)
            raw = smooth_ece(tp.max(1), (tp.argmax(1) == ty).astype(float))
            cal = smooth_ece(ts.max(1), (ts.argmax(1) == ty).astype(float))
            return raw - cal, T, raw, cal

        d_old, T_old, raw_old, cal_old = de(cy_old, ty_old)
        d_new, T_new, raw_new, cal_new = de(cy_new, ty_new)

        rows.append({
            "pair": f"{r['source']}->{r['target']}", "arch": r["arch"], "seed": r["seed"],
            "j_delta_obs_orig": r.get("delta_obs_orig"),
            "j_delta_obs": r.get("delta_obs"),
            "j_delta_pred": r.get("delta_pred"),
            "j_T": r.get("T"),
            "j_raw_orig": r.get("raw_ood_orig"),
            "j_cal_orig": r.get("cal_ood_orig"),
            "d_old": d_old, "T_old": T_old, "raw_old": raw_old, "cal_old": cal_old,
            "d_new": d_new, "T_new": T_new, "raw_new": raw_new, "cal_new": cal_new,
        })

    print(f"\n可匹配记录：{len(rows)}")

    def corr(a, b):
        a = np.asarray(a, dtype=float)
        b = np.asarray(b, dtype=float)
        m = np.isfinite(a) & np.isfinite(b)
        if m.sum() < 3:
            return float("nan")
        return float(np.corrcoef(a[m], b[m])[0, 1])

    def maxdiff(a, b):
        a = np.asarray(a, dtype=float)
        b = np.asarray(b, dtype=float)
        m = np.isfinite(a) & np.isfinite(b)
        return float(np.max(np.abs(a[m] - b[m]))) if m.sum() else float("nan")

    print("\n" + "=" * 96)
    print("字段匹配检验")
    print("=" * 96)

    jo = [r["j_delta_obs_orig"] for r in rows]
    jn = [r["j_delta_obs"] for r in rows]
    jt = [r["j_T"] for r in rows]
    do = [r["d_old"] for r in rows]
    dn = [r["d_new"] for r in rows]
    to = [r["T_old"] for r in rows]
    tn = [r["T_new"] for r in rows]

    print(f"\nJSON.delta_obs_orig  vs  npz+OLD  : corr={corr(jo,do):+.6f}  max|Δ|={maxdiff(jo,do):.3e}")
    print(f"JSON.delta_obs_orig  vs  npz+NEW  : corr={corr(jo,dn):+.6f}  max|Δ|={maxdiff(jo,dn):.3e}")
    print(f"\nJSON.delta_obs       vs  npz+NEW  : corr={corr(jn,dn):+.6f}  max|Δ|={maxdiff(jn,dn):.3e}")
    print(f"JSON.delta_obs       vs  npz+OLD  : corr={corr(jn,do):+.6f}  max|Δ|={maxdiff(jn,do):.3e}")
    print(f"\nJSON.T               vs  T_old    : corr={corr(jt,to):+.6f}  max|Δ|={maxdiff(jt,to):.3e}")
    print(f"JSON.T               vs  T_new    : corr={corr(jt,tn):+.6f}  max|Δ|={maxdiff(jt,tn):.3e}")

    # raw 字段
    jraw = [r["j_raw_orig"] for r in rows]
    ro = [r["raw_old"] for r in rows]
    rn = [r["raw_new"] for r in rows]
    print(f"\nJSON.raw_ood_orig    vs  raw_OLD  : corr={corr(jraw,ro):+.6f}  max|Δ|={maxdiff(jraw,ro):.3e}")
    print(f"JSON.raw_ood_orig    vs  raw_NEW  : corr={corr(jraw,rn):+.6f}  max|Δ|={maxdiff(jraw,rn):.3e}")

    # 均值
    print("\n" + "=" * 96)
    print("均值对照")
    print("=" * 96)
    print(f"  JSON.delta_obs_orig  mean = {np.nanmean(jo):+.6f}")
    print(f"  npz+OLD              mean = {np.nanmean(do):+.6f}")
    print(f"  JSON.delta_obs       mean = {np.nanmean(jn):+.6f}")
    print(f"  npz+NEW              mean = {np.nanmean(dn):+.6f}")
    print(f"  JSON.delta_pred      mean = {np.nanmean([r['j_delta_pred'] for r in rows]):+.6f}")
    print(f"  JSON.T               median = {np.nanmedian(jt):.4f}")
    print(f"  T_old                median = {np.nanmedian(to):.4f}")
    print(f"  T_new                median = {np.nanmedian(tn):.4f}")

    # 逐条明细（前 12 条）
    print("\n" + "=" * 96)
    print(f"{'pair':22s} {'seed':5s} {'J.obs_orig':>11s} {'OLD':>11s} {'J.obs':>11s} {'NEW':>11s} {'J.T':>8s} {'T_old':>8s} {'T_new':>8s}")
    for r in rows[:12]:
        print(f"{r['pair']:22s} {str(r['seed']):5s} {r['j_delta_obs_orig']:11.6f} {r['d_old']:11.6f} "
              f"{r['j_delta_obs']:11.6f} {r['d_new']:11.6f} {r['j_T']:8.4f} {r['T_old']:8.4f} {r['T_new']:8.4f}")


if __name__ == "__main__":
    main()
