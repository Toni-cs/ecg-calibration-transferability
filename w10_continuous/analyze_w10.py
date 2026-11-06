"""W10 analysis — F0, H1..H6, F1..F5, LOCO, figures, verdict.

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
from w10_kernel import COLS, LOCO_COLS, run_one

plt.rcParams['font.sans-serif'] = ['WenQuanYi Micro Hei']
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams['figure.dpi'] = 130

METHODS = ['CERT', 'HB', 'M1', 'M2', 'M3']
CANDIDATES = ['M1', 'M2', 'M3']
BASELINE = 'HB'
MARGIN = 0.002


def load(tag):
    folder = HERE / 'shards' / tag
    ps = sorted(folder.glob('shard_*.npz'))
    if not ps:
        return None, None, 0
    X = np.concatenate([np.load(p)['X'] for p in ps], axis=0)
    return X, None, len(ps)


X, _, n_shards = load('main')
if X is None:
    raise SystemExit('no main shards')
X = X[np.argsort(X[:, 0])]
u, c = np.unique(X[:, 0].astype(np.int64), return_counts=True)
assert not (c > 1).any(), 'duplicate confirmatory seeds'
D = {k: X[:, i] for i, k in enumerate(COLS)}
N = len(X)
print(f'loaded {N:,} confirmatory rows from {n_shards} shards', flush=True)

LX, _, n_ls = load('loco')
FX, _, n_fs = load('falsify')
if LX is not None:
    print(f'loaded {len(LX)} LOCO rows from {n_ls} shards', flush=True)
if FX is not None:
    print(f'loaded {len(FX)} falsification rows from {n_fs} shards', flush=True)

OUT = {'meta': {
    'prereg': 'PREREGISTRATION_W10.md v1.0 (frozen)',
    'endpoints': 'L = mean max(0, dECE+0.002); CVaR_0.1% = mean of each '
                 'method\'s OWN worst 0.1% dECE; A = mean dECE; '
                 'harm = secondary descriptive',
    'target_seeds': 20000, 'actual_seeds': int(N),
    'seed_range': [int(X[0, 0]), int(X[-1, 0])],
    'n_shards': n_shards, 'date': '2026-11-06',
    'zero_hyperparameters': True, 'no_exploration_set': True,
    'w1_w9_results_unchanged': True}}


# ---------------------------------------------------------------- bootstrap
def bootstrap_replicates(D, methods, nt, B=10000, seed=20261106, chunk=100):
    """One shared index stream for EVERY paired bootstrap CI.

    For each bootstrap resample compute, for every method, the three endpoint
    replicates (L, A, CVaR_0.1%). Any paired difference is then simply the
    difference of two replicate series under the SAME index stream, which is
    strictly paired by construction. CVaR is recomputed as an order statistic
    on every resample (not approximated by a fixed tail mask).
    """
    rng = np.random.default_rng(seed)
    Nn = len(D['loss_CERT'])
    names = [f'{p}_{k}' for p in ['L', 'A', 'CVaR'] for k in methods]
    acc = {n: [] for n in names}
    src_L = {k: np.asarray(D['loss_' + k], float) for k in methods}
    src_A = {k: np.asarray(D['dECE_' + k], float) for k in methods}
    for c_ in range(int(np.ceil(B / chunk))):
        m = min(chunk, B - c_ * chunk)
        idx = rng.integers(0, Nn, (m, Nn))
        for k in methods:
            acc[f'L_{k}'].append(src_L[k][idx].mean(axis=1))
            a = src_A[k][idx]
            acc[f'A_{k}'].append(a.mean(axis=1))
            ii = np.argpartition(a, -nt, axis=1)[:, -nt:]
            acc[f'CVaR_{k}'].append(
                np.take_along_axis(a, ii, axis=1).mean(axis=1))
    return {n: np.concatenate(v) for n, v in acc.items()}


def wilson(k, n, z=1.96):
    p = k / n; den = 1 + z * z / n
    cc = (p + z * z / (2 * n)) / den
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return [float(cc - h), float(cc + h)], float(h)


def cvar(d):
    """Each method's OWN worst 0.1% (pre-registered)."""
    n_tail = max(1, int(round(len(d) * 0.001)))
    return float(np.sort(d)[-n_tail:].mean()), n_tail, np.sort(d)[-n_tail:]


