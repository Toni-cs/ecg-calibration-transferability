# Preregistration ↔ manuscript ↔ release: alignment audit

**Method.** Read-only queries against the public OSF API on **2026-10-05**
(`api.osf.io/v2/nodes/53h64`, `/registrations/wjz3y`, `/nodes/53h64/files/osfstorage`,
`/nodes/53h64/children`), compared against the manuscript (`paper/main_bspc.tex`,
line numbers = the current lab copy) and against this repository. Nothing was
written to OSF; nothing in the frozen registration can be written anyway — OSF
registrations can only be withdrawn, never edited.

**Records compared**

| Record | Identifier | Frozen at |
|---|---|---|
| Project deposit (mutable files + description) | OSF `53h64` | description last modified 2026-09-18 |
| Registration (immutable) | OSF `wjz3y` | registered 2026-09-14T02:55:44Z |
| Protocol deposited in both | `02_PROTOCOL_ZH_original.md` | SHA-256 `0e8afa923986aba3…` |

---

## Findings

| # | Finding | Severity | Who can fix it |
|---|---|---|---|
| F1 | OSF project **and** registration descriptions still link the old GitHub account `gt17641001169-design` | **Blocking** | Author, on the OSF project page (registration: cannot) |
| F2 | Manuscript says *all three* amendments are archived at the OSF DOI; **A3 is not in the deposit** | **Blocking** | Author: upload A3, or change the sentence |
| F3 | Frozen registration carries superseded counts **51/60 → 45/60**; manuscript now says **50/60 → 44/60** | Explain (immutable) | Author: one clause in the manuscript |
| F4 | Registration "Analysis plan" field is narrower than what the manuscript calls registered | Explain / addendum | Author: addendum file on the (mutable) project |
| F5 | Frozen protocol's deviation-registry rows quote pre-correction numbers (29/60, R² upper 0.104) | Info (already reconciled in text) | None — read the note below |
| F6 | Manuscript dates `docs/osf_archive_manifest.json` to 2026-09-05; the file says 2026-09-16 | Fix in text | Author: one word |
| F7 | The release shipped no `docs/` while 11 shipped files cited it | **Fixed in this working tree** | — |
| F8 | Design, CI, family, and L2 coverage statements agree across all three records | OK | — |

---

### F1 — the old repository URL is live on OSF

The OSF **project description** (and its frozen copy inside the registration)
contains, under `RELATED MATERIAL`:

```
https://github.com/gt17641001169-design/ecg-calibration-transportability
```

Repository side, the old handle now appears **nowhere**: `git grep gt17641001169`
over the working tree returns nothing, and over `HEAD` it returns exactly one hit —
`LICENSE:3`, the copyright-holder string, already corrected to `Toni Guan`. Every
GitHub URL in the repository already uses the current account:

- `CITATION.cff:14` `repository-code: "https://github.com/Toni-cs/ecg-calibration-transportability"`
- `README.md:112` (release asset), `README.md:315` (BibTeX `url`), `README.md:323` (issues)
- `git remote -v` → `origin https://github.com/Toni-cs/ecg-calibration-transportability.git`

So the citation block the reviewer would check is clean; **the stale URL is on OSF**,
which is exactly where a referee follows the Data-availability DOI. The paste source
still sits in the lab tree at `paper/osf_upload/_local_notes/OSF_PASTE_VALUES.md:61,120`
and `OSF_PROJECT_DESCRIPTION.md:31`.

**Action.** Edit the OSF *project* description (Metadata → Description) to
`https://github.com/Toni-cs/ecg-calibration-transportability`. The registration
froze the same text on 2026-09-14 and cannot be edited; note that fact in the
manuscript only if a referee raises it.

### F2 — "all three amendments … archived at" the OSF DOI is not true today

`main_bspc.tex:2511-2513`:

> The protocol, all three amendments (A1, A2, A3), and a per-file archival-status
> report are publicly archived at `https://doi.org/10.17605/OSF.IO/53H64`.

