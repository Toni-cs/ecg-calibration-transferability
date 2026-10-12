# Review triage B — 2026-10-12: the second "Reject" report (14 points) against the delivered record

**Input:** a second external Reject (14 points; sharper than the first — it
quotes our own ledger, notices and verify gates as attack material).
**Method:** same as A — each point adjudicated against the delivered artifacts
(paper 83 pp @ main_cmpb.tex, results/ trees, ledger A1–A23 + B/C sections).
Verdicts: MISREAD / PARTIAL / REAL.

## Load-bearing corrections (the three facts the Reject stands on)

1. **"Effect is within ECE estimator noise ⇒ indistinguishable from zero."
   — numerically false on the delivered numbers.**
   The estimator's own noise is *measured* in the same deliverables:
   per-cell BCa CI half-widths (bootstrap_diagnostics.csv, verify check 10):
   min 2.1e-5, **median 8.3e-4** → the +0.0093 headline sits at ~11x the
   median estimator noise. The operative inference is not "a number next to
   noise": it is (i) the patient-level cluster-paired BCa interval per cell
   (45/60 cells with point = CI), (ii) the **cluster-robust 12-stratum
   interval [+0.0055, +0.0132]** (t, df = 11) whose lower bound excludes
   zero, and (iii) **6/12 strata surviving Bonferroni-12** (7/12 under
   BH-FDR). "Small" is true and disclosed (no pre-registered MDE —
   Limitation (xxiii) says exactly that); "indistinguishable from zero" is
   the claim the CIs refute.
2. **"I² ≈ 99.98% ⇒ any pooled mean is unusable, yet the author reports one."
   — a strawman.** The paper does not use pooling as evidence: it states
   "any fixed-effect or DL random-effects CI is spuriously narrow and must
   not be quoted" and names the **cluster-robust 12-stratum interval** as the
   operative one (README Results; paper Results/Discussion). The pooled rows
   sit in tables as descriptive metadata. Rejecting the paper for using a
   deferral it makes in print is a misread.
3. **"40 cells are still leak-era." — a direction-dependence error.** The
   leak exploited the PTB-XL training loader only (folds 1–8). The 40
   non-retrained cells are the Chapman↔CPSC directions, whose training
   *never touched PTB-XL splits*; the retrain scope 20/60 is exposure-derived
   and stated as such in the repair section + ledger (the 09-17 cpsc_ptbxl
   retrain was a different incident — byte-duplicate weights). The reviewer's
   phrasing "剩余 40 个 cell 的数字仍来自 leak-era 训练" mis-states the
   paper's own direction-dependence analysis.

## Per-point verdict table

| # | Claim | Verdict | Evidence / rebuttal line |
|---|---|---|---|
| 1 | Effect below estimator noise | **MISREAD** | CI median half-width 8.3e-4 ≪ 0.0093; cluster-robust interval excludes zero; 6/12 Bonferroni; 45/60 cell CIs. "No registered MDE" is disclosed verbatim (Limitation xxiii). |
| 2 | I² ⇒ pooled unusable but reported | **MISREAD** | "spuriously narrow and must not be quoted" is printed in both README and manuscript; operative interval = cluster-robust 12 strata. |
| 3 | 8 contamination notices ⇒ prior trust problem | **PARTIAL** | Trust is superseded by *independent re-derivation*: 60/60 transfer_result.json↔CSV gate (max diff 4.9e-7); splits byte-identical regeneration + 20/20 builder lockstep; checkpoint gate 60/60 + manifest 62/62; verify 12/12; pytest 11. The notices are why an auditor *can* check instead of trust. Residual: the count is a fair narrative-culture criticism — disclosed, not hidden. |
| 4 | Architectures stuck pre-2019 | **REAL (queued)** | Two registered architectures; BiMamba toy disclosed. Foundation-model re-grid = ledger C.2-class compute item; required for JBHI-tier, out of the registered CMPB claim. |
| 5 | Shift not decoupled from preprocessing/ontology | **PARTIAL** | L2 grid isolates resampling/leads/noise/gain (780 cells delivered); ontology half = A4 battery queued (2–5 GPU-days); the cross-corpus label-drift caveat is in the Data section. |
| 6 | No real-world hold-out | **REAL (author action)** | Public-data scope disclosed in Limitations; out of registered design; external hold-out needs governance/partner action — cannot promise in rebuttal. |
| 7 | Zero novelty | **PARTIAL (positioning)** | Boundary-characterization claim, not methods; repeat of triage A point 1. |
| 8 | OSF still v1; A3/A4 not in registration | **REAL, user-side, pending** | Paper text says exactly this for months; the update draft is authored (justification + files). Submitting it is the single mouse-action that closes the point — API probe still `in_progress`. |
| 9 | Single author + institution has no record | **PARTIAL: factual half outdated** | Second author added 2026-10-12 (title page, CRediT split, plurals, 83 pp recompiled). The "institution has no publication record" clause is not a valid review criterion for the contributions themselves; disregard in rebuttal. |
| 10 | 0.05 threshold unsupported | **PARTIAL** | Pre-registered operating value (protocol §9, frozen deposit) + DCA + Youden + leave-shift-type-out validation + Brier/NLL/classwise-ECE delivered. Add one Limitation sentence (zero compute) flagging author-set status — same as triage A. |
| 11 | Decomposition validated only synthetically; real-ECG identifiability not established | **PARTIAL, and half-wrong** | Identifiability WAS established on real cells: real-cell Fisher determinant 0.0093–0.016 >> τ = 1e-6 (rebuild_shapley_slopeT.csv); what fails on real data is **recovery accuracy** (RMSE 16.4x vs constant baseline; sign agreement = constant baseline) — *disclosed as a negative result*. "Real-data identifiability undetermined" is the one sentence wrong; "real-data recovery fails" is printed. |
| 12 | Negative wording lowers perceived contribution | **REAL but intentional** | Honest framing is the paper's identity (boundary study; all 15 counterexamples disclosed). Reverting wording would trade the strongest asset for cosmetics. |
| 13 | 2026-10-07→10-11 repository carried leak-era scripts | **REAL: disclosed, fixed** | Provenance note in README + ledger A3 (dated, tested end-to-end). No dispute; the "second pair of eyes" criticism is fair and the co-author partly addresses it going forward. |
| 14 | Only 20/60 retrained; the other 40 leak-era | **MISREAD** | Exposure-derived retrain scope: PTB-XL-source cells only; the 40 Chapman↔CPSC cells are structurally untouched by the leak (stated in the repair section with direction-dependence reasoning). |

## Delta queue added by this review (no duplicates of triage A)
- none — see triage A: sample-level/adaptive TS (cheap, queued),
  foundation-model re-grid (big, queued), external hold-out (author),
  one-sentence Limitation upgrade for the 0.05 operating value; **plus the one
  user-side action that already exists:** submit the OSF regulation-update
  draft (closes review point 8 end-to-end).

## Net classification unchanged
CMPB-ready with the strongest integrity story we can build; JBHI-tier
requires the two queued compute items + a governed external hold-out. Both
reviews now independently converge on the same frame our own adversarial
adjudication produced — with the second one factually misfiring on the three
load-bearing claims above.

— filed 2026-10-12; no manuscript change made by this triage itself.
