# Disposition of the 2026-10-17 review plan (12 facts + T1-T3 roadmap)

Context: an author-side review plan (12 "hard facts" + Tier 1/2/3 roadmap,
8-10 working days) was checked line-by-line against the repository state of
2026-10-17 (post audit waves of 2026-10-15, commits through `7897f79` in the
manuscript tree and `4eb6cdb` here). Verdict per item; evidence is on disk.

## Facts table: verdicts

| # | Claimed fact | Verdict | Evidence |
|---|---|---|---|
| 1 | README Results table uses pre-retrain pooled +0.0159 | **STALE — already fixed** | README L204 narrates the interim -> final transition; L383-408 carries +0.0093 [+0.0055,+0.0132], IT 24/30 (+0.0098), RN 21/30 (+0.0089). The claimed numbers appear nowhere in the current tree (they match a pre-2026-10-12 snapshot) |
| 2 | README deployment story is 1/157 pool-era | **STALE — already fixed** | no "157" anywhere in README; the 780-grid dual-criterion wording is present |
| 3 | README says CPSC2018+2019 | **STALE — already fixed** | README L45-50 explicitly states CPSC2018-only (6,877 + 3,453) and links A3 |
| 4 | BibTeX block URL points to the old account | **STALE — already fixed** | all URLs are Toni-cs (L10/L134/L158/L462/L470) |
| 5 | counterexample CSV/JSON are 2026-09-27 "ten counter-examples" | **HALF RIGHT** | data are CURRENT (mtime 2026-10-09, post-retrain; TP 45/FP 0/FN 0/TN 15; T band [0.932,0.997] — exactly the manuscript's numbers). Only the inventory LABEL was stale; label fixed 2026-10-17 |
| 6 | deployment_holdout_recompute.csv is pool-lineage | TRUE, already documented | its own inventory row carries the warning; now also in results/DO_NOT_QUOTE.md |
| 7 | manuscript 0.735-0.843 direction means come from the OLD_ENCODING file | **REFUTED** | recomputed from the unmarked file (test/ts, 60-grid, no mamba): direction means 0.7355-0.8498 -> exactly the manuscript's 0.735-0.850 (L2324, L2485). The claimed 0.7313-0.8425 range arises only if the 4 BiMamba toy cells are included |
| 8 | bh_fdr_correction.csv is a pre-retrain snapshot | TRUE, already documented | inventory row warns "do not quote this file's counts"; now also in DO_NOT_QUOTE.md |
| 9 | PREREGISTRATION_ALIGNMENT F1-F6 all unresolved | **PARTIALLY STALE** | F2 RESOLVED 2026-10-11 (A3+A4 uploaded to 53h64, SHA-verified); F3/F6 covered in the manuscript archival-status section; F1 remains open (author-side OSF description edit); addendum appended to the doc 2026-10-17 |
| 10 | reference-closure check must be re-run after edits | TRUE, adopted | run after this wave (424 refs) |
| 11 | reports/ audit files are a "negative list" reviewers may open | framing only | they are transparency assets; no action |
| 12 | robustness/meta CSVs are post-retrain but README pooled not updated | **STALE** | same as fact 1 |

## Tier 1 verdicts

| Item | Verdict | Action taken 2026-10-17 |
|---|---|---|
| T1.1 `oindent` LaTeX bug | **REAL (P0)** — survived three audit waves; renders literally in the PDF | fixed: `\noindent` restored at the abstract's first line |
| T1.2 Figure 9 in-plot title "Nine Counter-Examples" | **REAL** — figure plots 15 points (CE1-CE15) with a stale 9-era title and stale 8+1 legend taxonomy | generate_figures.py fig4 rewritten: canonical CE order = the JSON's negative_cells_detail (CE1-9 unchanged, CE10-15 pinned), title "Fifteen...", legend describes the coloring rule instead of asserting counts (data-driven rule flags 3 ID-negative cells, so hardcoded "1 case" would have contradicted the text); figure regenerated and verified (15 labels, new title) |
| T1.3 ResNet naming | **STALE — already unified** | manuscript has exactly one form (ResNet1D) plus the first-occurrence parenthetical "(a 1D-ResNet-34 backbone)" (L457) |
| T1.4 "70.05-seed" sticky typo | **NOT PRESENT** in the current tree (0 grep hits; the plan's line numbers come from a non-existent `main_bspc.tex` — an old checkout) | nothing to do; en-dash sweep DONE instead: 7 half-width "Chapman-Shaoxing" -> "Chapman--Shaoxing" |
| T1.5 drop the "What is new." label | **CONFLICT with the author's own 2026-10-15 directive** (novelty-up-front block was requested explicitly) | label KEPT, backslash bug fixed; one-line removal available on request |

## Tier 2 verdicts

| Item | Verdict | Action |
|---|---|---|
| T2.1 F1 OSF description | REAL, author-side | replacement text ready (`OSF_DESC_FULL_2026-10-12.txt`); needs the account owner's OSF action |
| T2.1 F2 upload A3/A4 | STALE — done 2026-10-11 | no action |
| T2.1 F3 clause | STALE — covered by the narration | no action |
| T2.1 F6 manifest dates | STALE — manuscript already distinguishes 2026-09-05 baseline vs 2026-09-16 snapshot | no action |
| T2.2 README rewrite | STALE — README already rewritten (2026-10-12 wave) | no action |
| T2.3 re-run discriminate script | NOT NEEDED — data current (fact 5) | inventory label fixed instead |
| T2.4 DO_NOT_QUOTE.md | GOOD IDEA, adopted | `results/DO_NOT_QUOTE.md` created (10 rows); results README counts 58->59 |
| T2.5 CITATION.cff | **REAL** — v1.0.0/2026-09-13/old title/single author | updated: new framework title, five authors, v1.1.1, 2026-10-17; README BibTeX block synced (title + five authors) |
| T2.6 reference-closure | adopted | re-run after this wave |

## Tier 3 verdicts (recommendations, not executed)

- **T3.1 abstract rewrite**: the current abstract already follows
  question -> method -> result -> significance and was restructured on
  2026-10-15 at the author's direction (components-first, TS-as-carrier).
  A second full rewrite would reverse that decision; only targeted trims are
  recommended (e.g., the LOO R^2 numeric can move to the body if desired).
- **T3.2 compress 85 -> 45 pp**: NOT recommended before submission. The
  amendment/archival sections are the integrity spine that three audit waves
  verified; relocating them re-opens every cross-reference and the
  hash-locked package (manifest regeneration + re-verification) for a
  speculative acceptance gain. Better done as a post-decision revision if
  requested.
- **T3.3 Limitations 23 -> 8-10**: the facts must not be deleted (they are
  load-bearing disclosures verified against disk); a zero-risk grouping
  (Major/Moderate/Minor lead-in over the existing numbered items) is
  available on request. Renumbering mid-submission would break
  cross-references ((xi), (xxi), (xxiii) are cited in text).
- **T3.4 references 40 -> 70**: accepted in principle, execution deferred to
  a dedicated verified round (every new citation needs the three-check
  discipline; bulk insertion without verification is how hallucinated
  references happen).
- **T3.5 cover letter trim**: light trim possible; the letter was re-audited
  on 2026-10-15 and every number in it is verified. Deferred.
- **T3.6 TRIPOD+AI compliance**: genuinely valuable for CMPB; proposed as a
  separate deliverable (reporting-guideline subsection + checklist mapping
  file), executed only with the author's go-ahead.
- **T3.7 boundary-study framing paragraph**: low-risk addition, available on
  request.

## Probability framing

The plan's "25-35% -> 55-65%" acceptance estimates are not falsifiable and
are not endorsed here. What is factual: after this wave the manuscript and
the repository are mutually consistent down to the inventory-label level, the
one-character LaTeX defect is gone, the figure/data/title/citation quartet is
coherent, and the only open blocking item is the author-side OSF description
edit (F1).
