# Corrections ledger — 2026-10-11

Scope: the defects raised by the 2026-10-10/11 cross-adversarial review (13
independent auditors) against this release tree, the submission package, and the
manuscript; what was fixed on this date, how it was verified, and what remains
deliberately queued. This file is the point-in-time reconciliation layer between
the multi-generation artifacts (preregistration records, audit reports, the
manuscript) and the delivered set, superseding stale readouts elsewhere.

## A. Fixed on 2026-10-11 (all verified mechanically)

| # | Defect | Fix | Verification |
|---|--------|-----|--------------|
| A1 | Release `scripts/train.py` / `scripts/export_splits.py` still carried the leak-era PTB-XL semantics (the 2026-10-10 regeneration wave updated splits/results/README but missed both scripts; `setdiff1d` 0 hits) | Ported the lab-tree fix (2026-10-05): `np.setdiff1d` exclusion of carved val records from the train loader; `assert_no_leakage` re-derived from the final loader positions | `pytest`: 11/11 pass (incl. 6 new lockstep tests); `export_splits --validate 42` vs real builders: **20/20 MATCH**; seed-42 regeneration of all 5 split variants **byte-identical** to the committed CSVs |
| A2 | README claimed `tests/test_ptbxl_val_holdout.py` and "189 tests" absent from this tree | Ported the regression test (6 tests, English comments); README test count corrected to 11 | file present; `pytest -q` 11 passed, 12.8 s |
| A3 | README's three hard-false fix claims (fix-in-train.py / regression test / 189 tests) + soft-misleading ones | Rewritten with the honest two-stage provenance (lab-tree fix date vs. release-tree ship date; wave omissions disclosed) | this ledger; see A1's end-to-end validation |
| A4 | verify script was described as "re-derives every number quoted in this README" (overclaim) | Wording narrowed to "headline aggregates; a table-level integrity check, not an estimator re-run" | README `paper-to-artifact map` row |
| A5 | Submission package: 29/40 co-named S2 tables were pre-retrain versions; SHA256SUMS header claimed 2026-10-10 regeneration while pinning 09-05/06/17 hashes | All 29 tables refreshed from this tree's post-repair `results/`; manifest regenerated + every entry re-verified | 29 refreshed, 11 already identical, co-named diffs now **0**; `SHA256SUMS.txt` 172 entries ALL OK |
| A6 | README "every result table byte-identical" falsified (11/40) at the package level, and `results/README.md` inventories stale (38/47, 376, Table-6 descriptions, outdated mtimes) | Both README levels corrected to the verified counts (40 co-named identical; 3 package-only legacy tables named; inventory rows updated with true mtimes/values) | refresh driver output; `l2_shift_full_summary.json` (`n_safe_cells`=348) and `verify_release_results.py` agree |
| A7 | `bh_fdr_correction.csv` is a pre-retrain (51/60-era) snapshot but was not flagged | `results/README.md` row now carries a ⚠ provenance warning naming the current source of the confirmatory counts | row edit; `verify_release_results.py` aggregations |
| A8 | Manuscript citations: `pseudocal2020` was a binding error (Garg et al. label-shift paper cited as "PseudoCal"); TransCal and LaSCal titles fabricated; Van Calster 2016 author list fabricated (Steyerberg doubled, Collins/Riley wrong, 4 true authors missing); LaSCal author list incomplete; PEACE entry pointed at the wrong arXiv (2605.00647 instead of the PEACE-bearing 2607.15928); in-text surnames Tan/Costa/Chen mismatches; missing nearest prior art (Zhang et al., ICML 2023, Shapley-over-shifts) | Related Work rebinding + new sentence for Garg/Zhang; all bibitems corrected; supplementary mirror synchronized | `paper_check.py`: main 39/39 bibitems all cited, zero duplicates, zero dangling, brace-balanced; authors verified against PubMed/NeurIPS proceedings/arXiv (LaSCal = Popordanoska, Radevski, Tuytelaars, Blaschko; PEACE = Liu et al., arXiv 2607.15928) |
| A9 | `tab:trivial` lookup-table row printed literal `$\mathtt{regen}$` placeholders into the PDF | Replaced with `--` and an explicit caption note (values pending recomputation on delivered post-retrain artifacts) | row + caption edit |
| A10 | `tab:deploy_sens` was claimed "regenerated on the completed 780-evaluation grid" but its arithmetic (TP=1015 at thr 0.172) is impossible on a 780-row grid; it comes from a checkpoint-level pool (n≈3,015) | Prose + tag rewritten with the pool provenance and reconciliation note; caption and numbers unchanged (numbers are pool-side, the claim was the defect) | pool arithmetic re-derived (P≈1233, N≈1784 per row) |
| A11 | `cover_letter.tex` "ten counter-examples (16.7%)" vs manuscript's fifteen (25%) | Corrected to fifteen (25%) | edit; `paper_check.py` residue scan clean |
| A12 | Delivered 8-method ΔECE per-cell tables share the calibrated-argmax correctness across both bootstrap branches (affects only argmax-flipping methods; TS / fixed-T Platt unaffected) | `benefit_inference` extended (`labels_raw`), `eval_transfer.py` now passes per-branch correctness, meta stamps the semantics; `_group_jackknife_benefit` consumes the caller rng instead of a hardcoded `default_rng(0)`; `_bca_interval` gained a percentile-inversion guard; `two_layer` refit failures no longer propagate NaN and `t_std` uses ddof=1 | code edits; release tests pass; delivered numbers unchanged (ts primary endpoint unaffected; the delivered non-TS rows keep the shared-label semantics and are flagged here — see section B) |
| A13 | Released checkpoint assets mismatched the delivered tables (v1.0.0 = pre-repair snapshot + 2 byte-duplicate direction weights) | **Post-repair asset built**: `ecg-release_assets_transfer_checkpoints_post_repair_2026-10-11.zip` — 62 .pt (60 grid + 2 partial-mamba toys), all 60 grid weights gate-verified against `results/robustness_validation_5seeds.csv` before packing | gate: 60/60 cells, max \|json−csv\| = 4.9e-7; duplicate-fix cells now differ; 60 unique grid hashes; manifest 62/62 inside the zip; README weight-caveat block updated |
| A14 | Manuscript quoted only the n=500 seed-42 decomposition readout (21/27), never the 4-seed rerun (12/27 all-pass, 22/27 majority) now present in the delivered CSV | Body (§ decomposition) + conclusion C3 now disclose the four-seed agreement explicitly | edits; numbers from `decomposition_validation_n500_seeds4.csv` |

