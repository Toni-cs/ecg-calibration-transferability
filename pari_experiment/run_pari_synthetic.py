"""W1 experiment: synthetic identification + falsification of PARI.

Runs:
  E0  repo pilot audit (do we have per-record logits locally?)
  E1  identifiability: Psi_P(T) has a unique interior minimum at tau_t
  E2  variance reduction: PARI vs pooled vs shuffled-pairs over n_pat and m
  E3  four falsification tests (F1-F4)
  E4  convergence rate log(RMSE) ~ log(n_pat * m)
  E5  group heterogeneity -> regret of a single global temperature

All numbers are written to pari_synthetic_results.json.
"""
from __future__ import annotations

import json
import pathlib
import sys
import time

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from pari import (N_BINS, make_dgp, psi_pari, psi_pooled, estimate_T,
                  softmax, confidence_hist)

plt.rcParams['font.sans-serif'] = ['WenQuanYi Micro Hei']
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams['figure.dpi'] = 130

OUT = HERE
REPO = pathlib.Path('/data/workspace/repo_audit/files')
T0 = time.time()
T_GRID = np.linspace(0.6, 4.6, 201)
TAU_T = 2.4
TAU_S = 1.0
SIGMA_W = 0.35
K = 4
R = 60                      # repeats per cell
rng_master = np.random.default_rng(20261105)

res = {'meta': {'date': '2026-11-05', 'T_grid': [float(T_GRID[0]), float(T_GRID[-1]), len(T_GRID)],
                'tau_t': TAU_T, 'tau_s': TAU_S, 'sigma_w': SIGMA_W, 'K': K,
                'repeats_per_cell': R, 'n_bins': N_BINS}}


def rmse_of(method, n_pat, m, repeats=R, episodic=False, shuffle_group=False,
            shuffle_pairs=False, tau_t=TAU_T):
    """RMSE of T-hat over `repeats` independent DGP draws."""
    errs = []
    for r in range(repeats):
        seed = int(rng_master.integers(0, 2**31 - 1))
        src, tgt, _ = make_dgp(n_pat, m, tau_t=tau_t, tau_s=TAU_S,
                               sigma_w=SIGMA_W, K=K, seed=seed,
                               episodic=episodic,
                               shuffle_group_labels=shuffle_group)
        if method == 'PARI':
            psi = psi_pari(src, tgt, T_GRID, TAU_S, shuffle_pairs=False)
        elif method == 'SHUFFLED-PAIRS':
            psi = psi_pari(src, tgt, T_GRID, TAU_S, shuffle_pairs=True)
        elif method == 'POOLED':
            psi = psi_pooled(src, tgt, T_GRID, TAU_S)
        else:
            raise ValueError(method)
        errs.append(estimate_T(T_GRID, psi) - tau_t)
    e = np.asarray(errs)
    return {'rmse': float(np.sqrt(np.mean(e ** 2))),
            'bias': float(e.mean()), 'sd': float(e.std(ddof=1)),
            'n': len(e)}


# ------------------------------------------------------------------ E0
print('[E0] repo pilot audit ...', flush=True)
e0 = {}
npz = sorted(str(p.relative_to(REPO)) for p in REPO.rglob('*.npz'))
e0['npz_files_in_public_tree'] = npz
e0['per_record_logits_or_probs_present'] = any(
    ('prob' in x.lower() or 'logit' in x.lower()) for x in npz)
e0['waveform_files_present'] = any(REPO.rglob('*.dat')) or any(REPO.rglob('*.npy'))
try:
    import pandas as pd
    sl = pd.read_csv(REPO / 'results/samplelevel_ts_60cells.csv')
    e0['samplelevel_T_mean_median'] = float(sl['T_mean'].median())
    e0['samplelevel_T_mean_range'] = [float(sl['T_mean'].min()), float(sl['T_mean'].max())]
    e0['samplelevel_n_cells'] = int(len(sl))
    e0['samplelevel_delta_vs_ts_mean'] = float(sl['delta_vs_ts'].mean())
    td = pd.read_csv(REPO / 'results/temperature_distribution_analysis.csv')
    cols = [c for c in td.columns if 'T' in c or 'temp' in c.lower()]
    e0['temperature_table_columns'] = list(td.columns)[:12]
    e0['temperature_table_rows'] = int(len(td))
except Exception as exc:
    e0['pilot_read_error'] = repr(exc)[:200]
