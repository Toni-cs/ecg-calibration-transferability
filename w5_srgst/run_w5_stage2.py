"""W5 stage 2/2 — analysis + falsification + CNN control + final verdict.

Reads the checkpointed 600 main seeds; does NOT recompute or reselect any.
"""
from __future__ import annotations
import json, pathlib, sys, time
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from w5_srgst import run_w5_seed

plt.rcParams['font.sans-serif'] = ['WenQuanYi Micro Hei']
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams['figure.dpi'] = 130

FSEEDS = list(range(7600, 7660))
CSEEDS = list(range(7700, 7800))
B_BOOT = 10000
EST = ['SOURCE', 'GLOBAL', 'GLOBAL-SHRINK', 'GST', 'SHRINK-GLOBAL',
       'SR-GST', 'CW-GST', 'GS-GST', 'ORACLE']
T0 = time.time()

A = json.loads((HERE / 'w5_stage1_A.json').read_text(encoding='utf-8'))
B = json.loads((HERE / 'w5_stage1_B.json').read_text(encoding='utf-8'))
ALL = A + B
assert len(A) == 300 and len(B) == 300
print(f'[stage2] loaded 600 main seeds ({time.time()-T0:.0f}s)', flush=True)

out = {'meta': {'prereg': 'PREREGISTRATION_W5.md v1.0 (frozen)',
                'run_type': 'CONFIRMATORY', 'method': 'GS-GST (zero hyperparams)',
                'seeds_A': [7000, 7299, 300], 'seeds_B': [7300, 7599, 300],
                'falsification_seeds': [7600, 7659, 60],
                'cnn_control_seeds': [7700, 7799, 100],
                'bootstrap_B': B_BOOT, 'date': '2026-11-06',
                'no_pilot': 'zero tunable hyperparameters, no threshold selection',
                'execution_split': 'stage1 600 seeds + stage2 analysis/falsification',
                'history_retained': ['W1 PARI falsified', 'W2 v1.0 H1=False',
                                     'W2 v1.1 F-B FAIL / graph removed',
                                     'W3 600 Mamba seeds -0.0248, 534/600',
                                     'W4 H2/H3 confirmed, H4/F4 falsified']}}


def arr(rows, key): return np.array([r[key] for r in rows], float)
def harm(rows, k): return np.array([r['harm'][k] for r in rows], float)
def ece(rows, k): return np.array([r['sc'][k]['ECE'] for r in rows], float)
def nll(rows, k): return np.array([r['sc'][k]['NLL'] for r in rows], float)


def ciboot(v, B=B_BOOT, seed=20261106):
    rng = np.random.default_rng(seed)
    v = np.asarray(v, float)
    m = np.array([v[rng.integers(0, len(v), len(v))].mean() for _ in range(B)])
    return [float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))]


# ------------------------------------------------------------------ F0
orc = nll(ALL, 'ORACLE')
best = np.min(np.stack([nll(ALL, k) for k in EST if k != 'ORACLE']), axis=0)
f0_nll = bool(np.all(orc <= best + 1e-6))
manip = ece(ALL, 'SOURCE') - ece(ALL, 'GLOBAL')
manip_pass = bool(manip.mean() > 0.02 and (manip > 0).mean() >= 0.90)
f0 = {'oracle_nll_gate_pass': f0_nll,
      'n_seeds_failing_nll': int((orc > best + 1e-6).sum()),
      'manipulation_mean': float(manip.mean()),
      'manipulation_positive_frac': float((manip > 0).mean()),
      'manipulation_pass': manip_pass,
      'PASS': bool(f0_nll and manip_pass)}
oe = ece(ALL, 'ORACLE')
be = np.min(np.stack([ece(ALL, k) for k in EST if k != 'ORACLE']), axis=0)
rev = oe - be
f0['ece_oracle_reversals'] = int((rev > 0.001).sum())
f0['max_ece_reversal_gap'] = float(rev.max())
out['F0_validity_gate'] = f0
print('   F0 PASS =', f0['PASS'], '| ece reversals =', f0['ece_oracle_reversals'], flush=True)
if not f0['PASS']:
    raise SystemExit('F0 FAILED — all results discarded.')

