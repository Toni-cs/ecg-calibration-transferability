"""W8 stage 1 — determine n* from the W7 60,000-seed EXPLORATION set only.

Implements PREREGISTRATION_W8.md section 2 VERBATIM. No confirmatory seed
(110000+) is touched here. The chosen n* is frozen to W8_FROZEN_GATE.json
and must not be changed afterwards.
"""
from __future__ import annotations
import json, pathlib, datetime
import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
W7 = HERE.parent / 'w7_60k'
sys_path = str(W7)
import sys
sys.path.insert(0, sys_path)
from w7_kernel import COLS

parts = sorted((W7 / 'shards').glob('shard_*.npz'))
X = np.concatenate([np.load(p)['X'] for p in parts], axis=0)
X = X[np.argsort(X[:, 0])]
D = {c: X[:, i] for i, c in enumerate(COLS)}
assert len(X) == 60000 and np.array_equal(D['seed'].astype(np.int64),
                                          np.arange(21000, 81000))
print(f'exploration set: {len(X):,} seeds from {len(parts)} shards '
      f'({int(D["seed"][0])}..{int(D["seed"][-1])})', flush=True)

GRID = [8, 12, 16, 20, 24, 30, 40, 60, 80]
MARGIN = 0.002
GAIN_REQUIREMENT = -0.010               # retain >=58% of W7 baseline gain

eg = D['ece_GLOBAL']
ec = D['ece_CERT']
cert = D['cert'].astype(int)
nmin = D['n_min']
base_gain = float((ec - eg).mean())
base_harm = float((ec > eg + MARGIN).mean())

rows = []
for c in GRID:
    use = (cert == 1) & (nmin >= c)
    e_dg = np.where(use, ec, eg)
    harm = float((e_dg > eg + MARGIN).mean())
    gain = float((e_dg - eg).mean())
    rows.append({'n_star': c, 'n_use_split': int(use.sum()),
                 'frac_use_split': float(use.mean()),
                 'harm': harm, 'gain': gain,
                 'qualified': bool(gain <= GAIN_REQUIREMENT),
                 'delta_vs_baseline_gain': float(gain - base_gain)})

Q = [r for r in rows if r['qualified']]
if Q:
    min_harm = min(r['harm'] for r in Q)
    tied = [r for r in Q if r['harm'] <= min_harm + 1e-15]
    chosen = min(tied, key=lambda r: r['n_star'])     # tie -> smallest c
    rule = 'Q nonempty: argmin harm_c over Q; tie -> smallest c'
else:
    min_harm = min(r['harm'] for r in rows)
    tied = [r for r in rows if r['harm'] <= min_harm + 1e-15]
    chosen = min(tied, key=lambda r: r['gain'])
    rule = 'Q empty: argmin harm_c; tie -> most negative gain_c'

out = {
 'frozen_at': datetime.datetime.now().astimezone().isoformat(),
 'preregistration': 'PREREGISTRATION_W8.md v1.0, section 2 (verbatim)',
 'exploration_set': {'n': 60000, 'seed_min': 21000, 'seed_max': 80999,
                     'n_shards': len(parts),
                     'note': 'W7 shards ONLY; no confirmatory seed touched'},
 'candidate_grid': GRID,
 'margin': MARGIN, 'gain_requirement': GAIN_REQUIREMENT,
 'baseline': {'harm_CERT': base_harm, 'gain_CERT': base_gain},
 'candidates': rows, 'qualified_set': [r['n_star'] for r in Q],
 'selection_rule_applied': rule,
 'FROZEN_N_STAR': int(chosen['n_star']),
 'chosen': chosen,
 'immutable': True}
(HERE / 'W8_FROZEN_GATE.json').write_text(
    json.dumps(out, indent=2, ensure_ascii=False), encoding='utf-8')

print('\n baseline: harm %.5f  gain %.5f' % (base_harm, base_gain))
print(' candidate grid (exploration only):')
for r in rows:
    print('   n*=%2d  use %5.1f%%  harm %.5f  gain %.5f  qualified=%s'
          % (r['n_star'], 100 * r['frac_use_split'], r['harm'], r['gain'],
             r['qualified']))
print('\n Q =', [r['n_star'] for r in Q])
print(' rule:', rule)
print(' >>> FROZEN n* =', chosen['n_star'], '<<<', flush=True)
