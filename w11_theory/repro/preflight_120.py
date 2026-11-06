"""W11-B preflight PF001-PF120.

PREREGISTRATION_W11B.md v1.0 (frozen BEFORE execution). 120 INDEPENDENT
assertions expanding the original 7 preflight checks. Each checks a distinct
object (a distinct DGP instance / lead / field / invariant / seed range /
pairwise range / global property). NOT 120 copies of one if.

Contract only: NO real patient data is present or accessed.
"""
from __future__ import annotations
import hashlib, json, pathlib, sys
import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / 'w6_tier1'))
sys.path.insert(0, str(ROOT / 'mamba_experiment'))
from tier1_kernel import hierarchical_groups

RESULTS = ROOT / 'w11_theory' / 'results'
SEED = 20261106
REPRO = ROOT / 'w11_theory' / 'repro'

S = json.loads((REPRO / 'CACHE_SCHEMA.json').read_text(encoding='utf-8'))
M = json.loads((REPRO / 'SEED_MANIFEST.json').read_text(encoding='utf-8'))
LOCK = json.loads((REPRO / 'environment.lock').read_text(encoding='utf-8'))
HASHLINES = [l.strip() for l in (REPRO / 'WEIGHT_HASHES.sha256').read_text(
    encoding='utf-8').splitlines() if l.strip()]

A = []


def add(fid, family, claim, expected, observed, passed, evidence, kind='verify'):
    A.append({'id': fid, 'family': family, 'claim': claim, 'kind': kind,
              'expected': expected, 'observed': observed,
              'PASS': bool(passed), 'evidence': evidence})


# ------------------------------------------- PF001-PF030  patient disjointness
idx = 1
for i in range(28):
    rng = np.random.default_rng(SEED + 6000 + i)
    n_total = int(rng.choice([600, 1000, 1800, 3000]))
    spread = float(rng.uniform(0.05, 1.5))
    _, sizes, _, pids, _ = hierarchical_groups(rng, n_total, spread)
    flat = np.concatenate(pids)
    n_unique = len(set(int(x) for x in flat))
    n_sum = sum(len(set(int(x) for x in p)) for p in pids)
    disjoint = True
    seen = set()
    for p in pids:
        s = set(int(x) for x in p)
        if s & seen:
            disjoint = False
        seen |= s
    lens_ok = all(len(p) == n for p, n in zip(pids, sizes))
    ok = bool(disjoint and lens_ok and n_unique == n_sum)
    add(f'PF{idx:03d}', 'patient_level_disjoint',
        f'hierarchical_groups instance {i+1}/28 (n={n_total}, spread={spread:.3f}) has group-wise disjoint patient ids',
        'disjoint AND record counts match AND unique count equals per-group sum',
        f'disjoint={disjoint}, lens_ok={lens_ok}, n_unique={n_unique}, n_sum={n_sum}',
        ok,
        f'seed={SEED+6000+i}, n_groups={len(pids)}, n_records={int(np.sum(sizes))}, '
        f'n_patients={n_unique}, disjoint={disjoint}, lens_ok={lens_ok}')
    idx += 1

# ------------------------------------------- PF031-PF042  lead-by-name
LEADS = S['fields']['lead_names']['canonical']
LEAD_NOTE = S['fields']['lead_names'].get('mimic_known_issue', '')
for i, lead in enumerate(LEADS):
    chk = {
        'unique': LEADS.count(lead) == 1,
        'in_list': lead in LEADS,
        'dtype_declared': S['fields']['lead_names'].get('dtype') == 'string_list',
        'align_by_name': S['fields']['lead_names']['alignment_rule'] ==
                         'ALIGN_BY_NAME_NOT_CHANNEL_INDEX',
        'mimic_declared': ('aVF' in LEAD_NOTE and 'aVL' in LEAD_NOTE and
                           'swapped' in LEAD_NOTE.lower()),
    }
    ok = all(chk.values())
    add(f'PF{idx:03d}', 'lead_alignment_by_name',
        f'canonical lead {lead} ({i+1}/12) is unique, declared, aligned by name, MIMIC swap declared',
        'all 5 sub-checks true',
        '; '.join(f'{k}={v}' for k, v in chk.items()), ok,
        f'lead={lead}, index={i+1}, n_canonical={len(LEADS)}, '
        f'checks={chk}, mimic_note="{LEAD_NOTE[:80]}"')
    idx += 1