The public file listing for `53h64` returns **11 files, no folders**: the protocol
(EN + ZH), amendment 1 (EN + ZH), amendment 2 (EN + ZH), two hash manifests, the
revision log, the archival-status report, `SHA256SUMS.txt` — and the children
endpoint returns **0 components**. The newest `date_modified` in the deposit is
2026-09-14; A3 is dated 2026-09-16, and the registration itself was taken
2026-09-14. The project description agrees with the files, not with the paper:
*"The experiment protocol and its **two** amendments…"*, as does
`09_REVISION_LOG.md` (*"the protocol, both amendments, and the archival-status report"*).

The manuscript's own §A3 says A3 was deliberately kept out of the registered pair
(`main_bspc.tex:539-541`: *"The registered protocol snapshots are left byte-identical
and A3 is archived separately"*) — so the intent is defensible, but the Data
availability sentence contradicts it, and `main_bspc.tex:527-528` points at
`docs/PROTOCOL_AMENDMENT_A3_CORPUS_IDENTITY.md`, a path that did not exist in the
release until this working tree.

**Action (pick one).** (a) Upload `PROTOCOL_AMENDMENT_A3_CORPUS_IDENTITY.md` to the
project and change the description's "two amendments" → "three"; or (b) rewrite the
sentence to say where A3 actually lives (this repository's `docs/`, bundled with the
submission). Option (a) is stronger — the before/after pair then exists publicly.

### F3 — the frozen registration still quotes 51/60 and 45/60

Registration `wjz3y`, response **344-79 (Missing data)**:

> Six supporting cells with degenerate CI widths (< 3e-4) are reported alongside the
> count that excludes them (**45/60 rather than 51/60**).

The manuscript (`main_bspc.tex:74-77`) now reads **50/60 (83.3%)** … *excluding the
six degenerate-CI cells leaves **44/60** (73.3%)*. The offset is internally
consistent (both old and new counts lose the same six cells), so this is the known
label-encoding re-run showing up after the registration was frozen, not an analysis
change.

The registration **cannot** be corrected. The manuscript should say so in one
clause, e.g. in the archival-status section: *counts in the registration predate the
2026-09-17 label-encoding re-run (51/60 → 50/60, and 45/60 → 44/60 after excluding
the six degenerate-CI cells); the criterion's verdict is unchanged.*

Everything else in the registration that was rechecked agrees (F8).

### F4 — the registered analysis plan is narrower than the reported analysis

Registration response **344-71 (Analysis plan)** lists exactly: BCa operating
interval (B = 10,000, full 60-cell grid), historical percentile intervals retained
as provenance, BH-12 with Bonferroni-12 as sensitivity, and fixed-effect +
DerSimonian-Laird pooling. It does **not** mention:

1. the label-free predictability failure branch (LOO R² 95% CI upper < 0.5 →
   downgrade to a two-step chain);
2. the S2 small-sample dose-response (budgets 50/100/250/500/1000);
3. the cluster-robust pooled interval over the 12 strata;
4. the discrimination (AUROC) component of the deployment gate.

Item 1 **is** preregistered — just not in that form field: it is written into the
deposited protocol, `docs/EXPERIMENT_PROTOCOL.md:168-174` (§8.5), repeated at `:449`,
in the file whose SHA-256 equals the OSF deposit's `02_PROTOCOL_ZH_original.md`.
So the manuscript's claim that the threshold is *"pre-registered"*
(`main_bspc.tex:1096-1097`) **is** verifiable by a third party against the deposit —
the gap is discoverability, not provenance. Item 2 lives in protocol §5; item 3 is a
later robustness addition; item 4 is registered only in its C5 form
(response 344-77: *"the C5 deployment gate requires accuracy >= the source-domain
baseline in addition to a positive dECE_OOD"*).

**Action.** Since the registration is immutable, add an **analysis-plan addendum**
file to the *project* (which accepts new files): one table mapping each reported
analysis → protocol § / amendment / registration field, and explicitly labelling
items introduced after 2026-09-14 as *post-registration robustness analyses*. That
closes the "the paper analyses more than it registered" objection without touching
the frozen record.

### F5 — pre-correction numbers inside the frozen protocol (no action)

`docs/EXPERIMENT_PROTOCOL.md:236` (registry row A2, dated 2026-09-07) still reads
*"(CI contains 0 ≥80%) measured 29/60=48.3% and failed"* and *"failure branch R² CI
upper bound 0.104<0.5"*. Both were superseded later: the BCa full-grid re-run moved
the boundary count to 23/60 = 38.3% (`docs/ROUND8_AUDIT_AND_FIXES.md:58`), and
`reports/NUMBER_PROVENANCE_SWEEP_2026-09-17.md:136` records 0.104 as *not
reproducible* (current input gives 0.292).

The manuscript already carries both calibers where it matters — `main_bspc.tex:482`,
`:821`, `:2394` state *"percentile CIs gave 29/60 = 48.3%"* beside the BCa value,
and the body no longer cites 0.104 at all (it survives only in commented audit
notes at `:1368` and `:1383`, now using 0.371 at `:1097`). Frozen documents are
supposed to keep the numbers they had on the day; nothing to change here.

### F6 — one date to correct in the manuscript

`main_bspc.tex:2513-2514`: *"`docs/osf_archive_manifest.json` is the internal
snapshot taken on 2026-09-05"*. The file's own header says
`"timestamp_utc": "2026-09-16T02:44:47.871553+00:00"` (`docs/osf_archive_manifest.json:2`).
2026-09-05 is the date of the *baseline* manifest —
`07_HASH_MANIFEST_baseline_2026-09-05.json`, taken 2026-09-05T04:19:46Z
(`README_ARCHIVAL_STATUS.md:10`). Change "2026-09-05" → "2026-09-16", or name the
baseline manifest instead.

### F7 — the release's missing `docs/` (fixed here)

Eleven shipped files referenced `docs/` paths that did not exist:

| Cited path | Referenced by |
|---|---|
| `docs/PROTOCOL_AMENDMENT_A3_CORPUS_IDENTITY.md` | `results/_ABLATION_TS_COMPONENTS_CONTAMINATION_NOTICE.md:14`, `results/_L2_SHIFT_CONTAMINATION_NOTICE.md:15`, `results/_TEMPERATURE_CONTAMINATION_NOTICE.md:8`, `src/data/mapping.py:11` |
| `docs/EXPERIMENT_PROTOCOL.md` | `src/data/mapping.py:3`, `scripts/noise_floor_signed.py:142`, `scripts/run_s2_small_sample.py:3`, `scripts/validate_decomposition.py:4` |
| `docs/osf_archive_manifest.json` | `results/_SUPPLEMENTARY_WINDOW_NOTICE.md:75` |
| `docs/adversarial_r1_attack_e1b.md` | `results/_LOCO_CONTAMINATION_NOTICE.md:77` |
| `docs/p0r2_final_verdict.md` | `scripts/run_e1a_l2_shift_full.py:187` |

The manuscript cites two of them as well (`main_bspc.tex:520-521` and `:527-528`).
All are now present, plus the `reports/` documents and audit scripts those files
themselves cite. Internal-reference scan: **424 references, 0 unresolved** — see
[`README.md`](README.md).

### F8 — what already agrees

| Statement | Registration | Manuscript | Artifact |
|---|---|---|---|
| Grid = 6 pairs × 2 arch × 5 seeds = 60 | 344-40, 344-51 | `:74-75` | `results/robustness_validation_5seeds.csv` |
| Operating CI = patient-level cluster BCa, B = 10,000, full grid | 344-71 | `:481` | `results/bootstrap_diagnostics.csv` |
| ID-boundary criterion failed, branch triggered | 344-2: 23/60 = 38.3% | `:79`, `:481` | same |
| Confirmatory family 156 → 12 (amendment A2) | 344-2 | `:514-521` | `docs/PROTOCOL_AMENDMENT_A2_FAMILY_REDUCTION.md` |
| L2 coverage 157 of 390 cells, 2 seeds, one architecture | 344-81 | `:1275-1295` | `results/deployment_metrics.csv` (157 rows) |
| All 60 results reported incl. 9 counter-examples | 344-79 | `:745` | `results/counterexample_discrimination.csv` |
| Predictability failure threshold 0.5 | protocol §8.5 (deposited) | `:1096-1101` | `results/predictability_3arch.csv` |

---

## Punch list

**On OSF (author, ~10 minutes, all on the mutable project):**

1. Project description: replace the old GitHub URL (F1) and "its two amendments" →
   "its three amendments" **iff** A3 is uploaded first (F2).
2. Upload `docs/PROTOCOL_AMENDMENT_A3_CORPUS_IDENTITY.md` (F2, option a).
3. Optionally upload an analysis-plan addendum file (F4).

**In the manuscript (next revision, three edits):**

4. `:2511-2513` — reconcile the "all three amendments archived at OSF" sentence with
   whatever action is taken in (2) (F2).
5. `:2513-2514` — "snapshot taken on 2026-09-05" → 2026-09-16 (F6).
6. Archival-status section — one clause reconciling 51/60 → 50/60 and 45/60 → 44/60
   against the frozen registration (F3).

**Already done in this working tree:**

7. `docs/`, `reports/`, and the audit scripts now ship; all internal references
   resolve; the three OSF-identical protocol files are byte-verified (F7).

---

## Addendum 2026-10-17: resolution status of F1-F8

Disposition as of the 2026-10-15/17 audit-and-fix waves (see
CORRECTIONS_LEDGER_2026-10-11.md and
FINAL_ADVERSARIAL_AUDIT_2026-10-15.md [manuscript-tree doc] in the manuscript tree):

- **F1 (OSF description links the old account) - STILL OPEN, author-side.**
  The replacement description text is prepared
  (OSF_DESC_FULL_2026-10-12.txt); applying it is an OSF-web/API action on
  project 53h64 that only the account owner can perform. Unchanged by the
  frozen-v1 doctrine (the deposit and registration metadata are separate
  editable surfaces).
- **F2 (A3 "archived at the OSF DOI" not true) - RESOLVED 2026-10-11.**
  A3 and A4 were uploaded to the project deposit (53h64, Files, 2026-10-11);
  SHA-256 verified against the repository copies (A3 2025126e...,
  A4 cfc8955...). The registration-metadata related-material link itself
  was corrected on 2026-10-11 (API-verified).
- **F3 (frozen registration quotes 51/60 -> 45/60) - COVERED in the
  manuscript.** The archival-status section narrates both retraining events
  and the frozen figure set (nine counter-examples, 51/60, 45/60-ex-six),
  states that the delivered values differ by both events, and adds the
  frozen ID-boundary figure (23/60 = 38.3% -> 30/60 = 50.0%) with the branch
  trigger unchanged.
- **F4 (registered analysis plan narrower than reported analysis) - PARTIALLY
  ADDRESSED; upload of the analysis-plan addendum to the deposit remains an
  author-side action** (OSF_JUSTIFICATION_2026-10-12.txt /
  OSF_ADDENDUM_2026-10-12.md prepared).
- **F5 - no action by design (pre-correction numbers inside the frozen
  protocol are historical record).**
- **F6 (one date to correct) - VERIFIED CORRECT in the manuscript**: the
  baseline freeze (2026-09-05) and the internal snapshot
  (docs/osf_archive_manifest.json, 2026-09-16) are distinguished explicitly.
- **F7 - shipped and reference-closure-checked (424 internal references,
  0 unresolved at last run).**
- **F8 - standing agreement, unchanged.**
