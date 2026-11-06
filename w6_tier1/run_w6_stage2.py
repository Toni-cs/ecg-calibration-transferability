"""W6 stage 2/2 — F0, H1-H6, falsification, CNN control, patient bootstrap,
Proposition 1 grid, figures and final verdict.

Reads checkpointed 600 main seeds; NEVER recomputes or reselects them.
Each expensive block checkpoints so a sandbox kill can be resumed.
"""
from __future__ import annotations
import json, pathlib, sys, time
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = pathlib.Path(__file__).resolve().parent
PARTS = HERE / 'stage2_parts'; PARTS.mkdir(exist_ok=True)
sys.path.insert(0, str(HERE))
from tier1_kernel import (run_tier1_seed, proposition1_verify,
                          METRIC_KEYS, PRIMARY_KEY, HARM_MARGIN)

plt.rcParams['font.sans-serif'] = ['WenQuanYi Micro Hei']
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams['figure.dpi'] = 130

T0 = time.time()
B_BOOT = 10000
A = json.loads((HERE / 'w6_stage1_A.json').read_text(encoding='utf-8'))['rows']
B = json.loads((HERE / 'w6_stage1_B.json').read_text(encoding='utf-8'))['rows']
ALL = A + B
assert len(A) == 300 and len(B) == 300
print(f'[stage2] loaded 600 main seeds ({time.time()-T0:.0f}s)', flush=True)

OUT = {'meta': {'prereg': 'PREREGISTRATION_W6.md v1.0 (frozen)',
                'run_type': 'CONFIRMATORY', 'primary': PRIMARY_KEY,
                'method': 'CERT-GATE + Proposition 1',
                'seeds_A': [10000, 10299, 300], 'seeds_B': [10300, 10599, 300],
                'falsification_seeds': [10600, 10659, 60],
                'cnn_seeds': [10700, 10799, 100],
                'bootstrap_seeds': [10800, 10809, 10],
                'bootstrap_B': B_BOOT, 'date': '2026-11-06',
                'no_pilot': 'zero tunable hyperparameters',
                'history_retained': ['W1 PARI falsified', 'W2 v1.0/v1.1',
                                     'W3 600 Mamba seeds 534/600',
                                     'W4 H2/H3 confirmed, H4/F4 falsified',
                                     'W5 GS-GST 543/600 crossed 90% line']}}


def arr(rows, path):
    return np.array([np.atleast_1d(_dig(r, path)) for r in rows], float).ravel()


def _dig(d, path):
    for k in path.split('.'):
        d = d[k]
    return d


def clean(v):
    """Drop non-finite values from degenerate tiny groups (single-class
    subgroup => AUROC undefined). The main-seed JSON is NEVER modified."""
    v = np.asarray(v, float)
    return v[np.isfinite(v)]


def ciboot(v, B=B_BOOT, seed=20261106):
    rng = np.random.default_rng(seed); v = clean(v)
    m = np.array([v[rng.integers(0, len(v), len(v))].mean() for _ in range(B)])
    return [float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))]


def cached(name, fn):
    p = PARTS / f'{name}.json'
    if p.exists():
        print(f'   [cache] {name}', flush=True)
        return json.loads(p.read_text(encoding='utf-8'))
    v = fn(); p.write_text(json.dumps(v, ensure_ascii=False), encoding='utf-8')
    return v


# ------------------------------------------------------------------ F0
manip = arr(ALL, 'chain.SOURCE.ECE_top') - arr(ALL, 'chain.GLOBAL.ECE_top')
auc_raw = arr(ALL, 'chain.GLOBAL.AUROC')
auc = clean(auc_raw)
orc_nll = arr(ALL, 'chain.ORACLE.NLL')
best_nll = np.min(np.stack([arr(ALL, f'chain.{k}.NLL')
                            for k in ['GLOBAL', 'GST', 'GS-GST', 'CERT-GATE']]), axis=0)
F0 = {'manipulation_mean': float(manip.mean()),
      'manipulation_positive_frac': float((manip > 0).mean()),
      'AUROC_mean': float(auc.mean()),
      'AUROC_n_undefined_of_600': int(np.isnan(auc_raw).sum()),
      'AUROC_note': ('tiny single-class subgroups make AUROC undefined; '
                     'nan-aware mean is used, main-seed JSON untouched'),
      'oracle_nll_pass': bool(np.all(orc_nll <= best_nll + 1e-6)),
      'n_seeds_failing_nll': int((orc_nll > best_nll + 1e-6).sum())}
