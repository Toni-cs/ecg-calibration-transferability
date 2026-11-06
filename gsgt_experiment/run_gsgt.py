"""W2 main experiment — GSGT vs 6 baselines, with pre-registered falsification.

Everything here is decided BEFORE looking at results:
  * estimands, baselines, lambda selection, endpoints, CI, falsification tests.
See PREREGISTRATION_W2_GSGT.md.
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
                  apply_and_score, bootstrap_delta, ece, softmax)

plt.rcParams['font.sans-serif'] = ['WenQuanYi Micro Hei']
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams['figure.dpi'] = 130

T_GRID = np.exp(np.linspace(np.log(0.7), np.log(5.0), 221))
LAM_GRID = np.array([0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 25.0])
SEEDS = list(range(30))          # 30 independent DGP draws
B = 2000

res = {'meta': {'date': '2026-11-05', 'preregistration': 'PREREGISTRATION_W2_GSGT.md',
                'n_seeds': len(SEEDS), 'T_grid': [float(T_GRID[0]), float(T_GRID[-1]), len(T_GRID)],
                'lambda_grid': LAM_GRID.tolist(), 'bootstrap_B': B,
                'G': 12, 'families': 3, 'spread': 0.9, 'size_skew': 1.0}}


def one_run(seed, spread=0.9, homogeneous=False, shuffle_graph=False,
            balanced_large=False, size_skew=1.0, episodic_frac=0.0):
    d = make_group_dgp(G=12, n_families=3, spread=spread, size_skew=size_skew,
                       seed=seed, homogeneous=homogeneous,
                       balanced_large=balanced_large, episodic_frac=episodic_frac)
    W = d['W'].copy()
    if shuffle_graph:                                   # F-B
        idx = np.random.default_rng(seed + 555).permutation(len(W))
        W = W[np.ix_(idx, idx)]
    psi = build_psi_table(d, T_GRID)
    sizes = d['sizes']
    lam, lam_scores = logo_select_lambda(psi, sizes, W, T_GRID, LAM_GRID)

    T = {
        'SOURCE': np.ones(len(sizes)),
        'GLOBAL': fit_global(psi, sizes, T_GRID),
        'INDEP': fit_indep(psi, T_GRID),
        'SHRINK-GLOBAL': fit_shrink_global(psi, sizes, T_GRID),
        'GSGT': fit_graph(psi, sizes, W, T_GRID, lam),
        'ORACLE': d['T_true'],
    }
    scores = {k: apply_and_score(d, v) for k, v in T.items()}
    rmse = {k: float(np.sqrt(np.mean((np.log(v) - d['logT_true']) ** 2)))
            for k, v in T.items() if k != 'ORACLE'}
    # small-group stratum
    small = sizes < np.median(sizes)
    if not small.any():                       # balanced_large: all groups equal
        small = np.ones(len(sizes), dtype=bool)
    small_ece = {k: float(np.mean([s['per_group_ECE'][g] for g in np.where(small)[0]]))
                 for k, s in scores.items()}
    return {'d': d, 'lam': lam, 'lam_scores': lam_scores.tolist(),
            'scores': scores, 'rmse_logT': rmse, 'small_group_ECE': small_ece,
            'sizes': sizes.tolist(), 'T_true': d['T_true'].tolist()}


def aggregate(runs):
    keys = ['SOURCE', 'GLOBAL', 'INDEP', 'SHRINK-GLOBAL', 'GSGT', 'ORACLE']
    out = {}
    for k in keys:
        for m in ['ECE', 'NLL', 'Brier']:
            v = np.array([r['scores'][k][m] for r in runs])
            out.setdefault(k, {})[m] = {'mean': float(v.mean()), 'sd': float(v.std(ddof=1))}
        v = np.array([r['small_group_ECE'][k] for r in runs])
        out[k]['small_group_ECE'] = {'mean': float(v.mean()), 'sd': float(v.std(ddof=1))}
        if k in runs[0]['rmse_logT']:
            v = np.array([r['rmse_logT'][k] for r in runs])
            out[k]['rmse_logT'] = {'mean': float(v.mean()), 'sd': float(v.std(ddof=1))}
    return out


print('[H1] main comparison, 30 independent DGP draws ...', flush=True)
runs = [one_run(s) for s in SEEDS]
agg = aggregate(runs)
res['H1_main'] = agg
for k in ['SOURCE', 'GLOBAL', 'INDEP', 'SHRINK-GLOBAL', 'GSGT', 'ORACLE']:
    print(f'  {k:15s} ECE={agg[k]["ECE"]["mean"]:.4f}±{agg[k]["ECE"]["sd"]:.4f}  '
          f'NLL={agg[k]["NLL"]["mean"]:.4f}  '
          f'small={agg[k]["small_group_ECE"]["mean"]:.4f}  '
          f'rmse_logT={agg[k].get("rmse_logT",{}).get("mean",float("nan")):.4f}', flush=True)

# ---- F0: PRE-REGISTERED VALIDITY GATE -------------------------------------
# If the ORACLE temperature (true T_g) is not the best or tied-best, the DGP /
# metric implementation is broken and ALL results below must be discarded.
# This is a debug gate, not a result-selection device.
oracle_ece = agg['ORACLE']['ECE']['mean']
best_baseline_ece = min(agg[k]['ECE']['mean'] for k in
                        ['SOURCE', 'GLOBAL', 'INDEP', 'SHRINK-GLOBAL', 'GSGT'])
f0_pass = bool(oracle_ece <= best_baseline_ece + 1e-3)
oracle_nll = agg['ORACLE']['NLL']['mean']
best_nll = min(agg[k]['NLL']['mean'] for k in
               ['SOURCE', 'GLOBAL', 'INDEP', 'SHRINK-GLOBAL', 'GSGT'])
f0_nll_pass = bool(oracle_nll <= best_nll + 1e-3)
res['F0_oracle_validity_gate'] = {
    'oracle_ECE': oracle_ece, 'best_estimator_ECE': best_baseline_ece,
    'ECE_PASS': f0_pass,
    'oracle_NLL': oracle_nll, 'best_estimator_NLL': best_nll,
    'NLL_PASS': f0_nll_pass,
    'PASS': bool(f0_pass and f0_nll_pass),
    'note': ('If False the implementation is invalid; no result may be reported. '
             'NLL is strictly convex in T and provides a binning-free cross-check; '
             'a tiny ECE reversal at ORACLE is expected from finite-bin bias.')}
print(f'  F0 oracle gate: oracle={oracle_ece:.4f} best_estimator={best_baseline_ece:.4f} '
      f'PASS={f0_pass}', flush=True)
if not f0_pass:
    (HERE / 'gsgt_results.json').write_text(
        json.dumps(res, indent=2, ensure_ascii=False), encoding='utf-8')
    raise SystemExit('F0 FAILED — implementation invalid, results discarded (see JSON).')

d0 = runs[0]['d']
psi0 = build_psi_table(d0, T_GRID)
T0 = {'SOURCE': np.ones(12), 'GLOBAL': fit_global(psi0, d0['sizes'], T_GRID),
      'INDEP': fit_indep(psi0, T_GRID),
      'SHRINK-GLOBAL': fit_shrink_global(psi0, d0['sizes'], T_GRID),
      'GSGT': fit_graph(psi0, d0['sizes'], d0['W'], T_GRID, runs[0]['lam']),
      'ORACLE': d0['T_true']}
boot = bootstrap_delta(d0, T0['GSGT'], T0['GLOBAL'], B=B)
res['H1_bootstrap_delta_ECE_GSGT_minus_GLOBAL'] = boot
print('  delta ECE (GSGT - GLOBAL), seed0:', round(boot['delta_ECE'], 4),
      'CI95', [round(x, 4) for x in boot['ci95']],
      'p~', round(boot['p_two_sided_approx'], 4), flush=True)

# paired per-seed deltas across all 30 draws (stronger than one bootstrap)
pd_g = np.array([r['scores']['GSGT']['ECE'] - r['scores']['GLOBAL']['ECE'] for r in runs])
pd_s = np.array([r['scores']['GSGT']['ECE'] - r['scores']['SHRINK-GLOBAL']['ECE'] for r in runs])
pd_i = np.array([r['scores']['GSGT']['ECE'] - r['scores']['INDEP']['ECE'] for r in runs])
res['H1_paired_deltas_30seeds'] = {
    'vs_GLOBAL': {'mean': float(pd_g.mean()), 'sd': float(pd_g.std(ddof=1)),
                  'n_negative': int((pd_g < 0).sum()), 'n': len(pd_g),
                  't': float(pd_g.mean() / max(pd_g.std(ddof=1) / np.sqrt(len(pd_g)), 1e-12))},
    'vs_SHRINK_GLOBAL': {'mean': float(pd_s.mean()), 'n_negative': int((pd_s < 0).sum()),
                         't': float(pd_s.mean() / max(pd_s.std(ddof=1) / np.sqrt(len(pd_s)), 1e-12))},
    'vs_INDEP': {'mean': float(pd_i.mean()), 'n_negative': int((pd_i < 0).sum()),
                 't': float(pd_i.mean() / max(pd_i.std(ddof=1) / np.sqrt(len(pd_i)), 1e-12))}}
print('  paired 30 seeds: vs GLOBAL', round(pd_g.mean(), 4),
      f'({int((pd_g<0).sum())}/30 negative, t={res["H1_paired_deltas_30seeds"]["vs_GLOBAL"]["t"]:.1f})',
      '| vs SHRINK', round(pd_s.mean(), 4),
      f'({int((pd_s<0).sum())}/30 neg)', flush=True)

print('[H2] lambda sensitivity + LOGO curve ...', flush=True)
lam_counts = {str(l): int(sum(1 for r in runs if abs(r['lam'] - l) < 1e-9)) for l in LAM_GRID}
res['H2_lambda'] = {'selected_counts': lam_counts,
                    'LOGO_score_curve_seed0': runs[0]['lam_scores']}
print('  lambda selected:', lam_counts, flush=True)

print('[F-A] homogeneous groups (spread=0) ...', flush=True)
fa = [one_run(s, homogeneous=True) for s in SEEDS[:15]]
res['FA_homogeneous'] = aggregate(fa)
print('  GSGT-SHRINK delta ECE =',
      round(res['FA_homogeneous']['GSGT']['ECE']['mean'] -
            res['FA_homogeneous']['SHRINK-GLOBAL']['ECE']['mean'], 5), flush=True)

print('[F-B] shuffled graph ...', flush=True)
fb = [one_run(s, shuffle_graph=True) for s in SEEDS[:15]]
res['FB_shuffled_graph'] = aggregate(fb)
print('  shuffled GSGT ECE =', round(res['FB_shuffled_graph']['GSGT']['ECE']['mean'], 4),
      'vs intact =', round(agg['GSGT']['ECE']['mean'], 4), flush=True)

print('[F-C] large balanced groups ...', flush=True)
fc = [one_run(s, balanced_large=True) for s in SEEDS[:15]]
res['FC_large_balanced'] = aggregate(fc)
print('  INDEP ECE =', round(res['FC_large_balanced']['INDEP']['ECE']['mean'], 4),
      'GSGT ECE =', round(res['FC_large_balanced']['GSGT']['ECE']['mean'], 4), flush=True)

print('[F-D] episodic-label subgroup (A1-violating layer) ...', flush=True)
fd = [one_run(s, episodic_frac=0.3) for s in SEEDS[:15]]
res['FD_episodic'] = aggregate(fd)
print('  GSGT ECE =', round(res['FD_episodic']['GSGT']['ECE']['mean'], 4),
      'GLOBAL ECE =', round(res['FD_episodic']['GLOBAL']['ECE']['mean'], 4), flush=True)

print('[S1] scale-up: spread x size_skew ...', flush=True)
srows = []
for sp in [0.3, 0.6, 0.9, 1.3]:
    for sk in [0.6, 1.0, 1.5]:
        rr = [one_run(s, spread=sp, size_skew=sk) for s in SEEDS[:8]]
        a = aggregate(rr)
        srows.append({'spread': sp, 'size_skew': sk,
                      'delta_vs_GLOBAL': float(a['GSGT']['ECE']['mean'] - a['GLOBAL']['ECE']['mean']),
                      'delta_vs_SHRINK': float(a['GSGT']['ECE']['mean'] - a['SHRINK-GLOBAL']['ECE']['mean']),
                      'GSGT_ECE': a['GSGT']['ECE']['mean']})
res['S1_sensitivity_grid'] = srows

# ---------------------------------------------------------------- figures
fig, axes = plt.subplots(1, 3, figsize=(14, 4.2))
ax = axes[0]
keys = ['SOURCE', 'GLOBAL', 'INDEP', 'SHRINK-GLOBAL', 'GSGT', 'ORACLE']
vals = [agg[k]['ECE']['mean'] for k in keys]
errs = [agg[k]['ECE']['sd'] for k in keys]
cols = ['#8c959f', '#d1242f', '#bf8700', '#8250df', '#1f6feb', '#2da44e']
b = ax.bar(range(len(keys)), vals, yerr=errs, color=cols, alpha=.9, capsize=3)
ax.bar_label(b, fmt='%.3f', fontsize=8, padding=2)
ax.set_xticks(range(len(keys))); ax.set_xticklabels(keys, rotation=25, ha='right', fontsize=8)
ax.set_ylabel('ECE（越低越好）'); ax.set_title('H1｜六种估计器主终点（30 次独立重复）')
ax.grid(alpha=.3, axis='y'); ax.set_ylim(0, max(np.array(vals) + np.array(errs)) * 1.2)

ax = axes[1]
svals = [agg[k]['small_group_ECE']['mean'] for k in keys]
ax.bar(range(len(keys)), svals, color=cols, alpha=.9)
ax.set_xticks(range(len(keys))); ax.set_xticklabels(keys, rotation=25, ha='right', fontsize=8)
ax.set_ylabel('小群 ECE'); ax.set_title('H1｜小群子集（长尾 cart_id 场景）'); ax.grid(alpha=.3, axis='y')

ax = axes[2]
ax.bar(range(len(keys[:-1])), [agg[k]['rmse_logT']['mean'] for k in keys[:-1]],
       color=cols[:-1], alpha=.9)
ax.set_xticks(range(len(keys[:-1]))); ax.set_xticklabels(keys[:-1], rotation=25, ha='right', fontsize=8)
ax.set_ylabel('RMSE(log T_hat)'); ax.set_title('H1｜真实温度恢复误差'); ax.grid(alpha=.3, axis='y')
fig.tight_layout(); fig.savefig(HERE / 'fig_H1_main.png'); plt.close(fig)

fig, ax = plt.subplots(figsize=(7.6, 4.2))
conds = ['主设定', 'F-A\n群同质', 'F-B\n打乱图', 'F-C\n大且均衡', 'F-D\n阵发标签']
sets = [agg, res['FA_homogeneous'], res['FB_shuffled_graph'],
        res['FC_large_balanced'], res['FD_episodic']]
g = [s['GSGT']['ECE']['mean'] for s in sets]
sh = [s['SHRINK-GLOBAL']['ECE']['mean'] for s in sets]
gl = [s['GLOBAL']['ECE']['mean'] for s in sets]
x = np.arange(len(conds)); w = 0.26
ax.bar(x - w, gl, w, label='GLOBAL', color='#d1242f', alpha=.9)
ax.bar(x, sh, w, label='SHRINK-GLOBAL', color='#8250df', alpha=.9)
ax.bar(x + w, g, w, label='GSGT', color='#1f6feb', alpha=.9)
ax.set_xticks(x); ax.set_xticklabels(conds, fontsize=9)
ax.set_ylabel('ECE'); ax.set_title('证伪检验：优势应在图/异质性被破坏时消失')
ax.legend(fontsize=9); ax.grid(alpha=.3, axis='y')
fig.tight_layout(); fig.savefig(HERE / 'fig_F_falsification.png'); plt.close(fig)

fig, ax = plt.subplots(figsize=(7.2, 4.2))
ax.plot(LAM_GRID, runs[0]['lam_scores'], 'o-', color='#2da44e', lw=2)
best = runs[0]['lam']
ax.axvline(best, color='#1f6feb', ls='--', lw=1.8, label=f'LOGO 选中 λ={best:g}')
ax.set_xscale('log'); ax.set_xlabel('λ'); ax.set_ylabel('LOGO 无标签 CV 得分')
ax.set_title('H2｜λ 由留一群无标签交叉验证事前确定'); ax.legend(); ax.grid(alpha=.3)
fig.tight_layout(); fig.savefig(HERE / 'fig_H2_lambda.png'); plt.close(fig)

(HERE / 'gsgt_results.json').write_text(
    json.dumps(res, indent=2, ensure_ascii=False), encoding='utf-8')

print('\n=== W2 SUMMARY ===', flush=True)
print('GSGT ECE', round(agg['GSGT']['ECE']['mean'], 4),
      '| GLOBAL', round(agg['GLOBAL']['ECE']['mean'], 4),
      '| SHRINK', round(agg['SHRINK-GLOBAL']['ECE']['mean'], 4),
      '| ORACLE', round(agg['ORACLE']['ECE']['mean'], 4), flush=True)
print('improvement vs GLOBAL:', round(-pd_g.mean(), 4),
      f'({int((pd_g<0).sum())}/30 seeds better)', flush=True)
print('bootstrap CI:', [round(x, 4) for x in boot['ci95']], flush=True)
print('F-A (should be ~0):', round(res['FA_homogeneous']['GSGT']['ECE']['mean'] -
      res['FA_homogeneous']['SHRINK-GLOBAL']['ECE']['mean'], 5), flush=True)
print('F-B (should degrade):', round(res['FB_shuffled_graph']['GSGT']['ECE']['mean'], 4), flush=True)
print('F-C (should converge):', round(res['FC_large_balanced']['INDEP']['ECE']['mean'], 4),
      round(res['FC_large_balanced']['GSGT']['ECE']['mean'], 4), flush=True)
print('DONE', flush=True)
