# -*- coding: utf-8 -*-
"""Recompute the 8-method OOD calibration deltas under per-branch correctness.

Background (fix 2026-10-11): the historical eval_transfer driver shared ONE
correctness vector across both bootstrap branches (the calibrated-argmax
correctness), which mismeasures the raw branch for argmax-flipping
recalibrators (per-class Platt, isotonic, vector, matrix, dirichlet, EM/BBSE
prior rescaling). The primary endpoint (method=ts) and any argmax-preserving
method are identical under both semantics.

This script recomputes the OOD-branch point estimates DIRECTLY from the cached
probability arrays in the lab tree (`checkpoints/e2_probs_cache/*.npz`, which
hold the source-cal fit set and the target-test evaluation set per cell), using
the corrected per-branch semantics and the same SmoothECE estimator as
eval_transfer. It does not retrain, does not touch any delivered table, and
writes its output to results/robustness_val_8method_perbranch_recheck.csv.

Gates (hard):
  - every cache cell must carry the same label_encoding stamp as the delivered
    post-label-repair set
  - method=ts rows must reproduce the delivered ood_deltaECE to within 1e-6
    (identical semantics -> identical numbers)
  - method=ts argmax must be preserved (0 flips)

Usage:
    python scripts/recheck_method_semantics.py                 # default paths
    python scripts/recheck_method_semantics.py --cache-dir <dir> --limit 2
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.utils.calibration import smooth_ece  # noqa: E402
from src.utils.calibration_methods import CALIBRATION_METHODS  # noqa: E402
from src.utils.prior_shift import fit_em, fit_bbse  # noqa: E402

METHODS_REG = ["ts", "platt", "isotonic", "vector", "matrix", "dirichlet",
               "em_prior", "bbse_prior"]
PRIOR_METHODS = ("em_prior", "bbse_prior")
ARCHS = ("inceptiontime", "resnet1d")
PAIRS = ("ptbxl_chapman", "ptbxl_cpsc", "chapman_ptbxl", "chapman_cpsc",
         "cpsc_ptbxl", "cpsc_chapman")
SEEDS = (42, 43, 44, 45, 46)


def parse_cache_name(stem: str) -> tuple:
    """'ptbxl_chapman_inceptiontime_seed42' -> (ptbxl_chapman, inceptiontime, 42)."""
    body, seed = stem.rsplit("_seed", 1)
    for arch in ARCHS:
        if body.endswith(arch):
            return body[: len(body) - len(arch) - 1], arch, int(seed)
    raise ValueError(f"cannot parse cache stem: {stem}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cache-dir", type=Path,
                    default=ROOT.parent / "ecg-lab-v2" / "checkpoints" / "e2_probs_cache")
    ap.add_argument("--delivered-csv", type=Path,
                    default=ROOT / "results" / "robustness_validation_5seeds.csv")
    ap.add_argument("--out", type=Path,
                    default=ROOT / "results" / "robustness_val_8method_perbranch_recheck.csv")
    ap.add_argument("--limit", type=int, default=None, help="debug: first N cells")
    args = ap.parse_args()

    deliv = pd.read_csv(args.delivered_csv)
    ref = deliv[deliv["method"].isin(METHODS_REG)].set_index(["pair", "arch", "seed", "method"])

    rows, gates = [], {"ts_gate_fail": 0, "ts_flip_fail": 0, "stamp_mismatch": 0}
    # Delivered encoding stamps depend on the class count: 5-class cells carry the
    # SUPERCLASSES order, 4-class subspace cells carry the delivered SUBSPACE_CPSC order
    # (the 2026-10-05 lab fix / 09-18 label-repair stamps).
    stamps_expected = {4: "NORM|CD|STTC|MI", 5: "NORM|MI|STTC|CD|HYP"}
    layout_seen = {}
    cells = []
    for pair in PAIRS:
        for arch in ARCHS:
            for seed in SEEDS:
                p = args.cache_dir / f"{pair}_{arch}_seed{seed}.npz"
                cells.append((pair, arch, seed, p))
    if args.limit:
        cells = cells[: args.limit]

    ok_cells = 0
    for pair, arch, seed, path in cells:
        if not path.exists():
            print(f"[MISS] {path.name}")
            continue
        z = np.load(path, allow_pickle=True)
        stamp = str(z["label_encoding"])
        K0 = int(z["num_classes"])
        layout_seen[K0] = layout_seen.get(K0, 0) + 1
        if stamp != stamps_expected[K0]:
            gates["stamp_mismatch"] += 1
            print(f"[STAMP] {path.name}: {stamp!r} != expected {stamps_expected[K0]!r}")
        cal_p = np.asarray(z["cal_probs"], dtype=float)
        cal_y = np.asarray(z["cal_labels"], dtype=int)
        ood_p = np.asarray(z["test_probs"], dtype=float)
        ood_y = np.asarray(z["test_labels"], dtype=int)
        K = ood_p.shape[1]
        if cal_p.shape[1] != K:
            print(f"[SKIP] {path.name}: cal/test class mismatch {cal_p.shape} vs {ood_p.shape}")
            continue
        ok_cells += 1
        raw_p = ood_p.max(axis=1)
        correct_raw = (ood_p.argmax(1) == ood_y).astype(float)

        for m in METHODS_REG:
            if m in PRIOR_METHODS:
                res = fit_em(cal_p, cal_y, ood_p) if m == "em_prior" else fit_bbse(cal_p, cal_y, ood_p)
                if res is None:
                    continue
                w = res["pi_hat"] / np.maximum(res["pi_train"], 1e-12)
                ood_cal = ood_p * w[None, :]
                ood_cal = ood_cal / ood_cal.sum(axis=1, keepdims=True)
            else:
                fit_fn, apply_fn, _ = CALIBRATION_METHODS[m]
                params = fit_fn(cal_p, cal_y)
                if params is None:  # e.g. isotonic small-cell guard
                    continue
                ood_cal = apply_fn(ood_p, params)
            flips = int((ood_cal.argmax(1) != ood_p.argmax(1)).sum())
            correct_cal = (ood_cal.argmax(1) == ood_y).astype(float)
            d = smooth_ece(raw_p, correct_raw) - smooth_ece(ood_cal.max(axis=1), correct_cal)
            try:
                d_deliv = float(ref.loc[(pair, arch, seed, m), "ood_deltaECE"])
            except KeyError:
                d_deliv = float("nan")
            if abs(d - d_deliv) > 1e-6:
                if m == "ts":
                    gates["ts_gate_fail"] += 1
            if m == "ts" and flips != 0:
                gates["ts_flip_fail"] += 1
            rows.append({
                "pair": pair, "arch": arch, "seed": seed, "method": m,
                "ood_deltaECE_delivered": d_deliv,
                "ood_deltaECE_perbranch": d,
                "abs_diff": abs(d - d_deliv),
                "n_argmax_flips": flips,
            })

    out = pd.DataFrame(rows)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.out, index=False)
    print(f"\nwrote {args.out} ({len(out)} rows over {ok_cells} cells); "
          f"cache layouts (K: cells) = {layout_seen}")
    print("gates:", gates)
    if gates["ts_gate_fail"] or gates["ts_flip_fail"] or gates["stamp_mismatch"]:
        print("GATE FAILED")
        return 1

    # ---- aggregates: per-method semantic drift ----
    print("\nper-method OOD deltaECE: delivered vs per-branch (n cells)")
    for m in METHODS_REG:
        sub = out[out["method"] == m]
        if not len(sub):
            print(f"  {m:11s} no rows")
            continue
        md = sub["ood_deltaECE_delivered"].mean()
        mr = sub["ood_deltaECE_perbranch"].mean()
        sgn = int(((sub["ood_deltaECE_delivered"] < 0) != (sub["ood_deltaECE_perbranch"] < 0)).sum())
        print(f"  {m:11s} delivered {md:+.4f} -> perbranch {mr:+.4f} "
              f"(mean shift {mr - md:+.5f}, sign flips {sgn}/{len(sub)}, "
              f"flips/cell median {sub['n_argmax_flips'].median():.0f})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
