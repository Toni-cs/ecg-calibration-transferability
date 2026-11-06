"""W11 verify_release_results.py — 12 release gates (PREREGISTRATION_W11.md §4).

Frozen BEFORE execution. Every gate is a real check on disk; nothing is
hard-coded as PASS. Gate 12 performs the equivalent of REPRODUCE.md's one
command: it requires gates 1-11 all PASS and the documented command present.

Usage:
    python verify_release_results.py            # human-readable
    python verify_release_results.py --json     # machine-readable + file
Exit 0 iff 12/12 PASS.
"""
from __future__ import annotations
import hashlib, json, pathlib, subprocess, sys
import numpy as np
import matplotlib
from PIL import Image
import scipy

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent               # /data/workspace
RESULTS = ROOT / 'w11_theory' / 'results'
RESULTS.mkdir(exist_ok=True)

ROUNDS = {
    'W1': ROOT / 'pari_experiment',
    'W2': ROOT / 'gsgt_experiment',
    'W3': ROOT / 'mamba_experiment',
    'W4': ROOT / 'w4_repro',
    'W5': ROOT / 'w5_srgst',
    'W6': ROOT / 'w6_tier1',
    'W7': ROOT / 'w7_60k',
    'W8': ROOT / 'w8_dualgate',
    'W9': ROOT / 'w9_lbst',
    'W10': ROOT / 'w10_continuous',
    'W11': ROOT / 'w11_theory',
}
RESULT_JSON = {
    'W1': ROOT / 'pari_experiment' / 'pari_synthetic_results.json',
    'W2': ROOT / 'gsgt_experiment' / 'gsgt_v1_1_results.json',
    'W3': ROOT / 'mamba_experiment' / 'mamba600_results.json',
    'W4': ROOT / 'w4_repro' / 'w4_results.json',
    'W5': ROOT / 'w5_srgst' / 'w5_results.json',
    'W6': ROOT / 'w6_tier1' / 'w6_results.json',
    'W7': ROOT / 'w7_60k' / 'w7_results.json',
    'W8': ROOT / 'w8_dualgate' / 'W8_FROZEN_GATE.json',
    'W9': ROOT / 'w9_lbst' / 'w9_results.json',
    'W10': ROOT / 'w10_continuous' / 'w10_results.json',
    'W11': RESULTS / 'w11_theory_results.json',
}
SHARDS = {
    'W7_main': (ROOT / 'w7_60k' / 'shards', 21000, 80999),
    'W9_main': (ROOT / 'w9_lbst' / 'shards' / 'main', 110000, 119999),
    'W9_falsify': (ROOT / 'w9_lbst' / 'shards' / 'falsify', 120000, 120599),
    'W10_main': (ROOT / 'w10_continuous' / 'shards' / 'main', 130000, 149999),
    'W10_loco': (ROOT / 'w10_continuous' / 'shards' / 'loco', 150000, 150599),
    'W10_falsify': (ROOT / 'w10_continuous' / 'shards' / 'falsify', 151000, 151599),
}


# ---------------------------------------------------------------- gates
def g1_env_lock():
    p = HERE / 'environment.lock'
    if not p.exists():
        return {'PASS': False, 'reason': 'missing'}
    L = json.loads(p.read_text(encoding='utf-8'))
    cur = {'python': sys.version.split()[0],
           'numpy': np.__version__, 'scipy': scipy.__version__,
           'matplotlib': matplotlib.__version__}
    diff = {k: [L.get(k), v] for k, v in cur.items() if L.get(k) != v}
    return {'PASS': not diff, 'locked': {k: L.get(k) for k in cur},
            'runtime': cur, 'mismatches': diff}


def g2_seed_manifest():
    M = json.loads((HERE / 'SEED_MANIFEST.json').read_text(encoding='utf-8'))
    segs = sorted((r['start'], r['end'], r['round'], r['tag'])
                  for r in M['ranges']
                  if r.get('start') is not None and r.get('end') is not None)
    overlaps = [(segs[i][2:], segs[i + 1][2:])
                for i in range(len(segs) - 1) if segs[i][1] >= segs[i + 1][0]]
    return {'PASS': bool(not overlaps and len(M['ranges']) >= 20
                         and M['all_w1_w11_seeds_pairwise_disjoint']),
            'n_ranges': len(M['ranges']), 'n_pairwise_checked': len(segs),
            'overlaps': overlaps}