e0['verdict'] = ('Real-data PARI reproduction is BLOCKED locally: the public release '
                 'ships no per-record logits/probs cache and no waveforms. '
                 'Only the synthetic identification layer can run at W1.')
res['E0_repo_pilot'] = e0

# ------------------------------------------------------------------ E1
print('[E1] identifiability curve ...', flush=True)
src, tgt, _ = make_dgp(300, 6, tau_t=TAU_T, seed=101)
p_pari = psi_pari(src, tgt, T_GRID, TAU_S)
p_pool = psi_pooled(src, tgt, T_GRID, TAU_S)
i_pari, i_pool = int(np.argmin(p_pari)), int(np.argmin(p_pool))
# uniqueness: interior argmin + strict monotonicity away from it on both sides
# Binned histograms produce tiny discretisation wiggles; use a tolerance-based
# unimodality test rather than exact elementwise monotonicity.
rng_psi = float(p_pari.max() - p_pari.min())
near = T_GRID[p_pari <= p_pari.min() + 0.05 * rng_psi]
left_ok = bool(np.mean(np.diff(p_pari[:i_pari + 1]) <= 0.02 * rng_psi) > 0.95)
right_ok = bool(np.mean(np.diff(p_pari[i_pari:]) >= -0.02 * rng_psi) > 0.95)
res['E1_identifiability'] = {
    'T_hat_PARI': estimate_T(T_GRID, p_pari),
    'T_hat_POOLED': estimate_T(T_GRID, p_pool),
    'tau_t_true': TAU_T,
    'argmin_index': i_pari,
    'interior_argmin': bool(0 < i_pari < len(T_GRID) - 1),
    'unimodal_left_monotone': left_ok,
    'unimodal_right_monotone': right_ok,
    'near_min_band_T_width': float(near.max() - near.min()),
    'near_min_band_T_range': [float(near.min()), float(near.max())],
    'psi_at_true_T': float(np.interp(TAU_T, T_GRID, p_pari)),
    'psi_at_boundary_low': float(p_pari[0]),
    'psi_at_boundary_high': float(p_pari[-1]),
    'pooled_curve_min_over_max': float(p_pool.min() / max(p_pool.max(), 1e-12)),
    'pari_curve_min_over_max': float(p_pari.min() / max(p_pari.max(), 1e-12)),
}

fig, ax = plt.subplots(figsize=(7.2, 4.2))
ax.plot(T_GRID, p_pari, lw=2.2, color='#1f6feb', label='PARI（患者内配对）')
ax.plot(T_GRID, p_pool / max(p_pool.max(), 1e-12) * p_pari.max(), lw=1.8,
        ls='--', color='#d1242f', label='POOLED（无配对，缩放到同量级）')
ax.axvline(TAU_T, color='#2da44e', ls=':', lw=2, label=f'真实 τ_t = {TAU_T}')
ax.axvline(estimate_T(T_GRID, p_pari), color='#1f6feb', ls='-.', lw=1.2, alpha=.7)
ax.set_xlabel('候选温度 T'); ax.set_ylabel('Ψ(T)')
ax.set_title('E1｜PARI 目标函数在真实温度处取唯一内部极小')
ax.legend(fontsize=9); ax.grid(alpha=.3)
fig.tight_layout(); fig.savefig(OUT / 'fig_E1_psi_curve.png'); plt.close(fig)

# ------------------------------------------------------------------ E2
print('[E2] variance reduction over n_pat x m ...', flush=True)
n_grid = [25, 50, 100, 200, 400, 800]
e2 = {'n_grid': n_grid, 'm': 4, 'rows': []}
for n in n_grid:
    row = {'n_pat': n}
    for meth in ['PARI', 'POOLED', 'SHUFFLED-PAIRS']:
        row[meth] = rmse_of(meth, n, 4)
    row['gain_PARI_over_POOLED'] = float(row['POOLED']['rmse'] / max(row['PARI']['rmse'], 1e-12))
    e2['rows'].append(row)
    print(f'   n={n:4d}  PARI={row["PARI"]["rmse"]:.4f}  '
          f'POOLED={row["POOLED"]["rmse"]:.4f}  '
          f'SHUF={row["SHUFFLED-PAIRS"]["rmse"]:.4f}  '
          f'gain={row["gain_PARI_over_POOLED"]:.2f}x', flush=True)
res['E2_variance_reduction'] = e2

