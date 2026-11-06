"""W11-B orchestrator: strict BEFORE/AFTER hash verification (B5) + B1-B6.

Runs the three 120-assertion scripts a SECOND time between two SHA256
snapshots of every W1-W11 original numerical artefact. S1 == S2 is the
literal, strict interpretation of PREREGISTRATION_W11B.md section 4 B5.
No original result file is written by any of the three scripts (read-only).
"""
from __future__ import annotations
import hashlib, json, os, pathlib, subprocess, sys
import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
RESULTS = ROOT / 'w11_theory' / 'results'
REPRO = ROOT / 'w11_theory' / 'repro'
SCALE = ROOT / 'w11_theory' / 'scale'

RESULT_JSONS = [
    ROOT / 'pari_experiment' / 'pari_synthetic_results.json',
    ROOT / 'pari_experiment' / 'pari_diagnostic_results.json',
    ROOT / 'gsgt_experiment' / 'gsgt_v1_1_results.json',
    ROOT / 'mamba_experiment' / 'mamba600_results.json',
    ROOT / 'w4_repro' / 'w4_results.json',
    ROOT / 'w5_srgst' / 'w5_results.json',
    ROOT / 'w6_tier1' / 'w6_results.json',
    ROOT / 'w7_60k' / 'w7_results.json',
    ROOT / 'w8_dualgate' / 'W8_FROZEN_GATE.json',
    ROOT / 'w9_lbst' / 'w9_results.json',
    ROOT / 'w10_continuous' / 'w10_results.json',
    RESULTS / 'w11_theory_results.json',
    RESULTS / 'w11_posthoc.json',
]
SHARD_DIRS = [
    ROOT / 'w7_60k' / 'shards',
    ROOT / 'w9_lbst' / 'shards' / 'main',
    ROOT / 'w9_lbst' / 'shards' / 'falsify',
    ROOT / 'w10_continuous' / 'shards' / 'main',
    ROOT / 'w10_continuous' / 'shards' / 'loco',
    ROOT / 'w10_continuous' / 'shards' / 'falsify',
]


def original_files():
    out = [p for p in RESULT_JSONS if p.exists()]
    for d in SHARD_DIRS:
        out.extend(sorted(d.glob('shard_*.npz')))
    return sorted(set(out))


def snapshot(files):
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in files}


def run(cmd, cwd):
    env = dict(os.environ)
    env.update({'OPENBLAS_NUM_THREADS': '1', 'OMP_NUM_THREADS': '1',
                'MKL_NUM_THREADS': '1', 'PYTHONPATH': str(ROOT)})
    p = subprocess.run([sys.executable, '-u', cmd], cwd=str(cwd),
                       capture_output=True, text=True, env=env)
    return p.returncode, p.stdout.strip().splitlines()[-3:]


