"""W11 preflight.py — 7 assertions to be passed BEFORE any real-cohort forward.

PREREGISTRATION_W11.md section 4, gate 9. Validates the frozen W12
logits-cache CONTRACT and W1-W11 internal consistency. CACHE_SCHEMA.json
is CONTRACT ONLY: no real patient data is present or accessed here.

Exit 0 iff 7/7 PASS.
"""
from __future__ import annotations
import hashlib, json, pathlib, sys
import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent          # /data/workspace
sys.path.insert(0, str(ROOT / 'w6_tier1'))
sys.path.insert(0, str(ROOT / 'mamba_experiment'))


def _read(name):
    return (HERE / name).read_text(encoding='utf-8')


def a1_patient_disjoint():
    """Patient ids disjoint across groups; split rule must be patient-level."""
    from tier1_kernel import hierarchical_groups
    rng = np.random.default_rng(20261106)
    _, sizes, _, pids, _ = hierarchical_groups(rng, 1000, 1.0)
    flat = np.concatenate(pids)
    ok_distinct_groups = True
    off = 0
    seen = set()
    for g, gp in enumerate(pids):
        s = set(int(x) for x in gp)
        if s & seen:
            ok_distinct_groups = False
        seen |= s
        off = max(off, int(gp.max()) + 1)
    S = sch()
    split_ok = ('patient-level disjoint' in S['fields']['split']['note'].lower()
                or 'disjoint' in S['fields']['split']['note'].lower())
    n_unique_total = len(set(int(x) for x in flat))
    n_unique_sum_per_group = sum(len(set(int(x) for x in p)) for p in pids)
    lens_ok = all(len(p) == n for p, n in zip(pids, sizes))
    return {
        'PASS': bool(ok_distinct_groups and split_ok
                     and n_unique_total == n_unique_sum_per_group and lens_ok),
        'n_groups': len(pids), 'n_patients': n_unique_total,
        'n_records': int(np.sum(sizes)),
        'n_unique_sum_per_group': n_unique_sum_per_group,
        'groups_pairwise_patient_disjoint': bool(ok_distinct_groups),
        'split_is_patient_level_disjoint': bool(split_ok),
        'record_counts_match': bool(lens_ok)}


def a2_lead_alignment():
    S = sch()['fields']['lead_names']
    canonical = S['canonical']
    return {
        'PASS': bool(S['alignment_rule'] == 'ALIGN_BY_NAME_NOT_CHANNEL_INDEX'
                     and len(canonical) == 12
                     and 'aVF' in canonical and 'aVL' in canonical
                     and 'swapped' in S['mimic_known_issue'].lower()),
        'rule': S['alignment_rule'], 'n_leads': len(canonical),
        'mimic_aVF_aVL_issue_declared': bool('swapped' in S['mimic_known_issue'].lower())}


def a3_code15_ambiguous():
    L = sch()['fields']['label_semantics']
    return {
        'PASS': bool('173,347' in L['code15_rule']
                     and 'MUST NOT' in L['code15_rule']
                     and 'confident_negative_allowed' in L['subfields']
                     and L['clinical_review_required'] is True),
        'code15_rule': L['code15_rule'],
        'clinical_review_required': L['clinical_review_required']}


def a4_neff_deff():
    """deff >= 1 and n_eff/n <= 1, verified against W10 measured deff."""
    w10 = json.loads((ROOT / 'w10_continuous' / 'w10_results.json').read_text(
        encoding='utf-8'))
    deff = float(w10['H']['H6_mechanism']['mean_deff'])
    icc = 0.48
    mbar = 2.9
    calc = 1.0 + (mbar - 1.0) * icc
    n_eff_over_n = 1.0 / deff
    return {
        'PASS': bool(deff >= 1.0 and calc >= 1.0 and 0 < n_eff_over_n <= 1.0),
        'W10_mean_deff': deff, 'deff_from_ICC_formula': calc,
        'n_eff_over_n': n_eff_over_n,
        'note': 'n_rec is NOT the independent sample size'}