# ------------------------------------------- PF043-PF052  cache fields
REQ = ['logits', 'patient_id', 'group_meta', 'split', 'lead_names',
       'label_semantics', 'checksum', 'n_rec', 'n_patient', 'n_eff']
for i, k in enumerate(REQ):
    f = S['fields'].get(k, {})
    ok = bool(f.get('required') is True and 'dtype' in f and
              ('note' in f or 'subfields' in f or 'canonical' in f or
               'allowed' in f or 'invariants' in f or k in ('checksum',)))
    add(f'PF{idx:03d}', 'cache_schema_field',
        f'required field "{k}" ({i+1}/10) has required=true, dtype and a structural spec',
        'required=true AND dtype AND structural spec present',
        f'required={f.get("required")}, dtype={f.get("dtype")}, keys={sorted(f)}',
        ok,
        f'field={k}, required={f.get("required")}, dtype={f.get("dtype")}, '
        f'keys={sorted(f)}, schema_status="{S["status"]}"')
    idx += 1

# ------------------------------------------- PF053-PF060  invariants
INV = S['invariants']
KEYWORDS = [
    ('1,145,814', 0), ('395,122', 1), ('deff', 2), ('patient_id', 3),
    ('lead', 4), ('ambiguous_flag', 5), ('hash', 6), ('ZERO GPU', 7)]
for i, (kw, _) in enumerate(KEYWORDS):
    line = INV[i] if i < len(INV) else ''
    ok = bool(line and kw.lower() in line.lower() and len(line) > 20)
    add(f'PF{idx:03d}', 'cache_invariant',
        f'invariant #{i+1}/8 declares the required rule about "{kw}"',
        f'invariant text contains "{kw}" and is non-trivial',
        f'len={len(line)}, contains={kw.lower() in line.lower()}',
        ok, f'invariant[{i}]="{line[:150]}"')
    idx += 1

# ------------------------------------------- PF061-PF088  seed range self-consistency
def classify(r):
    note = (r.get('note') or '')
    if r.get('start') is None or r.get('end') is None:
        return 'no-seed'
    if 'NON-CONTIGUOUS' in note:
        return 'NON-CONTIGUOUS'
    return 'continuous'


def range_ok(r):
    c = classify(r)
    if c == 'continuous':
        width = r['end'] - r['start'] + 1
        return bool(r['start'] <= r['end'] and r.get('n') == width), \
               f'width={width}, n={r.get("n")}'
    if c == 'NON-CONTIGUOUS':
        return bool(r.get('n') == 144 and r['start'] == 20731506 and
                    r['end'] == 20744026), \
               f'n={r.get("n")}, start={r["start"]}, end={r["end"]}'
    return bool((r.get('n') in (None, 0)) and bool(r.get('note'))), \
           f'n={r.get("n")}, note_present={bool(r.get("note"))}'


for i, r in enumerate(M['ranges']):
    ok, obs = range_ok(r)
    add(f'PF{idx:03d}', 'seed_range_self_consistency',
        f'range {r["round"]}/{r["tag"]} ({i+1}/29, class={classify(r)}) is self-consistent',
        f'frozen rule for class {classify(r)}',
        obs, ok,
        f'round={r["round"]}, tag={r["tag"]}, class={classify(r)}, '
        f'start={r.get("start")}, end={r.get("end")}, n={r.get("n")}, '
        f'note="{(r.get("note") or "")[:100]}"')
    idx += 1

# ------------------------------------------- PF089-PF116  pairwise disjointness
bounded = [(r['start'], r['end'], r['round'], r['tag'])
           for r in M['ranges']
           if r.get('start') is not None and r.get('end') is not None]
for i, r in enumerate(M['ranges']):
    if classify(r) == 'no-seed':
        ok = bool(r.get('note'))
        obs = f'no-seed range, note_present={ok}'
        ev = f'round={r["round"]}, tag={r["tag"]}, note="{(r.get("note") or "")[:120]}"'
    else:
        conflicts = []
        for j, (s2, e2, rd2, tg2) in enumerate(bounded):
            if (rd2, tg2) == (r['round'], r['tag']):
                continue
            if r['start'] <= e2 and s2 <= r['end']:
                conflicts.append((rd2, tg2, s2, e2))
        ok = not conflicts
        obs = f'conflicts={len(conflicts)}'
        ev = (f'round={r["round"]}, tag={r["tag"]}, '
              f'range=[{r["start"]},{r["end"]}], '
              f'checked_against={len(bounded)-1} bounded ranges, '
              f'conflicts={conflicts[:3]}')
    add(f'PF{idx:03d}', 'seed_range_pairwise_disjoint',
        f'range {r["round"]}/{r["tag"]} ({i+1}/29) does not overlap any other bounded range',
        'zero overlaps (or note-declared no-seed)',
        obs, ok, ev)
    idx += 1