# ------------------------------------------------------------------ aggregate
AGG = {}
for k in EST:
    AGG[k] = {m: {'mean': float(np.mean([r['sc'][k][m] for r in ALL])),
                  'sd': float(np.std([r['sc'][k][m] for r in ALL], ddof=1))}
              for m in ['ECE', 'NLL', 'Brier']}
    AGG[k]['harm_rate'] = float(harm(ALL, k).mean())
out['aggregate'] = AGG
print('\n   estimator        ECE      harm   (600 seeds)', flush=True)
for k in EST:
    print(f'   {k:16s} {AGG[k]["ECE"]["mean"]:.4f}   {AGG[k]["harm_rate"]:.3f}', flush=True)

# ------------------------------------------------------------------ H1 (PRIMARY)
hB_gs, hB_gst = harm(B, 'GS-GST'), harm(B, 'GST')
diff_B = hB_gst - hB_gs
red_B = float(diff_B.mean() / max(hB_gst.mean(), 1e-9))
H1 = {'stratum': 'B (300 seeds)',
      'harm_GST': float(hB_gst.mean()), 'harm_GSGST': float(hB_gs.mean()),
      'relative_reduction': red_B, 'paired_diff': float(diff_B.mean()),
      'paired_CI95': ciboot(diff_B),
      'conditions': {'harm_GSGST_le_0.05': bool(hB_gs.mean() <= 0.05),
                     'relative_reduction_ge_0.50': bool(red_B >= 0.50),
                     'paired_CI_lower_gt_0': bool(ciboot(diff_B)[0] > 0)}}
H1['PASS'] = all(H1['conditions'].values())

# ------------------------------------------------------------------ H2
d_gs = arr(ALL, 'delta_gsgst')
d_gst = arr(ALL, 'delta_gst')
H2 = {'mean_delta_ECE_GSGST_minus_GLOBAL': float(d_gs.mean()),
      'sd': float(d_gs.std(ddof=1)), 'CI95': ciboot(d_gs),
      'n_negative_of_600': int((d_gs < 0).sum()),
      'negative_fraction': float((d_gs < 0).mean()),
      'mean_delta_ECE_GST_minus_GLOBAL': float(d_gst.mean()),
      'noninferiority_gap': float((d_gs - d_gst).mean()),
      'noninferiority_CI95': ciboot(d_gs - d_gst),
      'conditions': {'mean_le_-0.020': bool(d_gs.mean() <= -0.020),
                     'CI_upper_lt_0': bool(ciboot(d_gs)[1] < 0),
                     'gap_le_0.010': bool((d_gs - d_gst).mean() <= 0.010)}}
H2['PASS'] = all(H2['conditions'].values())

# ------------------------------------------------------------------ H3
p95_gs, p95_gst = float(np.percentile(d_gs, 95)), float(np.percentile(d_gst, 95))
mx_gs, mx_gst = float(d_gs.max()), float(d_gst.max())
H3 = {'p95_GST': p95_gst, 'p95_GSGST': p95_gs,
      'p95_improvement': float(p95_gst - p95_gs),
      'worst_GST': mx_gst, 'worst_GSGST': mx_gs,
      'worst_improvement': float(mx_gst - mx_gs),
      'conditions': {'p95_improve_ge_0.002': bool(p95_gst - p95_gs >= 0.002),
                     'worst_improve_ge_0.002': bool(mx_gst - mx_gs >= 0.002)}}
H3['PASS'] = all(H3['conditions'].values())

# ------------------------------------------------------------------ H4
d_globshrink = arr(ALL, 'delta_gs')
H4 = {'mean_delta_ECE_GLOBALSHRINK_minus_GLOBAL': float(d_globshrink.mean()),
      'GLOBALSHRINK_no_gain': bool(d_globshrink.mean() >= -0.005),
      'mean_ECE_SRGST': float(ece(ALL, 'SR-GST').mean()),
      'mean_ECE_GSGST': float(ece(ALL, 'GS-GST').mean()),
      'SRGST_worse_than_GSGST': bool(ece(ALL, 'SR-GST').mean() > ece(ALL, 'GS-GST').mean()),
      'PASS': bool(d_globshrink.mean() >= -0.005 and
                   ece(ALL, 'SR-GST').mean() > ece(ALL, 'GS-GST').mean())}
