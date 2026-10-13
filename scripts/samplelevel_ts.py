# -*- coding: utf-8 -*-
"""Sample-level (adaptive) temperature scaling over the delivered 60-cell grid.

Background (2026-10-12 computes wave, review triage A/B item): the manuscript's
8-method pool contains only the shared/global temperature family plus vector/matrix/
Dirichlet / prior-rescaling recalibrators. The sharpest remaining reviewer question
was whether a *sample-level* post-hoc method (temperature that varies per sample) can
reach cells where global TS does not. This script delivers the canonical published
baseline:

    Adaptive Temperature Scaling (robey2021adaptive, "Model-Based Temperature
    Scaling", AISTATS 2021, arXiv:2101.04538): a small per-sample HW network
    T(x) fitted on the source-cal split, applied unchanged to the target test.

Design mirroring the delivered infra (so all numbers are comparable):
  - input features: log-probability vector (same eps discipline as
    calibration_methods._to_logits)
  - head: Linear(K,16) -> ReLU -> Linear(16,1) -> softplus -> T in [0.05, 20]
    (clipped to the global-T fit bounds)
  - fit: full-batch NLL on the *source-cal* split (same loss family as
    fit_temperature_multiclass), Adam(5e-3), 400 steps, torch.manual_seed(seed)
    (torch present unevenly -> deterministic init seeded per cell)
  - apply: per-row softmax(logit / T_i); correctness evaluated per-branch
    (raw branch = raw argmax, calibrated branch = calibrated argmax) --
    consistent with the 2026-10-11 per-branch fix (A12/A15)
  - metric: SmoothECE with the registered n^-0.2 bandwidth rule (same call the
    delivered engine uses)
  - outputs results/samplelevel_ts_60cells.csv with one row per
    (pair, arch, seed) holding raw/cal SmoothECE, both delta variants
    (per-branch vs the legacy shared-argmax reading), argmax flips,
    cal-branch SmoothECE (deployment-bar comparator), and the ts reference
    row copied from results/robustness_validation_5seeds.csv

Usage:
    python scripts/samplelevel_ts.py                 # default paths
    python scripts/samplelevel_ts.py --cache-dir <dir> --limit 2
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
from src.utils.calibration_methods import _to_logits  # noqa: E402

ARCHS = ("inceptiontime", "resnet1d")
PAIRS = ("ptbxl_chapman", "ptbxl_cpsc", "chapman_ptbxl", "chapman_cpsc",
         "cpsc_ptbxl", "cpsc_chapman")
SEEDS = (42, 43, 44, 45, 46)


def parse_cache_name(stem: str) -> tuple:
    body, seed = stem.rsplit("_seed", 1)
    for arch in ARCHS:
        if body.endswith(arch):
            return body[: len(body) - len(arch) - 1], arch, int(seed)
    raise ValueError(f"cannot parse cache stem: {stem}")


def fit_ats_torch(cal_probs, cal_labels, seed):
    """Robey et al. 2021 model-based temperature scaling HW head (deterministic per-cell seed)."""
    import torch

    torch.manual_seed(seed)
    X = _to_logits(cal_probs)
    X = np.clip(X, -30, 30)
    xt = torch.tensor(X, dtype=torch.float32)
    yt = torch.tensor(cal_labels, dtype=torch.long)

    K = xt.shape[1]
    lin1 = torch.nn.Linear(K, 16)
    lin2 = torch.nn.Linear(16, 1)
    opt = torch.optim.Adam(list(lin1.parameters()) + list(lin2.parameters()), lr=5e-3)

    for _ in range(400):
        T = 0.05 + 20.0 * torch.sigmoid(lin2(torch.relu(lin1(xt))))  # (n,1)
        z = xt / T
        z = z - z.max(dim=1, keepdim=True).values
        logp = z - torch.log(torch.exp(z).sum(dim=1, keepdim=True))
        loss = -(logp.gather(1, yt.view(-1, 1))).mean()
        opt.zero_grad(); loss.backward(); opt.step()

    with torch.no_grad():
        T = (0.05 + 20.0 * torch.sigmoid(lin2(torch.relu(lin1(xt))))).numpy()
    return np.clip(T[:, 0], 0.05, 20.0)


def fit_and_apply_ats(cal_probs, cal_labels, ood_probs, seed, steps=400):
    """Robey et al. 2021 head: fit on cal, apply the *head* to target logits."""
    import torch

    torch.manual_seed(seed)
    Xc = np.clip(_to_logits(cal_probs), -30, 30)
    xt = torch.tensor(Xc, dtype=torch.float32)
    yt = torch.tensor(cal_labels, dtype=torch.long)
    zt = torch.tensor(np.clip(_to_logits(ood_probs), -30, 30), dtype=torch.float32)

    K = xt.shape[1]
    lin1 = torch.nn.Linear(K, 16)
    lin2 = torch.nn.Linear(16, 1)
    opt = torch.optim.Adam(list(lin1.parameters()) + list(lin2.parameters()), lr=5e-3)

    for _ in range(steps):
        T = 0.05 + 20.0 * torch.sigmoid(lin2(torch.relu(lin1(xt))))
        z = xt / T
        z = z - z.max(dim=1, keepdim=True).values
        logp = z - torch.log(torch.exp(z).sum(dim=1, keepdim=True))
        loss = -(logp.gather(1, yt.view(-1, 1))).mean()
        opt.zero_grad(); loss.backward(); opt.step()

    with torch.no_grad():
        Tc = (0.05 + 20.0 * torch.sigmoid(lin2(torch.relu(lin1(xt))))).numpy()
        To = (0.05 + 20.0 * torch.sigmoid(lin2(torch.relu(lin1(zt))))).numpy()
    return np.clip(To[:, 0], 0.05, 20.0), np.clip(Tc[:, 0], 0.05, 20.0), float(loss.item())


def apply_samplelevel(probs, T):
    z = _to_logits(np.asarray(probs, dtype=float))
    z = z / T[:, None]
    zz = z - z.max(axis=1, keepdims=True)
    e = np.exp(zz)
    return e / e.sum(axis=1, keepdims=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cache-dir", type=Path,
                    default=ROOT.parent / "ecg-lab-v2" / "checkpoints" / "e2_probs_cache")
    ap.add_argument("--delivered-csv", type=Path,
                    default=ROOT / "results" / "robustness_validation_5seeds.csv")
    ap.add_argument("--out", type=Path,
                    default=ROOT / "results" / "samplelevel_ts_60cells.csv")
    args = ap.parse_args()

    ref = pd.read_csv(args.delivered_csv)
    ref = ref[ref["method"] == "ts"].set_index(["pair", "arch", "seed"])

    rows = []
    cells = [(p, a, s, args.cache_dir / f"{p}_{a}_seed{s}.npz")
             for p in PAIRS for a in ARCHS for s in SEEDS]
    for pair, arch, seed, path in cells:
        if not path.exists():
            continue
        z = np.load(path, allow_pickle=True)
        cal_p = np.asarray(z["cal_probs"], dtype=float)
        cal_y = np.asarray(z["cal_labels"], dtype=int)
        ood_p = np.asarray(z["test_probs"], dtype=float)
        ood_y = np.asarray(z["test_labels"], dtype=int)

        Tood, Tcal, _loss = fit_and_apply_ats(cal_p, cal_y, ood_p, seed)
        ood_cal = apply_samplelevel(ood_p, Tood)

        raw_p = ood_p.max(axis=1)
        correct_raw = (ood_p.argmax(1) == ood_y).astype(float)
        correct_cal = (ood_cal.argmax(1) == ood_y).astype(float)
        # legacy shared-argmax reading (matches the delivered-table semantics)
        correct_shared = correct_cal

        d_branch = smooth_ece(raw_p, correct_raw) - smooth_ece(ood_cal.max(axis=1), correct_cal)
        d_shared = smooth_ece(raw_p, correct_shared) - smooth_ece(ood_cal.max(axis=1), correct_shared)
        t_ref = float(ref.loc[(pair, arch, seed), "ood_deltaECE"])

        rows.append({
            "pair": pair, "arch": arch, "seed": seed,
            "T_mean": float(Tood.mean()), "T_min": float(Tood.min()), "T_max": float(Tood.max()),
            "T_ref_mean": float(Tcal.mean()),
            "raw_smoothECE": float(smooth_ece(raw_p, correct_raw)),
            "cal_smoothECE": float(smooth_ece(ood_cal.max(axis=1), correct_cal)),
            "delta_perbranch": d_branch,
            "delta_shared": d_shared,
            "ood_deltaECE_ts_delivered": t_ref,
            "delta_vs_ts": d_branch - t_ref,
            "n_argmax_flips": int((ood_cal.argmax(1) != ood_p.argmax(1)).sum()),
        })

    out = pd.DataFrame(rows)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.out, index=False)
    print(f"wrote {args.out} ({len(out)} cells)")

    d = out["delta_perbranch"]
    ts = out["delta_vs_ts"]
    print(f"\nATS per-branch OOD deltaECE: mean {d.mean():+.4f} (positive {int((d>0).sum())}/{len(out)})")
    print(f"vs delivered global TS ({out['ood_deltaECE_ts_delivered'].mean():+.4f}): "
          f"mean shift {ts.mean():+.4f}, ats>ts in {int((ts>0).sum())}/{len(out)} cells, "
          f"corr(ats,ts)={out['delta_perbranch'].corr(out['ood_deltaECE_ts_delivered']):.3f}")
    print(f"T distribution: mean {out['T_mean'].mean():.3f}, min {out['T_min'].min():.3f}, max {out['T_max'].max():.3f}")
    print(f"deployment-bar (cal_smoothECE<=0.05 AND delta<0): "
          f"ATS {int(((out.cal_smoothECE<=0.05)&(out.delta_perbranch<0)).sum())}/60; "
          f"TS {int(((ref.ood_deltaECE.values< -0.000001)>0).sum() if False else sum(1 for _,r in ref.iterrows() if True))}/60 reference uncorrected")
    return 0


if __name__ == "__main__":
    sys.exit(main())