def g3_prereg_complete():
    missing, found = [], {}
    for w in ['W2', 'W3', 'W4', 'W5', 'W6', 'W7', 'W8', 'W9', 'W10']:
        hits = list(ROUNDS[w].glob('PREREGISTRATION*.md'))
        found[w] = [p.name for p in hits]
        if not hits:
            missing.append(w)
    hits11 = list((ROOT / 'w11_theory').glob('PREREGISTRATION*.md'))
    found['W11'] = [p.name for p in hits11]
    if not hits11:
        missing.append('W11')
    return {'PASS': not missing, 'missing': missing, 'found': found}


def g4_shard_integrity():
    out = {}
    for name, (folder, lo, hi) in SHARDS.items():
        ps = sorted(folder.glob('shard_*.npz'))
        if not ps:
            out[name] = {'PASS': False, 'reason': 'no shards'}; continue
        X = np.concatenate([np.load(p)['X'] for p in ps], axis=0)
        seeds = np.unique(X[:, 0].astype(np.int64))
        exact = bool(np.array_equal(seeds, np.arange(lo, hi + 1, dtype=np.int64)))
        dupes = int(len(X) - len(seeds)) if name != 'W10_loco' else 0
        out[name] = {'PASS': bool(exact and dupes == 0), 'n_files': len(ps),
                     'n_rows': int(len(X)), 'n_unique_seeds': int(len(seeds)),
                     'exact_range': exact, 'duplicate_rows': dupes}
    return {'PASS': all(v['PASS'] for v in out.values()), 'shard_sets': out}


def g5_result_json():
    out = {}
    for w, p in RESULT_JSON.items():
        if not p.exists():
            out[w] = {'PASS': False, 'reason': 'missing'}; continue
        try:
            d = json.loads(p.read_text(encoding='utf-8'))
        except Exception as e:
            out[w] = {'PASS': False, 'reason': str(e)}; continue
        has_conclusion = any(k in d for k in
                             ['verdict', 'conclusion', 'FROZEN_N_STAR',
                              'verdict_summary'])
        structured = ('meta' in d and len(d) >= 3 and p.stat().st_size > 1024)
        out[w] = {'PASS': bool(has_conclusion or structured),
                  'bytes': p.stat().st_size,
                  'conclusion_field': has_conclusion,
                  'structured_result_block': structured}
    return {'PASS': all(v['PASS'] for v in out.values()), 'rounds': out}


def g6_code_hash():
    lines = [l.strip() for l in (HERE / 'WEIGHT_HASHES.sha256').read_text(
        encoding='utf-8').splitlines() if l.strip()]
    bad, missing = [], []
    covered = set()
    for l in lines:
        h, rel = l.split(None, 1); rel = rel.strip()
        p = ROOT / rel
        covered.add(rel)
        if not p.exists():
            missing.append(rel); continue
        if hashlib.sha256(p.read_bytes()).hexdigest() != h:
            bad.append(rel)
    # completeness: every .py in the round dirs must be listed
    all_py = set()
    for w, d in ROUNDS.items():
        for sub in [d, d / 'theory', d / 'repro']:
            if sub.exists():
                for f in sub.glob('*.py'):
                    all_py.add(str(f.relative_to(ROOT)))
    uncovered = sorted(all_py - covered)
    return {'PASS': bool(not bad and not missing and not uncovered
                         and len(lines) >= 40),
            'n_listed': len(lines), 'mismatches': bad[:10],
            'missing_files': missing[:10], 'uncovered_py': uncovered[:10],
            'n_uncovered': len(uncovered)}


def g7_figures():
    out = {}
    for w, d in ROUNDS.items():
        pngs = list(d.glob('*.png')) + list((d / 'figs').glob('*.png'))
        good = [p for p in pngs if p.stat().st_size > 1000]
        dims_ok = True
        for p in good[:3]:
            try:
                im = Image.open(p)
                if im.width <= 0 or im.height <= 0:
                    dims_ok = False
            except Exception:
                dims_ok = False
        out[w] = {'PASS': bool(good and dims_ok), 'n_png': len(good)}
    return {'PASS': all(v['PASS'] for v in out.values()), 'rounds': out}


def g8_cache_schema():
    S = json.loads((HERE / 'CACHE_SCHEMA.json').read_text(encoding='utf-8'))
    req = ['logits', 'patient_id', 'group_meta', 'split', 'lead_names',
           'label_semantics', 'checksum', 'n_rec', 'n_patient', 'n_eff']
    missing = [k for k in req if k not in S['fields']]
    return {'PASS': bool(not missing and S['status'].startswith('CONTRACT ONLY')
                         and len(S['invariants']) >= 8),
            'missing': missing, 'n_invariants': len(S['invariants']),
            'blocked_until': S['blocked_until']}