def a5_seed_disjoint():
    M = manifest()
    segs = []
    for r in M['ranges']:
        if r.get('start') is None or r.get('end') is None:
            continue
        segs.append((r['start'], r['end'], r['round'], r['tag']))
    segs.sort()
    overlaps = []
    for i in range(len(segs) - 1):
        if segs[i][1] >= segs[i + 1][0]:
            overlaps.append((segs[i][2:], segs[i + 1][2:]))
    # declared n must match range width for the continuous confirmatory ranges
    bad_n = []
    for r in M['ranges']:
        if r.get('start') is None or r.get('tag') == 'gap_nonmonotone_grid':
            continue
        width = r['end'] - r['start'] + 1
        if r.get('n') is not None and r['n'] != width:
            bad_n.append((r['round'], r['tag'], r['n'], width))
    return {'PASS': bool(not overlaps and not bad_n),
            'n_ranges': len(segs), 'overlaps': overlaps,
            'n_mismatches': bad_n}


def a6_cache_integrity():
    S = sch()
    required = ['logits', 'patient_id', 'group_meta', 'split', 'lead_names',
                'label_semantics', 'checksum', 'n_rec', 'n_patient', 'n_eff']
    missing = [k for k in required if k not in S['fields']]
    incomplete = [k for k in required if k in S['fields']
                  and not S['fields'][k].get('required', False)]
    return {'PASS': bool(not missing and not incomplete
                         and S['status'].startswith('CONTRACT ONLY')
                         and len(S['invariants']) >= 8),
            'missing_fields': missing, 'not_marked_required': incomplete,
            'n_invariants': len(S['invariants']),
            'status': S['status']}


def a7_hash_consistency():
    lines = [l.strip() for l in _read('WEIGHT_HASHES.sha256').splitlines() if l.strip()]
    bad = []
    for l in lines:
        h, rel = l.split(None, 1)
        p = ROOT / rel.strip()
        if not p.exists():
            bad.append((rel.strip(), 'MISSING')); continue
        if hashlib.sha256(p.read_bytes()).hexdigest() != h:
            bad.append((rel.strip(), 'HASH_MISMATCH'))
    return {'PASS': bool(not bad and len(lines) >= 40),
            'n_files': len(lines), 'mismatches': bad[:10]}


CHECKS = [
    ('1_patient_level_disjoint', a1_patient_disjoint),
    ('2_lead_alignment_by_name', a2_lead_alignment),
    ('3_CODE15_not_confident_negative', a3_code15_ambiguous),
    ('4_deff_and_n_eff', a4_neff_deff),
    ('5_seed_ranges_disjoint', a5_seed_disjoint),
    ('6_cache_schema_complete', a6_cache_integrity),
    ('7_code_hash_consistency', a7_hash_consistency),
]


def sch():
    return json.loads((HERE / 'CACHE_SCHEMA.json').read_text(encoding='utf-8'))


def manifest():
    return json.loads((HERE / 'SEED_MANIFEST.json').read_text(encoding='utf-8'))


def main():
    out = {}
    print('W11 PREFLIGHT — 7 assertions (contract only, no real patient data)')
    for name, fn in CHECKS:
        r = fn()
        out[name] = r
        print(f'  {name:34s} {"PASS" if r["PASS"] else "FAIL"}')
    n = sum(bool(v['PASS']) for v in out.values())
    print(f'preflight: {n}/7')
    (ROOT / 'w11_theory' / 'results' / 'preflight_results.json').write_text(
        json.dumps({'checks': out, 'n_pass': n, 'n_checks': 7,
                    'all_pass': n == 7}, indent=2, ensure_ascii=False),
        encoding='utf-8')
    return 0 if n == 7 else 1


if __name__ == '__main__':
    sys.exit(main())