# ---------------------------------------------------------------- descriptive
desc = {}
for k in METHODS:
    d = D['dECE_' + k]
    cv, nt, tail = cvar(d)
    ci, hw = wilson(int(D['harm_' + k].sum()), N)
    desc[k] = {'mean_loss_L': float(D['loss_' + k].mean()),
               'mean_dECE_A': float(d.mean()),
               'CVaR_0.1pct': cv, 'n_tail': nt,
               'harm_secondary': float(D['harm_' + k].mean()),
               'harm_CI95': ci,
               'p95_dECE': float(np.percentile(d, 95)),
               'p99_dECE': float(np.percentile(d, 99)),
               'max_dECE': float(d.max())}
OUT['descriptive'] = desc
print('\n[descriptive]', flush=True)
for k in METHODS:
    s = desc[k]
    print('  %-5s L %.6f  A %.6f  CVaR %.6f  harm %.4f'
          % (k, s['mean_loss_L'], s['mean_dECE_A'], s['CVaR_0.1pct'],
             s['harm_secondary']), flush=True)

# ---------------------------------------------------------------- F0
manip = D['ece_SOURCE'] - D['ece_GLOBAL']
gst_ok = D['ece_GST'] <= D['ece_GLOBAL']
F0 = {'manipulation_mean': float(manip.mean()),
      'manipulation_positive_frac': float((manip > 0).mean()),
      'direction_consistency_frac': float(gst_ok.mean()),
      'PASS': bool(manip.mean() > 0.02 and (manip > 0).mean() >= 0.90
                   and gst_ok.mean() >= 0.60)}

# ---------------------------------------------------------------- H1 selection
# ONE shared bootstrap stream (B=10,000, frozen seed) for every paired CI.
nt = desc['CERT']['n_tail']          # all methods share the same N -> same nt
REP = bootstrap_replicates(D, METHODS, nt)
print('bootstrap replicates done (B=10000, shared stream)', flush=True)


def ci_diff(a, b):
    d = REP[a] - REP[b]
    return [float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))]


def pt(stat, k, ref=None):
    key = {'L': 'mean_loss_L', 'A': 'mean_dECE_A',
           'CVaR': 'CVaR_0.1pct'}[stat]
    a = desc[k][key]
    b = desc[ref][key] if ref else 0.0
    return float(a - b)


qual = {}
for k in CANDIDATES:
    ciL = ci_diff(f'L_{k}', f'L_{BASELINE}')
    ciA = ci_diff(f'A_{k}', f'A_{BASELINE}')
    ciC = ci_diff(f'CVaR_{k}', f'CVaR_{BASELINE}')
    q = {
        'point_L_noninferior': bool(pt('L', k, BASELINE) <= 1e-12),
        'point_CVaR_noninferior': bool(pt('CVaR', k, BASELINE) <= 1e-12),
        'point_A_noninferior': bool(pt('A', k, BASELINE) <= 1e-12),
        'CI_L_upper_le_0': bool(ciL[1] <= 0),
        'CI_A_upper_le_0': bool(ciA[1] <= 0),
        'CI_CVaR_upper_le_0': bool(ciC[1] <= 0),
        'CI_L': ciL, 'CI_A': ciA, 'CI_CVaR': ciC,
        'point_L': pt('L', k, BASELINE), 'point_A': pt('A', k, BASELINE),
        'point_CVaR': pt('CVaR', k, BASELINE),
    }
    q['PASS'] = all(q[x] for x in ['point_L_noninferior', 'point_CVaR_noninferior',
                                   'point_A_noninferior', 'CI_L_upper_le_0',
                                   'CI_A_upper_le_0', 'CI_CVaR_upper_le_0'])
    qual[k] = q