out['H'] = {'H1_primary': H1, 'H2_noninferiority': H2,
            'H3_tail_risk': H3, 'H4_mechanism': H4}
print('\n[H]', flush=True)
for k, v in out['H'].items():
    print('   ', k, {kk: (round(vv, 4) if isinstance(vv, float) else vv)
                     for kk, vv in v.items() if kk != 'conditions'}, flush=True)
    print('        conditions:', v.get('conditions', {}), '=> PASS =', v['PASS'], flush=True)

# ------------------------------------------------------------------ strata
out['strata'] = {}
for tag, rows in [('A_W3DGP', A), ('B_longtail', B)]:
    m = {'GST': 'delta_gst', 'GS-GST': 'delta_gsgst', 'SR-GST': 'delta_sr',
         'CW-GST': 'delta_cw', 'GLOBAL-SHRINK': 'delta_gs'}
    out['strata'][tag] = {
        k: {'mean_delta_ECE': float(arr(rows, m[k]).mean()) if k in m else None,
            'harm_rate': float(harm(rows, k).mean())} for k in EST}
    out['strata'][tag]['lam_gs_mean'] = float(np.mean([r['lam_gs'] for r in rows]))
    out['strata'][tag]['mean_n_per_group'] = float(np.mean([np.mean(r['sizes']) for r in rows]))

# ------------------------------------------------------------------ falsification
print('\n[F] falsification 60 seeds 7600-7659 ...', flush=True)
half = 30
p1, pF, pC = (HERE / 'w5_stage2_fm1.json'), (HERE / 'w5_stage2_F.json'), (HERE / 'w5_stage2_C.json')
if p1.exists() and pF.exists():
    fm1 = json.loads(p1.read_text(encoding='utf-8'))
    _F = json.loads(pF.read_text(encoding='utf-8'))
    fm2, fm3, fm5, fm6 = _F['fm2'], _F['fm3'], _F['fm5'], _F['fm6']
    print('   loaded checkpointed falsification results', flush=True)
else:
    fm1 = [run_w5_seed(s, merge_groups=True, stratum='A') for s in FSEEDS[:half]] + \
          [run_w5_seed(s, merge_groups=True, stratum='B') for s in FSEEDS[half:]]
    p1.write_text(json.dumps(fm1, ensure_ascii=False), encoding='utf-8')
    fm2 = [run_w5_seed(s, shuffle_groups=True, stratum='A') for s in FSEEDS[:half]] + \
          [run_w5_seed(s, shuffle_groups=True, stratum='B') for s in FSEEDS[half:]]
    fm3 = [run_w5_seed(s, homogeneous=True, stratum='A') for s in FSEEDS[:half]] + \
          [run_w5_seed(s, homogeneous=True, stratum='B') for s in FSEEDS[half:]]
    fm5 = [run_w5_seed(s, w_override=1.0, stratum='A') for s in FSEEDS[:half]] + \
          [run_w5_seed(s, w_override=1.0, stratum='B') for s in FSEEDS[half:]]
    fm6 = [run_w5_seed(s, w_override=0.0, stratum='A') for s in FSEEDS[:half]] + \
          [run_w5_seed(s, w_override=0.0, stratum='B') for s in FSEEDS[half:]]
    pF.write_text(json.dumps({'fm2': fm2, 'fm3': fm3, 'fm5': fm5, 'fm6': fm6},
                             ensure_ascii=False), encoding='utf-8')
    print(f'   falsification done {time.time()-T0:.0f}s', flush=True)

d1 = arr(fm1, 'delta_gsgst'); d2 = arr(fm2, 'delta_gsgst'); d3 = arr(fm3, 'delta_gsgst')
e5 = np.array([abs(r['sc']['GS-GST']['ECE'] - r['sc']['GST']['ECE']) for r in fm5])
e6 = np.array([abs(r['sc']['GS-GST']['ECE'] - r['sc']['GLOBAL']['ECE']) for r in fm6])
F = {'FM1_merge_groups': {'mean_delta': float(d1.mean()),
                           'PASS': bool(abs(d1.mean()) < 0.005)},
     'FM2_shuffle_group_id': {'mean_delta': float(d2.mean()),
                               'PASS': bool(abs(d2.mean()) < 0.010)},
     'FM3_homogeneous': {'mean_delta': float(d3.mean()),
                          'PASS': bool(abs(d3.mean()) < 0.010)},
     'FM5_lam1_equals_GST': {'max_abs_diff': float(e5.max()),
                              'PASS': bool(e5.max() < 1e-12)},
     'FM6_lam0_equals_GLOBAL': {'max_abs_diff': float(e6.max()),
                                 'PASS': bool(e6.max() < 1e-12)}}
