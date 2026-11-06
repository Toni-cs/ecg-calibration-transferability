"""W1b diagnostic: in which regime does patient-anchored pairing actually help?

W1 found PARI ~ POOLED under balanced orbits + homogeneous drift. This script
isolates the mechanism by sweeping orbit imbalance and patient heterogeneity,
then re-runs the falsification tests under the regime where an advantage exists.
"""
from __future__ import annotations

import json
import pathlib
import sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from pari import (make_dgp_unbalanced, psi_pari_ragged, psi_pooled_ragged,
                  estimate_T, psi_pari, psi_pooled, make_dgp)

plt.rcParams['font.sans-serif'] = ['WenQuanYi Micro Hei']
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams['figure.dpi'] = 130

T_GRID = np.linspace(0.6, 4.6, 201)
TAU_T, TAU_S = 2.4, 1.0
R = 60
rng = np.random.default_rng(771105)
res = {'meta': {'repeats': R, 'tau_t': TAU_T, 'n_pat': 200, 'm_max': 8}}


def run(imbalance, repeats=R, shuffle_pairs=False, n_pat=200, m_max=8):
    ep, pp = [], []
    for _ in range(repeats):
        seed = int(rng.integers(0, 2**31 - 1))
        s, t, ms, mt = make_dgp_unbalanced(n_pat, m_max, imbalance=imbalance,
                                           tau_t=TAU_T, tau_s=TAU_S, seed=seed)
        a = psi_pari_ragged(s, t, ms, mt, T_GRID, TAU_S, shuffle_pairs=shuffle_pairs)
        b = psi_pooled_ragged(s, t, ms, mt, T_GRID, TAU_S)
        ep.append(estimate_T(T_GRID, a) - TAU_T)
        pp.append(estimate_T(T_GRID, b) - TAU_T)
    e = np.array(ep); p = np.array(pp)
    return {'PARI_rmse': float(np.sqrt((e**2).mean())),
            'POOLED_rmse': float(np.sqrt((p**2).mean())),
            'PARI_bias': float(e.mean()), 'POOLED_bias': float(p.mean()),
            'gain': float(np.sqrt((p**2).mean()) / max(np.sqrt((e**2).mean()), 1e-12))}


print('[D1] orbit imbalance sweep ...', flush=True)
imb = [0.0, 0.25, 0.5, 1.0, 2.0]
rows = []
for x in imb:
    r = run(x); r['imbalance'] = x; rows.append(r)
    print(f'  imbalance={x:4.2f}  PARI={r["PARI_rmse"]:.4f}  '
          f'POOLED={r["POOLED_rmse"]:.4f}  gain={r["gain"]:.2f}x', flush=True)
res['D1_imbalance_sweep'] = rows

print('[D2] falsification under the winning regime ...', flush=True)
base = run(1.0)
f1 = run(1.0, shuffle_pairs=True)
res['D2_falsification_in_winning_regime'] = {
    'baseline': base, 'F1_shuffled_pairs': f1,
    'F1_erases_gain': bool(f1['gain'] < 1.15 and base['gain'] > 1.15)}

print('[D3] patient-heterogeneity sweep (balanced, control) ...', flush=True)
# balanced DGP with varying prototype spread, to confirm W1's null is not an artefact
het = [0.05, 0.15, 0.30, 0.50]
hrows = []
for h in het:
    ep, pp = [], []
    for _ in range(R):
        seed = int(rng.integers(0, 2**31 - 1))
        rs = np.random.default_rng(seed)
        n_pat = 200
        y = rs.integers(0, 4, n_pat)
        p = np.full((n_pat, 4), 0.12)
        p[np.arange(n_pat), y] = 0.55 + rs.uniform(0, h, n_pat)
        p /= p.sum(1, keepdims=True)
        v = np.log(p)
        es = rs.normal(0, .35, (n_pat, 2, 4)); et = rs.normal(0, .35, (n_pat, 2, 4))
        s = TAU_S * (v[:, None, :] + es); t = TAU_T * (v[:, None, :] + et)
        ep.append(estimate_T(T_GRID, psi_pari(s, t, T_GRID, TAU_S)) - TAU_T)
        pp.append(estimate_T(T_GRID, psi_pooled(s, t, T_GRID, TAU_S)) - TAU_T)
    e = np.array(ep); q = np.array(pp)
    row = {'prototype_spread': h,
           'PARI_rmse': float(np.sqrt((e**2).mean())),
           'POOLED_rmse': float(np.sqrt((q**2).mean())),
           'gain': float(np.sqrt((q**2).mean()) / max(np.sqrt((e**2).mean()), 1e-12))}
    hrows.append(row)
    print(f'  spread={h:.2f}  PARI={row["PARI_rmse"]:.4f}  '
          f'POOLED={row["POOLED_rmse"]:.4f}  gain={row["gain"]:.2f}x', flush=True)