qualified = [k for k in CANDIDATES if qual[k]['PASS']]
selected = min(qualified, key=lambda k: (desc[k]['mean_loss_L'],
                                        desc[k]['CVaR_0.1pct'])) if qualified else None
H1 = {'qualified_set': qualified, 'selected': selected,
      'n_qualified': len(qualified), 'candidates': qual,
      'PASS': bool(len(qualified) > 0)}

# ---------------------------------------------------------------- H2 / H3
if selected:
    ciL = ci_diff(f'L_{selected}', 'L_CERT')
    ciA = ci_diff(f'A_{selected}', 'A_CERT')
    ciC = ci_diff(f'CVaR_{selected}', 'CVaR_CERT')
    H2 = {'vs': 'CERT-GATE', 'selected': selected,
          'mean_diff_L': pt('L', selected, 'CERT'), 'CI_L': ciL,
          'mean_diff_A': pt('A', selected, 'CERT'), 'CI_A': ciA,
          'CI_CVaR': ciC,
          'CVaR_selected': desc[selected]['CVaR_0.1pct'],
          'CVaR_CERT': desc['CERT']['CVaR_0.1pct'],
          'conditions': {'CI_L_upper_lt_0': bool(ciL[1] < 0),
                         'CI_CVaR_upper_lt_0': bool(ciC[1] < 0)},
          'PASS': bool(ciL[1] < 0 and ciC[1] < 0)}
    H3 = {'selected_own_CVaR': desc[selected]['CVaR_0.1pct'],
          'CERT_own_CVaR': desc['CERT']['CVaR_0.1pct'],
          'W9_HB_own_CVaR': desc['HB']['CVaR_0.1pct'],
          'PASS': bool(desc[selected]['CVaR_0.1pct']
                       <= desc['CERT']['CVaR_0.1pct'])}
else:
    H2 = {'PASS': False, 'note': 'no qualified candidate; H2/H3 not applicable'}
    H3 = {'PASS': False, 'note': 'no qualified candidate',
          'CERT_own_CVaR': desc['CERT']['CVaR_0.1pct'],
          'W9_HB_own_CVaR': desc['HB']['CVaR_0.1pct']}

# descriptive comparison vs CERT for ALL methods (no judgement)
OUT['vs_CERT_descriptive'] = {
    k: {'mean_diff_L': pt('L', k, 'CERT'),
        'CI_L': ci_diff(f'L_{k}', 'L_CERT'),
        'mean_diff_A': pt('A', k, 'CERT'),
        'CI_A': ci_diff(f'A_{k}', 'A_CERT'),
        'CI_CVaR': ci_diff(f'CVaR_{k}', 'CVaR_CERT'),
        'CVaR': desc[k]['CVaR_0.1pct']}
    for k in METHODS}

# ---------------------------------------------------------------- H4 LOCO
if LX is not None:
    LD = {k: LX[:, i] for i, k in enumerate(LOCO_COLS)}
    dim_names = ['site', 'cart', 'year']
    loco_rows = []
    ok = 0
    for dim in range(3):
        m = LD['dim'] == dim
        g = float(LD['dECE_global_cert'][m].mean())
        s = float(LD['dECE_strat_cert'][m].mean())
        better = bool(s <= g + 1e-12)
        ok += int(better)
        loco_rows.append({'dim': dim_names[dim], 'n_seeds': int(m.sum()),
                          'mean_dECE_global_cert': g,
                          'mean_dECE_strat_cert': s,
                          'strat_not_worse': better, 'diff': s - g})
    H4 = {'folds': loco_rows, 'n_dims_strat_not_worse': ok,
          'n_dims': 3, 'threshold': 2,
          'PASS': bool(ok >= 2)}
