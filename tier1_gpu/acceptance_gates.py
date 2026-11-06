#!/usr/bin/env python3
"""T2 acceptance-gate evaluator. Pure Python / NumPy.

The 12 frozen gates from PREREGISTRATION_T2.md §6.2. This is a LOGIC
SELF-TEST on SYNTHETIC logits: it verifies that every gate can be evaluated,
has an independent failure condition, and is reported verbatim.

It is NOT a scientific result. No real data, no GPU, no claims.
"""
from __future__ import annotations
import json, pathlib
import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / 'results'; OUT.mkdir(exist_ok=True)
SEED = 920000

GATES = [
    ('G01', 'F0 validity: ORACLE NLL not worse than all estimators', 'ratio == 1.00', 1.00),
    ('G02', 'primary endpoint three-way non-inferiority', 'all 3 CI upper <= 0', 0),
    ('G03', 'CVaR_0.1pct improvement', 'paired CI upper <= 0', 0),
    ('G04', 'mean delta-ECE improvement', 'paired CI upper <= 0', 0),
    ('G05', 'LOCO non-inferiority', '>= 10 of 12 folds', 10),
    ('G06', 'Proposition 1 on real logits', 'certificate/truth agreement >= 0.80', 0.80),
    ('G07', 'Proposition 2 on real logits', 'Jensen gap >= 0 and >= 95% cells', 0.95),
    ('G08', 'T2 bound non-trivial fraction', '> 0.10 (synthetic was 0.066)', 0.10),
    ('G09', 'patient-level deff / ICC consistency', 'deff>=1, n_eff/n<=1, ICC in [0,1]', 1),
    ('G10', 'W11-B 360 assertions re-run', '>= 354 of 360', 354),
    ('G11', 'architecture-family sign consistency', '>= 4 of 5 families same sign', 4),
    ('G12', 'third-party independent reproduction', '12/12 gates', 12),
]


def bootstrap_ci_upper(deltas, B=10000, alpha=0.05, seed=0):
    rng = np.random.default_rng(seed)
    n = len(deltas)
    idx = rng.integers(0, n, (B, n))
    means = deltas[idx].mean(axis=1)
    return float(np.quantile(means, 1 - alpha))


def main():
    rng = np.random.default_rng(SEED)
    # ---- SYNTHETIC stand-ins ONLY. These are NOT results. ----
    n = 3000
    delta_ece = rng.normal(-0.0033, 0.012, n)      # mimics W6 scale
    cvar_delta = rng.normal(-0.0011, 0.004, n)
    loss_delta = rng.normal(-0.0009, 0.003, n)
    ci2 = bootstrap_ci_upper(delta_ece, seed=SEED + 1)
    ci3 = bootstrap_ci_upper(cvar_delta, seed=SEED + 2)
    ci4 = bootstrap_ci_upper(loss_delta, seed=SEED + 3)

    loco_ok = int(rng.integers(9, 13))            # deliberately may fail
    prop1 = float(rng.uniform(0.74, 0.92))
    prop2_cells = float(rng.uniform(0.90, 1.00))
    jensen = float(rng.uniform(-0.002, 0.02))
    nontrivial = float(rng.uniform(0.04, 0.22))   # deliberately may fail
    icc = float(rng.uniform(0.30, 0.65))
    mbar = 2.9
    deff = 1 + (mbar - 1) * icc
    neff = 1 / deff
    w11b_pass = int(rng.integers(350, 361))
    arch_sign = int(rng.integers(3, 6))
    third_party = 12                              # cannot be self-asserted

    obs = {
        'G01': {'value': 1.00, 'detail': 'ORACLE NLL ratio vs best estimator (synthetic stand-in)'},
        'G02': {'value': [ci2, ci3, ci4],
                'detail': 'three paired bootstrap CI uppers (synthetic stand-in)'},
        'G03': {'value': ci3, 'detail': 'CVaR paired CI upper'},
        'G04': {'value': ci2, 'detail': 'delta-ECE paired CI upper'},
        'G05': {'value': loco_ok, 'detail': 'LOCO folds non-inferior / 12'},
        'G06': {'value': prop1, 'detail': 'certificate vs truth agreement'},
        'G07': {'value': [jensen, prop2_cells], 'detail': 'Jensen gap + cell fraction'},
        'G08': {'value': nontrivial, 'detail': 'T2 bound non-trivial fraction'},
        'G09': {'value': [deff, neff, icc], 'detail': 'deff, n_eff/n, ICC'},
        'G10': {'value': w11b_pass, 'detail': 'W11-B assertions passed / 360'},
        'G11': {'value': arch_sign, 'detail': 'architecture families with same sign / 5'},
        'G12': {'value': None, 'detail': 'MUST be filled by an independent third party'},
    }

    results = []
    for gid, claim, expected, thr in GATES:
        v = obs[gid]['value']
        if gid == 'G01':
            ok = v >= thr
        elif gid == 'G02':
            ok = all(x <= 0 for x in v)
        elif gid in ('G03', 'G04'):
            ok = v <= 0
        elif gid == 'G05':
            ok = v >= thr
        elif gid == 'G06':
            ok = v >= thr
        elif gid == 'G07':
            ok = v[0] >= 0 and v[1] >= thr
        elif gid == 'G08':
            ok = v > thr
        elif gid == 'G09':
            ok = v[0] >= 1 and 0 < v[1] <= 1 and 0 <= v[2] <= 1
        elif gid == 'G10':
            ok = v >= thr
        elif gid == 'G11':
            ok = v >= thr
        else:  # G12
            ok = False  # cannot be self-certified; honest FAIL in a self-test
        results.append({'id': gid, 'claim': claim, 'kind': 'verify',
                        'expected': expected, 'observed': str(v),
                        'PASS': bool(ok), 'evidence': obs[gid]['detail'],
                        'note': ('self-certification impossible; requires independent '
                                 'third party' if gid == 'G12' else
                                 'evaluated on SYNTHETIC logits stand-ins')})

    n_pass = sum(r['PASS'] for r in results)
    out = {
        'prereg': 'PREREGISTRATION_T2.md v1.0 §6.2 (12 frozen gates)',
        'mode': 'LOGIC SELF-TEST on synthetic stand-ins',
        'real_gpu_training_performed': False,
        'real_waveform_data_used': False,
        'n_gates': 12, 'n_pass': n_pass, 'n_fail': 12 - n_pass,
        'gates': results,
        'honesty': [
            'Every number above is a random SYNTHETIC stand-in from seed 920000',
            'This verifies ONLY that all 12 gates are evaluable and independently fail',
            'It is NOT a scientific result and must never be cited as one',
            'G12 is deliberately FAIL: no self-test may certify independent reproduction',
            'Thresholds were frozen BEFORE this smoke test; none changed',
        ],
    }
    d = OUT / 'acceptance_gates_smoke.json'
    d.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding='utf-8')
    print('=== T2 ACCEPTANCE GATES — LOGIC SELF-TEST (NOT A RESULT) ===')
    print(f'  {n_pass}/12 gates evaluated as PASS on synthetic stand-ins')
    for r in results:
        print(f"  {r['id']} {'PASS' if r['PASS'] else 'FAIL'} | {r['observed'][:60]}")
    print('  NOTE: G12 always FAIL here by design (third-party only).')
    print('written', d)


if __name__ == '__main__':
    main()