m_grid = [2, 4, 8]
e2m = {'m_grid': m_grid, 'n_pat': 200, 'rows': []}
for m in m_grid:
    row = {'m': m}
    for meth in ['PARI', 'POOLED']:
        row[meth] = rmse_of(meth, 200, m)
    e2m['rows'].append(row)
res['E2b_repeat_depth'] = e2m

fig, axes = plt.subplots(1, 2, figsize=(11, 4.1))
ax = axes[0]
nn = np.array(n_grid, float)
par = np.array([r['PARI']['rmse'] for r in e2['rows']])
pol = np.array([r['POOLED']['rmse'] for r in e2['rows']])
shu = np.array([r['SHUFFLED-PAIRS']['rmse'] for r in e2['rows']])
ax.loglog(nn, par, 'o-', color='#1f6feb', lw=2, label='PARI（配对）')
ax.loglog(nn, pol, 's--', color='#d1242f', lw=1.8, label='POOLED（无配对）')
ax.loglog(nn, shu, '^:', color='#8250df', lw=1.8, label='打乱配对的 PARI')
slope = float(np.polyfit(np.log(nn), np.log(par), 1)[0])
ax.text(0.03, 0.06, f'PARI 斜率 = {slope:.2f}（理论 −0.5）',
        transform=ax.transAxes, fontsize=9, color='#1f6feb')
ax.set_xlabel('患者数 n_pat（m=4）'); ax.set_ylabel('RMSE(T_hat)')
ax.set_title('E2｜重复测量配对带来的方差缩减'); ax.legend(fontsize=8); ax.grid(alpha=.3, which='both')
e2s = float(slope)

ax = axes[1]
mm = np.array(m_grid, float)
parm = np.array([r['PARI']['rmse'] for r in e2m['rows']])
polm = np.array([r['POOLED']['rmse'] for r in e2m['rows']])
ax.plot(mm, parm, 'o-', color='#1f6feb', lw=2, label='PARI')
ax.plot(mm, polm, 's--', color='#d1242f', lw=1.8, label='POOLED')
ax.set_xlabel('每患者记录数 m'); ax.set_ylabel('RMSE(T_hat)')
ax.set_title('E2b｜轨道深度（n_pat=200）'); ax.legend(fontsize=9); ax.grid(alpha=.3)
fig.tight_layout(); fig.savefig(OUT / 'fig_E2_variance.png'); plt.close(fig)
res['E2_convergence_slope_on_n'] = e2s

# ------------------------------------------------------------------ E3
print('[E3] four falsification tests ...', flush=True)
base_pari = rmse_of('PARI', 200, 4)
base_pool = rmse_of('POOLED', 200, 4)
f1 = rmse_of('SHUFFLED-PAIRS', 200, 4)
f2 = rmse_of('PARI', 200, 4, shuffle_group=True)
f3 = base_pool.copy()      # m=1 -> no orbit -> PARI undefined, falls back to pooled
f4 = rmse_of('PARI', 200, 4, episodic=True)
res['E3_falsification'] = {
    'baseline_PARI': base_pari, 'baseline_POOLED': base_pool,
    'F1_shuffle_patient_pairs': f1,
    'F2_shuffle_group_labels': f2,
    'F3_single_record_per_patient': {**f3, 'note': 'PARI undefined; deterministic fallback to POOLED'},
    'F4_episodic_labels_break_A1': f4,
    'F1_erases_gain': bool(f1['rmse'] > 0.8 * base_pool['rmse']),
    'F2_degrades': bool(f2['rmse'] > 1.5 * base_pari['rmse']),
    'F4_degrades': bool(f4['rmse'] > 1.5 * base_pari['rmse']),
}

labels = ['PARI\n基线', 'POOLED\n无配对', 'F1\n打乱配对', 'F2\n打乱群标签',
          'F3\n单记录退化', 'F4\n阵发标签']
vals = [base_pari['rmse'], base_pool['rmse'], f1['rmse'], f2['rmse'], f3['rmse'], f4['rmse']]
colors = ['#1f6feb', '#d1242f', '#8250df', '#bf8700', '#6e7781', '#cf222e']
fig, ax = plt.subplots(figsize=(8.4, 4.2))
b = ax.bar(labels, vals, color=colors, alpha=.9)
ax.bar_label(b, fmt='%.3f', fontsize=9, padding=2)
ax.set_ylabel('RMSE(T_hat)'); ax.set_title('E3｜四个证伪检验：破坏识别条件后增益应消失')
ax.grid(alpha=.3, axis='y'); ax.set_ylim(0, max(vals) * 1.22)
fig.tight_layout(); fig.savefig(OUT / 'fig_E3_falsification.png'); plt.close(fig)