F0['PASS'] = bool(F0['manipulation_mean'] > 0.02 and
                  F0['manipulation_positive_frac'] >= 0.90 and
                  F0['AUROC_mean'] >= 0.55 and F0['oracle_nll_pass'])
OUT['F0'] = F0
print('   F0 =', F0, flush=True)
if not F0['PASS']:
    raise SystemExit('F0 FAILED — all results discarded.')

# ------------------------------------------------------------------ H1 PRIMARY
h_cert = arr(ALL, 'harm.CERT-GATE'); h_gst = arr(ALL, 'harm.GST')
h_gs = arr(ALL, 'harm.GS-GST'); diff = h_gst - h_cert
red = float(diff.mean() / max(h_gst.mean(), 1e-9))
H1 = {'harm_GST': float(h_gst.mean()), 'harm_GSGST': float(h_gs.mean()),
      'harm_CERTGATE': float(h_cert.mean()), 'relative_reduction': red,
      'paired_diff': float(diff.mean()), 'paired_CI95': ciboot(diff),
      'margin': HARM_MARGIN,
      'conditions': {'harm_le_0.025': bool(h_cert.mean() <= 0.025),
                     'reduction_ge_0.50': bool(red >= 0.50),
                     'paired_CI_lower_gt_0': bool(ciboot(diff)[0] > 0)}}
H1['PASS'] = all(H1['conditions'].values())

# ------------------------------------------------------------------ H2 certificate accuracy
certA = [r['certificate']['certificate'] for r in A]
certB = [r['certificate']['certificate'] for r in B]
H2 = {'A_accuracy_expect_GST': float(certA.count('GST') / 300),
      'B_accuracy_expect_GLOBAL': float(certB.count('GLOBAL') / 300),
      'lam_A_mean': float(np.mean([r['certificate']['lam'] for r in A])),
      'lam_B_mean': float(np.mean([r['certificate']['lam'] for r in B])),
      'conditions': {'A_ge_0.85': bool(certA.count('GST') / 300 >= 0.85),
                     'B_ge_0.85': bool(certB.count('GLOBAL') / 300 >= 0.85)}}
H2['PASS'] = all(H2['conditions'].values())

# ------------------------------------------------------------------ H3 full metric chain
LOWER = {'ECE_top', 'ECE_classwise_macro', 'ECE_canonical', 'Brier', 'NLL'}
HIGHER = {'AUROC', 'DCA_net_benefit'}
chain_delta = {}
for m in METRIC_KEYS:
    g = arr(ALL, f'chain.GLOBAL.{m}'); c = arr(ALL, f'chain.CERT-GATE.{m}')
    if m == 'cal_slope':
        d = np.abs(c - 1.0) - np.abs(g - 1.0)
    elif m == 'cal_intercept':
        d = np.abs(c) - np.abs(g)
    elif m in LOWER:
        d = c - g
    else:
        d = g - c
    dc = clean(d)
    chain_delta[m] = {'mean': float(dc.mean()), 'CI95': ciboot(d),
                      'improved': bool(dc.mean() <= 0),
                      'n_undefined': int(len(d) - len(dc))}
n_improved = sum(v['improved'] for v in chain_delta.values())
d_primary = clean(arr(ALL, 'chain.CERT-GATE.ECE_canonical') -
                  arr(ALL, 'chain.GLOBAL.ECE_canonical'))
H3 = {'n_improved_of_9': n_improved, 'per_metric': chain_delta,
      'mean_delta_primary': float(d_primary.mean()),
      'primary_CI95': ciboot(d_primary),
      'conditions': {'n_improved_ge_7': bool(n_improved >= 7),
                     'primary_CI_upper_lt_0': bool(ciboot(d_primary)[1] < 0)}}
H3['PASS'] = all(H3['conditions'].values())

