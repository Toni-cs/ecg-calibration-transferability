# -*- coding: utf-8 -*-
"""Reconstruct the aggregate summary for real_prior_recovery.csv (fix for the
real_prior_recovery_summary.json orphan file).

History (see docs/CORRECTIONS_LEDGER_2026-10-11.md, B1):
The historical real_prior_recovery_summary.json (2026-09-27 epoch) had no
generator in any surviving checkout (its writer lived on the retired
full-work branch). This script reconstructs the aggregation from the
delivered results/real_prior_recovery.csv so the summary stays a live
artifact of the delivered data instead of a frozen stale file.

Fields reproduced from the archived 2026-09-27 file (deterministic aggregations
of the CSV columns):

    n_cells, n_bbse_identifiable, n_em_identifiable
    err_baseline_mean, err_bbse_mean, err_em_mean
    bbse_beats_baseline ("56/60" style), bbse_rel_improvement_pct
    bbse_beats_em, cond_median, cond_max, cond_gt_1e4
    delta_mean, direction_sign_positive

Fields NOT reproducible from the CSV and therefore reported as null with a
note: cluster_ci_low / cluster_ci_high. The pair-clustered bootstrap CI
requires patient-level cluster labels, which real_prior_recovery.csv does not
carry; it remains recomputable only in the lab tree via the original runner
(scripts/real_prior_recovery.py with checkpoints + data). The manuscript
quotes that CI from the runner's own artifacts, not from this summary.

Usage:
    python scripts/real_prior_recovery_summary.py               # default paths
    python scripts/real_prior_recovery_summary.py --csv ... --out ...
Deterministic: no RNG, byte-stable output (JSON key order fixed).
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

PAIRS = ("ptbxl_chapman", "ptbxl_cpsc", "chapman_ptbxl", "chapman_cpsc",
         "cpsc_ptbxl", "cpsc_chapman")


def pair_prefix(cell: str) -> str:
    for p in PAIRS:
        if cell.startswith(p + "_"):
            return p
    return cell


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--csv", type=Path,
                    default=ROOT / "results" / "real_prior_recovery.csv")
    ap.add_argument("--out", type=Path,
                    default=ROOT / "results" / "real_prior_recovery_summary.json")
    args = ap.parse_args()

    df = pd.read_csv(args.csv)
    n = len(df)
    bbse_ok = df["err_bbse"].notna() & (df["bbse_failed"] == 0)
    em_ok = df["err_em"].notna() & (df["em_failed"] == 0)

    base_mean = float(df["err_baseline"].mean())
    bbse_mean = float(df.loc[bbse_ok, "err_bbse"].mean())
    em_mean = float(df.loc[em_ok, "err_em"].mean())

    beats_base = int((df.loc[bbse_ok, "err_bbse"] < df.loc[bbse_ok, "err_baseline"]).sum())
    beats_em = int((df.loc[bbse_ok, "err_bbse"] < df.loc[bbse_ok, "err_em"]).sum())
    rel_pct = round((base_mean - bbse_mean) / base_mean * 100.0, 1) if base_mean > 0 else 0.0

    cond = df.loc[bbse_ok, "cond_bbse"].astype(float)
    delta = df["err_baseline"].astype(float) - df["err_bbse"].astype(float)

    df = df.assign(_pair=df["cell"].map(pair_prefix),
                   _delta=delta.values)
    pair_sign = (df.groupby("_pair")["_delta"].mean() > 0).sum()
    pairs_total = df["_pair"].nunique()

    summary = {
        "n_cells": int(n),
        "n_bbse_identifiable": int(bbse_ok.sum()),
        "n_em_identifiable": int(em_ok.sum()),
        "err_baseline_mean": round(base_mean, 4),
        "err_bbse_mean": round(bbse_mean, 4),
        "err_em_mean": round(em_mean, 4),
        "bbse_beats_baseline": f"{beats_base}/{n}",
        "bbse_rel_improvement_pct": rel_pct,
        "bbse_beats_em": f"{beats_em}/{n}",
        "cond_median": round(float(cond.median()), 1),
        "cond_max": round(float(cond.max()), 1),
        "cond_gt_1e4": f"{int((cond > 1e4).sum())}/{n}",
        "delta_mean": round(float(delta.mean()), 4),
        "direction_sign_positive": f"{int(pair_sign)}/{pairs_total}",
        "cluster_ci_low": None,
        "cluster_ci_high": None,
        "cluster_ci_note": ("not recomputable from real_prior_recovery.csv alone "
                           "(requires patient-level cluster labels; recompute path = "
                           "the lab-tree runner scripts/real_prior_recovery.py with "
                           "checkpoints + data; see docs/CORRECTIONS_LEDGER_2026-10-11.md B1)"),
        "note": ("generator reconstructed on 2026-10-12 and re-run on the "
                 "delivered post-retrain real_prior_recovery.csv; replaces the "
                 "2026-09-27-epoch summary (archived at "
                 "results/archive/no-generator/real_prior_recovery_summary.2026-09-27.json); "
                 "target-domain labels used for scoring only; estimator is label-free"),
    }
    order = list(summary.keys())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.out} from {args.csv} ({n} cells)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
