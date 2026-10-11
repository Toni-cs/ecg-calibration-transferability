# -*- coding: utf-8 -*-
"""Recompute the deployment sensitivity/specificity table on the delivered 780-cell grid.

Background (fix 2026-10-11): the paper's tab:deploy_sens rows (and the accompanying
in-sample/holdout numbers) were originally computed on the checkpoint-level
evaluation pool (~3015 rows, era of step3_deployment), not on the 780-evaluation
L2 grid the surrounding section quotes. This script recomputes the same Youden /
leave-shift-type-out / frozen-threshold scheme DIRECTLY from the delivered
artifact results/l2_shift_full_780cells_detail.csv, mirroring
scripts/deployment_holdout_recompute.py exactly:

  - beneficial class = ts_delta_ece < -0.01 (the deployment-metrics strict convention,
    SAFE = -0.01 in the pool script; the same definition behind deployment_metrics'
    n_beneficial = 368 on this grid)
  - threshold search = percentile grid of raw_ece (0..100, step 0.5) over the pool
  - leave-shift-type-out: search on all rows except the held-out single level,
    evaluate on the held-out level ({downsample: fs125, lead_drop: leads2,
    noise: noise0, gain: gain2.0})
  - frozen threshold (0.126725, the pool-era optimum) evaluated on the union of the
    four held-out levels

It also computes the lookup-table strategy row for tab:trivial (route rows with
raw_ece > optimum to TS; n = routed count; mean/std of their ts_delta_ece).

Read-only w.r.t. delivered artifacts; writes
results/deployment_780grid_recompute.csv.

Usage:
    python scripts/recompute_deployment_780grid.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SAFE = -0.01          # deployment-metrics strict improvement convention
FROZEN_T_DEFAULT = 0.126725   # pool-era frozen optimum (kept as a diagnostic row)
HOLDOUT = {"downsample": "fs125", "lead_drop": "leads2",
           "noise": "noise0", "gain": "gain2.0"}
TABLE_T_DEFAULT = [0.073, 0.102, 0.172, 0.213, 0.321]  # the five thresholds quoted in tab:deploy_sens


def youden(raw, ben, idx, t):
    pred = raw[idx] > t
    b = ben[idx]
    tp = int((pred & b).sum())
    tn = int((~pred & ~b).sum())
    sens = tp / max(int(b.sum()), 1)
    spec = tn / max(int((~b).sum()), 1)
    return sens, spec, sens + spec - 1.0, tp, int((pred & ~b).sum()), tn, int((~pred & b).sum())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--detail", type=Path,
                    default=ROOT / "results" / "l2_shift_full_780cells_detail.csv")
    ap.add_argument("--out", type=Path,
                    default=ROOT / "results" / "deployment_780grid_recompute.csv")
    ap.add_argument("--frozen", type=float, default=FROZEN_T_DEFAULT)
    ap.add_argument("--table-thresholds", type=float, nargs="+", default=TABLE_T_DEFAULT)
    args = ap.parse_args()

    d = pd.read_csv(args.detail)
    raw = d["raw_ece"].to_numpy(dtype=float)
    delta = d["ts_delta_ece"].to_numpy(dtype=float)
    lvl = d["shift"].to_numpy(dtype=str)
    ben = delta < SAFE
    P = int(ben.sum())
    N = int((~ben).sum())
    print(f"rows={len(d)}, beneficial(P)={P}, non-beneficial(N)={N} "
          f"(strict: ts_delta_ece < {SAFE}; paper's deployment_metrics n_beneficial=368)")

    out = []
    allidx = np.arange(len(raw))
    grid = np.percentile(raw, np.arange(0, 100.01, 0.5))
    js = [youden(raw, ben, allidx, float(t))[2] for t in grid]
    bt_in = float(grid[int(np.argmax(js))])
    s, sp, J, tp, fp, tn, fn = youden(raw, ben, allidx, bt_in)
    out.append(("in_sample_780grid", "*", bt_in, s, sp, J, tp, fp, tn, fn))
    print(f"in-sample optimum: thr={bt_in:.6f} sens={s:.4f} spec={sp:.4f} J={J:+.4f} (TP={tp}, FP={fp})")

    for st, hs in HOLDOUT.items():
        tr = np.where(lvl != hs)[0]
        te = np.where(lvl == hs)[0]
        g = np.percentile(raw[tr], np.arange(0, 100.01, 0.5))
        js_t = [youden(raw, ben, tr, float(t))[2] for t in g]
        bt = float(g[int(np.argmax(js_t))])
        s, sp, J, tp, fp, tn, fn = youden(raw, ben, te, bt)
        out.append((st, hs, bt, s, sp, J, tp, fp, tn, fn))
        print(f"leave-type-out {st:10s} (held-out {hs:8s}): thr={bt:.6f} "
              f"sens={s:.4f} spec={sp:.4f} J={J:+.4f}")

    fh = np.where(np.isin(lvl, list(HOLDOUT.values())))[0]
    s, sp, J, tp, fp, tn, fn = youden(raw, ben, fh, args.frozen)
    out.append(("frozen_threshold_poolera", "4 holdout levels", args.frozen, s, sp, J, tp, fp, tn, fn))
    print(f"frozen (pool-era) threshold {args.frozen}: sens={s:.4f} spec={sp:.4f} J={J:+.4f}")

    print("\nfixed-threshold rows (the five thresholds quoted in tab:deploy_sens):")
    for t in args.table_thresholds:
        s, sp, J, tp, fp, tn, fn = youden(raw, ben, allidx, float(t))
        out.append((f"fixed_t_{t}", "*", float(t), s, sp, J, tp, fp, tn, fn))
        print(f"  t={t:.3f}: sens={s:.4f} spec={sp:.4f} J={J:+.4f} (TP={tp}, FP={fp})")

    # ---- lookup-table strategy row for tab:trivial ----
    routed = np.where(raw > bt_in)[0]
    md = float(delta[routed].mean())
    sd = float(delta[routed].std(ddof=1)) if len(routed) > 1 else 0.0
    print(f"\nlookup-table strategy @ in-sample optimum: n_routed={len(routed)}, "
          f"mean deltaECE {md:+.4f}, std {sd:.4f}")

    summary = pd.DataFrame([
        {"scheme": "in_sample_780grid", "holdout_level": "*", "best_threshold": bt_in,
         "mean_delta_routed": "", "std_delta_routed": "", "n_routed": ""},
        {"scheme": "lookup_table_strategy", "holdout_level": "raw_ece > in-sample optimum",
         "best_threshold": bt_in, "mean_delta_routed": md, "std_delta_routed": sd,
         "n_routed": int(len(routed))},
    ])
    rows = pd.DataFrame({
        "scheme": [o[0] for o in out],
        "holdout_level": [o[1] for o in out],
        "best_threshold": [o[2] for o in out],
        "sensitivity": [o[3] for o in out],
        "specificity": [o[4] for o in out],
        "youden_J": [o[5] for o in out],
        "TP": [o[6] for o in out],
        "FP": [o[7] for o in out],
        "TN": [o[8] for o in out],
        "FN": [o[9] for o in out],
        "note": ["780-grid recompute (beneficial = ts_delta_ece < -0.01, deployment-metrics strict convention)"
                 for _ in out],
    })
    args.out.parent.mkdir(parents=True, exist_ok=True)
    pd.concat([rows, summary], ignore_index=True).to_csv(args.out, index=False)
    print(f"saved -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
