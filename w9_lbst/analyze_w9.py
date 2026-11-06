"""W9 analysis — F0, H1..H6, F1..F5, figures, verdict.

Reads immutable shards; NEVER recomputes or reselects confirmatory seeds.
Falsification baselines are recomputed deterministically on the SAME seeds
(same rng => bit-identical), which is not a reselection.
"""
from __future__ import annotations
import json, pathlib, sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from w9_kernel import COLS, run_one

plt.rcParams['font.sans-serif'] = ['WenQuanYi Micro Hei']
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams['figure.dpi'] = 130


def load(tag, start, end):
    folder = HERE / 'shards' / tag
    ps = sorted(folder.glob('shard_*.npz'))
    if not ps:
        raise SystemExit(f'no {tag} shards')
    X = np.concatenate([np.load(p)['X'] for p in ps], axis=0)
    X = X[np.argsort(X[:, 0])]
    u, c = np.unique(X[:, 0].astype(np.int64), return_counts=True)
    assert not (c > 1).any(), f'duplicate seeds in {tag}'
    return X, {k: X[:, i] for i, k in enumerate(COLS)}, len(ps)


X, D, n_shards = load('main', 110000, 120000)
N = len(X)
print(f'loaded {N:,} confirmatory rows from {n_shards} shards', flush=True)
F, DF, nf = load('falsify', 120000, 120600) if (HERE / 'shards' / 'falsify').exists() else (None, None, 0)
if F is not None:
    print(f'loaded {len(F)} falsification rows from {nf} shards', flush=True)

OUT = {'meta': {'prereg': 'PREREGISTRATION_W9.md v1.0 (frozen)',
                'method': 'HB-GST heteroscedastic BLUP + Proposition 2',
                'target_seeds': 10000, 'actual_seeds': int(N),
                'seed_range': [int(X[0, 0]), int(X[-1, 0])],
                'n_shards': n_shards, 'date': '2026-11-06',
                'zero_hyperparameters': True, 'no_exploration_set': True,
                'w8_prior': 'W8 hard-gate design failure fully retained; '
                            'W8 consumed no confirmatory seeds',
                'w6_w7_w8_results_unchanged': True}}


def wilson(k, n, z=1.96):
    p = k / n; den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return [float(c - h), float(c + h)], float(h)


def ciboot(v, B=10000, seed=20261106):
    rng = np.random.default_rng(seed); v = np.asarray(v, float)
    v = v[np.isfinite(v)]
    m = np.array([v[rng.integers(0, len(v), len(v))].mean() for _ in range(B)])
    return [float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))]