else:
    H4 = {'PASS': False, 'note': 'LOCO shards absent'}

# ---------------------------------------------------------------- H5 / H6
mm, cc = D['arch'] == 0, D['arch'] == 1
if selected:
    dm, dc = (float(D['dECE_' + selected][mm].mean()),
              float(D['dECE_' + selected][cc].mean()))
else:
    dm = dc = 0.0
H5 = {'n_mamba': int(mm.sum()), 'n_cnn': int(cc.sum()),
      'mean_dECE_mamba': dm, 'mean_dECE_cnn': dc,
      'conditions': {'same_sign': bool(dm < 0 and dc < 0),
                     'cnn_le_-0.002': bool(dc <= -0.002)},
      'PASS': bool(dm < 0 and dc < 0 and dc <= -0.002)}

H6 = {'mean_deff': float(D['deff'].mean()),
      'mean_rel': float(D['rel'].mean()), 'sd_rel': float(D['rel'].std()),
      'mean_tau2_strat_sd': float(D['tau2_strat_sd'].mean()),
      'mean_lam_g_range': float(D['lam_g_range'].mean()),
      'conditions': {'deff_gt_1': bool(D['deff'].mean() > 1),
                     'rel_in_0_1': bool(0 < D['rel'].mean() < 1),
                     'rel_sd_gt_0': bool(D['rel'].std() > 0),
                     'strat_sd_gt_0': bool(D['tau2_strat_sd'].mean() > 0)},
      'PASS': bool(all([D['deff'].mean() > 1, 0 < D['rel'].mean() < 1,
                        D['rel'].std() > 0, D['tau2_strat_sd'].mean() > 0]))}

# ---------------------------------------------------------------- spread bins
bins = np.linspace(0.05, 1.50, 21)
curve = []
for i in range(20):
    m = (D['spread'] >= bins[i]) & (D['spread'] < bins[i + 1])
    if m.sum() < 50:
        continue
    row = {'spread_mid': float((bins[i] + bins[i + 1]) / 2), 'n': int(m.sum())}
    for k in METHODS:
        row['L_' + k] = float(D['loss_' + k][m].mean())
        row['harm_' + k] = float(D['harm_' + k][m].mean())
    curve.append(row)
OUT['spread_curve'] = curve

# ---------------------------------------------------------------- falsification
if FX is not None:
    i = {k: j for j, k in enumerate(COLS)}
    base = np.asarray([run_one(int(s)) for s in FX[:, 0]], dtype=np.float64)
    B = {k: base[:, j] for j, k in enumerate(COLS)}
    # condition assignment is (seed - 151000) % 5
    sel = [(FX[:, 0].astype(np.int64) - 151000) % 5 == j for j in range(5)]
    FALS = {}
    f1 = FX[sel[0]]
    FALS['F1_deff1'] = {
        'max_abs_diff_M1_vs_HB': float(np.abs(f1[:, i['ece_M1']] -
                                              f1[:, i['ece_HB']]).max()),
        'PASS': bool(np.abs(f1[:, i['ece_M1']] - f1[:, i['ece_HB']]).max() < 1e-12)}
    f2 = FX[sel[1]]
    FALS['F2_rel1'] = {
        'max_abs_diff_M2_vs_HB': float(np.abs(f2[:, i['ece_M2']] -
                                              f2[:, i['ece_HB']]).max()),
        'PASS': bool(np.abs(f2[:, i['ece_M2']] - f2[:, i['ece_HB']]).max() < 1e-12)}
    f3 = FX[sel[2]]
    FALS['F3_rel0'] = {
        'max_abs_diff_M2_vs_CERT': float(np.abs(f3[:, i['ece_M2']] -
                                                f3[:, i['ece_CERT']]).max()),
        'PASS': bool(np.abs(f3[:, i['ece_M2']] - f3[:, i['ece_CERT']]).max() < 1e-12)}
    f4 = FX[sel[3]]; b4 = {k: B[k][sel[3]] for k in B}
    FALS['F4_random_strata'] = {
        'mean_dECE_M3_random': float(f4[:, i['dECE_M3']].mean()),
        'mean_dECE_M3_baseline': float(b4['dECE_M3'].mean()),
        'mean_dECE_CERT_baseline': float(b4['dECE_CERT'].mean()),
        'PASS': bool(f4[:, i['dECE_M3']].mean() >= b4['dECE_M3'].mean() - 1e-12)}
    f5 = FX[sel[4]]
    dev = {k: float(np.abs(f5[:, i['ece_' + k]] -
                           f5[:, i['ece_GLOBAL']]).mean()) for k in CANDIDATES}
    FALS['F5_homogeneous'] = {
        'mean_abs_dev_from_GLOBAL': dev,
        'note': 'Pre-registered correction: W9-F4 compared to CERT, which '
                'was wrong because spread=0 does not remove heteroscedasticity.',
        'PASS': bool(all(v < 0.005 for v in dev.values()))}
    print('\n[F]', {k: v['PASS'] for k, v in FALS.items()}, flush=True)