## B. Queued (not addressable without lab-tree compute / author action)

1. **§10 preregistered CPSC mapping-sensitivity analysis** (Kendall τ≥0.8 gate;
   promised in the protocol, never executed): requires mapping-variant reruns on
   real data in the lab tree. Until then the cross-corpus claims must keep their
   label-drift caveat (`main_cmpb.tex` L862-865-class wording).
2. **780-grid deployment recomputation** (`tab:deploy_sens` + lookup-table row):
   the pool-side numbers in the manuscript are provenance-tagged as of today;
   the 780-grid recomputation of the same table is queued.
3. **NCV artifacts** (e3/c3 families) — second-source adjudication of the
   post-retrain NCV shrinkage wording remains open.
4. **Semantics change notice**: results computed by the *pre-fix*
   `benefit_inference` (shared labels) for non-argmax-preserving methods carry
   the shared-correctness semantics; this ledger line is the reveal. Recomputing
   those rows requires the lab-tree checkpoint pool (`l2_shift_results.json`
   per checkpoint — currently absent from both trees), same blocker as (2).
5. **OSF deposit housekeeping**: A3 not in the deposit (now disclosed in the
   README), dead project-page link (F1), frozen registration cannot carry the
   51→50→45 evolution — upload the addendum instead.
6. **Submission recompile**: done on 2026-10-11 — `main_cmpb.pdf` (80 pages,
   exit 0, zero undefined citations after the second pass), `cover_letter.pdf`
   (2 pages, exit 0), `supplementary.pdf` (12 pages, exit 0) rebuilt from the
   corrected sources. Remaining step: copy the rebuilt PDFs into the
   submission bundle per the author's packaging convention and re-sign that
   bundle if it is ever hash-manifested.
7. **Package-only legacy tables kept in the supplementary**
   (`decomposition_validation_n500_20260829.bak.csv`,
   `...n20000_postfix_20260830.csv`, `..._rerun_20260830.csv`): retained
   deliberately as archives; do not quote them as current readouts.
8. **GitHub release asset upload** for the post-repair checkpoint zip (queued
   for the next tag).

## C. Calibration of prior audit artifacts

- Round-9 (2026-09-09) verdict numbers (51/60, 2/12 Bonferroni, 23/60) were
  superseded by the 2026-09-17 label repair and the 2026-10-07 val-leak
  retrain wave; current confirmatory counts are BH-12 = 7/12, Bonferroni-12 =
  6/12 over the delivered `robustness_validation_5seeds.csv`. Do not quote the
  older verdicts; treat them as snapshots.
- The `p0r2` fix chain on `SUBSPACE_CPSC` order was subsequently reverted
  (2026-09-16, tombstone comment in `src/data/mapping.py`); that event is
  documented in `reports/CPSC_OFFICIAL_DEFINITION_VERDICT_2026-09-16.md`.