def g9_preflight():
    p = subprocess.run([sys.executable, str(HERE / 'preflight.py')],
                       capture_output=True, text=True, cwd=str(HERE))
    ok = (p.returncode == 0 and 'preflight: 7/7' in p.stdout)
    f = RESULTS / 'preflight_results.json'
    detail = json.loads(f.read_text(encoding='utf-8')) if f.exists() else {}
    return {'PASS': bool(ok), 'returncode': p.returncode,
            'n_pass': detail.get('n_pass'), 'stdout_tail': p.stdout.strip().splitlines()[-2:]}


def g10_no_overclaim():
    BANNED = ['达到一区', '已达到一区', 'SOTA', '已发表算法',
              '真实 1.15M 已完成', '完成真实队列', '已达成一区']
    NEG = ['不', '未', '非', '无法', '尚未', '禁止', '不等于', '不声称',
           '不得', '达不到', '没有', '仍需', '卡在']
    hits = []
    mds = []
    for d in [ROOT] + list(ROUNDS.values()):
        mds.extend(d.glob('*.md'))
        mds.extend((d / 'repro').glob('*.md'))
    mds.extend((ROOT / 'w11_theory' / 'repro').glob('*.md'))
    seen = set()
    for p in mds:
        if str(p) in seen:
            continue
        seen.add(str(p))
        for ln, line in enumerate(p.read_text(encoding='utf-8',
                                             errors='ignore').splitlines(), 1):
            if any(b in line for b in BANNED) and not any(x in line for x in NEG):
                hits.append({'file': p.name, 'line': ln, 'text': line[:120]})
    return {'PASS': not hits, 'n_md_scanned': len(seen),
            'violations': hits[:10], 'n_violations': len(hits)}


def g11_direction_ledger():
    L = json.loads((HERE / 'DIRECTION_LEDGER.json').read_text(encoding='utf-8'))
    e = L['entries']
    neg = [x for x in e if x['status'] in ('not_passed', 'falsified')]
    rounds = sorted(set(x['round'] for x in e))
    return {'PASS': bool(len(e) >= 30 and len(neg) >= 8 and len(rounds) >= 11),
            'n_entries': len(e), 'n_negative_or_falsified': len(neg),
            'rounds_covered': rounds, 'n_rounds': len(rounds)}


def g12_one_command(previous):
    md = HERE / 'REPRODUCE.md'
    if not md.exists():
        return {'PASS': False, 'reason': 'REPRODUCE.md missing'}
    t = md.read_text(encoding='utf-8')
    has_cmd = ('python -u verify_release_results.py' in t
               and 'python -u preflight.py' in t)
    all_prev = all(previous[k]['PASS'] for k in previous)
    return {'PASS': bool(has_cmd and all_prev),
            'equivalent_verification': ('this process IS the documented command: '
                                        'gates 1-11 all PASS'),
            'command_documented': has_cmd,
            'previous_gates_all_pass': all_prev}


GATES = [('01_env_lock', g1_env_lock), ('02_seed_manifest', g2_seed_manifest),
         ('03_prereg_complete', g3_prereg_complete),
         ('04_shard_integrity', g4_shard_integrity),
         ('05_result_json', g5_result_json), ('06_code_hash', g6_code_hash),
         ('07_figure_existence', g7_figures), ('08_cache_schema', g8_cache_schema),
         ('09_preflight_7of7', g9_preflight), ('10_no_overclaim', g10_no_overclaim),
         ('11_direction_ledger', g11_direction_ledger)]


def run_all():
    res = {}
    print('W11 RELEASE VERIFICATION — 12 gates (frozen in PREREGISTRATION_W11.md §4)')
    for name, fn in GATES:
        r = fn()
        res[name] = r
        print(f'  {name:26s} {"PASS" if r["PASS"] else "FAIL"}')
    res['12_one_command_reproduce'] = g12_one_command(res)
    print(f'  {"12_one_command_reproduce":26s} '
          f'{"PASS" if res["12_one_command_reproduce"]["PASS"] else "FAIL"}')
    n = sum(bool(v['PASS']) for v in res.values())
    summary = {'gates': res, 'n_pass': n, 'n_checks': len(res),
               'all_pass': n == len(res),
               'prereg': 'PREREGISTRATION_W11.md v1.0 (frozen)',
               'no_real_patient_data': True,
               'note': 'A8 requires 12/12; any FAIL is reported, never skipped.'}
    (RESULTS / 'verify_release_results.json').write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'\nverify_release_results: {n}/{len(res)}')
    return summary


if __name__ == '__main__':
    s = run_all()
    if '--json' in sys.argv:
        print(json.dumps({'n_pass': s['n_pass'],
                          'n_checks': s['n_checks'],
                          'all_pass': s['all_pass']}, ensure_ascii=False))
    sys.exit(0 if s['all_pass'] else 1)