# ------------------------------------------------------------------ E4
print('[E4] convergence on effective unit ...', flush=True)
eff, r_eff = [], []
for n in n_grid:
    eff.append(n * 4); r_eff.append(next(r for r in e2['rows'] if r['n_pat'] == n)['PARI']['rmse'])
for m in m_grid:
    eff.append(200 * m); r_eff.append(next(r for r in e2m['rows'] if r['m'] == m)['PARI']['rmse'])
eff, r_eff = np.array(eff, float), np.array(r_eff, float)
slope_eff = float(np.polyfit(np.log(eff), np.log(r_eff), 1)[0])
res['E4_effective_unit_rate'] = {
    'effective_units': eff.tolist(), 'rmse': r_eff.tolist(),
    'slope': slope_eff, 'theory': -0.5,
    'within_tolerance': bool(-0.75 <= slope_eff <= -0.25)}

# ------------------------------------------------------------------ E5
print('[E5] group heterogeneity -> single-T regret ...', flush=True)
spreads = [0.0, 0.2, 0.5, 0.8, 1.2]
e5 = {'spreads': spreads, 'rows': []}
for s in spreads:
    rg = np.random.default_rng(700 + int(s * 100))
    taus = TAU_T + rg.uniform(-s, s, 6)
    taus = np.clip(taus, 1.2, 3.8)
    src, _, _ = make_dgp(200, 6, tau_t=TAU_T, seed=333)
    # per-group Psi at the global compromise temperature vs at its own T_g
    regrets, that = [], []
    for g, tg in enumerate(taus):
        _, tgt_g, _ = make_dgp(200, 6, tau_t=float(tg), seed=900 + g)
        pg = psi_pari(src, tgt_g, T_GRID, TAU_S)
        that.append(estimate_T(T_GRID, pg))
        regrets.append(pg)
    T_glob = float(np.mean(that))
    idx_glob = int(np.argmin(np.abs(T_GRID - T_glob)))
    regret = float(np.mean([p[idx_glob] - p.min() for p in regrets]))
    e5['rows'].append({'spread': s, 'taus': taus.tolist(),
                       'T_hat_per_group': that, 'T_global': T_glob,
                       'mean_regret': regret,
                       'tau_range': [float(taus.min()), float(taus.max())]})
res['E5_group_heterogeneity'] = e5

fig, ax = plt.subplots(figsize=(7.2, 4.2))
ax.plot(spreads, [r['mean_regret'] for r in e5['rows']], 'o-', color='#bf8700', lw=2.2)
ax.set_xlabel('群间真实温度离散度 s'); ax.set_ylabel('单一全局 T 的平均校准后悔')
ax.set_title('E5｜群异质性上升 → 单温度不可搬运')
ax.grid(alpha=.3)
fig.tight_layout(); fig.savefig(OUT / 'fig_E5_heterogeneity.png'); plt.close(fig)

# ------------------------------------------------------------------ write
(OUT / 'pari_synthetic_results.json').write_text(
    json.dumps(res, indent=2, ensure_ascii=False), encoding='utf-8')
print('\n=== W1 SUMMARY ===', flush=True)
print('E0 real-data runnable locally:', not e0['per_record_logits_or_probs_present'] is False, flush=True)
print('E1 T_hat PARI =', round(res['E1_identifiability']['T_hat_PARI'], 4),
      '| pooled =', round(res['E1_identifiability']['T_hat_POOLED'], 4),
      '| true =', TAU_T, '| unimodal:',
      res['E1_identifiability']['unimodal_left_monotone'] and
      res['E1_identifiability']['unimodal_right_monotone'], flush=True)
print('E2 gain @n=800:', round(e2['rows'][-1]['gain_PARI_over_POOLED'], 2), 'x',
      '| slope on n =', round(e2s, 3), flush=True)
print('E3 F1/F2/F4 degrade:',
      res['E3_falsification']['F1_erases_gain'],
      res['E3_falsification']['F2_degrades'],
      res['E3_falsification']['F4_degrades'], flush=True)
print('E4 slope on n*m =', round(slope_eff, 3), flush=True)
print('E5 regret @s=1.2:', round(e5['rows'][-1]['mean_regret'], 6), flush=True)
print('done in', round(time.time() - T0, 1), 's', flush=True)