# ------------------------------------------------------------------ H4 LOCO
loco = {}
for axis in ['site', 'cart', 'year']:
    frac = np.array([r['LOCO'][axis]['folds_CERT_better_than_GST'] /
                     r['LOCO'][axis]['n_folds'] for r in ALL])
    u_cert = np.array([r['LOCO'][axis]['mean_U_CERT'] for r in ALL])
    u_gst = np.array([r['LOCO'][axis]['mean_U_GST'] for r in ALL])
    loco[axis] = {'mean_fold_frac_CERT_not_worse_than_GST': float(frac.mean()),
                  'mean_U_CERT': float(u_cert.mean()),
                  'mean_U_GST': float(u_gst.mean()),
                  'U_CERT_better': bool(u_cert.mean() <= u_gst.mean())}
H4 = {'per_axis': loco,
      'conditions': {f'{a}_ge_two_thirds': bool(loco[a]['mean_fold_frac_CERT_not_worse_than_GST'] >= 2/3)
                     for a in loco}}
H4['PASS'] = all(H4['conditions'].values())

# ------------------------------------------------------------------ H5 Proposition 1
P1 = cached('proposition1', lambda: proposition1_verify())
p1rows = P1['rows']
p_r = float(np.mean([r['P_R_lamhat_le_min'] for r in p1rows]))
H5 = {'mean_P_R_lamhat_le_min': p_r,
      'mean_loglog_slope': P1['mean_loglog_slope'],
      'theory_slope': P1['theory_slope'],
      'closed_form': P1['closed_form'],
      'conditions': {'P_ge_0.95': bool(p_r >= 0.95),
                     'slope_le_-0.7': bool(P1['mean_loglog_slope'] <= -0.7)}}
H5['PASS'] = all(H5['conditions'].values())
OUT['proposition1_rows'] = p1rows

# ------------------------------------------------------------------ H6 patient-level
neff = arr(ALL, 'patient_stats.n_eff_over_n')
icc = arr(ALL, 'patient_stats.ICC_hat')
deff = arr(ALL, 'patient_stats.design_effect')
boot = cached('patient_bootstrap', lambda: [
    run_tier1_seed(s, spread=0.20, do_full_chain=False, do_loco=False,
                   do_block_boot=True, n_boot=2000)['bootstrap_CI']
    for s in range(10800, 10810)])
wr = np.array([b['width_ratio'] for b in boot])
H6 = {'mean_n_eff_over_n': float(neff.mean()),
      'mean_ICC': float(icc.mean()), 'mean_design_effect': float(deff.mean()),
      'mean_records_per_patient': float(np.mean([r['records_per_patient'] for r in ALL])),
      'patient_block_width_ratio_mean': float(wr.mean()),
      'patient_block_width_ratio_min': float(wr.min()),
      'conditions': {'neff_in_range': bool(0.40 <= neff.mean() <= 0.65),
                     'width_ratio_ge_1.05': bool(wr.mean() >= 1.05)}}
H6['PASS'] = all(H6['conditions'].values())

OUT['H'] = {'H1_primary': H1, 'H2_certificate': H2, 'H3_metric_chain': H3,
            'H4_LOCO': H4, 'H5_proposition1': H5, 'H6_patient_stats': H6}
print('\n[H]', flush=True)
for k, v in OUT['H'].items():
    print('   ', k, 'PASS =', v['PASS'], flush=True)
    for kk in ['harm_CERTGATE','relative_reduction','n_improved_of_9',
               'mean_loglog_slope','mean_n_eff_over_n','patient_block_width_ratio_mean',
               'A_accuracy_expect_GST','B_accuracy_expect_GLOBAL']:
        if kk in v: print('        ', kk, round(v[kk], 4), flush=True)
    if 'conditions' in v: print('        conditions:', v['conditions'], flush=True)