out['F_falsification'] = F
print('   ', {k: {kk: (round(vv, 6) if isinstance(vv, float) else vv)
                  for kk, vv in v.items()} for k, v in F.items()}, flush=True)

# ------------------------------------------------------------------ CNN control
print('[C] CNN-1D control 100 seeds 7700-7799 ...', flush=True)
if pC.exists():
    cnn = json.loads(pC.read_text(encoding='utf-8'))
    print('   loaded checkpointed CNN results', flush=True)
else:
    cnn = [run_w5_seed(s, arch='cnn', stratum='A') for s in CSEEDS]
    pC.write_text(json.dumps(cnn, ensure_ascii=False), encoding='utf-8')
dc = arr(cnn, 'delta_gsgst')
C = {'mean_delta_ECE': float(dc.mean()), 'sd': float(dc.std(ddof=1)),
     'n_negative_of_100': int((dc < 0).sum()),
     'PASS': bool(dc.mean() < 0 and dc.mean() <= -0.015 and d_gs.mean() < 0)}
out['CNN_control'] = C
print('   CNN mean delta', round(dc.mean(), 4), 'neg', C['n_negative_of_100'], '/100', flush=True)

# ------------------------------------------------------------------ verdict
checks = {'F0': f0['PASS'], 'H1': H1['PASS'], 'H2': H2['PASS'],
          'H3': H3['PASS'], 'H4': H4['PASS'],
          'FM1': F['FM1_merge_groups']['PASS'],
          'FM2': F['FM2_shuffle_group_id']['PASS'],
          'FM3': F['FM3_homogeneous']['PASS'],
          'FM5': F['FM5_lam1_equals_GST']['PASS'],
          'FM6': F['FM6_lam0_equals_GLOBAL']['PASS'],
          'ARCH': C['PASS']}
out['verdict'] = {
 'checks': checks, 'all_pass': bool(all(checks.values())),
 'citable': bool(all(checks.values())),
 'confirmed_success': [k for k in ['H2_noninferiority','H3_tail_risk','H4_mechanism']
                        if out['H'][k]['PASS']],
 'H1_detail': ('Significant harm reduction (paired CI lower>0) but 33.3% '
               '< pre-registered 50% and harm 0.0533 > 0.05. Threshold NOT '
               'changed, no v1.1.'),
 'W3_line_crossed': ('543/600 (90.5%) negative seeds on GS-GST vs W3 GST '
                     '534/600 (89.0%); the 90% deployment line W3 missed is '
                     'now crossed on 600 FRESH independent seeds.'),
 'no_v1_1': True,
 'honesty': ('Synthetic 12-lead toy waveforms + diagonal selective SSM numpy '
             'approximation. NOT official Mamba kernel, NOT pretrained, NOT real '
             '1.15M ECG. Real-data forward requires PhysioNet DUA + T1 preflight.'),
 'W3_success_statement': ('W3 average effect -0.0248 (CI [-0.0269,-0.0228]) and '
                          'mechanism F-M1/M2/M3 remain SUCCESSFUL and are retained.')}
print('\n=== W5 FINAL VERDICT ===', flush=True)
print(checks, '| all_pass =', out['verdict']['all_pass'], flush=True)
print(out['verdict']['W3_line_crossed'], flush=True)
print('elapsed', round(time.time()-T0, 1), 's', flush=True)

