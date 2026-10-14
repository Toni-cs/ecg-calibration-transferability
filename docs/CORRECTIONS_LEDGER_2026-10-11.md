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
| A15 | The delivered 8-method rows carry the historical shared-correctness semantics (see A12); the paper's C4 claims (EM harmful, BBSE positive) had no corrected-semantics counterparty | `scripts/recheck_method_semantics.py` recomputes the OOD branch of all 8 methods directly from the lab-tree probability caches with per-branch correctness; output `results/robustness_val_8method_perbranch_recheck.csv`; paper C4 (contribution + conclusion) now discloses the recheck | **TS gate: 60/60 rows reproduce the delivered values exactly (0 argmax flips)** — machinery proven; stamps 60/60 consistent per class-count; EM $-0.0040 \to -0.0378$ (claim strengthened), BBSE $+0.0270 \to +0.0172$ (still positive), parametric methods shift ≤0.003, no qualitative claim flips |
| A16 | `tab:deploy_sens` + the lookup-table row of `tab:trivial` had no delivered-grid-computable generator (pool era); placeholders/honest tags were interim | `scripts/recompute_deployment_780grid.py` recomputes the full Youden / leave-shift-type-out / frozen-threshold scheme on the delivered `l2_shift_full_780cells_detail.csv` (strict beneficial convention, P=368 exact match to `deployment_metrics.csv`); manuscript table + prose replaced with the 780-grid values; `tab:trivial` lookup row now carries computed values (476/780 routed, mean −0.0116) | `P/N` exact match (368/412); new in-sample optimum J=+0.306 @ 0.206; every leave-type-out J exceeds in-sample (generalization claim survives and is stronger); main PDF recompiled 81 pp, zero undefined citations |
| A17 | The preregistered §10 mapping-sensitivity promise was unexecutable as written: its τ≥0.8 gate is defined on the secondary endpoint G, which the paper's own Limitations (xviii) acknowledge as undelivered on real data; execution status was also falsely implicit (never run, never registered as a deviation) | **Amendment A4** (`docs/PROTOCOL_AMENDMENT_A4_MAPPING_SENSITIVITY.md`, both trees, 2026-10-11) re-operationalizes the gate on delivered ΔECE_OOD: 6-pair ordering Kendall τ≥0.8 + confirmatory counts unchanged (7/12, 6/12), failure clause unchanged (claim downgrade); variants V1/V2 enumerated, V3 excluded with reason; anti-HARKing: criterion defined before any variant result exists; paper gains a §amendment-A4 subsection, the preregistration record lists A1–A4, cover letter synchronized; A3+A4 deposit upload queued and disclosed | main PDF recompiled; no delivered value touched; battery execution remains an author-scheduled deliverable (est. 2–5 GPU-days for two variants) |

## B. Resolved on 2026-10-12 (zero-compute wave; verification for each)

1. **Two orphan results files given generators / archived (ledger A18).**
   - `real_prior_recovery_summary.json`: generator **reconstructed** as
     `scripts/real_prior_recovery_summary.py` (route A). Byte-stable across
     repeated runs; its output matches the delivered CSV's quoted numbers
     (err_bbse 0.1109, 42.1%, 56/60, 33/60) and the archived 2026-09-27 copy
     differs exactly as the two retrain epochs predict (0.1127/0.1377/41.2%/
     38/60). The pair-cluster CI fields are honestly `null` from the CSV alone
     (needs patient-level clusters; the manuscript quotes the runner-side CI).
     The stale predecessor is archived at
     `results/archive/no-generator/real_prior_recovery_summary.2026-09-27.json`.
   - `predictability_sensitivity.json`: no generator in any branch → route B,
     archived at the lab tree's
     `results/archive/no-generator/predictability_sensitivity.withheld.json`
     (inventory updated; it was already withheld from the release tree).