# ------------------------------------------------------------------ falsification
FSEEDS = list(range(10600, 10660))
F = cached('falsification', lambda: {
    'fm1': [run_tier1_seed(s, spread=1.0, do_full_chain=True, do_loco=False,
                           merge_groups=True) for s in FSEEDS[0:12]],
    'fm2': [run_tier1_seed(s, spread=1.0, do_full_chain=True, do_loco=False,
                           shuffle_groups=True) for s in FSEEDS[12:24]],
    'fm3': [run_tier1_seed(s, spread=1.0, do_full_chain=True, do_loco=False,
                           homogeneous=True) for s in FSEEDS[24:36]],
    'fm4a': [run_tier1_seed(s, spread=1.0, do_full_chain=True, do_loco=False,
                            lam_override=1.0) for s in FSEEDS[36:48]],
    'fm4b': [run_tier1_seed(s, spread=1.0, do_full_chain=True, do_loco=False,
                            lam_override=0.0) for s in FSEEDS[36:48]],
    'fm5': [run_tier1_seed(s, spread=1.0, do_full_chain=True, do_loco=False,
                           random_certificate=True) for s in FSEEDS[48:60]],
})
d1 = np.array([r['delta_U_CERT'] for r in F['fm1']])
d2 = np.array([r['delta_U_CERT'] - r['delta_U_GST'] for r in F['fm2']])
d3 = np.array([r['delta_U_GST'] for r in F['fm3']])
e4a = np.array([abs(r['chain']['GS-GST']['U'] - r['chain']['GST']['U']) for r in F['fm4a']])
e4b = np.array([abs(r['chain']['GS-GST']['U'] - r['chain']['GLOBAL']['U']) for r in F['fm4b']])
d5 = np.array([r['delta_U_CERT'] for r in F['fm5']])
FALS = {
 'FM1_merge_groups': {'mean_delta_CERT': float(d1.mean()), 'PASS': bool(abs(d1.mean()) < 0.005)},
 'FM2_shuffle_group_id': {'mean_delta_CERT_minus_GST': float(d2.mean()),
                           'PASS': bool(abs(d2.mean()) < 0.010)},
 'FM3_homogeneous': {'mean_delta_GST': float(d3.mean()),
                      'PASS': bool(abs(d3.mean()) < 0.005)},
 'FM4_lam1_equals_GST': {'max_abs_diff': float(e4a.max()), 'PASS': bool(e4a.max() < 1e-12)},
 'FM4_lam0_equals_GLOBAL': {'max_abs_diff': float(e4b.max()), 'PASS': bool(e4b.max() < 1e-12)},
 'FM5_random_certificate': {'mean_delta_CERT': float(d5.mean()),
                             'PASS': bool(abs(d5.mean()) < 0.005)}}
OUT['F_falsification'] = FALS
print('\n[F]', {k: v for k, v in FALS.items()}, flush=True)

# ------------------------------------------------------------------ CNN control
cnn = cached('cnn_control', lambda: [
    run_tier1_seed(s, arch='cnn', spread=1.0, do_full_chain=True, do_loco=False)
    for s in range(10700, 10800)])
dc = np.array([r['delta_U_CERT'] for r in cnn])
dm = float(np.mean([r['delta_U_CERT'] for r in ALL]))
CNN = {'mean_delta_CERT': float(dc.mean()), 'sd': float(dc.std(ddof=1)),
       'n_negative_of_100': int((dc < 0).sum()),
       'mamba_mean_delta_CERT': dm,
       'PASS': bool(dc.mean() < 0 and dc.mean() <= -0.003 and dm < 0)}
OUT['CNN_control'] = CNN
print('\n[C] CNN mean delta', round(dc.mean(), 4), 'neg', CNN['n_negative_of_100'], '/100', flush=True)

# ------------------------------------------------------------------ aggregates
AGG = {}
for k in ['GLOBAL', 'GST', 'GS-GST', 'CERT-GATE', 'ORACLE']:
    AGG[k] = {m: float(np.nanmean([r['chain'][k][m] for r in ALL])) for m in METRIC_KEYS}
    AGG[k]['harm_rate'] = float(np.mean([r['harm'][k] for r in ALL])) if k != 'GLOBAL' else 0.0
OUT['aggregate'] = AGG
OUT['strata'] = {}
for tag, rows in [('A_high_heterogeneity', A), ('B_low_heterogeneity', B)]:
    OUT['strata'][tag] = {
        k: {'mean_U': float(np.mean([r['chain'][k]['U'] for r in rows])),
            'harm_rate': (0.0 if k == 'GLOBAL' else
                          float(np.mean([r['harm'][k] for r in rows])))}
        for k in ['GLOBAL', 'GST', 'GS-GST', 'CERT-GATE', 'ORACLE']}
    OUT['strata'][tag]['certificate_GLOBAL_frac'] = float(
        np.mean([r['certificate']['certificate'] == 'GLOBAL' for r in rows]))