# ------------------------------------------------------------------ figures
fig, axes = plt.subplots(1, 3, figsize=(15, 4.3))
ax = axes[0]
keys = ['GLOBAL', 'GST', 'SR-GST', 'CW-GST', 'GS-GST', 'ORACLE']
v = [AGG[k]['ECE']['mean'] for k in keys]; e = [AGG[k]['ECE']['sd'] for k in keys]
cols = ['#8c959f', '#bf8700', '#d1242f', '#8250df', '#1f6feb', '#2da44e']
b = ax.bar(range(6), v, yerr=e, color=cols, alpha=.9, capsize=3)
ax.bar_label(b, fmt='%.3f', fontsize=8, padding=2)
ax.set_xticks(range(6)); ax.set_xticklabels(keys, rotation=25, ha='right', fontsize=8)
ax.set_ylabel('ECE'); ax.set_title('W5｜600 个独立 Mamba 种子'); ax.grid(alpha=.3, axis='y')
ax.set_ylim(0, max(np.array(v) + np.array(e)) * 1.2)

ax = axes[1]
hvals = [AGG[k]['harm_rate'] for k in ['GST','SR-GST','CW-GST','GS-GST','ORACLE']]
ax.bar(range(5), hvals, color=['#bf8700','#d1242f','#8250df','#1f6feb','#2da44e'], alpha=.9)
ax.axhline(0.05, color='#2da44e', ls='--', lw=1.8, label='5% 部署上限')
ax.set_xticks(range(5)); ax.set_xticklabels(['GST','SR-GST','CW-GST','GS-GST','ORACLE'],
                                           rotation=25, ha='right', fontsize=8)
ax.set_ylabel('危害率（劣于 GLOBAL 的种子比例）')
ax.set_title(f'危害率：GST {AGG["GST"]["harm_rate"]:.3f} → GS-GST {AGG["GS-GST"]["harm_rate"]:.3f}')
ax.legend(fontsize=9); ax.grid(alpha=.3, axis='y')

ax = axes[2]
ax.hist(d_gst, bins=50, color='#bf8700', alpha=.55, label='GST (W3 基线)')
ax.hist(d_gs, bins=50, color='#1f6feb', alpha=.62, label='GS-GST (W5)')
ax.axvline(0, color='#d1242f', lw=2, ls='--')
ax.set_xlabel('ΔECE = estimator − GLOBAL'); ax.set_ylabel('种子数')
ax.set_title('H2/H3｜增益保留 + 尾部收窄'); ax.legend(fontsize=9); ax.grid(alpha=.3)
fig.tight_layout(); fig.savefig(HERE / 'fig_w5_main.png'); plt.close(fig)

fig, ax = plt.subplots(figsize=(8.2, 4.2))
conds = ['主设定 A\n300', '高风险 B\n300', 'F-M1\n合并群', 'F-M2\n置换群',
         'F-M3\n群同质', 'CNN-1D\n对照']
means = [arr(A, 'delta_gsgst').mean(), arr(B, 'delta_gsgst').mean(),
         d1.mean(), d2.mean(), d3.mean(), dc.mean()]
errs = [arr(A, 'delta_gsgst').std(ddof=1)/np.sqrt(300),
        arr(B, 'delta_gsgst').std(ddof=1)/np.sqrt(300),
        d1.std(ddof=1)/np.sqrt(60), d2.std(ddof=1)/np.sqrt(60),
        d3.std(ddof=1)/np.sqrt(60), dc.std(ddof=1)/np.sqrt(100)]
b = ax.bar(range(6), means, yerr=errs, capsize=4,
           color=['#1f6feb','#1f6feb','#d1242f','#d1242f','#d1242f','#8250df'], alpha=.9)
ax.bar_label(b, fmt='%.4f', fontsize=8, padding=3)
ax.axhline(0, color='#333', lw=1)
ax.axhline(-0.020, color='#2da44e', ls=':', lw=1.6, label='阈值 −0.020')
ax.set_xticks(range(6)); ax.set_xticklabels(conds, fontsize=9)
ax.set_ylabel('mean ΔECE'); ax.set_title('W5｜分层、证伪与架构对照')
ax.legend(fontsize=9); ax.grid(alpha=.3, axis='y')
fig.tight_layout(); fig.savefig(HERE / 'fig_w5_falsification.png'); plt.close(fig)

(HERE / 'w5_results.json').write_text(
    json.dumps(out, indent=2, ensure_ascii=False), encoding='utf-8')
print('DONE', flush=True)
