"""诊断 JSON.delta_obs_orig 的偏差来源。"""
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


def swap13(l):
    o = l.copy(); o[l == 1] = 3; o[l == 3] = 1; return o


def onehot(y, k):
    m = np.zeros((len(y), k)); m[np.arange(len(y)), y] = 1.0; return m


recs = json.loads(JSON_PATH.read_text(encoding="utf-8"))
npz_index = {}
for p in CACHE.glob("*.npz"):
    a = p.stem.split("_")
    npz_index[(a[0], a[1], "_".join(a[2:-1]), a[-1])] = p

print(f"{'pair':22s} {'arch':12s} {'seed':5s} | {'J.raw_o':>9s} {'J.cal_o':>9s} {'raw-cal':>9s} {'J.d_orig':>9s} | {'OLD':>9s} {'diff':>9s}")
print("-" * 108)
bad = []
for r in recs:
    key = (r["source"], r["target"], r["arch"], f"seed{r['seed']}")
    p = npz_index.get(key)
    if p is None:
        print(f"  [NO NPZ] {key}")
        continue
    d = np.load(p)
    tp, ty = d["test_probs"].astype(float), d["test_labels"].astype(int)
    cp, cy = d["cal_probs"].astype(float), d["cal_labels"].astype(int)
    k = tp.shape[1]
    if "cpsc" in (r["source"], r["target"]):
        ty_o, cy_o = swap13(ty), swap13(cy)
    else:
        ty_o, cy_o = ty, cy
    T = fit_temperature(cp, onehot(cy_o, k))
    ts = apply_temperature(tp, T)
    raw = smooth_ece(tp.max(1), (tp.argmax(1) == ty_o).astype(float))
    cal = smooth_ece(ts.max(1), (ts.argmax(1) == ty_o).astype(float))
    old = raw - cal

    jraw = r.get("raw_ood_orig")
    jcal = r.get("cal_ood_orig")
    jdo = r.get("delta_obs_orig")
    diff = old - jdo
    flag = "" if abs(diff) < 1e-6 else "  <<<"
    if abs(diff) >= 1e-6:
        bad.append((key, jraw, jcal, jdo, raw, cal, old, diff))
    print(f"{r['source']+'->'+r['target']:22s} {r['arch']:12s} {str(r['seed']):5s} | "
          f"{jraw:9.6f} {jcal:9.6f} {jraw-jcal:9.6f} {jdo:9.6f} | {old:9.6f} {diff:+9.6f}{flag}")

print("\n" + "=" * 108)
print(f"不匹配 cell 数：{len(bad)} / {len(recs)}")
if bad:
    print("\n不匹配明细（检查 J.raw/J.cal 与 npz 的 raw/cal 是否吻合）：")
    for key, jraw, jcal, jdo, raw, cal, old, diff in bad:
        print(f"  {key}")
        print(f"    JSON raw_orig={jraw:.6f}  cal_orig={jcal:.6f}  delta={jdo:.6f}")
        print(f"    npz  raw     ={raw:.6f}  cal     ={cal:.6f}  delta={old:.6f}   (Δdelta={diff:+.6f})")

# 内部一致性：J.delta_obs_orig == J.raw_ood_orig - J.cal_ood_orig ?
inc = [abs((r["raw_ood_orig"] - r["cal_ood_orig"]) - r["delta_obs_orig"]) for r in recs]
print(f"\nJSON 内部一致性 max|(raw-cal) - delta_obs_orig| = {max(inc):.3e}")

# 只看 60 main（排除 mamba）
main = [r for r in recs if r["arch"] != "mamba"]
print(f"\n排除 mamba 后 {len(main)} 条：")
print(f"  mean delta_obs_orig = {np.mean([r['delta_obs_orig'] for r in main]):+.6f}")
print(f"  mean delta_obs      = {np.mean([r['delta_obs'] for r in main]):+.6f}")
print(f"  mean delta_pred     = {np.mean([r['delta_pred'] for r in main]):+.6f}")