# ------------------------------------------------------------------ verdict
checks = {'F0': F0['PASS'], **{f'H{i+1}': OUT['H'][k]['PASS'] for i, k in enumerate(
    ['H1_primary','H2_certificate','H3_metric_chain','H4_LOCO','H5_proposition1','H6_patient_stats'])},
          **{k: v['PASS'] for k, v in FALS.items()}, 'ARCH': CNN['PASS']}
OUT['diagnostics'] = {
 'H4_LOCO_fold_fractions': {a: loco[a]['mean_fold_frac_CERT_not_worse_than_GST']
                            for a in loco},
 'H4_U_CERT_vs_GST': {a: (loco[a]['mean_U_CERT'], loco[a]['mean_U_GST'])
                      for a in loco},
 'H5_P_by_G': {str(g): float(np.mean([r['P_R_lamhat_le_min'] for r in p1rows
                                       if r['G'] == g]))
               for g in sorted(set(r['G'] for r in p1rows))},
 'H5_certificate_accuracy_mean': float(np.mean([r['certificate_accuracy']
                                                for r in p1rows])),
 'H6_bootstrap_width_ratios': [float(b['width_ratio']) for b in boot],
 'H6_note': ('paired delta-ECE is nearly insensitive to resampling and '
             'within-patient clusters are homogeneous, so the synthetic-layer '
             'block/record width ratio can fall below 1. The design effect '
             '(deff ~1.95, n_eff/n ~0.51) is the robust patient-level quantity; '
             'the real 1.15M cohort MUST use patient/centre-blocked bootstrap '
             'for cross-centre effect CIs. Reported as-is; threshold not changed.')}
OUT['verdict'] = {
 'checks': checks, 'all_pass': bool(all(checks.values())),
 'n_pass': int(sum(checks.values())), 'n_checks': len(checks),
 'primary_claim': ('CERT-GATE cuts deployment harm vs unconditional GST while '
                   'Proposition 1 supplies the first closed-form identification '
                   'condition for when NOT to split calibration'),
 'no_v1_1': True,
 'honesty': ('Synthetic 12-lead toy waveforms + diagonal selective SSM numpy '
             'approximation + HIERARCHICAL drift proxy. NOT official Mamba-2 '
             'kernel, NOT pretrained weights, NOT real 1.15M ECG. Real-data '
             'forward requires PhysioNet DUA + T1 preflight + frozen foundation '
             'encoder. n_eff/ICC are synthetic-layer numbers, not real-cohort '
             'estimates. 600 seeds are independent DGP draws, NOT patients/centres.'),
 'tier1_dimensions_delivered': ['hierarchical site-cart-year-patient drift',
    '9-metric calibration chain incl. classwise/canonical ECE, slope, DCA',
    'patient-level design effect + blocked bootstrap',
    'three non-in-sample LOCO external validations',
    'Proposition 1 risk decomposition + numerical verification',
    'explicit zero-hyperparameter deployment certificate',
    'falsification x5 + CNN architecture control + full negative-result ledger']}
print('\n=== W6 FINAL VERDICT ===', flush=True)
print(checks, '| pass', OUT['verdict']['n_pass'], '/', OUT['verdict']['n_checks'], flush=True)
print('elapsed', round(time.time()-T0, 1), 's', flush=True)

# ------------------------------------------------------------------ figures
fig, axes = plt.subplots(1, 3, figsize=(15.2, 4.4))
ax = axes[0]
keys = ['GLOBAL','GST','GS-GST','CERT-GATE','ORACLE']
v = [AGG[k]['ECE_canonical'] for k in keys]
e = [np.std([r['chain'][k]['ECE_canonical'] for r in ALL], ddof=1) for k in keys]
b = ax.bar(range(5), v, yerr=e, capsize=3,
           color=['#8c959f','#bf8700','#1f6feb','#2da44e','#8250df'], alpha=.9)
ax.bar_label(b, fmt='%.4f', fontsize=8, padding=2)
ax.set_xticks(range(5)); ax.set_xticklabels(keys, rotation=22, ha='right', fontsize=8)
ax.set_ylabel('canonical multiclass ECE'); ax.set_title('W6｜600 个独立 Mamba 种子')
ax.grid(alpha=.3, axis='y')