else:
    FALS = {'not_run': {'PASS': False}}

OUT.update({'F0': F0,
            'H': {'H1_selection': H1, 'H2_vs_CERT': H2,
                  'H3_no_new_tail': H3, 'H4_LOCO': H4,
                  'H5_architecture': H5, 'H6_mechanism': H6},
            'F_falsification': FALS})

checks = {'F0': F0['PASS'],
          **{f'H{i+1}': OUT['H'][k]['PASS'] for i, k in enumerate(
              ['H1_selection', 'H2_vs_CERT', 'H3_no_new_tail', 'H4_LOCO',
               'H5_architecture', 'H6_mechanism'])},
          **{k: v['PASS'] for k, v in FALS.items()}}
OUT['verdict'] = {
    'checks': checks, 'n_pass': int(sum(checks.values())),
    'n_checks': len(checks), 'all_pass': bool(all(checks.values())),
    'actual_seeds': int(N), 'no_v1_1': True,
    'primary_claim': ('Continuous endpoints replace the binary harm proxy; '
                      'three zero-hyperparameter candidates are compared '
                      'under a frozen three-way non-inferiority rule'),
    'does_not_substitute_tier1': ('Real 1.15M cohort, non-asymptotic bound, '
      'clinical/biostat collaborators, third-party reproduction remain unmet'),
    'honesty': ('Synthetic toy waveforms + diagonal selective SSM numpy '
                'approximation + hierarchical drift proxy. NOT official '
                'Mamba-2, NOT pretrained, NOT real 1.15M ECG. 20,000 seeds '
                'are independent DGP draws, NOT patients/centres. W10 uses '
                'W7 stress regime. W1-W10 are internal experiments, not '
                'published algorithms/SOTA.')}
print('\n=== W10 VERDICT ===', checks, '| pass', OUT['verdict']['n_pass'],
      '/', OUT['verdict']['n_checks'], flush=True)
for k, v in OUT['H'].items():
    print('   ', k, 'PASS =', v['PASS'], flush=True)
print('    qualified =', qualified, '| selected =', selected, flush=True)

# ---------------------------------------------------------------- figures
fig, axes = plt.subplots(1, 3, figsize=(15.4, 4.4))
ax = axes[0]
v = [desc[k]['mean_loss_L'] for k in METHODS]
b = ax.bar(range(5), v, color=['#8250df', '#2da44e', '#1f6feb', '#bf8700', '#d1242f'], alpha=.9)
ax.bar_label(b, fmt='%.6f', fontsize=8, padding=2)
ax.set_xticks(range(5)); ax.set_xticklabels(['CERT\n(W6)', 'HB\n(W9)', 'M1\ndeff', 'M2\nrel', 'M3\nstrat'], fontsize=8)
ax.set_ylabel('连续部署损失 L')
ax.set_title(f'W10｜{N:,} 全新种子\n主终点（越低越好）')
ax.grid(alpha=.3, axis='y')

