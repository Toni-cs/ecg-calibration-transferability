# _VAL_LEAK_RETRAIN_NOTICE_2026-10-10.md

**Scope.** Every `results/` result table in this repository (2026-10-09/10
regeneration wave) and every number quoted in this README reflect the
**post-repair** grid described here. Earlier snapshots of this repository
pinned the pre-repair publication set.

**Incident.** In the originally shipped PTB-XL split semantics, every
carved-out `val` patient's records were still fed to the training loader
(early-stopping monitoring only, but drawn from the training data). The
`splits/*.csv` files faithfully displayed this via `in_train_loader=yes` on
`val` rows, and the builder asserted nothing about `val`.

**Fix (2026-10-07).** `scripts/train.py` now excludes all `val` patients from
the training loader (`np.setdiff1d` patient filter plus a build-time
disjointness assertion); `scripts/export_splits.py` mirrors the logic
line-by-line (lockstep re-verified). `export_splits.py --validate 42` passes
20/20 against the dataset builders; the new regression test
`tests/test_ptbxl_val_holdout.py` covers the semantics; the repository test
suite passes (189 tests). Across the ten PTB-XL-family split exports the
**only** differences are `val` rows: 21,397 records changed from
`in_train_loader=yes` to `no`.

**Retrain.** The affected cells are the PTB-XL-source cells:
(pair) x (architecture) x (seed) = 2 x 2 x 5 = **20 of 60 cells retrained**
under the fixed splits; the other 40 cells are unchanged (no PTB-XL training
dependence). All 16 downstream result families were regenerated on the
ranked post-retrain checkpoints (seed-43 late swaps and Chapman chain delays
documented in the lab plan), the primary table and every derived table were
rebuilt, and the manuscript's numbers were updated accordingly.

**Numbers (primary endpoint, TS support).** 50/60 -> **45/60 (75.0%)**;
mean OOD benefit +0.0154 -> **+0.0093**; ID benefit +0.0082 -> **+0.0034**
(the repair removed ~58% of the ID residual); the pre-registered ID-boundary
failure branch still triggers (30/60 = 50.0% of cells have a CI containing
zero).

**Reproducibility.** Release asset **v1.0.0** carries the
**pre-repair** checkpoint snapshot; retrained checkpoints are planned for the
next release tag. `scripts/verify_release_results.py` re-derives the numbers
quoted in this README directly from `results/` (11 checks; exits non-zero on
any mismatch).