res['D3_heterogeneity_control'] = hrows

print('[D4] informative orbit size (selection bias) ...', flush=True)
d4rows = []
for x in [0.5, 1.0, 2.0]:
    ep, pp = [], []
    for _ in range(R):
        seed = int(rng.integers(0, 2**31 - 1))
        s, t, ms, mt = make_dgp_unbalanced(200, 8, imbalance=x, tau_t=TAU_T,
                                           tau_s=TAU_S, seed=seed,
                                           informative=True)
        a = psi_pari_ragged(s, t, ms, mt, T_GRID, TAU_S)
        b = psi_pooled_ragged(s, t, ms, mt, T_GRID, TAU_S)
        ep.append(estimate_T(T_GRID, a) - TAU_T)
        pp.append(estimate_T(T_GRID, b) - TAU_T)
    e = np.array(ep); q = np.array(pp)
    row = {'imbalance': x,
           'PARI_rmse': float(np.sqrt((e**2).mean())),
           'POOLED_rmse': float(np.sqrt((q**2).mean())),
           'PARI_bias': float(e.mean()), 'POOLED_bias': float(q.mean()),
           'gain': float(np.sqrt((q**2).mean()) / max(np.sqrt((e**2).mean()), 1e-12))}
    d4rows.append(row)
    print(f'  informative={x:.1f}  PARI={row["PARI_rmse"]:.4f}  '
          f'POOLED={row["POOLED_rmse"]:.4f}  '
          f'bias(PARI/POOLED)={row["PARI_bias"]:+.4f}/{row["POOLED_bias"]:+.4f}  '
          f'gain={row["gain"]:.2f}x', flush=True)
res['D4_informative_orbit'] = d4rows
best_d4 = float(np.max([r['gain'] for r in d4rows]))

res['conclusion'] = (
    'FALSIFIED. No tested regime gives PARI a consistent advantage: '
    'balanced orbits 1.00x (D3), skewed orbits 0.91-1.09x (D1), informative '
    'orbits 0.83-0.94x (D4, PARI worse). D4 does show the expected bias '
    'mechanism (PARI bias ~+0.001 vs POOLED ~-0.010) but pairing pays for it '
    'with larger variance, so RMSE is worse. Under this DGP family the '
    'patient-anchored estimator is NOT a better estimator of a global '
    'temperature than a simple pooled histogram matcher. Per the registered '
    'failure clause, PARI as specified must be DOWNGRADED / abandoned; it '
    'cannot be the novelty claim of the T1 paper. The surviving empirical '
    'finding is E5: group heterogeneity makes a single global T untransferable '
    '(regret 0 -> 0.156), which supports the PROBLEM, not this solution.')

fig, axes = plt.subplots(1, 2, figsize=(11, 4.1))
ax = axes[0]
ax.plot(imb, [r['PARI_rmse'] for r in rows], 'o-', color='#1f6feb', lw=2, label='PARI（患者加权）')
ax.plot(imb, [r['POOLED_rmse'] for r in rows], 's--', color='#d1242f', lw=1.8, label='POOLED（记录加权）')
ax.set_xlabel('轨道长度不均衡度'); ax.set_ylabel('RMSE(T_hat)')
ax.set_title('D1｜不均衡轨道是配对收益的来源'); ax.legend(fontsize=9); ax.grid(alpha=.3)
ax = axes[1]
ax.plot(imb, [r['gain'] for r in rows], 'o-', color='#2da44e', lw=2.2)
ax.axhline(1.0, color='#6e7781', ls=':', lw=1.5)
ax.set_xlabel('轨道长度不均衡度'); ax.set_ylabel('POOLED / PARI 的 RMSE 比')
ax.set_title('D1｜增益比（>1 表示 PARI 更优）'); ax.grid(alpha=.3)
fig.tight_layout(); fig.savefig(HERE / 'fig_D1_imbalance.png'); plt.close(fig)

(HERE / 'pari_diagnostic_results.json').write_text(
    json.dumps(res, indent=2, ensure_ascii=False), encoding='utf-8')
print('\n=== DIAGNOSTIC SUMMARY ===', flush=True)
print('best gain:', round(max(r['gain'] for r in rows), 2), 'x at imbalance =',
      rows[int(np.argmax([r['gain'] for r in rows]))]['imbalance'], flush=True)
print('F1 erases gain:', res['D2_falsification_in_winning_regime']['F1_erases_gain'], flush=True)
print('D4 best gain (informative orbit):', round(best_d4, 2), 'x', flush=True)
print(res['conclusion'], flush=True)