ax = axes[1]
v = [desc[k]['CVaR_0.1pct'] for k in METHODS]
b = ax.bar(range(5), v, color=['#8250df', '#2da44e', '#1f6feb', '#bf8700', '#d1242f'], alpha=.9)
ax.bar_label(b, fmt='%.5f', fontsize=8, padding=2)
ax.set_xticks(range(5)); ax.set_xticklabels(['CERT', 'HB', 'M1', 'M2', 'M3'], fontsize=8)
ax.set_ylabel('CVaR 0.1%（各自最差）')
ax.set_title('H3｜自身新尾部\n（越低越好；W9 曾在此失败）')
ax.grid(alpha=.3, axis='y')

ax = axes[2]
for k, col in [('CERT', '#8250df'), ('HB', '#2da44e'), ('M1', '#1f6feb'),
               ('M2', '#bf8700'), ('M3', '#d1242f')]:
    ax.plot([c['spread_mid'] for c in curve], [c['L_' + k] for c in curve],
            'o-', lw=1.6, ms=3, color=col, label=k)
ax.set_xlabel('群异质性 spread'); ax.set_ylabel('L（分箱）')
ax.set_title('20 箱分层｜连续损失')
ax.legend(fontsize=8, ncol=2); ax.grid(alpha=.3)
fig.tight_layout(); fig.savefig(HERE / 'fig_w10_main.png'); plt.close(fig)

fig, axes = plt.subplots(1, 3, figsize=(15.4, 4.2))
ax = axes[0]
v = [desc[k]['harm_secondary'] for k in METHODS]
b = ax.bar(range(5), v, color=['#8250df', '#2da44e', '#1f6feb', '#bf8700', '#d1242f'], alpha=.9)
ax.bar_label(b, fmt='%.4f', fontsize=8, padding=2)
ax.set_xticks(range(5)); ax.set_xticklabels(['CERT', 'HB', 'M1', 'M2', 'M3'], fontsize=8)
ax.set_ylabel('危害率（次要描述性）'); ax.set_title('W10｜二值指标已降为次要')
ax.grid(alpha=.3, axis='y')

ax = axes[1]
ax.hist(D['deff'], bins=45, color='#1f6feb', alpha=.8, label='deff')
ax.set_xlabel('deff'); ax.set_ylabel('种子数')
ax.set_title(f'H6｜mean {D["deff"].mean():.3f}')
ax.legend(fontsize=8); ax.grid(alpha=.3)
ax2 = ax.twinx()
ax2.hist(D['rel'], bins=45, color='#bf8700', alpha=.45)
ax2.set_ylabel('rel 计数', color='#bf8700')

ax = axes[2]
if LX is not None:
    names = [r['dim'] for r in H4['folds']]
    g = [r['mean_dECE_global_cert'] for r in H4['folds']]
    s = [r['mean_dECE_strat_cert'] for r in H4['folds']]
    x = np.arange(len(names)); w = 0.35
    ax.bar(x - w/2, g, w, label='全局证书', color='#8250df', alpha=.9)
    ax.bar(x + w/2, s, w, label='分层证书 M3', color='#d1242f', alpha=.9)
    ax.set_xticks(x); ax.set_xticklabels(names)
    ax.axhline(0, color='#333', lw=1)
    ax.set_ylabel('LOCO mean ΔECE')
    ax.set_title(f'H4｜LOCO {H4.get("n_dims_strat_not_worse", 0)}/3 类不劣')
    ax.legend(fontsize=8); ax.grid(alpha=.3, axis='y')
fig.tight_layout(); fig.savefig(HERE / 'fig_w10_diagnostics.png'); plt.close(fig)

(HERE / 'w10_results.json').write_text(
    json.dumps(OUT, indent=2, ensure_ascii=False), encoding='utf-8')
print('DONE', flush=True)
