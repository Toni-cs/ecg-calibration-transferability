"""W2 v1.1 CONFIRMATORY — fresh seeds 2000-2029.

Only change vs v1.0: uncertainty for the primary endpoint is now a
CROSS-SEED paired bootstrap (unit = DGP draw), fixing the unit mismatch.
Everything else (estimators, DGP, threshold, lambda selection, falsification)
is byte-identical to the frozen v1.0 design.
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
from gsgt import (make_group_dgp, build_psi_table, fit_global, fit_indep,
                  fit_shrink_global, fit_graph, logo_select_lambda,
                  apply_and_score, bootstrap_delta)

plt.rcParams['font.sans-serif'] = ['WenQuanYi Micro Hei']
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams['figure.dpi'] = 130

T_GRID = np.exp(np.linspace(np.log(0.7), np.log(5.0), 221))
LAM_GRID = np.array([0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 25.0])
SEEDS = list(range(2000, 2030))
KEYS = ['SOURCE', 'GLOBAL', 'INDEP', 'SHRINK-GLOBAL', 'GSGT', 'ORACLE']
B_SEED = 10000
B_REC = 2000

out = {'meta': {'prereg': 'PREREGISTRATION_W2_GSGT_v1_1.md (frozen)',
                'run_type': 'CONFIRMATORY v1.1', 'seeds': [SEEDS[0], SEEDS[-1], len(SEEDS)],
                'v1_0_result_retained': 'gsgt_confirmatory_results.json, H1=False',
                'single_change': 'primary-endpoint CI now cross-seed bootstrap',
                'unchanged': ['estimators', 'DGP', 'threshold -0.020', 'lambda LOGO-CV',
                              'F-A/B/C', 'ECE definition', 'n_bins=10'],
                'date': '2026-11-05'}}


def run_one(seed, spread=0.9, homogeneous=False, shuffle_graph=False,
            balanced_large=False, episodic_frac=0.0):
    d = make_group_dgp(G=12, n_families=3, spread=spread, seed=seed,
                       homogeneous=homogeneous, balanced_large=balanced_large,
                       episodic_frac=episodic_frac)
    W = d['W'].copy()
    if shuffle_graph:
        idx = np.random.default_rng(seed + 555).permutation(len(W))
        W = W[np.ix_(idx, idx)]
    psi = build_psi_table(d, T_GRID)
    n = d['sizes']
    lam, lam_curve = logo_select_lambda(psi, n, W, T_GRID, LAM_GRID)
    T = {'SOURCE': np.ones(len(n)), 'GLOBAL': fit_global(psi, n, T_GRID),
         'INDEP': fit_indep(psi, T_GRID),
         'SHRINK-GLOBAL': fit_shrink_global(psi, n, T_GRID),
         'GSGT': fit_graph(psi, n, W, T_GRID, lam), 'ORACLE': d['T_true']}
    sc = {k: apply_and_score(d, v) for k, v in T.items()}
    small = n < np.median(n)
    if not small.any():
        small = np.ones(len(n), bool)
    sm = {k: float(np.mean([s['per_group_ECE'][g] for g in np.where(small)[0]]))
          for k, s in sc.items()}
    return {'d': d, 'T': T, 'sc': sc, 'small': sm, 'lam': lam,
            'lam_curve': lam_curve.tolist(), 'sizes': n.tolist()}


def agg(runs):
    a = {}
    for k in KEYS:
        a[k] = {}
        for m in ['ECE', 'NLL', 'Brier']:
            v = np.array([r['sc'][k][m] for r in runs])
            a[k][m] = {'mean': float(v.mean()), 'sd': float(v.std(ddof=1))}
        v = np.array([r['small'][k] for r in runs])
        a[k]['small_ECE'] = {'mean': float(v.mean()), 'sd': float(v.std(ddof=1))}
    return a


print('[v1.1] 30 fresh seeds 2000-2029 ...', flush=True)
runs = [run_one(s) for s in SEEDS]
A = agg(runs)

# ---- F0 (unchanged) ----
orc, be = A['ORACLE']['ECE']['mean'], min(A[k]['ECE']['mean'] for k in KEYS if k != 'ORACLE')
on, bn = A['ORACLE']['NLL']['mean'], min(A[k]['NLL']['mean'] for k in KEYS if k != 'ORACLE')
f0 = {'ECE_PASS': bool(orc <= be + 1e-3), 'NLL_PASS': bool(on <= bn + 1e-3)}
f0['PASS'] = bool(f0['ECE_PASS'] and f0['NLL_PASS'])
out['F0'] = f0
print('   F0:', f0, flush=True)
if not f0['PASS']:
    raise SystemExit('F0 FAILED — all results discarded.')

# ---- H1 with CROSS-SEED bootstrap (the single v1.1 fix) ----
dlt = np.array([r['sc']['GSGT']['ECE'] - r['sc']['GLOBAL']['ECE'] for r in runs])
rng = np.random.default_rng(20261105)
boot_means = np.array([dlt[rng.integers(0, len(dlt), len(dlt))].mean()
                       for _ in range(B_SEED)])
ci = [float(np.percentile(boot_means, 2.5)), float(np.percentile(boot_means, 97.5))]
rec_boot = bootstrap_delta(runs[0]['d'], runs[0]['T']['GSGT'],
                           runs[0]['T']['GLOBAL'], B=B_REC, seed=31337)
h1 = {'delta_ECE_mean': float(dlt.mean()), 'delta_ECE_sd': float(dlt.std(ddof=1)),
      'n_negative_of_30': int((dlt < 0).sum()),
      't': float(dlt.mean() / max(dlt.std(ddof=1) / np.sqrt(len(dlt)), 1e-12)),
      'cross_seed_bootstrap_CI95': ci,
      'cross_seed_bootstrap_p': float((boot_means >= 0).mean()),
      'single_seed_record_bootstrap_SECONDARY_ONLY': rec_boot,
      'conditions': {'mean_le_-0.020': bool(dlt.mean() <= -0.020),
                     'ge_27_of_30_negative': bool((dlt < 0).sum() >= 27),
                     'cross_seed_CI_upper_lt_0': bool(ci[1] < 0)},
      'threshold': -0.020}
h1['PASS'] = all(h1['conditions'].values())
out['H1'] = h1
out['H1_aggregate'] = A
out['H1_attribution'] = {
    'GLOBAL_to_INDEP': float(A['INDEP']['ECE']['mean'] - A['GLOBAL']['ECE']['mean']),
    'INDEP_to_SHRINK': float(A['SHRINK-GLOBAL']['ECE']['mean'] - A['INDEP']['ECE']['mean']),
    'SHRINK_to_GSGT_graph': float(A['GSGT']['ECE']['mean'] - A['SHRINK-GLOBAL']['ECE']['mean']),
    'GSGT_vs_INDEP': float(A['GSGT']['ECE']['mean'] - A['INDEP']['ECE']['mean']),
    'small_group_GSGT_minus_INDEP': float(A['GSGT']['small_ECE']['mean'] -
                                          A['INDEP']['small_ECE']['mean'])}
for k in KEYS:
    print(f'   {k:15s} ECE={A[k]["ECE"]["mean"]:.4f}±{A[k]["ECE"]["sd"]:.4f}  '
          f'NLL={A[k]["NLL"]["mean"]:.4f}', flush=True)
print('   H1:', {k: v for k, v in h1.items() if k not in
                 ('single_seed_record_bootstrap_SECONDARY_ONLY',)}, flush=True)
print('   attribution:', out['H1_attribution'], flush=True)

# ---- F-A/B/C on the NEW seeds (unchanged definitions) ----
fa = agg([run_one(s, homogeneous=True) for s in SEEDS[:15]])
fb = agg([run_one(s, shuffle_graph=True) for s in SEEDS[:15]])
fc = agg([run_one(s, balanced_large=True) for s in SEEDS[:15]])
fa_d = fa['GSGT']['ECE']['mean'] - fa['SHRINK-GLOBAL']['ECE']['mean']
fb_d = fb['GSGT']['ECE']['mean'] - A['GSGT']['ECE']['mean']
fc_d = abs(fc['GSGT']['ECE']['mean'] - fc['INDEP']['ECE']['mean'])
out['F'] = {'FA': {'delta': fa_d, 'PASS': bool(abs(fa_d) < 0.005)},
            'FB': {'delta_vs_intact': fb_d, 'PASS': bool(fb_d > 0)},
            'FC': {'abs_delta': fc_d, 'PASS': bool(fc_d < 0.005)},
            'aggregates': {'FA': fa, 'FB': fb, 'FC': fc}}
print('   F-A', round(fa_d, 5), '| F-B', round(fb_d, 5), '| F-C', round(fc_d, 5), flush=True)

# ---- verdict ----
checks = {'F0': f0['PASS'], 'H1': h1['PASS'],
          'FA': out['F']['FA']['PASS'], 'FB': out['F']['FB']['PASS'],
          'FC': out['F']['FC']['PASS']}
out['verdict'] = {
    'checks': checks, 'all_pass': bool(all(checks.values())),
    'v1_0_H1_False_retained': True,
    'novelty_scope': ('NARROWED (locked by v1.0 clause): primary contribution is '
                      'GROUP-STRUCTURED TEMPERATURE ESTIMATION (single T -> G '
                      'temperatures from observable deployment metadata). Graph '
                      'shrinkage is a robustness component with a small '
                      'main-setting gain; NOT the primary novelty, NOT in the title.'),
    'terminal': 'If all_pass is False, GSGT is downgraded to exploratory; no v1.2 exists.'}
print('\n=== v1.1 FINAL VERDICT ===', flush=True)
print(checks, '| all_pass =', out['verdict']['all_pass'], flush=True)
print(out['verdict']['novelty_scope'], flush=True)
print('v1.0 H1=False RETAINED:', out['verdict']['v1_0_H1_False_retained'], flush=True)

# ---- figures ----
fig, axes = plt.subplots(1, 2, figsize=(10.6, 4.2))
cols = ['#8c959f', '#d1242f', '#bf8700', '#8250df', '#1f6feb', '#2da44e']
ax = axes[0]
v = [A[k]['ECE']['mean'] for k in KEYS]; e = [A[k]['ECE']['sd'] for k in KEYS]
b = ax.bar(range(6), v, yerr=e, color=cols, alpha=.9, capsize=3)
ax.bar_label(b, fmt='%.3f', fontsize=8, padding=2)
ax.set_xticks(range(6)); ax.set_xticklabels(KEYS, rotation=25, ha='right', fontsize=8)
ax.set_ylabel('ECE'); ax.set_title('v1.1 确认性｜全新种子 2000–2029'); ax.grid(alpha=.3, axis='y')
ax.set_ylim(0, max(np.array(v) + np.array(e)) * 1.2)
ax = axes[1]
seg = ['GLOBAL→INDEP', 'INDEP→SHRINK', 'SHRINK→GSGT\n(图)']
segv = [out['H1_attribution']['GLOBAL_to_INDEP'],
        out['H1_attribution']['INDEP_to_SHRINK'],
        out['H1_attribution']['SHRINK_to_GSGT_graph']]
ax.bar(seg, segv, color=['#bf8700', '#8250df', '#1f6feb'], alpha=.9)
ax.axhline(0, color='#333', lw=1); ax.set_ylabel('ΔECE')
ax.set_title('归因：增益来自群结构化，非图收缩'); ax.grid(alpha=.3, axis='y')
fig.tight_layout(); fig.savefig(HERE / 'fig_v1_1_main.png'); plt.close(fig)

fig, ax = plt.subplots(figsize=(7.4, 4.0))
ax.hist(boot_means, bins=60, color='#1f6feb', alpha=.85)
ax.axvline(0, color='#d1242f', lw=2, ls='--', label='零效应')
ax.axvline(ci[0], color='#2da44e', lw=1.5, ls=':')
ax.axvline(ci[1], color='#2da44e', lw=1.5, ls=':', label='95% CI')
ax.set_xlabel('跨种子 mean ΔECE'); ax.set_ylabel('bootstrap 频次')
ax.set_title(f'v1.1 跨种子 paired bootstrap (B={B_SEED})'); ax.legend(fontsize=9); ax.grid(alpha=.3)
fig.tight_layout(); fig.savefig(HERE / 'fig_v1_1_bootstrap.png'); plt.close(fig)

(HERE / 'gsgt_v1_1_results.json').write_text(
    json.dumps(out, indent=2, ensure_ascii=False), encoding='utf-8')
print('DONE', flush=True)