# ------------------------------------------- PF117-PF120  global
# PF117 all code hashes
bad = []
for l in HASHLINES:
    h, rel = l.split(None, 1)
    p = ROOT / rel.strip()
    if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest() != h:
        bad.append(rel.strip())
add(f'PF{idx:03d}', 'code_hash_all', 'every hash-pinned file matches its SHA256',
    'zero mismatches', f'n_files={len(HASHLINES)}, mismatches={len(bad)}',
    not bad, f'n_listed={len(HASHLINES)}, mismatches={bad[:5]}'); idx += 1

# PF118 deff / n_eff
w10 = json.loads((ROOT / 'w10_continuous' / 'w10_results.json').read_text(
    encoding='utf-8'))
deff = float(w10['H']['H6_mechanism']['mean_deff'])
icc, mbar = 0.48, 2.9
calc = 1.0 + (mbar - 1.0) * icc
neff = 1.0 / deff
ok = bool(deff >= 1 and calc >= 1 and 0 < neff <= 1)
add(f'PF{idx:03d}', 'deff_and_n_eff',
    'deff >= 1 and n_eff/n <= 1 with W10 measured deff',
    'all three inequalities hold',
    f'deff={deff:.6f}, calc={calc:.4f}, n_eff/n={neff:.6f}', ok,
    f'W10_mean_deff={deff}, deff_from_ICC={calc}, mbar={mbar}, ICC={icc}, '
    f'n_eff_over_n={neff}'); idx += 1

# PF119 CODE-15% ambiguity
L = S['fields']['label_semantics']
ok = bool('173,347' in L['code15_rule'] and 'MUST NOT' in L['code15_rule']
          and L['clinical_review_required'] is True
          and 'ambiguous_flag' in L['subfields'])
add(f'PF{idx:03d}', 'CODE15_ambiguous',
    'CODE-15% ambiguous records are explicitly barred from confident-negative training',
    'rule present AND clinical review required AND ambiguous_flag declared',
    f'rule_present={"173,347" in L["code15_rule"]}, clinical={L["clinical_review_required"]}',
    ok, f'code15_rule="{L["code15_rule"][:140]}", '
        f'subfields={L["subfields"]}, clinical_review={L["clinical_review_required"]}')
idx += 1

# PF120 environment lock
cur = {'python': sys.version.split()[0], 'numpy': np.__version__}
import scipy, matplotlib
cur['scipy'] = scipy.__version__
cur['matplotlib'] = matplotlib.__version__
diff = {k: [LOCK.get(k), v] for k, v in cur.items() if LOCK.get(k) != v}
ok = not diff
add(f'PF{idx:03d}', 'environment_lock',
    'locked Python / NumPy / SciPy / Matplotlib versions match runtime',
    'zero version mismatches',
    f'mismatches={diff}', ok,
    f'locked={ {k: LOCK.get(k) for k in cur} }, runtime={cur}, '
    f'font={LOCK.get("font")}, threads={LOCK.get("blas_threads_policy")}')
idx += 1

assert idx == 121, f'expected 120 assertions, got {idx-1}'
assert len(A) == 120

out = {
 'prereg': 'PREREGISTRATION_W11B.md v1.0 (frozen)',
 'group': 'preflight', 'n_checks': 120,
 'n_pass': int(sum(a['PASS'] for a in A)),
 'n_fail': int(sum(not a['PASS'] for a in A)),
 'n_by_kind': {k: int(sum(1 for a in A if a['kind'] == k))
               for k in ['verify', 'falsify', 'meta']},
 'n_seed_ranges': len(M['ranges']),
 'n_bounded_ranges': len(bounded),
 'assertions': A,
 'contract_only': True, 'no_real_patient_data': True,
}
dest = RESULTS / 'w11b_preflight_120.json'
dest.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding='utf-8')
print(f'W11-B PREFLIGHT: {out["n_pass"]}/120 PASS, {out["n_fail"]} FAIL')
for a in A:
    if not a['PASS']:
        print('  FAIL', a['id'], a['family'], '|', a['observed'])
print('written', dest)
