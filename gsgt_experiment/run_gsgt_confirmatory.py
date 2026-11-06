"""W2 CONFIRMATORY run — frozen design, fresh independent seeds 1000-1029.

The exploratory run (run_gsgt.py, seeds 0-29) is NOT citable. Only this file's
output constitutes the paper-level evidence, per PREREGISTRATION_W2_GSGT.md.
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
SEEDS = list(range(1000, 1030))
B = 2000
KEYS = ['SOURCE', 'GLOBAL', 'INDEP', 'SHRINK-GLOBAL', 'GSGT', 'ORACLE']

out = {'meta': {'prereg': 'PREREGISTRATION_W2_GSGT.md v1.0 (frozen)',
                'run_type': 'CONFIRMATORY', 'seeds': [SEEDS[0], SEEDS[-1], len(SEEDS)],
                'exploratory_seeds_excluded': '0-29, not citable',
                'T_grid_n': len(T_GRID), 'lambda_grid': LAM_GRID.tolist(),
                'bootstrap_B': B, 'date': '2026-11-05'}}


def run_one(seed, spread=0.9, homogeneous=False, shuffle_graph=False,
            balanced_large=False, size_skew=1.0, n_min=15, episodic_frac=0.0):
    d = make_group_dgp(G=12, n_families=3, spread=spread, size_skew=size_skew,
                       n_min=n_min, seed=seed, homogeneous=homogeneous,
                       balanced_large=balanced_large, episodic_frac=episodic_frac)
    W = d['W'].copy()
    if shuffle_graph:
        idx = np.random.default_rng(seed + 555).permutation(len(W))
        W = W[np.ix_(idx, idx)]
    psi = build_psi_table(d, T_GRID)
    n = d['sizes']
    lam, scores_lam = logo_select_lambda(psi, n, W, T_GRID, LAM_GRID)
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
    rm = {k: float(np.sqrt(np.mean((np.log(v) - d['logT_true']) ** 2)))
          for k, v in T.items() if k != 'ORACLE'}
    return {'d': d, 'T': T, 'sc': sc, 'small': sm, 'rmse': rm,
            'lam': lam, 'lam_curve': scores_lam.tolist(), 'sizes': n.tolist()}


def agg(runs):
    a = {}
    for k in KEYS:
        a[k] = {}
        for m in ['ECE', 'NLL', 'Brier']:
            v = np.array([r['sc'][k][m] for r in runs])
            a[k][m] = {'mean': float(v.mean()), 'sd': float(v.std(ddof=1))}
        v = np.array([r['small'][k] for r in runs])
        a[k]['small_ECE'] = {'mean': float(v.mean()), 'sd': float(v.std(ddof=1))}
        if k in runs[0]['rmse']:
            v = np.array([r['rmse'][k] for r in runs])
            a[k]['rmse_logT'] = {'mean': float(v.mean()), 'sd': float(v.std(ddof=1))}
    return a


print('[F0] validity gate ...', flush=True)
main = [run_one(s) for s in SEEDS]
A = agg(main)
orc_ece = A['ORACLE']['ECE']['mean']
best_ece = min(A[k]['ECE']['mean'] for k in KEYS if k != 'ORACLE')
orc_nll = A['ORACLE']['NLL']['mean']
best_nll = min(A[k]['NLL']['mean'] for k in KEYS if k != 'ORACLE')
f0 = {'oracle_ECE': orc_ece, 'best_estimator_ECE': best_ece,
      'ECE_PASS': bool(orc_ece <= best_ece + 1e-3),
      'oracle_NLL': orc_nll, 'best_estimator_NLL': best_nll,
      'NLL_PASS': bool(orc_nll <= best_nll + 1e-3)}
f0['PASS'] = bool(f0['ECE_PASS'] and f0['NLL_PASS'])
out['F0'] = f0
print('   ', f0, flush=True)
if not f0['PASS']:
    (HERE / 'gsgt_confirmatory_results.json').write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding='utf-8')
    raise SystemExit('F0 FAILED — all results discarded.')

print('[H1] primary endpoint ...', flush=True)
dlt = np.array([r['sc']['GSGT']['ECE'] - r['sc']['GLOBAL']['ECE'] for r in main])
d_s = np.array([r['sc']['GSGT']['ECE'] - r['sc']['SHRINK-GLOBAL']['ECE'] for r in main])
d_i = np.array([r['sc']['GSGT']['ECE'] - r['sc']['INDEP']['ECE'] for r in main])
boot = bootstrap_delta(main[0]['d'], main[0]['T']['GSGT'],
                       main[0]['T']['GLOBAL'], B=B, seed=20261105)
h1 = {'delta_ECE_mean': float(dlt.mean()), 'delta_ECE_sd': float(dlt.std(ddof=1)),
      'n_negative_of_30': int((dlt < 0).sum()),
      't': float(dlt.mean() / max(dlt.std(ddof=1) / np.sqrt(len(dlt)), 1e-12)),
      'bootstrap_seed1000': boot,
      'threshold': -0.020,
      'PASS': bool(dlt.mean() <= -0.020 and (dlt < 0).sum() >= 27
                   and boot['ci95'][1] < 0)}
out['H1'] = h1
out['H1_aggregate'] = A
out['H1_attribution'] = {
    'GLOBAL_to_INDEP': float(A['INDEP']['ECE']['mean'] - A['GLOBAL']['ECE']['mean']),
    'INDEP_to_SHRINK': float(A['SHRINK-GLOBAL']['ECE']['mean'] - A['INDEP']['ECE']['mean']),
    'SHRINK_to_GSGT_graph': float(A['GSGT']['ECE']['mean'] - A['SHRINK-GLOBAL']['ECE']['mean']),
    'GSGT_vs_INDEP': float(d_i.mean()),
    'GSGT_vs_SHRINK': float(d_s.mean()),
    'small_group_GSGT_minus_INDEP': float(A['GSGT']['small_ECE']['mean'] -
                                          A['INDEP']['small_ECE']['mean'])}
for k in KEYS:
    print(f'   {k:15s} ECE={A[k]["ECE"]["mean"]:.4f}±{A[k]["ECE"]["sd"]:.4f}  '
          f'NLL={A[k]["NLL"]["mean"]:.4f}  small={A[k]["small_ECE"]["mean"]:.4f}', flush=True)
print('   H1:', h1, flush=True)
print('   attribution:', out['H1_attribution'], flush=True)

print('[H2] lambda ...', flush=True)
lam_count = {str(l): int(sum(1 for r in main if abs(r['lam'] - l) < 1e-9)) for l in LAM_GRID}
out['H2'] = {'selected_counts': lam_count, 'LOGO_curve_seed1000': main[0]['lam_curve']}

print('[F-A..F-D] falsification ...', flush=True)
fa = agg([run_one(s, homogeneous=True) for s in SEEDS[:15]])
fb = agg([run_one(s, shuffle_graph=True) for s in SEEDS[:15]])
fc = agg([run_one(s, balanced_large=True) for s in SEEDS[:15]])
fd = agg([run_one(s, episodic_frac=0.3) for s in SEEDS[:15]])
fa_d = fa['GSGT']['ECE']['mean'] - fa['SHRINK-GLOBAL']['ECE']['mean']
fb_d = fb['GSGT']['ECE']['mean'] - A['GSGT']['ECE']['mean']
fc_d = abs(fc['GSGT']['ECE']['mean'] - fc['INDEP']['ECE']['mean'])
out['F'] = {
    'FA_homogeneous': {'delta_GSGT_minus_SHRINK': fa_d, 'PASS': bool(abs(fa_d) < 0.005),
                       'aggregate': fa},
    'FB_shuffled_graph': {'delta_vs_intact': fb_d, 'PASS': bool(fb_d > 0),
                          'aggregate': fb},
    'FC_large_balanced': {'abs_delta_GSGT_minus_INDEP': fc_d, 'PASS': bool(fc_d < 0.005),
                          'aggregate': fc},
    'FD_episodic': {'aggregate': fd, 'GSGT_ECE': fd['GSGT']['ECE']['mean'],
                    'GLOBAL_ECE': fd['GLOBAL']['ECE']['mean']}}
print('   F-A', round(fa_d, 5), '| F-B', round(fb_d, 5), '| F-C', round(fc_d, 5), flush=True)

print('[S2] pre-registered long-tail stress test ...', flush=True)
s2_base = agg([run_one(s, n_min=8, size_skew=1.6) for s in SEEDS[:15]])
s2_ctl = agg([run_one(s, n_min=15, size_skew=1.0) for s in SEEDS[:15]])
g_base = s2_base['GSGT']['ECE']['mean'] - s2_base['INDEP']['ECE']['mean']
g_ctl = s2_ctl['GSGT']['ECE']['mean'] - s2_ctl['INDEP']['ECE']['mean']
out['S2_longtail'] = {
    'delta_GSGT_minus_INDEP_longtail': g_base,
    'delta_GSGT_minus_INDEP_control': g_ctl,
    'predicted_direction': 'long-tail advantage should be MORE negative',
    'PASS': bool(g_base < g_ctl),
    'longtail_aggregate': s2_base, 'control_aggregate': s2_ctl}
print('   long-tail', round(g_base, 5), '| control', round(g_ctl, 5),
      '| PASS', out['S2_longtail']['PASS'], flush=True)

print('[S1] sensitivity grid ...', flush=True)
grid = []
for sp in [0.3, 0.6, 0.9, 1.3]:
    for sk in [0.6, 1.0, 1.5]:
        a = agg([run_one(s, spread=sp, size_skew=sk) for s in SEEDS[:8]])
        grid.append({'spread': sp, 'size_skew': sk,
                     'delta_vs_GLOBAL': a['GSGT']['ECE']['mean'] - a['GLOBAL']['ECE']['mean'],
                     'delta_vs_SHRINK': a['GSGT']['ECE']['mean'] - a['SHRINK-GLOBAL']['ECE']['mean']})
out['S1_grid'] = grid

# ------------------------------------------------------------ verdict
checks = {'F0': f0['PASS'], 'H1': h1['PASS'],
          'FA': out['F']['FA_homogeneous']['PASS'],
          'FB': out['F']['FB_shuffled_graph']['PASS'],
          'FC': out['F']['FC_large_balanced']['PASS']}
graph_share = out['H1_attribution']['SHRINK_to_GSGT_graph']
if abs(graph_share) < 0.002:
    out['novelty_scope'] = ('NARROWED per pre-registered clause: the dominant '
                            'contribution is GROUP-STRUCTURED ESTIMATION (single T -> G '
                            'temperatures). Graph shrinkage is a robustness component '
                            'with a small main-setting gain; it must NOT be presented '
                            'as the primary novelty.')
else:
    out['novelty_scope'] = 'Graph shrinkage contributes materially; full claim allowed.'
out['verdict'] = {
    'checks': checks, 'all_pass': all(checks.values()),
    'formal_result_citable': all(checks.values()),
    'note': 'Only this confirmatory run (seeds 1000-1029) is citable.'}
print('\n=== CONFIRMATORY VERDICT ===', flush=True)
print(checks, '| all_pass =', all(checks.values()), flush=True)
print(out['novelty_scope'], flush=True)

# ------------------------------------------------------------ figures
fig, axes = plt.subplots(1, 3, figsize=(14, 4.2))
cols = ['#8c959f', '#d1242f', '#bf8700', '#8250df', '#1f6feb', '#2da44e']
ax = axes[0]
v = [A[k]['ECE']['mean'] for k in KEYS]; e = [A[k]['ECE']['sd'] for k in KEYS]
b = ax.bar(range(6), v, yerr=e, color=cols, alpha=.9, capsize=3)
ax.bar_label(b, fmt='%.3f', fontsize=8, padding=2)
ax.set_xticks(range(6)); ax.set_xticklabels(KEYS, rotation=25, ha='right', fontsize=8)
ax.set_ylabel('ECE'); ax.set_title('确认性 H1｜30 个全新种子'); ax.grid(alpha=.3, axis='y')
ax.set_ylim(0, max(np.array(v) + np.array(e)) * 1.2)
ax = axes[1]
ax.bar(range(6), [A[k]['small_ECE']['mean'] for k in KEYS], color=cols, alpha=.9)
ax.set_xticks(range(6)); ax.set_xticklabels(KEYS, rotation=25, ha='right', fontsize=8)
ax.set_ylabel('小群 ECE'); ax.set_title('小群子集（长尾 cart_id）'); ax.grid(alpha=.3, axis='y')
ax = axes[2]
seg = ['GLOBAL→INDEP', 'INDEP→SHRINK', 'SHRINK→GSGT\n(图)']
segv = [out['H1_attribution']['GLOBAL_to_INDEP'],
        out['H1_attribution']['INDEP_to_SHRINK'],
        out['H1_attribution']['SHRINK_to_GSGT_graph']]
ax.bar(seg, segv, color=['#bf8700', '#8250df', '#1f6feb'], alpha=.9)
ax.axhline(0, color='#333', lw=1)
ax.set_ylabel('ΔECE'); ax.set_title('归因拆解：增益主要来自群结构化'); ax.grid(alpha=.3, axis='y')
fig.tight_layout(); fig.savefig(HERE / 'fig_confirmatory_main.png'); plt.close(fig)

fig, ax = plt.subplots(figsize=(7.6, 4.2))
conds = ['主设定', 'F-A\n群同质', 'F-B\n打乱图', 'F-C\n大且均衡', 'F-D\n阵发标签', 'S2\n长尾压力']
sets = [A, fa, fb, fc, fd, s2_base]
x = np.arange(len(conds)); w = .26
ax.bar(x - w, [s['GLOBAL']['ECE']['mean'] for s in sets], w, label='GLOBAL', color='#d1242f', alpha=.9)
ax.bar(x, [s['SHRINK-GLOBAL']['ECE']['mean'] for s in sets], w, label='SHRINK', color='#8250df', alpha=.9)
ax.bar(x + w, [s['GSGT']['ECE']['mean'] for s in sets], w, label='GSGT', color='#1f6feb', alpha=.9)
ax.set_xticks(x); ax.set_xticklabels(conds, fontsize=9)
ax.set_ylabel('ECE'); ax.set_title('确认性证伪与压力测试'); ax.legend(fontsize=9); ax.grid(alpha=.3, axis='y')
fig.tight_layout(); fig.savefig(HERE / 'fig_confirmatory_falsification.png'); plt.close(fig)

(HERE / 'gsgt_confirmatory_results.json').write_text(
    json.dumps(out, indent=2, ensure_ascii=False), encoding='utf-8')
print('DONE', flush=True)
