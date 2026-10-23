# Calibration Transferability in Cross-Corpus ECG Deployment: A 60-Experiment Boundary Validation

Official code and data-split release for the accompanying article.

> **⚠️ If you cloned before 2026-10-11 or are on the v1.0.0 tag:** the scripts
> carried in earlier snapshots still implement the pre-fix PTB-XL split
> semantics (the 2026-10-05 val-leak repair ships from 2026-10-11 onward),
> and the v1.0.0 checkpoint asset contains two byte-duplicate direction
> weights. **Re-clone or checkout
> [`v1.1.0`](https://github.com/Toni-cs/ecg-calibration-transferability/releases/tag/v1.1.0)**
> (tag commit `46dadf1`: leak-free code line, 60 unique-hash grid weights,
> gate-verified against the delivered result tables). Details and the fix
> history: `docs/CORRECTIONS_LEDGER_2026-10-11.md`.

Given a calibration fix with a benefit in-distribution (ID), this study measures how much of that benefit survives out-of-distribution (OOD) transfer across three public ECG corpora, decomposes the decay into three interpretable components (slope / intercept / prevalence), and derives a deployment-safety criterion for recalibration before transfer.

## Contents

- [Requirements](#requirements)
- [Dataset](#dataset)
- [Reproducing the results](#reproducing-the-results)
- [Post-publication repair: PTB-XL early-stopping val leak](#post-publication-repair-ptb-xl-early-stopping-val-leak)
- [Preregistration record](#preregistration-record)
- [Data integrity notices](#data-integrity-notices)
- [Data splits](#data-splits)
- [Paper-to-artifact map](#paper-to-artifact-map)
- [Results](#results)
- [License](#license)
- [Citation](#citation)
- [Contact](#contact)

## Requirements

- Python ≥ 3.10, PyTorch ≥ 2.4 (CUDA optional; CPU suffices for evaluation-only reproduction)
- All Python dependencies: `pip install -r requirements.txt`

## Dataset

Three public databases, unified to five superclasses (`NORM / MI / STTC / CD / HYP`; CPSC uses a four-class subspace `{NORM, CD, STTC, MI}` because HYP has n = 11):

| Database | Records (after preprocessing) | Source |
|---|---|---|
| PTB-XL | 21,522 | [PhysioNet v1.0.3](https://physionet.org/content/ptb-xl/1.0.3/) |
| Chapman–Shaoxing (mixed cohort) | 20,243 (48.6% Chapman–Shaoxing + 51.4% Ningbo) | [PhysioNet ecg-arrhythmia](https://physionet.org/content/ecg-arrhythmia/1.0.0/); composition audit: [`reports/MIXING_AUDIT_DATA_LAYER_2026-10-22.md`](reports/MIXING_AUDIT_DATA_LAYER_2026-10-22.md) |
| CPSC2018 | 10,285 | [PhysioNet/CinC 2020](https://physionet.org/content/challenge-2018/) |

The CPSC corpus is **CPSC2018 only**, i.e. the union of the *CPSC Database*
(6,877 records; the public CPSC2018 training set) and the *CPSC-Extra Database*
(3,453 records; the CPSC2018 recordings not used by the Challenge), both
distributed via PhysioNet/CinC 2020. It does **not** include CPSC2019, which was
a QRS/heart-rate *detection* task with no diagnostic labels. 10,297 records are
read after preprocessing; 10,296 map to a superclass, and 11 of those are HYP,
leaving 10,285 records in the four-class subspace `{NORM, CD, STTC, MI}` that the
CPSC experiments use. Note that CPSC2018's own official taxonomy is nine disease
classes (Normal, AF, I-AVB, LBBB, RBBB, PAC, PVC, STD, STE) with no superclass
grouping and no MI; the superclass system used here is PTB-XL's, applied as a
cross-corpus harmonization choice, and the MI class is populated entirely by
CPSC-Extra's SNOMED annotations.

Raw waveforms are **not redistributed** in this repository (database licenses, size). Download the databases from the sources above, then build the unified NPZ + metadata:

```bash
python scripts/preprocess_ptbxl.py   --source-root data/ptbxl   --output-root data/ptbxl_processed
python scripts/preprocess_chapman.py --source-root data/chapman --output-root data/chapman_processed_v2

# CPSC uses two roots because argparse names them that way (the flag name is legacy):
#   --cpsc2018-root must contain Training_WFDB/   (CPSC Database, 6,877 records)
#   --cpsc2019-root must contain Training_2/      (CPSC-Extra,     3,453 records)
# Both usually point at the same extraction directory. No CPSC2019 data is read.
python scripts/preprocess_cpsc.py \
    --cpsc2018-root data/cpsc --cpsc2019-root data/cpsc \
    --output-root data/cpsc_processed
```

Each preprocessor writes `metadata_single_label.csv`, `preprocess_summary.json` and
`data/*.npy` under its `--output-root`; that directory is what you pass as
`--data_dir` (training) / `--source-dir` / `--target-dir` (evaluation) below.

## Reproducing the results

```bash
# 0. Quick self-check: re-derive the README's headline aggregates (primary endpoint,
#    cluster-robust CI, pooled estimates, deployment table, dose response, L2 grid
#    counts, patient-level BCa unit, raw-ECE range, bootstrap widths) from results/
#    and assert that the 4 withheld contaminated artifacts stay absent. It is a
#    table-level integrity check against results/ -- NOT a re-run of the estimators;
#    generation provenance is documented in the paper-to-artifact map below.
#    (seconds; needs no dataset, no checkpoints, no GPU; exit 1 on any mismatch)
python scripts/verify_release_results.py
# current status: 12 checks PASS, exit 0

# 1. Install and preprocess (see above)

# 2. Regenerate the exact as-used split indices (byte-identical to splits/*.csv;
#    verified 2026-10-11: seed 42 regenerates all 5 variants byte-identical, and
#    --validate 42 passes 20/20 against the real builders)
python scripts/export_splits.py
python scripts/export_splits.py --validate 42   # cross-check against the dataset builders

# 3. Train + main endpoint for one grid cell (60 cells: 6 corpus pairs x 2 archs x 5 seeds)
python scripts/train.py --dataset ptbxl --data_dir data/ptbxl_processed \
    --arch inceptiontime --seed 42
# NOTE: --arch defaults to `mamba`, which is NOT part of the published 60-cell grid.
#       The grid is {inceptiontime, resnet1d}; pass --arch explicitly.

# 4. Cross-corpus transfer / recalibration evaluation
python scripts/eval_transfer.py \
    --source ptbxl --source-dir data/ptbxl_processed \
    --target chapman --target-dir data/chapman_processed_v2 \
    --arch inceptiontime --methods ts platt --seeds 42 \
    --load-model
# --load-model evaluates the released checkpoint at
#   checkpoints/transfer/ptbxl_chapman/inceptiontime/seed42/best_model.pt
# Without it, eval_transfer.py TRAINS from scratch (50 epochs) and only then evaluates.

# 5. Standalone synthetic validation of the decomposition estimator (no data needed)
python scripts/validate_decomposition.py --boot 500
# ~8 min on CPU; rewrites results/decomposition_validation_n20000.csv and
# results/decomposition_error_map_n20000.png (both are byte-identical to the
# committed copies, so this is a safe self-check).
# Exit codes are meaningful, not just 0/1: 0 = PASS, 1 = a preregistered-n cell
# failed, 2 = informative mode (n < 20000, e.g. --n 500), 3 = all cells
# entangled, 5 = entanglement demo failed.
# A faster synthetic run (seconds) that writes outside results/ — the output
# directory is created if absent, and tmp_*/ is gitignored:
#   python scripts/validate_decomposition.py --n 500 --boot 0 --output tmp_decomp

# 6. Unit tests (no data, no GPU, ~13 s; 5 mapping-encoding tests + 6 builder/export
#    lockstep tests pinning the val-holdout fix)
python -m pytest -q
```

Licensed checkpoint assets (62 `best_model.pt` + SHA-256 manifest) are provided
as assets of [release v1.0.0](https://github.com/Toni-cs/ecg-calibration-transferability/releases/tag/v1.0.0).
Unpack them under `checkpoints/` so the paths used above resolve, then verify:

```bash
unzip ecg-release_assets_transfer_checkpoints.zip -d checkpoints   # -> checkpoints/transfer/...
cd checkpoints && sha256sum -c CHECKSUMS.sha256                   # expect 62/62 OK
```

> **Which snapshot to download.** For a runnable tree, clone `main` (or a tag that
> includes the `src/data/` fix). The `v1.0.0` **source archive** was cut *before*
> `src/data/` and `tests/` were committed, so 10 of its 22 scripts die on
> `from src.data ...` (ImportError); `README.md` at that tag still describes the
> full layout. The release's **checkpoint assets** are unaffected by this and are
> the ones unpacked above.

> **Weight caveat.** The v1.0.0 assets are the **pre-repair** snapshot: they
> reproduce the 40 non-PTB-XL-source cell tables but **not** the 20 retrained
> PTB-XL-source cells, and two InceptionTime weight files inside them are
> byte-duplicates across directions (`transfer/cpsc_chapman/inceptiontime/seed42`
> == `transfer/cpsc_ptbxl/inceptiontime/seed42`, same for `seed43`) predating the
> 2026-09-17 checkpoint-independence retrain (see
> [`reports/CHECKPOINT_INDEPENDENCE_AUDIT_2026-09-17.md`](reports/CHECKPOINT_INDEPENDENCE_AUDIT_2026-09-17.md)).
> **A post-repair asset resolves this**:
> `ecg-release_assets_transfer_checkpoints_post_repair_2026-10-11.zip`
> (GitHub release [**v1.1.0**](https://github.com/Toni-cs/ecg-calibration-transferability/releases/tag/v1.1.0),
> published 2026-10-11) ships 60 unique-hash grid
> weights including all 20 post-val-leak retrained cells, gate-verified cell by
> cell against `results/robustness_validation_5seeds.csv` (methods.ts ood/id
> ΔECE, max diff < 5·10⁻⁶) before packing; manifest 62/62 verified (60 grid +
> 2 partial-mamba toys). See the [post-publication repair](#post-publication-repair-ptb-xl-early-stopping-val-leak) section
> and `docs/CORRECTIONS_LEDGER_2026-10-11.md` for the fix history.

## Post-publication repair: PTB-XL early-stopping val leak

**Incident.** In the originally shipped PTB-XL split semantics, every
carved-out `val` patient's records were still fed to the training loader
(`in_train_loader=yes` on `val` rows in `splits/*.csv`). The early-stopping
monitor therefore read from the training data, which invalidates model
*selection* within those cells (it does **not** contaminate the reported
test/cal evaluation: fold-9 `cal` and fold-10 `test` patients were always
asserted disjoint from folds 1–8). This is a protocol deviation, not a
label breach.

**Fix (2026-10-05 lab tree; shipped to this repository's scripts 2026-10-11).**
`scripts/train.py` excludes all `val` patients from the training loader
(`np.setdiff1d` record filter plus a disjointness assertion that is re-derived
from the final loader positions, not from the pre-carve patient lists);
`scripts/export_splits.py` mirrors the logic line-by-line, and `--validate 42`
passes 20/20 against the dataset builders on real preprocessed data
(re-verified 2026-10-11). A regression test (`tests/test_ptbxl_val_holdout.py`)
pins the semantics; the release test suite passes (11 tests). Honest
provenance note: the 2026-10-10 regeneration wave updated `splits/`,
`results/` and this README but **missed the two scripts** (their previous
commits predate the fix: `train.py` 2026-09-16, `export_splits.py`
2026-09-13), so the scripts carried here between 2026-10-07 and 2026-10-11
were the leak-era versions; they have now been synchronized and the fix is
verified end-to-end. Across the ten PTB-XL-family split exports the **only**
data changes remain the `val` rows: 21,397 records switched from
`in_train_loader=yes` to `no` (committed 2026-10-10).

**Retrain.** The affected cells are the PTB-XL-source cells — 2 directed pairs
× 2 architectures × 5 seeds = **20 of 60** — retrained under the fixed splits.
The remaining 40 cells (no PTB-XL training dependence) are unchanged. All
sixteen downstream result families were regenerated on the post-retrain
checkpoints, and the manuscript's numbers were updated accordingly — the
numbers below are those regenerated values; see
[`results/_VAL_LEAK_RETRAIN_NOTICE_2026-10-10.md`](results/_VAL_LEAK_RETRAIN_NOTICE_2026-10-10.md)
and `scripts/verify_release_results.py` for the mechanical self-check.

**Impact on the primary endpoint.** Positive OOD benefits 50/60 → **45/60
(75.0%)**; mean D_ECE_OOD +0.0154 → **+0.0093**; mean ID benefit +0.0082 →
**+0.0034** (the repair removes ~58% of the ID residual — the val-early-stop
had been exploiting exactly that shortcut); the pre-registered ID-boundary
branch still triggers (30/60 = 50.0% cells have CI containing zero).

## Preregistration record

The preregistered protocol and its registered amendments are publicly archived on
OSF as an immutable record with per-file SHA-256 checksums:
[https://doi.org/10.17605/OSF.IO/53H64](https://doi.org/10.17605/OSF.IO/53H64)
(project `53h64`; registration `wjz3y`, registered 2026-09-14).

The protocol and amendments A1, A2, A3, A4 also ship in this
repository under [`docs/`](docs/), **byte-identical to the deposited
files for A1 and A2** — check with

```bash
sha256sum docs/EXPERIMENT_PROTOCOL.md
# 0e8afa923986aba3f5030133c59b8a87b475c3551b819b0137ab9da66eeb9498
# (the SHA-256 the OSF API reports for 02_PROTOCOL_ZH_original.md)
```

A3 and A4 ship here and are **in the project deposit** (53h64 Files,
uploaded 2026-10-11 with per-file SHA-256 verified bit-identical to the
repository copies); the frozen registration WJZ3Y is intentionally left
at v1 (frozen-snapshot doctrine: the registration is the dated record of
its date, amendments live in the project deposit); see
[`docs/PREREGISTRATION_ALIGNMENT.md`](docs/PREREGISTRATION_ALIGNMENT.md)
and [`docs/OSF_ADDENDUM_2026-10-12.md`](docs/OSF_ADDENDUM_2026-10-12.md).

They are duplicated deliberately rather than left to the OSF record alone: the
manuscript cites two of these files by path, and eleven files already committed to
this repository referenced `docs/…` before the directory existed.

Two documents are worth reading first:

- [`docs/README.md`](docs/README.md) — what each archived file is, and how to verify it.
- [`docs/PREREGISTRATION_ALIGNMENT.md`](docs/PREREGISTRATION_ALIGNMENT.md) — what the
  OSF registration, the protocol and the manuscript each say, and the places where
  they still disagree (checked against the public OSF API on 2026-10-05).

[`reports/`](reports/) holds the audit reports cited by the integrity notices below.

## Data integrity notices

`results/` is the **regenerated, post-repair** set: all 40 co-named result
tables are byte-identical (SHA-256, verified 2026-10-11) to the article's
supplementary result tables after the same-day package refresh (29 stale
pre-retrain tables in the package were replaced and the manifest re-signed;
three package-only legacy archive tables are kept and named explicitly), and
both the contamination-era and the pre-repair versions that earlier snapshots
of this repository shipped have been replaced. The correction history is kept as
notices inside [`results/`](results/) — read them before quoting a number:

| Notice | What it records |
|---|---|
| [`_VAL_LEAK_RETRAIN_NOTICE_2026-10-10.md`](results/_VAL_LEAK_RETRAIN_NOTICE_2026-10-10.md) | the PTB-XL early-stopping val leak, the split-semantics fix, the 20-cell retrain, and the 50/60 → 45/60 primary-endpoint shift (the latest wave — all tables below are post-repair) |
| [`_ABLATION_TS_COMPONENTS_CONTAMINATION_NOTICE.md`](results/_ABLATION_TS_COMPONENTS_CONTAMINATION_NOTICE.md) | the 2026-09-10 `ablation_ts_components.csv` (40 CPSC cells; raw ECE mean 0.273, range to 0.469); the corrected table is `ablation_ts_components.OLD_ENCODING.csv` (0.211, to 0.357); the current table is the post-retrain 2026-10 regeneration (0.203, 0.036–0.357) |
| [`_TEMPERATURE_CONTAMINATION_NOTICE.md`](results/_TEMPERATURE_CONTAMINATION_NOTICE.md) | the fitted-temperature columns of the three temperature-family tables |
| [`_DISCRIMINATION_CONTAMINATION_NOTICE.md`](results/_DISCRIMINATION_CONTAMINATION_NOTICE.md) | the 2026-09-10 `discrimination_metrics_60exp.csv`, whose AUROCs were computed with mismatched labels (per-direction means 0.629–0.792 → **0.735–0.843** corrected); the corrected table is `discrimination_metrics_60exp.OLD_ENCODING.csv` |
| [`_L2_SHIFT_CONTAMINATION_NOTICE.md`](results/_L2_SHIFT_CONTAMINATION_NOTICE.md) | the pre-correction L2 shift grid and its downstream `predictability_3arch.csv` |
| [`_C1_DCR_NCV_SMOKE_NOTICE.md`](results/_C1_DCR_NCV_SMOKE_NOTICE.md) | the E3 family produced at n = 20 smoke scale; rerun at full scale |
| [`_LOCO_CONTAMINATION_NOTICE.md`](results/_LOCO_CONTAMINATION_NOTICE.md) | `deployment_loco_validation.*` — **withheld from this repository**, the only archived copy is contaminated |
| [`_SUPPLEMENTARY_WINDOW_NOTICE.md`](results/_SUPPLEMENTARY_WINDOW_NOTICE.md) | the article supplementary package assembled inside the contamination window |
| [`_PROBS_CACHE_LABEL_REPAIR_NOTICE_2026-09-18.md`](results/_PROBS_CACHE_LABEL_REPAIR_NOTICE_2026-09-18.md) | `e2_probs_cache` label repair and the two retrained cells (see the weight caveat above) |

> **What the `.OLD_ENCODING` suffix means.** It names the *label encoding* the
> recomputation used, not the age of the numbers. The tables flagged above were
> computed from checkpoints trained under the original `SUBSPACE_CPSC` ordering,
> and the 2026-09-09 change to that ordering is what later broke agreement
> between cached `probs` and `labels`; recomputing under the original encoding is
> therefore the **correction**, not the obsolete run. Both `.OLD_ENCODING.csv`
> files here hold corrected values. Note on attribution: the OLD_ENCODING
> discrimination table's own per-direction AUROC range is (0.735–0.843)
> (62 cells incl. 2 mamba toys), but the **manuscript-cited table is the
> unmarked `discrimination_metrics_60exp.csv`**, whose test/ts 60-grid
> direction means span 0.7355–0.8498 — the article's 0.735–0.850
> (re-verified 2026-10-17).

Residual status notes:

- `results/meta_analytic_pooled.csv` was regenerated on 2026-10-10 from the
  post-retrain cells: `simple_mean` holds the per-stratum cell means
  (0.009769 / 0.008909 / 0.009339), `re_pooled_effect` holds the
  DerSimonian–Laird pooling recomputed from per-cell BCa standard errors
  (0.009607 / 0.008862 / 0.009123), and `I2` the between-cell heterogeneity
  (≥ 99.97% for every stratum — the honest-interval note in
  [Results](#results) is derived from these).
- `results/c1_brier_reliability*.csv`, `results/c4_resnet1d_8method.csv`,
  `results/discrimination_metrics_60exp.OLD_ENCODING.csv` and
  `results/predictability_corrected_v2.csv` carry leading `#` comment headers:
  load them with `pd.read_csv(path, comment="#")`.
  Three further files are **multi-block** (several stacked tables with
  different column counts, so `comment="#"` still fails):
  `results/c1_dcr_ncv_*.csv`, `results/predictability_3arch.csv` — split on
  the `#`/section markers first.

The per-file inventory of `results/` (what each table holds, which script writes
it, when it was generated, and which files were deliberately withheld) is in
[`results/README.md`](results/README.md).

## Data splits

[`splits/`](splits/) contains the exact patient-level partition indices used by all 60 experiments: 25 CSVs = 5 dataset variants (`ptbxl`, `ptbxl_sub4`, `chapman`, `chapman_sub4`, `cpsc`) × seeds 42–46, with columns `record_id`, `patient_id`, `split` (`train/val/cal/test`), `in_train_loader` (`yes/no`).

Two documented properties:

- **PTB-XL holdout semantics (post-repair).** The carved-out `val` patients'
  records are **excluded** from the training loader; all CSVs carry
  `in_train_loader=no` on `val` rows, and the trainer asserts at build time
  that `val`/`cal`/`test` patients are disjoint from the fold-1–8 training
  patients. For Chapman/CPSC, `val` patients were always excluded. Earlier
  snapshots of this repository shipped PTB-XL exports in which `val` records
  carried `in_train_loader=yes` (early-stopping on training data) — see the
  [post-publication repair](#post-publication-repair-ptb-xl-early-stopping-val-leak)
  section.
- **Builder cross-validation.** `scripts/export_splits.py` mirrors the split logic of `scripts/train.py` line-by-line and was verified against the real dataset builders: 20/20 split×builder checks MATCH (5 variants × train/val/cal/test, seed 42).

## Paper-to-artifact map

Each row names the script that *writes* the artifact (verified by locating the
`to_csv` / `open(..., "w")` target, not by file-name similarity). For the full
per-file inventory of `results/` — including files whose generator is not in any
branch — see [`results/README.md`](results/README.md).

**Script tiers.** `scripts/` deliberately holds two layers. The pipeline layer
(train / eval / export_splits / preprocess / run_e* / step* / regenerate_* /
verify_release) is what the rows below name. The audit-provenance layer
(`probe_*`, `adjudicate_*`, `diagnose_*`, `recompute_*_old_encoding`,
`retrain_cpsc_ptbxl_it_seed42_43`, `verify_*_encoding`, …) re-derives or
cross-checks numbers cited by the notices in [`results/`](results/) and the
reports in [`reports/`](reports/) — it is kept verbatim so every archived claim
stays re-runnable; it is *not* part of the reproduction pipeline above.

| Paper element | Script | Artifact |
|---|---|---|
| Data splits (all experiments) | `scripts/export_splits.py` | `splits/*.csv` |
| Primary endpoint ΔECE_OOD, paired BCa CIs | `generate_robustness_report_v2.py` (repo root) | `results/robustness_validation_5seeds.csv` |
| Pooled estimates (simple means + Dersimonian–Laird) | regenerated 2026-10-10 from `robustness_validation_5seeds.csv` (method documented in `_VAL_LEAK_RETRAIN_NOTICE_2026-10-10.md`) | `results/meta_analytic_pooled.csv` |
| Multiple-testing control | `regenerate_stats_60exp.py` (repo root) | `results/bh_fdr_correction.csv` |
| Bootstrap bookkeeping | `scripts/p2_optional_fixes.py` | `results/bootstrap_diagnostics.csv` |
| Discrimination (per-direction AUROC/AUPRC) | `scripts/run_e2_ablation_discrimination.py`; original-encoding recompute: `scripts/recompute_discrimination_old_encoding.py` | `results/discrimination_metrics_60exp.csv` (64 cells × 4 variants; **the manuscript-cited table**) and `results/discrimination_metrics_60exp.OLD_ENCODING.csv` (62 cells × {raw, ts}; release-lineage recompute only) |
| Recalibration deployment safety (780-eval detail grid, strict caliber) | original 2026-09-05 snapshot: `scripts/step3_deployment.py` (not re-derivable); regenerated 2026-10-10 from the shipped detail grid by `scripts/regenerate_deployment_metrics.py` | `results/deployment_metrics.csv` |
| Holdout / Youden threshold recompute | `scripts/deployment_holdout_recompute.py` | `results/deployment_holdout_recompute.csv` |
| L2 shift sensitivity grid | `scripts/run_e1a_l2_shift_full.py` | `results/l2_shift_full_390cells.csv`, `results/l2_shift_full_780cells_detail.csv`, `results/l2_shift_full_summary.json` |
| Three-component decomposition | `scripts/validate_decomposition.py` (wraps `src/utils/decomposition.py`) | `results/decomposition_validation_n20000.csv`, `results/decomposition_error_map_n20000.png` |
| TS component ablation | `scripts/run_e2_ablation_discrimination.py`; original-encoding recompute: `scripts/recompute_ablation_old_encoding.py` | `results/ablation_ts_components.csv` and `results/ablation_ts_components.OLD_ENCODING.csv` (the table the [Results](#results) section quotes for the raw-ECE range) |
| E3 Brier / DCR / NCV | `scripts/run_e3_brier_dcr_ncv.py` | `results/c1_brier_reliability*.csv`, `results/c1_dcr_ncv_*.csv` |
| Fitted temperatures and shift sensitivity | `scripts/run_e4_temperature_analysis.py` | `results/temperature_distribution_analysis.csv`, `results/temperature_shift_sensitivity.csv` |
| Label-free predictability experiment | `scripts/step2_predictability.py` | `results/predictability_3arch.csv` |
| T-based directional discrimination (v2) | `scripts/predictability_corrected_v2.py` | `results/predictability_corrected_v2.csv` (pre-retrain era snapshot, mtime 2026-09-27; its `const_positive_baseline = 0.8333` reflects the pre-retrain 50/60 grid — do not quote its counts; regenerate on post-retrain cells before citing any number from it) |
| Small-sample dose-response (protocol §S2) | `scripts/run_s2_small_sample.py` | `results/s2_dose_response.csv`, `results/s2_dose_response_summary.json` |
| Counter-example discrimination | `scripts/discriminate_counterexamples.py` | `results/counterexample_discrimination.csv`, `.json` |
| Shapley decomposition rebuilds | `scripts/rebuild_shapley_crossfit.py`, `scripts/rebuild_shapley_slopeT.py` | `results/rebuild_shapley_*.csv/.json` |
| Registered-unit NCV/DCR (patient-level BCa, B=10,000) | `scripts/e3_patient_bca.py` | `results/e3_patient_bca_cells.csv`, `results/e3_patient_bca_summary.json`, `results/e3_patient_bca_pooled_draws.npz` |
| 8-method per-branch semantics recheck | `scripts/recheck_method_semantics.py` | `results/robustness_val_8method_perbranch_recheck.csv` |
| Deployment sens/spec + lookup-table (780-cell grid) | `scripts/recompute_deployment_780grid.py` | `results/deployment_780grid_recompute.csv` |
| README self-check (re-derives the README's headline aggregates; a table-level integrity check, not an estimator re-run) | `scripts/verify_release_results.py` | exit 0 = 12 checks PASS |
| Preregistered protocol and amendments A1–A4 | — (archived, not generated) | `docs/EXPERIMENT_PROTOCOL.md`, `docs/PROTOCOL_AMENDMENT_A1_*.md`, `docs/PROTOCOL_AMENDMENT_A2_*.md`, `docs/PROTOCOL_AMENDMENT_A3_*.md`, `docs/PROTOCOL_AMENDMENT_A4_*.md`, `docs/OSF_ADDENDUM_2026-10-12.md` — A1/A2 byte-identical to OSF archive [10.17605/OSF.IO/53H64](https://doi.org/10.17605/OSF.IO/53H64) (immutable, per-file SHA-256); **A3/A4/addendum/ledger are in the project deposit (53h64 Files, 2026-10-11 uploads, per-file SHA-256 verified)**; the frozen registration WJZ3Y is intentionally left at v1 (frozen-snapshot doctrine) |

Generators that are **no longer missing** (fixed 2026-10-12, ledger B1):
`results/real_prior_recovery_summary.json`'s generator was reconstructed as
`scripts/real_prior_recovery_summary.py` — its route-A diff against the
archived 2026-09-27 copy (`results/archive/no-generator/`) shows exactly the
expected cross-epoch deltas; the pair-cluster CI fields are intentionally
`null` when derived from the CSV alone (they need patient-level clusters;
the manuscript quotes the runner-side CI). The pre-correction /
duplicate-rerun decomposition copies and the no-generator
`predictability_sensitivity.json` are archived rather than co-located with
live tables: the lab tree keeps them under `results/archive/pre-retrain/`
and `results/archive/no-generator/` (see `results/archive/README.md`), and
the submission package keeps them under `S2_result_tables/archive_pre_retrain/`.
`results/decomposition_validation.csv` (no suffix)
is a legacy name for the archived n = 500 run — byte-identical to the archived
`decomposition_validation_n500_20260829.bak.csv` — and is *not* the n = 20,000
table.

## Results

**Primary endpoint.** D_ECE_OOD = ECE_raw_OOD − ECE_TS_OOD (this is the article's
primary endpoint; it is *not* the undelivered secondary endpoint
G = ECE_S1 − ECE_oracle). Over the 60-experiment grid (6 corpus pairs ×
2 architectures × 5 seeds, post-retrain) it is **positive in 45/60 cells
(75.0%), mean +0.0093** — `results/robustness_validation_5seeds.csv`, column
`ood_deltaECE`, rows with `method == ts`. InceptionTime supports 24/30
(mean +0.0098) and ResNet-1D 21/30 (mean +0.0089). On the OOD primary
endpoint every cell's BCa CI is sign-resolved: 45 fully positive, 15 fully
negative (the disclosed counter-examples), none contains zero. On the **ID**
side (ΔECE_ID, a different response), 30/60 cells (50.0%) have a
patient-level paired BCa CI containing zero — the pre-registered ID-boundary
branch fired.

Pooled estimates over the same cells, from
`results/meta_analytic_pooled.csv` (regenerated 2026-10-10):

| Stratum | n | Simple mean | DerSimonian–Laird pooled |
|---|---|---|---|
| InceptionTime | 30 | +0.0098 | +0.0096 |
| ResNet-1D | 30 | +0.0089 | +0.0089 |
| **All (cross-architecture)** | **60** | **+0.0093** | **+0.0091** |

**Pooled uncertainty (honest interval).** The 60 grid cells are NOT
independent studies: they share the same three corpora, patient sets, and
architectures. The between-cell heterogeneity is extreme (I² ≥ 99.97% in
every stratum; Q = 98,416 / 144,562 / 252,893 for InceptionTime /
ResNet-1D / cross-architecture), so any fixed-effect or DerSimonian–Laird
random-effects CI is spuriously narrow and must not be quoted. The
interpretable pooled interval is the cluster-robust one over the 12 pair +
architecture strata: **D_ECE_OOD = +0.0093 [+0.0055, +0.0132]** (t,
df = 11; stratum SD 0.0060, three orders of magnitude above any single
cell's BCa sampling error).

**Two safety numbers with DIFFERENT criteria (do not conflate):**

- **Deployment-safety criterion (`results/deployment_metrics.csv`, TS row,
  strict caliber regenerated 2026-10-10 on the 780-evaluation detail grid
  `l2_shift_full_780cells_detail.csv`):** of the 780
  (pair, seed, shift, architecture) evaluations, **368/780 (47.2%)** are
  *beneficial* (ΔECE ≤ −0.01, point-estimate convention), but only **18/780
  (2.3%)** also meets the calibration-adequacy bar (post-TS ECE ≤ 0.05), and
  the joint criterion holds for **8/780 (1.0%)**. Under this joint criterion,
  post-hoc TS alone essentially does not reach the deployment bar —
  recalibrating on a small locally labeled sample (protocol §S2, below) is
  the practical path; the article reports this explicitly.
- **L2 input-robustness criterion (`results/l2_shift_full_390cells.csv`):**
  the delivered per-cell safety flag (relative Brier-reliability
  improvement > 0 under TS) holds for **570/780** of the (architecture ×
  direction × seed × shift) evaluations — a per-row mean safety rate of
  **73.1%** — with **222/390 (56.9%)** cells passing under *both*
  architectures simultaneously and **348/390 (89.2%)** under at least one.
  This says the fitted temperature is stable under mild input changes, NOT
  that cells pass the deployment-safety criterion above.

**What to do when TS is not enough (protocol §S2).** The dose-response of
local recalibration is in `results/s2_dose_response.csv`
(5 budgets × 5 methods × 60 cells × 20 patient-level repeats): the zero-shot
control reproduces the primary endpoint (+0.0093, positive in 45/60), while
**50 labeled target records** already give a mean benefit of **+0.150 with a
per-class Platt scaler and +0.127 with TS** — an order of magnitude above the
zero-shot gain, saturating by n_cal ≈ 250.

Bottom line: the OOD calibration benefit (~0.009 ECE points on average) is
real but small relative to residual miscalibration (raw ECE 0.036–0.357,
mean 0.203, in the post-retrain 64-cell ablation grid —
`results/ablation_ts_components.csv`, `stage == raw`); treat post-hoc
recalibration as one component, not a standalone fix.

## License

Code: MIT (see [LICENSE](LICENSE)). The three databases remain under their respective PhysioNet / challenge licenses.

## Citation

If you use this codebase or the split indices, please cite the accompanying article (see also [CITATION.cff](CITATION.cff)):

```bibtex
@misc{ecgcalib2026,
  title  = {Calibration Transferability in Cross-Corpus ECG Deployment:
            A 60-Experiment Boundary Validation},,
  author = {Guan, Toni and Liu, Ziyan and Gao, Yingrui and Feng, Chuhan and Li, Yue},
  year   = {2026},
  note   = {Official code and data-split release},
  url    = {https://github.com/Toni-cs/ecg-calibration-transferability}
}
```

Please also cite the source databases (PTB-XL: Wagner et al., *Scientific Data* 2020; Chapman–Shaoxing: Zheng et al. 2020; CPSC2018: Liu et al., *CinC* 2018).

## Contact

Questions and issues: please open a [GitHub issue](https://github.com/Toni-cs/ecg-calibration-transferability/issues).

## Manuscript alignment (2026-10-17)

- The manuscript (paper/main_cmpb.tex in the submission tree) is titled
  **"Calibration Transferability in Cross-Corpus ECG Deployment: A 60-Experiment Boundary Validation"**; CITATION.cff and the BibTeX block above carry the same title.
- The full protocol-provenance record (amendments A1-A4, the 2026-09-17
  checkpoint retrain, the 2026-10-07 validation-leak repair, and the
  retrospective-registration disclosure) is consolidated as **Appendix A**
  of the manuscript; a one-paragraph-per-event summary lives in the Methods
  section.
- **Reporting compliance:** the manuscript follows TRIPOD+AI
  (Collins et al., *BMJ* 2024;385:e078378). The completed item-level map is
  in [docs/TRIPOD_AI_item_map.csv](docs/TRIPOD_AI_item_map.csv) (39 rows;
  every not-applicable item is disclosed, none silently marked).
- **Artifact gate:** never quote the files listed in
  [results/DO_NOT_QUOTE.md](results/DO_NOT_QUOTE.md) as current readouts;
  each row names the correct replacement source.
- The per-seed values of the primary endpoint now live as **Supplementary
  Table S1** (supplementary.pdf, section S2); the main text carries the
  12-stratum summary table.