ax = axes[1]
labels = ['A 高异质\n300', 'B 低异质\n300', '合并\n600']
hg = [OUT['strata']['A_high_heterogeneity']['GST']['harm_rate'],
      OUT['strata']['B_low_heterogeneity']['GST']['harm_rate'], h_gst.mean()]
hc = [OUT['strata']['A_high_heterogeneity']['CERT-GATE']['harm_rate'],
      OUT['strata']['B_low_heterogeneity']['CERT-GATE']['harm_rate'], h_cert.mean()]
x = np.arange(3); w = .36
ax.bar(x-w/2, hg, w, color='#bf8700', alpha=.9, label='无条件 GST')
ax.bar(x+w/2, hc, w, color='#2da44e', alpha=.9, label='CERT-GATE')
ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=9)
ax.set_ylabel('部署危害率（非劣容差 0.002）')
ax.set_title(f'H1｜相对下降 {red*100:.0f}%'); ax.legend(fontsize=9); ax.grid(alpha=.3, axis='y')

ax = axes[2]
ms = [m for m in METRIC_KEYS]
d = [chain_delta[m]['mean'] for m in ms]
cols = ['#2da44e' if v <= 0 else '#d1242f' for v in d]
ax.barh(range(len(ms)), d, color=cols, alpha=.88)
ax.set_yticks(range(len(ms))); ax.set_yticklabels(ms, fontsize=8)
ax.axvline(0, color='#333', lw=1.2)
ax.set_xlabel('Δ (CERT-GATE − GLOBAL)，负=改善')
ax.set_title(f'H3｜9 指标链不劣 {n_improved}/9'); ax.grid(alpha=.3, axis='x')
fig.tight_layout(); fig.savefig(HERE / 'fig_w6_main.png'); plt.close(fig)

fig, axes = plt.subplots(1, 3, figsize=(15.2, 4.3))
ax = axes[0]
Gs = sorted(set(r['G'] for r in p1rows))
x = np.log(Gs)
y = [np.log(max(np.mean([r['mse_lam'] for r in p1rows if r['G'] == g]), 1e-12)) for g in Gs]
ax.plot(x, y, 'o-', color='#1f6feb', lw=2)
ax.plot(x, np.polyval(np.polyfit(x, y, 1), x), '--', color='#d1242f',
        label=f'斜率 {H5["mean_loglog_slope"]:.2f}（理论 −1）')
ax.set_xlabel('log G'); ax.set_ylabel('log MSE(λ̂)')
ax.set_title(f'H5｜命题 1 收敛；P(R≤min)={p_r:.3f}'); ax.legend(fontsize=9); ax.grid(alpha=.3)

ax = axes[1]
ax.hist(neff, bins=35, color='#8250df', alpha=.85)
ax.axvline(0.5, color='#2da44e', ls='--', lw=1.8, label='n_eff/n = 0.5')
ax.set_xlabel('n_eff / n_records'); ax.set_ylabel('种子数')
ax.set_title(f'H6｜deff {H6["mean_design_effect"]:.2f}, ICC {H6["mean_ICC"]:.2f}')
ax.legend(fontsize=9); ax.grid(alpha=.3)

ax = axes[2]
ax_names = ['site 3折','cart 12折','year 3折','CNN-1D']
vals = [H4['per_axis'][a]['mean_fold_frac_CERT_not_worse_than_GST']
        for a in ['site','cart','year']] + [CNN['n_negative_of_100']/100]
ax.bar(range(4), vals, color=['#1f6feb']*3+['#8250df'], alpha=.9)
ax.axhline(2/3, color='#d1242f', ls='--', lw=1.6, label='2/3 门槛')
ax.set_xticks(range(4)); ax.set_xticklabels(ax_names, fontsize=9)
ax.set_ylabel('不劣折比例'); ax.set_title('H4｜三类非 in-sample 外验 + 架构对照')
ax.set_ylim(0, 1.05); ax.legend(fontsize=9); ax.grid(alpha=.3, axis='y')
fig.tight_layout(); fig.savefig(HERE / 'fig_w6_theory_external.png'); plt.close(fig)

(HERE / 'w6_results.json').write_text(
    json.dumps(OUT, indent=2, ensure_ascii=False), encoding='utf-8')
print('DONE', flush=True)
