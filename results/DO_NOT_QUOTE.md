# DO NOT QUOTE — artifacts that must not be cited as current readouts

Status: 2026-10-17. This file aggregates every do-not-quote warning that the
inventory (`README.md` in this directory) carries inline, so a reader who
downloads the release and greps the CSVs hits the gate before quoting.
Each row names the artifact, the reason, and the correct source to cite
instead. The same discipline lives in
`_EIGHT_METHOD_SEMANTICS_NOTICE.md` (non-`ts` rows),
`_VAL_LEAK_RETRAIN_NOTICE_2026-10-10.md` (pre-retrain supersession), and
`_ABLATION_TS_COMPONENTS_CONTAMINATION_NOTICE.md` (encoding lineage).

| Artifact | Why it must not be quoted as current | Quote instead |
|---|---|---|
| `bh_fdr_correction.csv` | pre-retrain era snapshot (51/60-generation readout) | BH-12 = 7/12 and Bonferroni-12 = 6/12 re-derived from `robustness_validation_5seeds.csv` (`regenerate_stats_60exp.py`; re-checked by `scripts/verify_release_results.py`) |
| `deployment_holdout_recompute.csv` | rows come from the checkpoint method pool, not the 780-cell grid the article quotes alongside it | `deployment_780grid_recompute.csv` (and `deployment_metrics.csv`) |
| `decomposition_validation.csv` | legacy filename: byte-identical to the archived n=500 single-seed run, not the registered gate | `decomposition_validation_n20000.csv` |
| `predictability_sensitivity.json` | no generator exists in any branch; its `y` is built from pre-correction values | `predictability_corrected_v2.csv` |
| `ablation_ts_components.OLD_ENCODING.csv` | pre-retrain-era artifact under the 2026-09-16 label encoding; release-lineage comparison only | `ablation_ts_components.csv` (the manuscript-cited file) |
| `discrimination_metrics_60exp.OLD_ENCODING.csv` | pre-retrain-era artifact; release-lineage comparison only | `discrimination_metrics_60exp.csv` (the manuscript-cited file) |
| `archive/` subtree (incl. `no-generator/`, `pre-retrain/`) | kept for provenance, explicitly NOT for quoting | the live top-level files named in each archive README |
| `noise_floor_curve.csv` aggregate rows (`__min__` / `__median__` / `__max__`) | synthetic-block aggregates, not per-cell readouts | the 60 empirical cell rows (and the synthetic block labeled as sensitivity) |
| `real_prior_recovery_summary.json` field `cluster_ci_low/high` | intentionally `null` (not recomputable from the per-cell CSV alone; needs patient-level cluster labels) | the means/counts in the same JSON (0.1916 -> 0.1109, 42.1%, 56/60, 6/6); no CI is quoted |
| `checkpoints/e2_probs_cache/*.npz` derived sub-claims | caches are not shipped in the repository | none — the dependent manuscript sub-sentences were removed on 2026-10-15 |

Rule of thumb: any number quoted in the manuscript must be recomputable from a
shipped artifact listed in `README.md` without the warnings above. If a file
appears here and also in a manuscript citation, the manuscript citation is the
bug — file an issue.