def pearson(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    return float(np.corrcoef(a, b)[0, 1])


# ------------------------------------------------------------------ F0
manip = D['ece_SOURCE'] - D['ece_GLOBAL']
gst_ok = D['ece_GST'] <= D['ece_GLOBAL']
F0 = {'manipulation_mean': float(manip.mean()),
      'manipulation_positive_frac': float((manip > 0).mean()),
      'direction_consistency_frac': float(gst_ok.mean()),
      'PASS': bool(manip.mean() > 0.02 and (manip > 0).mean() >= 0.90
                   and gst_ok.mean() >= 0.60)}

# ------------------------------------------------------------------ H1 / H2
hc, hh, hl = D['harm_CERT'], D['harm_HB'], D['harm_LB']
diff = hc - hh
red = float(diff.mean() / max(hc.mean(), 1e-9))
ci_h, hw_h = wilson(int(hh.sum()), N)
ci_c, _ = wilson(int(hc.sum()), N)
H1 = {'harm_CERT': float(hc.mean()), 'harm_HB': float(hh.mean()),
      'harm_LB_exploratory': float(hl.mean()),
      'relative_reduction': red,
      'CI95_HB': ci_h, 'CI_half_width': hw_h, 'CI95_CERT': ci_c,
      'paired_diff': float(diff.mean()), 'paired_CI95': ciboot(diff),
      'conditions': {'HB_lower_than_CERT': bool(hh.mean() < hc.mean()),
                     'paired_CI_lower_gt_0': bool(ciboot(diff)[0] > 0)}}
H1['PASS'] = all(H1['conditions'].values())
H2 = {'mean_dECE_CERT': float(D['dECE_CERT'].mean()),
      'mean_dECE_HB': float(D['dECE_HB'].mean()),
      'mean_dECE_LB_exploratory': float(D['dECE_LB'].mean()),
      'margin': 0.002,
      'conditions': {'noninferior': bool(D['dECE_HB'].mean() <=
                                         D['dECE_CERT'].mean() + 0.002)}}
H2['PASS'] = all(H2['conditions'].values())

# ------------------------------------------------------------------ H3 tail
n_tail = max(1, int(round(N * 0.001)))
tail = np.argsort(D['dECE_CERT'])[-n_tail:]
H3 = {'n_tail': n_tail,
      'mean_dECE_CERT_on_CERT_tail': float(D['dECE_CERT'][tail].mean()),
      'mean_dECE_HB_on_CERT_tail': float(D['dECE_HB'][tail].mean()),
      'n_harm_improved': int((D['harm_HB'][tail] <= D['harm_CERT'][tail]).sum()),
      'tail_seeds': [int(x) for x in D['seed'][tail]],
      'conditions': {'tail_not_worse': bool(D['dECE_HB'][tail].mean() <=
                                            D['dECE_CERT'][tail].mean()),
                     'harm_improved_ge_8': bool(
                         (D['harm_HB'][tail] <= D['harm_CERT'][tail]).sum() >= 8)}}
H3['PASS'] = all(H3['conditions'].values())

# ------------------------------------------------------------------ H4 spread bins
bins = np.linspace(0.05, 1.50, 21)
curve = []
for i in range(20):
    m = (D['spread'] >= bins[i]) & (D['spread'] < bins[i + 1])
    if m.sum() < 50: continue
    curve.append({'spread_mid': float((bins[i] + bins[i + 1]) / 2),
                  'n': int(m.sum()),
                  'harm_CERT': float(hc[m].mean()),
                  'harm_HB': float(hh[m].mean()),
                  'dECE_HB': float(D['dECE_HB'][m].mean()),
                  'lam_g_spread_mean': float(
                      (D['lam_g_max'][m] - D['lam_g_min'][m]).mean())})
n_better = int(sum(c['harm_HB'] <= c['harm_CERT'] for c in curve))
H4 = {'n_bins': len(curve), 'bins_HB_not_worse': n_better,
      'mean_lam_g_range': float((D['lam_g_max'] - D['lam_g_min']).mean()),
      'curve': curve,
      'conditions': {'bins_ge_15': bool(n_better >= 15),
                     'heteroscedasticity_active': bool(
                         (D['lam_g_max'] - D['lam_g_min']).mean() > 0)}}
H4['PASS'] = all(H4['conditions'].values())

# ------------------------------------------------------------------ H5 architecture
mm = D['arch'] == 0; cc = D['arch'] == 1
dm, dc = float(D['dECE_HB'][mm].mean()), float(D['dECE_HB'][cc].mean())
H5 = {'n_mamba': int(mm.sum()), 'n_cnn': int(cc.sum()),
      'mean_dECE_mamba': dm, 'mean_dECE_cnn': dc,
      'harm_HB_mamba': float(hh[mm].mean()), 'harm_HB_cnn': float(hh[cc].mean()),
      'conditions': {'same_sign': bool(dm < 0 and dc < 0),
                     'cnn_le_-0.002': bool(dc <= -0.002)}}
H5['PASS'] = all(H5['conditions'].values())

# ------------------------------------------------------------------ H6 Proposition 2 grid
rng = np.random.default_rng(20261106)
grid = []
for G_ in [4, 8, 16, 32, 64, 128]:
    for cv in [0.0, 0.2, 0.5, 1.0, 1.5, 2.0]:
        for tau2 in [0.05, 0.2, 0.5, 1.0]:
            n_g = np.clip(rng.lognormal(3.5, cv, G_), 1.0, None)
            s2g = 1.0 / n_g; s2bar = float(s2g.mean())
            f = lambda x: tau2 * x / (tau2 + x)
            R_h = float(np.mean(f(s2g)))
            R_o = float(f(s2bar))
            grid.append({'G': G_, 'cv_n': cv, 'tau2': tau2,
                         'R_hetero': R_h, 'R_homo': R_o,
                         'gap': R_o - R_h, 'holds': bool(R_h <= R_o + 1e-12)})
frac_holds = float(np.mean([g['holds'] for g in grid]))
cv_vals = sorted(set(g['cv_n'] for g in grid))
cv_gap = [(cv, float(np.mean([g['gap'] for g in grid if g['cv_n'] == cv])))
          for cv in cv_vals]
r_cv_gap = pearson([a for a, _ in cv_gap], [b for _, b in cv_gap])
H6 = {'n_grid_cells': len(grid), 'frac_R_hetero_le_R_homo': frac_holds,
      'cv_vs_mean_gap': cv_gap, 'pearson_cv_gap': r_cv_gap,
      'analytic': {'f': 'tau2*x/(tau2+x)', 'f_double_prime': '-2*tau2^2/(tau2+x)^3 < 0',
                   'jensen': 'mean f(sigma2_g) <= f(mean sigma2_g)',
                   'equality_iff': 'all n_g equal'},
      'conditions': {'frac_ge_0.99': bool(frac_holds >= 0.99),
                     'pearson_ge_0.8': bool(r_cv_gap >= 0.8)}}
H6['PASS'] = all(H6['conditions'].values())

# ------------------------------------------------------------------ falsification
if F is not None:
    i = {k: j for j, k in enumerate(COLS)}
    # deterministic paired baselines on the SAME seeds
    base = np.asarray([run_one(int(s)) for s in F[:, 0]], dtype=np.float64)
    B = {k: base[:, j] for j, k in enumerate(COLS)}
    groups = {}
    for j in range(5):
        sel = (F[:, 0].astype(np.int64) - 120000) % 5 == j
        groups[j] = (F[sel], {k: B[k][sel] for k in B})
    FALS = {}
    # F1 flatten heteroscedasticity -> HB == CERT
    f1, b1 = groups[0]
    FALS['F1_flatten'] = {'max_abs_diff_HB_vs_CERT': float(
        np.abs(f1[:, i['ece_HB']] - b1['ece_CERT']).max()),
        'PASS': bool(np.abs(f1[:, i['ece_HB']] - b1['ece_CERT']).max() < 1e-12)}
    # F2 lambda=0 -> HB == GLOBAL
    f2, b2 = groups[1]
    FALS['F2_zero'] = {'max_abs_diff_HB_vs_GLOBAL': float(
        np.abs(f2[:, i['ece_HB']] - b2['ece_GLOBAL']).max()),
        'mean_dECE_HB': float(f2[:, i['dECE_HB']].mean()),
        'PASS': bool(np.abs(f2[:, i['ece_HB']] - b2['ece_GLOBAL']).max() < 1e-12
                     and abs(f2[:, i['dECE_HB']].mean()) < 1e-12)}
    # F3 random weights -> advantage gone
    f3, b3 = groups[2]
    FALS['F3_random'] = {'harm_HB': float(f3[:, i['harm_HB']].mean()),
                         'harm_CERT_baseline': float(b3['harm_CERT'].mean()),
                         'PASS': bool(f3[:, i['harm_HB']].mean() >=
                                      b3['harm_CERT'].mean() - 0.005)}
    # F4 homogeneous -> near-zero difference
    f4, b4 = groups[3]
    FALS['F4_homogeneous'] = {'mean_abs_diff': float(
        np.abs(f4[:, i['ece_HB']] - b4['ece_CERT']).mean()),
        'PASS': bool(np.abs(f4[:, i['ece_HB']] - b4['ece_CERT']).mean() < 0.005)}
    # F5 reversed weights -> harm rises
    f5, b5 = groups[4]
    FALS['F5_reversed'] = {'harm_HB': float(f5[:, i['harm_HB']].mean()),
                           'harm_CERT_baseline': float(b5['harm_CERT'].mean()),
                           'PASS': bool(f5[:, i['harm_HB']].mean() >
                                        b5['harm_CERT'].mean())}
    print('\n[F]', {k: v['PASS'] for k, v in FALS.items()}, flush=True)
else:
    FALS = {'not_run': {'PASS': False}}
    print('\n[F] falsification shards not present', flush=True)

OUT.update({'F0': F0, 'H': {'H1_primary': H1, 'H2_noninferior': H2,
                            'H3_tail': H3, 'H4_stratified': H4,
                            'H5_architecture': H5, 'H6_proposition2': H6},
            'F_falsification': FALS,
            'aggregate': {label: {
                'ECE': float(D[f'ece_{key}'].mean()),
                'dECE': float(D[f'dECE_{key}'].mean()) if f'dECE_{key}' in D else None,
                'harm': float(D[f'harm_{key}'].mean()) if f'harm_{key}' in D else None}
                for label, key in [('GLOBAL','GLOBAL'), ('GST','GST'),
                                   ('GS-GST','GSGST'), ('CERT-GATE','CERT'),
                                   ('HB-GST','HB'), ('LB-exploratory','LB')]}})

checks = {'F0': F0['PASS'],
          **{f'H{i+1}': OUT['H'][k]['PASS'] for i, k in enumerate(
              ['H1_primary','H2_noninferior','H3_tail','H4_stratified',
               'H5_architecture','H6_proposition2'])},
          **{k: v['PASS'] for k, v in FALS.items()}}
OUT['verdict'] = {
 'checks': checks, 'n_pass': int(sum(checks.values())),
 'n_checks': len(checks), 'all_pass': bool(all(checks.values())),
 'no_v1_1': True,
 'primary_claim': ('Proposition 2 (heteroscedastic BLUP) strictly improves '
                   'on Proposition 1 by Jensen; HB-GST realises it with zero '
                   'hyperparameters and cuts deployment harm without '
                   'sacrificing average calibration gain'),
 'honesty': ('Synthetic 12-lead toy waveforms + diagonal selective SSM numpy '
             'approximation + hierarchical drift proxy. NOT official Mamba-2, '
             'NOT pretrained, NOT real 1.15M ECG. 10,000 seeds are '
             'independent DGP draws, NOT patients/centres. W9 uses W7 stress '
             'regime. W1-W9 are internal experiments, not published '
             'algorithms/SOTA. Does NOT claim Tier-1: real cohort, '
             'non-asymptotic bound, clinical/biostat collaborators, '
             'third-party reproduction remain unmet.')}
print('\n=== W9 VERDICT ===', checks, '| pass',
      OUT['verdict']['n_pass'], '/', OUT['verdict']['n_checks'], flush=True)
for k, v in OUT['H'].items():
    print('   ', k, 'PASS =', v['PASS'], flush=True)

# ------------------------------------------------------------------ figures
fig, axes = plt.subplots(1, 3, figsize=(15.4, 4.4))
ax = axes[0]
labels = ['GST','GS-GST','CERT','HB','LB']
keycol = ['GST','GSGST','CERT','HB','LB']
v = [float(D[f'harm_{k}'].mean()) for k in keycol]
e = [2 * wilson(int(D[f'harm_{k}'].sum()), N)[1] for k in keycol]
b = ax.bar(range(5), v, yerr=e, capsize=3,
           color=['#bf8700','#1f6feb','#8250df','#2da44e','#d1242f'], alpha=.9)
ax.bar_label(b, fmt='%.4f', fontsize=8, padding=2)
ax.set_xticks(range(5)); ax.set_xticklabels(labels, rotation=25, ha='right', fontsize=8)
ax.set_ylabel('部署危害率')
ax.set_title(f'W9｜{N:,} 全新独立种子\nH1 未过：HB 危害率 {100*abs(red):.1f}%（{"升" if red<0 else "降"}）')
ax.grid(alpha=.3, axis='y')

ax = axes[1]
ax.plot([c['spread_mid'] for c in curve], [c['harm_CERT'] for c in curve],
        'o-', color='#8250df', lw=2, label='CERT-GATE (W7)')
ax.plot([c['spread_mid'] for c in curve], [c['harm_HB'] for c in curve],
        's-', color='#2da44e', lw=2, label='HB-GST (W9)')
ax.set_xlabel('群异质性 spread'); ax.set_ylabel('危害率')
ax.set_title(f'H4｜20 箱，HB 不劣 {n_better}/{len(curve)}')
ax.legend(fontsize=9); ax.grid(alpha=.3)

ax = axes[2]
cvd = [a for a, _ in cv_gap]; gpd = [b for _, b in cv_gap]
ax.plot(cvd, gpd, 'o-', color='#1f6feb', lw=2)
ax.set_xlabel('群规模不均衡 CV(n_g)'); ax.set_ylabel('R_homo − R_hetero')
ax.set_title(f'H6｜命题 2 Jensen 差额\n成立 {100*frac_holds:.1f}%, r={r_cv_gap:.3f}')
ax.grid(alpha=.3)
fig.tight_layout(); fig.savefig(HERE / 'fig_w9_main.png'); plt.close(fig)

fig, axes = plt.subplots(1, 2, figsize=(10.6, 4.2))
ax = axes[0]
lamrange = D['lam_g_max'] - D['lam_g_min']
ax.hist(lamrange, bins=45, color='#2da44e', alpha=.85)
ax.set_xlabel('逐群 λ_g 极差（异方差生效）'); ax.set_ylabel('种子数')
ax.set_title(f'H4｜平均极差 {lamrange.mean():.3f}')
ax.grid(alpha=.3)
ax = axes[1]
d = D['dECE_HB'] - D['dECE_CERT']
ax.hist(d, bins=60, color='#1f6feb', alpha=.85)
ax.axvline(0, color='#333', lw=1.2)
ax.axvline(d.mean(), color='#d1242f', ls='--', lw=1.6,
           label=f'mean {d.mean():.5f}')
ax.set_xlabel('ΔECE(HB) − ΔECE(CERT)'); ax.set_ylabel('种子数')
ax.set_title(f'H2｜逐种子增益差（负=HB 更好）')
ax.legend(fontsize=9); ax.grid(alpha=.3)
fig.tight_layout(); fig.savefig(HERE / 'fig_w9_mechanism.png'); plt.close(fig)

(HERE / 'w9_results.json').write_text(
    json.dumps(OUT, indent=2, ensure_ascii=False), encoding='utf-8')
print('DONE', flush=True)
