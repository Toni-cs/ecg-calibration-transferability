# `results/archive/` — files kept for provenance, NOT for quoting

Nothing in this tree is a current readout. Each file is preserved because some
generation of the audit trail referenced it; the live numbers live in the
unsuffixed tables one level up, and `results/README.md` is the inventory of
record.

## `no-generator/`

Files that had no reconstructable generator at their time of archival.

| File | Why archived | Disposition |
|---|---|---|
| `real_prior_recovery_summary.2026-09-27.json` | The 2026-09-27-epoch aggregate of `real_prior_recovery.csv`, superseded byte-for-value by the post-retrain rebuilds (2026-09-17 / 2026-10-07). Its generator lived on the retired branch. | Superseded by the **reconstructed generator** `scripts/real_prior_recovery_summary.py` (2026-10-12): route-A diff against this file shows exactly the expected cross-epoch deltas (`err_bbse_mean` 0.1127 → 0.1109, `err_em_mean` 0.1377 → 0.1326, `bbse_rel_improvement_pct` 41.2 → 42.1, `bbse_beats_em` 38/60 → 33/60, `delta_mean` 0.0788 → 0.0807); the pair-cluster CI fields are NOT recomputable from the CSV alone (needs patient-level clusters) and are reported as `null` with a note in the regenerated summary. |
| `predictability_sensitivity.withheld.json` | No generator exists in any branch and its inputs predate the 2026-09 label repair; the article's own audit block records it as *not citable*. | Also on the release tree's `results/README.md` "deliberately withheld" list; do not upload, do not quote. |

## `pre-retrain/`

Byte-for-byte legacy reruns of the decomposition synthetic-validation family
from **before the 2026-09-17 and 2026-10-07 retrain waves**; kept only to make
the correction history auditable. The current validation readouts are
`results/decomposition_validation_n20000.csv` (27/27), the disclosed
`decomposition_validation_n500_seeds4.csv` (seed-42 readout 21/27; four-seed
all-pass 12/27), and the legacy-named single-seed `decomposition_validation.csv`
(21/27).

| File | Note |
|---|---|
| `decomposition_validation_n500_20260829.bak.csv` | the baseline `n=500` binary |
| `decomposition_validation_n20000_postfix_20260830.csv` / `..._rerun_20260830.csv` | byte-identical duplicate runs of each other, pre-repair epoch |