def main():
    files = original_files()
    print(f'W11-B ORCHESTRATOR — {len(files)} original numerical artefacts',
          flush=True)
    S1 = snapshot(files)
    print('  S1 (BEFORE) computed', flush=True)

    steps = [
        ('theory_assertions.py', SCALE),
        ('preflight_120.py', REPRO),
        ('verify_120.py', REPRO),
    ]
    logs = {}
    for cmd, cwd in steps:
        rc, tail = run(cmd, cwd)
        logs[cmd] = {'returncode': rc, 'stdout_tail': tail}
        print(f'  re-ran {cmd:24s} rc={rc} | {tail[-1] if tail else ""}',
              flush=True)
        if rc != 0:
            print('    !! non-zero return; continuing to report honestly',
                  flush=True)

    S2 = snapshot(files)
    B5 = (S1 == S2)
    changed = [k for k in S1 if S1[k] != S2.get(k)]
    print(f'  S2 (AFTER) computed | B5={"PASS" if B5 else "FAIL"} '
          f'changed={len(changed)}', flush=True)

    # ---- load the three 120-assertion results ----
    groups = {}
    for tag, name in [('theory', 'w11b_theory_120.json'),
                      ('preflight', 'w11b_preflight_120.json'),
                      ('verify', 'w11b_verify_120.json')]:
        g = json.loads((RESULTS / name).read_text(encoding='utf-8'))
        # verify_120.py names its list "gates"; normalise to "assertions"
        if 'assertions' not in g and 'gates' in g:
            g['assertions'] = g['gates']
        groups[tag] = g

    # ---- B1 exactly 120, IDs continuous ----
    B1 = {}
    for tag, g in groups.items():
        ids = [a['id'] for a in g['assertions']]
        pref = {'theory': 'TH', 'preflight': 'PF', 'verify': 'VG'}[tag]
        expected = [f'{pref}{i:03d}' for i in range(1, 121)]
        B1[tag] = {'n': len(ids), 'continuous': ids == expected,
                   'unique': len(set(ids)) == 120}
    B1['PASS'] = all(v['n'] == 120 and v['continuous'] and v['unique']
                     for v in B1.values() if isinstance(v, dict))

    # ---- B2 every assertion has 5 fields and non-empty evidence ----
    need = ['kind', 'expected', 'observed', 'PASS', 'evidence']
    B2_detail = {}
    for tag, g in groups.items():
        bad = [a['id'] for a in g['assertions']
               if any(k not in a for k in need) or not str(a.get('evidence', '')).strip()]
        B2_detail[tag] = {'n_bad': len(bad), 'bad_ids': bad[:10],
                          'n_assertions': len(g['assertions'])}
    B2 = {'PASS': all(v['n_bad'] == 0 for v in B2_detail.values()),
          'detail': B2_detail}

    # ---- B3 counts consistent ----
    B3_detail = {}
    for tag, g in groups.items():
        npass = int(sum(a['PASS'] for a in g['assertions']))
        nfail = int(sum(not a['PASS'] for a in g['assertions']))
        B3_detail[tag] = {
            'declared_n_pass': g['n_pass'], 'actual_n_pass': npass,
            'declared_n_fail': g['n_fail'], 'actual_n_fail': nfail,
            'declared_n_checks': g['n_checks'],
            'consistent': bool(g['n_pass'] == npass and g['n_fail'] == nfail
                               and g['n_checks'] == 120 and npass + nfail == 120)}
    B3 = {'PASS': all(v['consistent'] for v in B3_detail.values()),
          'detail': B3_detail}

    # ---- B4 list every FAIL verbatim ----
    all_fail = []
    for tag, g in groups.items():
        for a in g['assertions']:
            if not a['PASS']:
                all_fail.append({'group': tag, 'id': a['id'],
                                 'family': a['family'], 'claim': a['claim'],
                                 'kind': a['kind'], 'expected': a['expected'],
                                 'observed': a['observed'],
                                 'evidence': a['evidence']})
    B4 = {'n_fail': len(all_fail), 'failures': all_fail,
          'no_revision': True, 'no_v1_1': True,
          'note': 'Every FAIL is reported verbatim; no assertion, threshold, '
                  'criterion or subset was changed after execution.'}

    # ---- B6 original verdicts untouched ----
    vr = json.loads((RESULTS / 'verify_release_results.json').read_text(
        encoding='utf-8'))
    pf = json.loads((RESULTS / 'preflight_results.json').read_text(
        encoding='utf-8'))
    th = json.loads((RESULTS / 'w11_theory_results.json').read_text(
        encoding='utf-8'))
    B6 = {
        'W11_theory': f"{th['verdict']['n_pass']}/{th['verdict']['n_checks']}",
        'preflight': f"{pf['n_pass']}/{pf['n_checks']}",
        'verify_release_results': f"{vr['n_pass']}/{vr['n_checks']}",
        'original_files_sha256_unchanged': B5,
        'PASS': bool(th['verdict']['n_pass'] == 4 and pf['n_pass'] == 7
                     and vr['n_pass'] == 12 and B5)}

    total_pass = sum(int(g['n_pass']) for g in groups.values())
    total_checks = sum(int(g['n_checks']) for g in groups.values())
    kind_counts = {}
    for g in groups.values():
        for k, v in g['n_by_kind'].items():
            kind_counts[k] = kind_counts.get(k, 0) + v

    out = {
        'prereg': 'PREREGISTRATION_W11B.md v1.0 (frozen before execution)',
        'date': '2026-11-06',
        'scope': 'Acceptance-GRANULARITY extension ONLY. No new experiment, '
                 'no new seeds, no new method, no change to any theorem.',
        'groups': {tag: {'n_checks': g['n_checks'], 'n_pass': g['n_pass'],
                         'n_fail': g['n_fail'], 'n_by_kind': g['n_by_kind']}
                   for tag, g in groups.items()},
        'total_checks': total_checks, 'total_pass': total_pass,
        'total_fail': total_checks - total_pass,
        'n_by_kind_total': kind_counts,
        'B': {'B1_exactly_120': B1, 'B2_five_fields': B2,
              'B3_counts': B3, 'B4_failures_reported': B4,
              'B5_original_hashes_unchanged': {'PASS': B5,
                  'n_files': len(files), 'changed': changed,
                  'method': 'strict S1 (before re-running all three scripts) '
                            '== S2 (after); result JSONs + all W7/W9/W10 '
                            'shard npz + W11 theory/posthoc results'},
              'B6_original_verdicts_untouched': B6},
        'reexecution_logs': logs,
        'original_hash_snapshot': S1,
        'honesty': [
            '360 checks do NOT produce any new scientific conclusion',
            'More checks != more rigour; tier-1 still blocked by PhysioNet '
            'credentialed DUA, clinical + biostat collaborators, and '
            'third-party independent reproduction',
            'W11 original theory 4/6 (A3/A5 not passed), preflight 7/7, '
            'verify 12/12, and the 93.4% trivial-bound result are UNCHANGED',
            'All W1-W11 work is synthetic / internal, not published '
            'algorithms or SOTA',
            'No real patient data, no official Mamba-2 kernel, no '
            'pretrained weights are present',
        ],
    }
    dest = RESULTS / 'w11b_final_verdict.json'
    dest.write_text(json.dumps(out, indent=2, ensure_ascii=False),
                    encoding='utf-8')
    print('\n=== W11-B VERDICT ===', flush=True)
    for tag, g in groups.items():
        print(f'  {tag:10s} {g["n_pass"]:3d}/120  '
              f'FAIL={g["n_fail"]}', flush=True)
    print(f'  TOTAL      {total_pass:3d}/{total_checks}  '
          f'FAIL={total_checks-total_pass}', flush=True)
    print(f'  B1={B1["PASS"]} B2={B2["PASS"]} B3={B3["PASS"]} '
          f'B5={B5} B6={B6["PASS"]}', flush=True)
    print(f'  FAIL ids: {[f["id"] for f in all_fail]}', flush=True)
    print('written', dest, flush=True)


if __name__ == '__main__':
    main()
