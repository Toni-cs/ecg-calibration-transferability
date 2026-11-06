"""W9 POST-HOC diagnostics (explicitly NOT confirmatory).

PREREGISTRATION_W9.md H1 failed on the BINARY harm proxy while H2/H3
(continuous endpoints) passed. This script tests ONE explanation, declared
after seeing the results and therefore EXCLUDED from all H judgements:

    a binary threshold on a continuous shrinkage estimator creates
    boundary artefacts near the 0.002 non-inferiority margin.

No new seeds, no new estimator, no threshold change. Reuses the 10,000
immutable confirmatory rows only.
"""
from __future__ import annotations
import json, pathlib, sys
import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from w9_kernel import COLS

ps = sorted((HERE / 'shards' / 'main').glob('shard_*.npz'))
X = np.concatenate([np.load(p)['X'] for p in ps], axis=0)
X = X[np.argsort(X[:, 0])]
D = {c: X[:, i] for i, c in enumerate(COLS)}
N = len(X)
MARGIN = 0.002

dC, dH = D['dECE_CERT'], D['dECE_HB']
hC, hH = D['harm_CERT'], D['harm_HB']


def ciboot(v, B=10000, seed=20261106):
    rng = np.random.default_rng(seed); v = np.asarray(v, float)
    m = np.array([v[rng.integers(0, len(v), len(v))].mean() for _ in range(B)])
    return [float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))]


def stats(d, h):
    pen = np.maximum(0.0, d + MARGIN)          # continuous deployment loss
    n_tail = max(1, int(round(N * 0.001)))
    top = np.argsort(d)[-n_tail:]
    return {'mean_dECE': float(d.mean()),
            'mean_continuous_loss': float(pen.mean()),
            'p95_dECE': float(np.percentile(d, 95)),
            'p99_dECE': float(np.percentile(d, 99)),
            'CVaR_0.1pct': float(d[top].mean()),
            'max_dECE': float(d.max()),
            'binary_harm': float(h.mean()),
            'frac_near_margin': float((np.abs(d + MARGIN) < 0.003).mean())}


out = {
 'status': 'POST-HOC / EXPLORATORY — excluded from all confirmatory H judgements',
 'n_seeds': int(N), 'margin': MARGIN,
 'CERT_GATE': stats(dC, hC), 'HB_GST': stats(dH, hH),
 'paired_dH_minus_dC': {'mean': float((dH - dC).mean()),
                        'CI95': ciboot(dH - dC)},
 'boundary_artefact': {
   'n_harm_flips_CERT_ok_to_HB_harm': int(((hC == 0) & (hH == 1)).sum()),
   'n_harm_flips_HB_ok_to_CERT_harm': int(((hH == 0) & (hC == 1)).sum()),
   'among_flips_CERT_ok_to_HB_harm': {
     'n': int(((hC == 0) & (hH == 1)).sum()),
     'mean_abs_dECE_CERT': float(np.abs(dC[(hC == 0) & (hH == 1)] - (-MARGIN)).mean())
       if ((hC == 0) & (hH == 1)).any() else None,
     'frac_within_0.003_of_margin': float(
       (np.abs(dH[(hC == 0) & (hH == 1)] + MARGIN) < 0.003).mean())
       if ((hC == 0) & (hH == 1)).any() else None},
   'interpretation': ('If HB reduces continuous loss / CVaR / mean dECE but '
                      'raises the binary harm rate, and the new harm events '
                      'cluster within +-0.003 of the 0.002 margin, then the '
                      'H1 failure is a threshold artefact of the proxy, not '
                      'a degradation of the calibration estimator.')},
 'conclusion_honesty': ('This does NOT overturn H1. H1 remains FAILED per '
                        'PREREGISTRATION_W9.md section 6. It only diagnoses '
                        'why, and motivates a pre-registered continuous '
                        'endpoint in W10.')}
(HERE / 'w9_posthoc_diagnostics.json').write_text(
    json.dumps(out, indent=2, ensure_ascii=False), encoding='utf-8')

print('POST-HOC (not confirmatory), n =', N)
for k in ['CERT_GATE', 'HB_GST']:
    s = out[k]
    print(' ', k, {kk: round(vv, 5) for kk, vv in s.items()})
print(' paired dH-dC mean %.5f CI %s' % (
    out['paired_dH_minus_dC']['mean'],
    [round(x, 5) for x in out['paired_dH_minus_dC']['CI95']]))
print(' flips C-ok->H-harm', out['boundary_artefact']['n_harm_flips_CERT_ok_to_HB_harm'],
      '| H-ok->C-harm', out['boundary_artefact']['n_harm_flips_HB_ok_to_CERT_harm'])
print(' near-margin fraction among new harms',
      out['boundary_artefact']['among_flips_CERT_ok_to_HB_harm']['frac_within_0.003_of_margin'])
