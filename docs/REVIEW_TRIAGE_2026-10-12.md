# Review triage — 2026-10-12: the "7 fatal problems" report against the delivered artifacts

**Input:** an external review recommending Reject (7 claimed killer issues).
**Method:** every point is mapped against the *delivered* artifacts (paper
`main_cmpb.tex` at 83 pp, `results/`, `docs/CORRECTIONS_LEDGER_2026-10-11.md`).
Verdicts: **MISREAD** (the paper already does it — paper section cited for the
rebuttal), **PARTIAL** (some mitigation exists, named residual), or **REAL**
(genuine gap; → queued with cost, consistent with ledger C).

| # | Review's claim | Verdict | Evidence in the delivered record | Rebuttal-ready line | Actual residual action |
|---|---|---|---|---|---|
| 1 | "Zero methodological novelty; confirms a phenomenon" | **PARTIAL (position, not error)** | Novelty was never claimed as methods: contributions are C1–C5 *boundary characterization* ("first systematic characterization in cross-corpus ECG", Related Work L280 cites Ovadia 2019 openly). Reviewer's own write-up concedes statistics are the strength. | "The paper does not claim new methods; it claims the missing boundary quantification (multi-seed, pre-registered, 15 counterexamples disclosed) for a deployment-relevant modality — reproducible end-to-end (verify 12/12)." | None needed for CMPB-level; for a higher venue see ledger C.2–C.3. |
| 2 | "'Distribution shift' not decoupled from preprocessing/sampling-rate/label ontology" | **PARTIAL** | Isolated-factor shifts ARE a registered experiment family: the L2 eval-time grid separates resampling (fs250/fs125), lead drop (leads1–6), noise SNR ladder, gain — 390/780-cell results + `recompute_deployment_780grid.py`. Cross-corpus label-ontology drift is disclosed (A3: CPSC MI entirely from CPSC-Extra SNOMED; paper Data §). | "Degradation sources are already measured separately: the preregistered L2 grid isolates resampling/leads/noise/gain, and the I²≈99.98% figure you cite is exactly why all inference is stratified (cluster-robust 12-stratum interval), not pooled." | The §10 mapping-sensitivity battery (A4, 2–5 GPU-days, queued) is the honest closure of the ontology half. |
| 3 | "Only TS and Platt tested; 2020s calibration literature missing" | **MISREAD (factually wrong for half the list)** | The delivered pool is **8 methods**: ts, per-class Platt, isotonic (OvR), Vector scaling, Matrix scaling, **Dirichlet calibration (Kull 2019 — cited)**, EM prior adaptation (Saerens), BBSE (Lipton 2018) — Results 5.3 table (isotonic 12/30, Dirichlet 16/30 …) + 8-method Results section + dose-response × 5 methods. Cumulative 480-row table + per-branch recheck artifact. | "Seven recalibration families beyond TS are delivered and reported (incl. Dirichlet, Kull 2019; BBSE; EM), plus meta-analysis and a dose-response study over all 8; the *not delivered* subset (CORAL, TTA, MC-Dropout, oracle) is a **registered deviation with limitations entry**." | Sample-level/adaptive TS is a genuine untested baseline → queued (cheap: reuses caches; add to compute list). Fine-tune baseline: author decision (compute). |
| 4 | "The 0.05 threshold has no source; no NLL/Brier/reliability" | **MISREAD on metrics; PARTIAL on threshold** | Metrics: SmoothECE primary + **Brier Murphy decomposition, classwise-ECE, NLL, reliability diagrams** are all DELIVERED (registration-methods text L513ff; results tables brier/reliability + 60 diagrams as supplementary). Threshold: 0.05 is **pre-registered** (protocol §9, OSF-frozen with dated amendments) — the review's "no source" skips that it is a *registered* author-chosen operating value, and its status is stated. | "The 0.05 bar is not post-hoc: it is a pre-registered operating value (protocol §9, dated in the frozen deposit), and the paper additionally reports DCA, Youden sweeps, leave-shift-type-out validation, and multi-metric (Brier/NLL/classwise-ECE) provenance." | One sentence upgrade (zero compute): flag in Limitations that 0.05 is an author-set registered operating point, not literature-derived; suggest multi-metric gate as sensitivity check (Brier already delivered, one table). |
| 5 | "Architecture stuck in 2019; no 2024+ foundation model" | **REAL (acknowledged)** | Limitation (i)-class entry already exists; BiMamba exists only as a toy (n=60 records, disclosed). Related Work §2.4 cites the 2024–2026 foundation-model line (ECGFounder, ECG-FM, HeartLang, ADAPTOOD). | "The boundary claim is scoped to the two registered architectures; foundation-model recalibration is named future work (Limitations)." | Re-grid with one 2024+ pretrained model — the largest compute item; required for JBHI-tier, **not** required for the registered CMPB claim. (Ledger C.3) |
| 6 | "Single author + preregistered G endpoint never delivered" | **PARTIAL but fast-moving** | (a) Second author added 2026-10-12 (CRediT split; cover letter updated) — the review was written before this. (b) G-undelivered is **self-declared** in Limitations (xviii) and is now *the very reason A4 exists*: A4 re-operationalizes the §10 gate on the delivered endpoint, registered **anti-HARKing (before any variant result exists)**. | "Single-author status was addressed by a co-author. G is disclosed as undelivered in the manuscript itself, and amendment A4 converts the defect into a registered, pre-result criterion — the opposite of selective reporting." | None for CMPB; the OSF addendum/v2 notes the author-list update. |
| 7 | "No real-world hold-out; zero real-world validation" | **REAL for real-world; MISREAD on 'S2 learning curve missing'** | Real-world: TRUE — all corpora are public (disclosed; Limitations data entry). Learning curve: **already exists** — `s2_dose_response.csv`: 5 budgets (20/50/100/250/…/1000 fresh labeled target samples × 5 methods × 60 cells × 20 repeats ≈ 30,000 rows); headline: platt@50 +0.150 (60/60), ts@50 +0.127 (60/60) — a CEC-recovery learning curve to one significant digit. | "The S2 protocol you ask for already exists as 30,000-row dose-response results; the open point is only an *external* hold-out, which is outside the registered scope and named as such." | External/clinical hold-out is an author-action item (coop., governance) — explicitly out of the registered scope; keep in limitations, not in rebuttal promises. |

## Structural verdict on the report

The report's七-point frame maps almost one-to-one onto our own 13-agent
adjudication (final score band, venue call): its **real** items (#2-ontology
half, #3-sample-level TS, #5-foundation model, #7-external hold-out) are the
**same** compute/author-action items already queued in ledger C — its facts
about the delivered set are wrong for #3 metrics and #7 learning-curve, and
its CMPB-level fallback venue call ("Physiological Measurement") matches our
adjudicator's banding. Nothing in it changes the classification: **CMPB-ready
with the best-in-class integrity story; not a JBHI paper without the two big
compute items.**

## Concrete additions this review adds to the queue (delta, not replacements)

1. Sample-level/adaptive TS baseline over the 60-cell caches (cheap, closure of
   review #3's sharpest line).
2. 2024+ foundation-model re-grid (expensive; only if targeting JBHI upward).
3. External hold-out (author action, governance-bound).

— filed against the delivered record on 2026-10-12; no manuscript change
required by this triage itself.
