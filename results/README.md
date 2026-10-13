# `results/` — inventory and provenance

## Provenance rule

- **40 of the 57 top-level files are byte-identical (SHA-256, verified 2026-10-11) to the
  same-named result tables in the article's submitted supplementary package**
  (`paper/submission/supplementary/S2_result_tables/`; the two compute-pass
  artifacts added on 2026-10-11 are mirrored into the package as well). The
  other 17 are the integrity notices, the figure, the npz draw file, and
  auxiliary files that are not tables. (The directory holds 57 top-level
  files — 56 + this inventory.) The `archive/` subtree additionally holds
  frozencopies kept only for provenance — see
  [`archive/README.md`](archive/README.md); nothing there is quotable.
- The directory is the **corrected** set. Earlier snapshots of this repository
  shipped pre-correction copies of 17 of these tables; they have been replaced
  with the corrected ones. What was wrong, when, and what replaced it is recorded
  in the eight `_*NOTICE*.md` files — **read them before quoting a number**.
- The `generated` column is the file's own mtime, preserved from its source. Use it
  to check that a table post-dates the notice that governs it: a table older than
  its notice is pre-correction and must not be used.
- **`.OLD_ENCODING` names an encoding, not an age.** Both `.OLD_ENCODING.csv`
  files are recomputations under the *original* `SUBSPACE_CPSC` label ordering —
  the ordering the checkpoints behind these tables were trained with — so they
  hold **corrected** values, not obsolete ones.
  `discrimination_metrics_60exp.OLD_ENCODING.csv` is the table the article cites
  for its per-direction AUROC range (0.735–0.843).
- Generators were verified by grepping the writer (the `to_csv`/`open(..., "w")`
  target), not by guessing from the file name.

## Files deliberately withheld

These exist in the submitted supplementary (or in older snapshots) but are **not**
shipped here, because the project's own notices or audit block them:

| Withheld | Why |
|---|---|
| `deployment_loco_validation.csv`, `deployment_loco_validation_smoke.csv` | [`_LOCO_CONTAMINATION_NOTICE.md`](#notices): the only archived copy is contaminated (135 cells × 13 metrics); the 2026-10-04 rerun did not complete |
| `c3_inceptiontime_lite_30exp.csv` | header-only stub of an aborted run (0 training / 0 transfer experiments) |
| `predictability_sensitivity.json` | no generator exists in any branch, and its `y` is built from pre-correction values; the article's own audit block records it as *not citable* |
| `decomposition_validation_n500_20260829.bak.csv` | `.bak` duplicate of `decomposition_validation.csv` |
| `decomposition_validation_n20000_postfix_20260830.csv`, `..._rerun_20260830.csv` | byte-identical duplicate reruns of each other |

## Inventory

Generated names in `scripts/` unless a path is given. `run_e1a`, `run_e1b`,
`step2_predictability`, `run_s2_small_sample`, `step3_deployment`,
`p2_optional_fixes`, `predictability_corrected_v2`, `noise_floor_signed`,
`real_prior_recovery`, `rebuild_shapley_*`, `discriminate_counterexamples`,
`recompute_discrimination_old_encoding` and the two root-level scripts were added
to this checkout to close the result↔script gap; the rest were already here.

### Primary endpoint and meta-analysis

| File | Holds | Generator | Generated |
|---|---|---|---|
| `robustness_validation_5seeds.csv` | 60-cell per-method ΔECE with paired BCa CIs (the primary-endpoint table). ⚠ **read [`_EIGHT_METHOD_SEMANTICS_NOTICE.md`](_EIGHT_METHOD_SEMANTICS_NOTICE.md) before quoting any non-`ts` row** — the delivered non-TS rows carry the historical shared-correctness semantics; the per-branch recheck artifact is `robustness_val_8method_perbranch_recheck.csv` | `generate_robustness_report_v2.py` (repo root) | 2026-10-08 |
| `meta_analytic_pooled.csv` | fixed-effect / DerSimonian–Laird pooled rows and Q statistics | `regenerate_stats_60exp.py` (repo root) | 2026-10-10 (post-retrain regeneration wave) |
| `bh_fdr_correction.csv` | BH-60 and Bonferroni multiple-testing control | `regenerate_stats_60exp.py` (repo root) | 2026-09-06 ⚠ pre-retrain era snapshot (51/60-generation readout), retained for provenance; the current confirmatory counts quoted by the article (BH-12 = 7/12, Bonferroni-12 = 6/12) come from `robustness_validation_5seeds.csv` via `regenerate_stats_60exp.py` and are re-derived in `verify_release_results.py` — do not quote this file's counts |
| `bootstrap_diagnostics.csv` | per-method bootstrap bookkeeping | `p2_optional_fixes.py` | 2026-10-08 |
| `robustness_val_8method_perbranch_recheck.csv` | 8-method OOD ΔECE recomputed from the cached probability arrays with per-branch correctness (TS gate: 60/60 exact; EM $-0.0040 \to -0.0378$ corrected; see the ledger) | `recheck_method_semantics.py` | 2026-10-11 |

### Deployment safety and the L2 grid

| File | Holds | Generator | Generated |
|---|---|---|---|
| `deployment_metrics.csv` | the strict deployment-safety aggregate: `method,ts,780,8,368,18,0.010256` (n_total / n_safe / n_beneficial / n_calibrated, strict: ΔECE ≤ −0.01 AND calibrated ECE ≤ 0.05) + per-architecture strict rows | redeployed by `regenerate_deployment_metrics.py` (2026-10-10 regeneration wave) | 2026-10-10 |
| `deployment_holdout_recompute.csv` | holdout threshold / Youden recompute | `deployment_holdout_recompute.py` | 2026-10-09 ⚠ these rows come from the checkpoint method pool (`load_l2_data()` over `checkpoints/…/l2_shift_results.json`), **not** from the 780-cell grid the article quotes alongside it; the article's `tab:deploy_sens` sens/spec rows carry the same pool lineage and were re-stated in the paper's post-2026-10-10 pass (recompute on the delivered 780-grid detail CSV is queued) |
| `l2_shift_full_390cells.csv` | 390-cell (pair, seed, shift) safety grid | `run_e1a_l2_shift_full.py` | 2026-10-09 |
| `l2_shift_full_780cells_detail.csv` | per-architecture detail behind it | `run_e1a_l2_shift_full.py` | 2026-10-09 |
| `l2_shift_full_summary.json` | counters (`n_safe_cells` = 348; 348/390 = 89.2% pass with ≥1 architecture, 222/390 = 56.9% with both) | `run_e1a_l2_shift_full.py` | 2026-10-09 |
| `deployment_780grid_recompute.csv` | the article's `tab:deploy_sens` sens/spec/J rows recomputed on the delivered 780-cell grid (P=368/N=412, matching `deployment_metrics.csv` exactly) + leave-shift-type-out rows + the `tab:trivial` lookup-table strategy row (n_routed=476, mean −0.0116) | `recompute_deployment_780grid.py` | 2026-10-11 |

### Decomposition estimator

| File | Holds | Generator | Generated |
|---|---|---|---|
| `decomposition_validation_n20000.csv` | n = 20,000 baseline validation | `validate_decomposition.py` (default `--n`) | 2026-09-01 |
| `decomposition_validation_n500_seeds4.csv` | n = 500, 4 seeds | `validate_decomposition.py --n 500 --seeds 4` | 2026-09-01 — full transparency: per-seed single-seed passes are 21/22/21/22 (the article quotes the seed-42 readout, 21/27); cells passing all four seeds = **12/27**, majority (≥3 of 4) = **22/27** |
| `decomposition_validation.csv` | ⚠ **legacy file name**: byte-identical to the archived `decomposition_validation_n500_20260829.bak.csv`, i.e. the **n = 500 single-seed** run, *not* the n = 20,000 table | `validate_decomposition.py --n 500` (written under this name by an earlier invocation) | 2026-08-31 |
| `decomposition_error_map_n20000.png` | error-map figure for the n = 20,000 run | `validate_decomposition.py` | 2026-09-01 |

### Discrimination, Brier/DCR/NCV, temperature

| File | Holds | Generator | Generated |
|---|---|---|---|
| `discrimination_metrics_60exp.csv` | per-direction AUROC/AUPRC/F1/… over **64 cells** (the 60-cell grid plus 4 mamba cells) × {cal, test} × {raw, ts, binned, threshold}; full re-run under the corrected labels. Its six direction means span 0.7313–0.8425, not the article's 0.735–0.843, because it adds two mamba cells to the Chapman directions — quote the sidecar below for the article's range | `run_e2_ablation_discrimination.py` | 2026-09-27 |
| `discrimination_metrics_60exp.OLD_ENCODING.csv` | **corrected** recompute under the original label encoding: 62 cells × {cal, test} × {raw, ts} — **the table the article cites** (per-direction means 0.7353–0.8425) | `recompute_discrimination_old_encoding.py` | 2026-09-17 |
| `c1_brier_reliability.csv`, `c1_brier_reliability_summary.csv` | E3 Brier reliability (full scale) | `run_e3_brier_dcr_ncv.py` | 2026-09-17 |
| `c1_dcr_ncv_multiclass.csv`, `c1_dcr_ncv_summary.csv` | E3 DCR / NCV (full scale) — **multi-block files** | `run_e3_brier_dcr_ncv.py` | 2026-09-17 |
| `temperature_distribution_analysis.csv` | fitted temperatures per cell | `run_e4_temperature_analysis.py` | 2026-09-28 |
| `temperature_shift_sensitivity.csv` | temperature-shift sensitivity | `run_e4_temperature_analysis.py` | 2026-09-28 |
| `binned_temperature_exploratory.csv` | exploratory binned temperatures | `run_e4_temperature_analysis.py` | 2026-09-28 |

### Ablation, counter-examples, mechanism

| File | Holds | Generator | Generated |
|---|---|---|---|
| `ablation_ts_components.csv` | four-stage TS-component ablation, 64 raw cells under the corrected labels (raw smooth-ECE mean 0.2127, range 0.036–0.357) | `run_e2_ablation_discrimination.py` | 2026-09-27 |
| `ablation_ts_components.OLD_ENCODING.csv` | **corrected** ablation under the original label encoding, 62 cells (raw smooth-ECE mean 0.2114, range 0.036–0.357) — the table the article quotes for the raw-ECE range | `recompute_ablation_old_encoding.py` | 2026-09-17 |
| `counterexample_discrimination.csv` / `.json` | the ten counter-examples | `discriminate_counterexamples.py` | 2026-09-27 |
| `rebuild_shapley_crossfit.csv` / `.json` | cross-fit Shapley rebuild | `rebuild_shapley_crossfit.py` | 2026-09-18 |
| `rebuild_shapley_slopeT.csv` / `.json` | slope/intercept-T Shapley rebuild | `rebuild_shapley_slopeT.py` | 2026-09-27 |
| `noise_floor_curve.csv` | signed noise-floor curve | `noise_floor_signed.py` | 2026-09-18 |
| `c3_crossfit_results.csv` | cross-fit diagnostics | `p2_optional_fixes.py` | 2026-09-18 |
| `c4_resnet1d_8method.csv` | ResNet1D 8-method run — **needs `comment="#"`** | `p2_optional_fixes.py` | 2026-09-18 |

### Predictability, priors, dose-response

| File | Holds | Generator | Generated |
|---|---|---|---|
| `predictability_3arch.csv` | label-free predictability experiment, corrected — **multi-block file** | `step2_predictability.py` | 2026-09-27 |
| `predictability_corrected_v2.csv` | T-based directional discrimination (v2) — needs `comment="#"` | `predictability_corrected_v2.py` | 2026-09-27 |
| `real_prior_recovery.csv` | prior-recovery check on real checkpoints | `real_prior_recovery.py` | 2026-09-18 |
| `real_prior_recovery_summary.json` | ⚠ **generator reconstructed on 2026-10-12** (`scripts/real_prior_recovery_summary.py`): route-A diff vs the archived 2026-09-27 copy = exactly the cross-epoch deltas (ledger B1); the pair-cluster CI fields are intentionally `null` from the CSV alone (needs patient clusters) — archived predecessor at `archive/no-generator/` | `real_prior_recovery_summary.py` | 2026-10-12 |
| `samplelevel_ts_60cells.csv` | **sample-level (adaptive) TS baseline**, Robey et al. AISTATS 2021 (`scripts/samplelevel_ts.py`): HW head T(x) fitted on source-cal and applied to the target, per-branch correctness convention. Headline: mean +0.0190 (47/60 positive), beats global TS on 41/60 cells (pearson r 0.646), deployment bar again 0/60 strict criteria met. | `samplelevel_ts.py` | 2026-10-13 |
| `s2_dose_response.csv`, `s2_dose_response_summary.json` | small-sample recalibration dose-response (protocol §S2): 5 budgets × 5 methods × 60 cells × 20 repeats | `run_s2_small_sample.py` | 2026-09-27 |

### Notices {#notices}

| Notice | Declares unusable / records |
|---|---|
| `_ABLATION_TS_COMPONENTS_CONTAMINATION_NOTICE.md` | label-encoding mismatch in the 2026-09-10 `ablation_ts_components.csv` (40 CPSC cells; raw ECE mean 0.273 → 0.211 corrected). The shipped table has since been regenerated (2026-09-27) and is corrected |
| `_TEMPERATURE_CONTAMINATION_NOTICE.md` | fitted-temperature columns of the temperature family |
| `_DISCRIMINATION_CONTAMINATION_NOTICE.md` | the 2026-09-10 `discrimination_metrics_60exp.csv`, computed with mismatched labels (per-direction means 0.629–0.792 → 0.735–0.843 corrected; the audited cell 0.642 → 0.861). The shipped table has since been regenerated (2026-09-27) |
| `_L2_SHIFT_CONTAMINATION_NOTICE.md` | pre-correction L2 grid and its downstream `predictability_3arch.csv` |
| `_C1_DCR_NCV_SMOKE_NOTICE.md` | E3 family produced at n = 20 smoke scale. The shipped tables have since been regenerated (2026-09-17, full scale) and are what `results/README.md` documents above; the notice's open item is now the **paper's** five in-text NCV/DCR figures, which still cite the discarded run |
| `_LOCO_CONTAMINATION_NOTICE.md` | `deployment_loco_validation.*` — withheld above |
| `_SUPPLEMENTARY_WINDOW_NOTICE.md` | supplementary package assembled inside the contamination window |
| `_PROBS_CACHE_LABEL_REPAIR_NOTICE_2026-09-18.md` | `e2_probs_cache` label repair and the two retrained cells |

## Parsing notes

Plain `pd.read_csv(path)` works for 23 of the 32 CSVs. For the rest:

- **Leading `#` comment lines** (`pd.read_csv(path, comment="#")`):
  `c1_brier_reliability.csv`, `c1_brier_reliability_summary.csv`,
  `c4_resnet1d_8method.csv`, `discrimination_metrics_60exp.OLD_ENCODING.csv`,
  `predictability_corrected_v2.csv`.
- **Multi-block files** — several stacked tables with different column counts in
  one file, so even `comment="#"` fails (`Expected N fields, saw M`). Split on the
  section markers first: `c1_dcr_ncv_multiclass.csv`, `c1_dcr_ncv_summary.csv`,
  `deployment_metrics.csv`, `predictability_3arch.csv`.

## 2026-10-10 additions (post-repair wave)

Three artifacts beyond the inventory counts above (54 files total: 33 CSVs,
9 *NOTICE* files incl. the 2026-10-10 val-leak notice, and 12 other files):

- \e3_patient_bca_cells.csv\ / \e3_patient_bca_summary.json\ /
  \e3_patient_bca_pooled_draws.npz\ — the **registered-unit NCV/DCR
  deliverable**: patient-level cluster bootstrap, B = 10,000, BCa per cell with
  leave-one-patient-out acceleration; equal-cell-weight pooled draws archived.
  Producer \scripts/e3_patient_bca.py\; per-cell recomputed NCV/DCR are
  integrity-gate-matched to \c1_dcr_ncv_multiclass.csv\ (60/60 exact at 1e-9).
  Pooled OOD NCV $+0.000238$, BCa CI $[+0.000125, +0.000353]$; DCR
  $+0.000526$, $[+0.000280, +0.000775]$; ID side covers zero. This is the
  registered unit closed out after the 2026-10-10 review exchange (previously
  the paper reported proxy units only).
