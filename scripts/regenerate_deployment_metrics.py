#!/usr/bin/env python
"""Regenerate results/deployment_metrics.csv from the shipped L2 detail grid.

Strict deployment caliber (protocol S9 wording):
    benefit-leg      ts_delta_ece <= -0.01      (absolute post-TS improvement > 0.01;
                                                 DeltaECE = post-TS ECE - raw ECE,
                                                 negative = improvement)
    calibration-leg  (raw_ece + ts_delta_ece) <= 0.05   (post-recalibration SmoothECE <= 0.05)
    safe (joint)     both of the above

Unit calibers:
- `raw_ece` and `ts_delta_ece` are the ECE (SmoothECE-binned) quantities of the
  L2 evaluation grid; the Brier-reliability column `ts_brier_rel` is a DIFFERENT
  scale and must not be mixed in here (a 2026-10-10 audit fixed exactly that mix).
- Per-cell confidence intervals are unavailable on the L2 grid, so the joint
  rate is a point-estimate convention.

Output layout matches the shipped artifact (plain-read by pandas; the trailing
informational block is separated by a '# ' marker line).
"""
import csv
from pathlib import Path

RESULTS = Path(__file__).resolve().parents[1] / "results"
DETAIL = RESULTS / "l2_shift_full_780cells_detail.csv"

det = list(csv.DictReader(open(DETAIL, encoding="utf-8-sig")))
n_total = len(det)
n_strict = n_benef = n_calf = 0
n_strict_IT = n_strict_RN = 0
for r in det:
    raw_ece = float(r["raw_ece"])
    delta = float(r["ts_delta_ece"])
    post = raw_ece + delta
    if delta <= -0.01:
        n_benef += 1
    if post <= 0.05:
        n_calf += 1
    if delta <= -0.01 and post <= 0.05:
        n_strict += 1
        if r["arch"] == "inceptiontime":
            n_strict_IT += 1
        else:
            n_strict_RN += 1
rate = n_strict / n_total

txt = (
    "arbitrator,method,n_total,n_safe,n_beneficial_only,n_calibrated_only,safe_rate\n"
    f"method,ts,{n_total},{n_strict},{n_benef},{n_calf},{rate:.6f}\n"
    "\n"
    "# per-architecture strict-cell breakdown (informational; DeltaECE = post-TS ECE - raw)\n"
    "arch,inceptiontime,resnet1d\n"
    f"n_strict,{n_strict_IT},{n_strict_RN}\n"
)
out = RESULTS / "deployment_metrics.csv"
out.write_text(txt, encoding="utf-8")
print(f"deployment_metrics.csv written: ts row = [{n_total},{n_strict},{n_benef},{n_calf}] rate={rate:.6f}")
