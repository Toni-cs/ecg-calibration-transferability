# `docs/` — preregistration record and audit trail

This directory was **missing from the release**: eleven files that ship in the
repository (five `results/*NOTICE.md` files, four scripts, `src/data/mapping.py`)
pointed at `docs/...` paths that did not exist, and the manuscript itself cites
two of these files as the archival location of its amendments. It is now present,
copied byte-for-byte from the development tree.

## Provenance of each file

| File | What it is | Verified against |
|---|---|---|
| `EXPERIMENT_PROTOCOL.md` | The preregistered experiment protocol (Chinese original — the record of authority). §7 fixes the operating CI, §8-2/§8-3 the synthetic decomposition validation, §8.5 the label-free predictability failure branch. | SHA-256 `0e8afa923986aba3…` = OSF `02_PROTOCOL_ZH_original.md` → **byte-identical to the deposited preregistration** |
| `PROTOCOL_AMENDMENT_A1_PREREG_RELOCATION.md` | Amendment A1 — primary endpoint relocated to ΔECE_OOD. | SHA-256 `9251eaefd9b7652…` = OSF `04_AMENDMENT_1_ZH_original.md` → byte-identical |
| `PROTOCOL_AMENDMENT_A2_FAMILY_REDUCTION.md` | Amendment A2 — confirmatory family reduced 156 → 12. | SHA-256 `6ef3b46ff238f50…` = OSF `06_AMENDMENT_2_ZH_original.md` → byte-identical |
| `PROTOCOL_AMENDMENT_A3_CORPUS_IDENTITY.md` | Amendment A3 — corpus identity (CPSC2018 not "CPSC2018+2019") and MI provenance. | **In the project deposit (53h64 Files)** — uploaded 2026-10-11, SHA-256 `2025126e…` verified bit-identical to this repository copy; the frozen registration WJZ3Y still carries v1 (update draft in progress) |
| `PROTOCOL_AMENDMENT_A4_MAPPING_SENSITIVITY.md` | Amendment A4 (2026-10-11) — re-operationalizes the §10 mapping-sensitivity gate on delivered ΔECE_OOD (the registered G endpoint is undelivered; Limitations xviii); variants V1/V2 enumerated, V3 excluded with reason; criterion defined before any variant result exists. | **In the project deposit (53h64 Files)** — uploaded 2026-10-11, SHA-256 `cfc8955…` verified; frozen registration WJZ3Y update draft in progress |
| `CORRECTIONS_LEDGER_2026-10-11.md` | The point-in-time reconciliation of the 2026-10-10/11 integrity review (A1–A17, each mechanically verified) + calibration of earlier audit generations. | **In the project deposit (53h64 Files)** — uploaded 2026-10-11, SHA-256 `75bd139…` verified |
| `OSF_ADDENDUM_2026-10-12.md` | The F1/F2/F3 closure statement for the OSF deposit (dead-link correction already applied 2026-10-11 in the registration metadata; the four closure files; the frozen 51/60 → 50/60 → 45/60 evolution with the不可改 principle). | **In the project deposit (53h64 Files)** — uploaded 2026-10-11, SHA-256 `97d3c42a…` verified |
| `osf_archive_manifest.json` | Internal 14-file SHA-256 snapshot, `timestamp_utc` **2026-09-16T02:44:47**. | Self-describing; `_post_manifest_corrections` records post-snapshot drift |
| `OSF_MANIFEST_POST_CORRECTIONS_2026-09-16.md`, `…_2026-09-17.md` | Drift audits of that snapshot (which recorded hashes changed, which are still recoverable). | Cited by `osf_archive_manifest.json:82` |
| `ROUND8_AUDIT_AND_FIXES.md` | R8 independent adversarial audit: the 21 manuscript fixes and the deviation registry they feed. | Cited by `docs/EXPERIMENT_PROTOCOL.md:236` |
| `p0r2_final_verdict.md`, `p0_final_verdict.md`, `adversarial_r1_attack_e1b.md`, `Q2_UPGRADE_PROPOSAL_R5.md` | Internal adversarial-review records, cited as evidence by scripts and contamination notices. | Cited by `scripts/run_e1a_l2_shift_full.py:187`, `results/_LOCO_CONTAMINATION_NOTICE.md:77`, etc. |

Verify the three OSF-identical files yourself:

```bash
sha256sum docs/EXPERIMENT_PROTOCOL.md docs/PROTOCOL_AMENDMENT_A*.md
# then compare with the OSF public file listing:
#   https://api.osf.io/v2/nodes/53h64/files/osfstorage/?format=json
# The sha256 in each file's `extra.hashes` must match exactly.
```

## What else was added to make the references resolve

- `reports/` (10 files) — audit reports cited by the `results/*NOTICE.md` files and
  by `src/utils/encoding_guard.py:23`. Every notice in this repository now leads
  to the document that justifies it.
- 29 audit / probe / verification scripts under `scripts/` (e.g.
  `verify_l2_shift_encoding.py`, `rebuild_missing_probs_cache.py`,
  `probe_mamba_*.py`) plus `src/models/mamba_chunked.py` — the tools the notices
  and reports name when they say how a contaminated table was diagnosed.

None of these added scripts is part of the documented pipeline: the
[paper-to-artifact map](../README.md#paper-to-artifact-map) still names exactly one
writer per shipped result table. The added scripts are one-off audit instruments;
they are included so that every citation in this repository resolves to a real
file, and **none of them was executed while preparing this release**. All of them
are `py_compile`-clean.

## Reference closure

A scan of every `docs/…`, `reports/…`, `scripts/…` and `src/…` path written in any
`.py` / `.md` / `.json` / `.txt` file of this repository reports
**424 internal references, 0 unresolved targets**. Re-run that check after editing:

```bash
python - <<'PY'
import os, re
pat = re.compile(r'\b(docs|reports|scripts|src)/[A-Za-z0-9_./-]+\.(?:md|json|py|csv|txt)')
miss = {}
for r, ds, fs in os.walk('.'):
    ds[:] = [d for d in ds if d not in ('.git', '__pycache__', '.pytest_cache')]
    for fn in fs:
        if not fn.endswith(('.py', '.md', '.json', '.txt', '.cff')):
            continue
        p = os.path.join(r, fn)
        t = open(p, encoding='utf-8', errors='replace').read()
        for m in pat.finditer(t):
            ref = m.group(1) + '/' + m.group(0).split('/', 1)[1]
            if not os.path.exists(ref):
                miss.setdefault(ref, set()).add(os.path.relpath(p, '.'))
print('unresolved:', len(miss))
for k in sorted(miss):
    print(' ', k, '<-', ', '.join(sorted(miss[k])))
PY
```

## Read next

[`PREREGISTRATION_ALIGNMENT.md`](PREREGISTRATION_ALIGNMENT.md) — file-by-file
comparison of what the OSF registration says, what the protocol says, and what the
manuscript says, including the places where they still disagree and who can fix
each one. It was produced by reading the public OSF API on 2026-10-05 (read-only)
and comparing it with this repository and the manuscript.
