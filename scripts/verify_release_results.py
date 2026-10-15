#!/usr/bin/env python3
"""Quick self-check of the published result tables.

Runs in seconds, needs no dataset, no checkpoints and no GPU: every number
quoted in the repository README (and the article's headline figures) is
re-derived from the CSV/JSON files under ``results/`` and compared against the
published value.

    python scripts/verify_release_results.py          # human-readable report
    python scripts/verify_release_results.py --quiet  # only failures

Exit status is 0 when every check passes, 1 otherwise, so it can be used as a
pre-release gate.

This is a *table* self-check. To exercise the model itself instead, see the
"Reproducing the results" section of the README: ``scripts/train.py`` +
``scripts/eval_transfer.py --load-model`` (needs the preprocessed corpora), or
``scripts/validate_decomposition.py --n 500 --boot 0`` for a data-free
synthetic run of the estimator.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

RESULTS = Path(__file__).resolve().parent.parent / "results"

PASS, FAIL = "PASS", "FAIL"
_results: list[tuple[str, str, str]] = []


def check(name: str, ok: bool, detail: str) -> None:
    _results.append((name, PASS if ok else FAIL, detail))


def close(got: float, want: float, tol: float) -> bool:
    return got is not None and abs(float(got) - want) <= tol


def csv_census() -> None:
    csvs = sorted(RESULTS.glob("*.csv"))
    plain, comment, blocked = [], [], []
    for p in csvs:
        try:
            pd.read_csv(p)
            plain.append(p.name)
        except Exception:
            try:
                pd.read_csv(p, comment="#")
                comment.append(p.name)
            except Exception:
                blocked.append(p.name)
    # 2026-10-11: +2 plain CSVs from the A15/A16 compute pass
    # (robustness_val_8method_perbranch_recheck.csv, deployment_780grid_recompute.csv)
    # 2026-10-13: +1 plain CSV (samplelevel_ts_60cells.csv)
    expect = (36, 28, 5, 3)
    ok = (len(csvs), len(plain), len(comment), len(blocked)) == expect
    check("csv_census", ok,
          f"36 CSVs = 28 plain + 5 comment-header + 3 multi-block; "
          f"got {len(csvs)} = {len(plain)} + {len(comment)} + {len(blocked)}")


def primary_endpoint() -> None:
    rob = pd.read_csv(RESULTS / "robustness_validation_5seeds.csv")
    ts = rob[rob["method"] == "ts"]
    n, pos = len(ts), int((ts["ood_deltaECE"] > 0).sum())
    mean = float(ts["ood_deltaECE"].mean())
    ok = n == 60 and pos == 45 and close(mean, 0.0093, 5e-5)
    check("primary_endpoint", ok,
          f"{pos}/{n} cells positive ({100 * pos / n:.1f}%), mean {mean:+.4f} "
          f"(published: 45/60 = 75.0%, +0.0093)")

    # cluster-robust interval over the 12 pair x architecture strata
    strata = ts.groupby(["pair", "arch"])["ood_deltaECE"].mean()
    m, sd = float(strata.mean()), float(strata.std(ddof=1))
    se = sd / math.sqrt(len(strata))
    tcrit = stats.t.ppf(0.975, len(strata) - 1)
    lo, hi = m - tcrit * se, m + tcrit * se
    ok = (len(strata) == 12 and close(sd, 0.0060, 5e-5)
          and close(lo, 0.0055, 5e-5) and close(hi, 0.0132, 5e-5))
    check("cluster_robust_ci", ok,
          f"12 strata, SD {sd:.4f}, {m:+.4f} [{lo:.4f}, {hi:.4f}] "
          f"(published: +0.0093 [+0.0055, +0.0132], SD 0.0060)")


def pooled_estimates() -> None:
    m = pd.read_csv(RESULTS / "meta_analytic_pooled.csv").set_index("strata")
    # paper quotes two scales: simple stratum means (Table tab:arch_robust) and
    # DerSimonian-Laird random-effects pooling (Limitations); recompute both.
    want_sm = {"InceptionTime": 0.0098, "ResNet1D": 0.0089, "CrossArchitecture": 0.0093}
    want_dl = {"InceptionTime": 0.0096, "ResNet1D": 0.0089, "CrossArchitecture": 0.0091}
    got_sm = {k: float(m.loc[k, "simple_mean"]) for k in want_sm}
    got_dl = {k: float(m.loc[k, "re_pooled_effect"]) for k in want_dl}
    ok = (all(close(got_sm[k], v, 5e-5) for k, v in want_sm.items())
          and all(close(got_dl[k], v, 5e-5) for k, v in want_dl.items()))
    check("pooled_estimates", ok,
          "simple_mean " + ", ".join(f"{k}={got_sm[k]:.4f}" for k in want_sm)
          + " | DL re_pooled_effect " + ", ".join(f"{k}={got_dl[k]:.4f}" for k in want_dl)
          + " (published simple means: 0.0098 / 0.0089 / 0.0093; DL: 0.0096 / 0.0089 / 0.0091)")
    sm = float(m.loc["CrossArchitecture", "simple_mean"])
    i2 = float(m.loc["CrossArchitecture", "I2"])
    check("pooled_residual_note", close(sm, 0.0093, 5e-5) and i2 > 0.99,
          f"cross-architecture simple_mean {sm:.4f}, I2 {i2:.4f}"
          " (published: cross mean +0.0093; between-strata heterogeneity ~99.97%)")


def l2_grid() -> None:
    d = pd.read_csv(RESULTS / "l2_shift_full_390cells.csv")
    n = len(d)
    ge1 = int((d["safety_count"] >= 1).sum())
    both = int((d["safety_count"] >= 2).sum())
    j = json.loads((RESULTS / "l2_shift_full_summary.json").read_text(encoding="utf-8"))
    ok = n == 390 and ge1 == 348 and both == 222 and j["n_safe_cells"] == 348
    check("l2_grid", ok,
          f"{n} cells: {ge1}/{n} pass with >=1 architecture ({100 * ge1 / n:.1f}%), "
          f"{both}/{n} pass with both ({100 * both / n:.1f}%), "
          f"summary n_safe_cells={j['n_safe_cells']} "
          f"(published: 570/780 flags = 73.1% mean per-row rate; 222/390 both architectures)")


def deployment_table() -> None:
    rows = [ln.split(",") for ln in
            (RESULTS / "deployment_metrics.csv").read_text(encoding="utf-8").splitlines()
            if ln.startswith("method,ts,")]
    ts = next((r for r in rows if r[1] == "ts"), None)
    ok = ts is not None and [int(x) for x in ts[2:6]] == [780, 8, 368, 18]  # strict: delta<=-0.01 AND cal<=0.05
    check("deployment_table", ok,
          "TS row = " + (",".join(ts[2:6]) if ts else "missing")
          + " (n_total, n_safe, n_beneficial, n_calibrated; "
          "published: 780, 8, 368, 18 (strict: delta<=-0.01 AND cal<=0.05; rate 0.0103))")


def raw_ece_range() -> None:
    a = pd.read_csv(RESULTS / "ablation_ts_components.csv", comment="#")
    raw = a.loc[a["stage"] == "raw", "smooth_ece"]
    ok = (len(raw) == 64 and close(raw.min(), 0.036, 5e-4)
          and close(raw.max(), 0.357, 5e-4) and close(raw.mean(), 0.203, 5e-4))
    check("raw_ece_range", ok,
          f"n={len(raw)}, range [{raw.min():.3f}, {raw.max():.3f}], "
          f"mean {raw.mean():.3f} (published: 0.036-0.357, mean 0.203). "
          f"The contaminated copy would read up to 0.469.")


def dose_response() -> None:
    s = pd.read_csv(RESULTS / "s2_dose_response.csv")
    cells = s.groupby(["method", "n_cal", "pair", "arch", "seed"])["benefit"].mean().reset_index()
    shape_ok = (len(s) == 30000 and s["n_cal"].nunique() == 5
                and s["method"].nunique() == 5 and s.groupby(
                    ["pair", "arch", "seed"]).ngroups == 60
                and s["repeat"].nunique() == 20)

    def agg(method: str, n_cal: int):
        c = cells[(cells["method"] == method) & (cells["n_cal"] == n_cal)]["benefit"]
        return float(c.mean()), int((c > 0).sum())

    zs, zs_pos = agg("ts_s1", 50)
    pl, pl_pos = agg("platt", 50)
    ts, _ = agg("ts", 50)
    pl_1000, _ = agg("platt", 1000)
    ok = (shape_ok and close(zs, 0.0093, 5e-5) and zs_pos == 45
          and close(pl, 0.150, 5e-4) and pl_pos == 60 and close(ts, 0.127, 5e-4)
          and abs(pl_1000 - pl) < 0.02)
    check("dose_response", ok,
          f"{len(s)} rows (5 budgets x 5 methods x 60 cells x 20 repeats); "
          f"zero-shot {zs:+.4f} ({zs_pos}/60), platt@50 {pl:+.4f} ({pl_pos}/60), "
          f"ts@50 {ts:+.4f}, platt@1000 {pl_1000:+.4f} (saturates by 250) "
          f"(published: +0.0093 (75%), +0.1502 (100%), +0.1269)")


def bootstrap_widths() -> None:
    b = pd.read_csv(RESULTS / "bootstrap_diagnostics.csv", comment="#")
    w = b.loc[b["method"] == "ts", "ood_ci_width"]
    ok = close(float(w.min()), 2.1e-5, 1e-7) and close(float(w.median()), 8.3e-4, 5e-5)
    check("bootstrap_ci_widths", ok,
          f"min {w.min():.1e}, median {w.median():.1e} "
          f"(published: widths span 2.1e-5 to 7.5e-3, median 8.3e-4)")


def withheld_absent() -> None:
    forbidden = ["deployment_loco_validation.csv", "deployment_loco_validation_smoke.csv",
                 "c3_inceptiontime_lite_30exp.csv", "predictability_sensitivity.json"]
    present = [f for f in forbidden if (RESULTS / f).exists()]
    check("withheld_absent", not present,
          "4 blocked artifacts are withheld" if not present
          else "present but must not be shipped: " + ", ".join(present))


def e3_patient_bca() -> None:
    """Registered-unit E3 deliverable: patient-level BCa summary."""
    summ = json.loads((RESULTS / "e3_patient_bca_summary.json").read_text(encoding="utf-8"))
    pooled = summ["pooled"]
    ncv = pooled["ncv_ood"]
    dcr = pooled["dcr_ood"]
    idc = pooled["ncv_id"]
    ok = (close(ncv["point"], 0.000238, 5e-5) and ncv["bca_lo"] > 0
          and close(ncv["bca_lo"], 0.000125, 5e-5)
          and close(ncv["bca_hi"], 0.000353, 5e-5)
          and close(dcr["point"], 0.000526, 5e-5) and dcr["bca_lo"] > 0
          and close(dcr["bca_lo"], 0.000280, 5e-5) and close(dcr["bca_hi"], 0.000775, 5e-5)
          and idc["bca_lo"] < 0 < idc["bca_hi"])
    count_cells = len(pd.read_csv(RESULTS / "e3_patient_bca_cells.csv"))
    ok = ok and count_cells == 60 and summ["percell_support_counts"]["ncv_ood_lo_gt0"] == 9
    check("e3_patient_bca", ok,
          f"pooled OOD NCV {ncv['point']:+.6f}, patient-level BCa CI "
          f"[{ncv['bca_lo']:+.6f}, {ncv['bca_hi']:+.6f}] excludes zero; DCR CI "
          f"[{dcr['bca_lo']:+.6f}, {dcr['bca_hi']:+.6f}]; per-cell support 9/60 "
          f"(published: patient-level registered unit, B=10,000, integrity gate 60/60)")


CHECKS = [csv_census, primary_endpoint, pooled_estimates, l2_grid,
          deployment_table, raw_ece_range, dose_response, bootstrap_widths,
          e3_patient_bca, withheld_absent]


def main() -> int:
    ap = argparse.ArgumentParser(description="Re-derive the published numbers from results/")
    ap.add_argument("--quiet", action="store_true", help="print failures only")
    args = ap.parse_args()

    if not RESULTS.is_dir():
        print(f"results/ not found at {RESULTS}", file=sys.stderr)
        return 2

    for fn in CHECKS:
        try:
            fn()
        except Exception as exc:  # a check that cannot run is a failed check
            check(fn.__name__, False, f"{type(exc).__name__}: {exc}")

    n_pass = sum(1 for _, s, _ in _results if s == PASS)
    for name, status, detail in _results:
        if status == PASS and args.quiet:
            continue
        print(f"[{status}] {name}: {detail}")
    print(f"\n{n_pass}/{len(_results)} checks passed")
    return 0 if n_pass == len(_results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