2. **Downstream propagation guard for the leak-era snapshots (A19).**
   README top banner added ("re-clone or checkout v1.1.0, tag commit
   `46dadf1`"); the **v1.0.0 GitHub release page** now opens with a ⚠️
   DO-NOT-USE preamble listing the three defects (incomplete script archive /
   two byte-duplicate weights / leak-era split semantics) and redirects to
   v1.1.0 (correction visible on the release page; PATCH verified 200).
3. **Submission bundle repackaged + re-signed (A20).** The rebuilt PDFs
   (main 83 pp, supplementary 12 pp, cover 3 pp) are packaged at
   `S0_manuscript/`; the three pre-retrain legacy decomposition tables moved
   out of the live-table namespace into `S2_result_tables/archive_pre_retrain/`
   (with the archive README inside); `real_prior_recovery_summary.json` in the
   package refreshed to the regenerated post-retrain epoch (byte-identical to
   the release tree). `SHA256SUMS.txt` re-signed: **178 entries, ALL OK**.
4. **Legacy-table quarantine (A21).** Lab tree: the two pre-retrain rerun CSVs
   and the 2026-08-29 .bak moved to `results/archive/pre-retrain/`;
   `predictability_sensitivity.json` and the stale summary JSON to
   `results/archive/no-generator/`; both trees got `archive/README.md`
   (nothing in the tree is quotable). Inventories updated accordingly.
5. **NCV/DCR second-source adjudication (A22).** **Decision (2026-10-12):
   keep the current post-retrain wording.** Rationale: the manuscript already
   discloses the one-order-of-magnitude NCV shrinkage and reports the
   registered patient-level BCa unit as the operative interval; those numbers
   are bound by `verify_release_results.py` check 11 (`e3_patient_bca`, NCV
   CI [+0.000125, +0.000353]) and by `e3_patient_bca_summary.json` (born
   2026-10-10, the post-retrain wave). No second run is material; the item is
   closed as *resolved-by-existing-disclosure*.
6. **8-method semantics labeling layer (A23; the fallback branch of the
   compute item).** `results/_EIGHT_METHOD_SEMANTICS_NOTICE.md` written (exact
   shared-correctness definition, affected rows, measured per-method shift
   table, quoting rules); mirrored into the lab tree; the robustness row of
   `results/README.md` now points at it, and the main text's C4 already
   discloses the recheck. Full regeneration of the delivered non-TS rows
   remains queued on lab-tree compute (see C.1).

## C. Still queued (compute-bound or user-side only)

1. **Full per-branch regeneration of the delivered 8-method rows** — needs the
   lab-tree runner (`l2_shift_results.json` per checkpoint is absent from both
   trees). The labeling layer (B6) + the recheck artifact (A15) cover the
  citation risk in the meantime.
2. **§10 preregistered CPSC mapping-sensitivity battery (A4)** — est. 2–5
   GPU-days for variants V1/V2 (gate re-operationalized on delivered
   ΔECE_OOD). Incremental plan: one pair per run, partial CSV + ledger dot once
   committed. If compute never materializes, the A4-registered failure clause
   and the paper's disclosure ("not executed") remain the honest fallback.
3. **OSF registration-layer closure (user-side).** Project deposit ✅ (B
   section, A18 context). Still pending: submitting the registration-update
   draft (justification + four files authored) so WJZ3Y mints v2, and applying
   the full-text description replacement (`OSF_DESC_FULL_2026-10-12.txt`; the
   dead related-material link itself was already corrected on 2026-10-11 in
   the registration metadata — API-verified). API probe 2026-10-12:
   `revision_state: in_progress`, description not yet carrying the ADDENDUM
   block. The frozen value stays untouched by design (F3 doctrine: frozen
   record + additive disclosure).

## C. Calibration of prior audit artifacts

- Round-9 (2026-09-09) verdict numbers (51/60, 2/12 Bonferroni, 23/60) were
  superseded by the 2026-09-17 label repair and the 2026-10-07 val-leak
  retrain wave; current confirmatory counts are BH-12 = 7/12, Bonferroni-12 =
  6/12 over the delivered `robustness_validation_5seeds.csv`. Do not quote the
  older verdicts; treat them as snapshots.
- The `p0r2` fix chain on `SUBSPACE_CPSC` order was subsequently reverted
  (2026-09-16, tombstone comment in `src/data/mapping.py`); that event is
  documented in `reports/CPSC_OFFICIAL_DEFINITION_VERDICT_2026-09-16.md`.

## C. Project fork record (2026-10-14)

- New project forked per the author's whitepaper v2.0 (cross-corpus calibration
  drift quantification & correction): repo at `D:\A1\ecg-drift\`, governed by
  its own signed-protocol chain (WHITEPAPER_v2.0 transcription + sign-blockers
  appendix v2.1 + prefilled seeds.md; pre-registration commit chain
  `9208b1b` / `ac801ff` / `8caa87a`).
- Ledger boundary: queued items C.1-C.3 above remain obligations of THIS tree;
  the fork neither absorbs nor closes them. Conversely, the new project
  consumes no resources from this repo (it re-fetches data and re-derives
  backbone configs per its own protocol).
- A24 deliverables (`scripts/samplelevel_ts.py`, `results/samplelevel_ts_60cells.csv`)
  stay paper-side in this repo; the new project's Tier 0-4 ladder
  (raw -> TS -> PTS -> BCTS-BBSE -> oracle) is an independent methodological
  line and does not supersede the delivered per-branch tables here.
