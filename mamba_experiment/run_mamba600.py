"""W3 CONFIRMATORY — Mamba backbone, 600 independent seeds (3000-3599).

Frozen BEFORE execution by PREREGISTRATION_W3_MAMBA600.md.
All 600 per-seed deltas are saved; nothing is trimmed or selected.
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
from mamba_gst import run_seed

plt.rcParams['font.sans-serif'] = ['WenQuanYi Micro Hei']
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams['figure.dpi'] = 130

T_GRID = np.exp(np.linspace(np.log(0.4), np.log(8.0), 241))
TAU_GRID = np.exp(np.linspace(np.log(0.05), np.log(10.0), 161))
SEEDS = list(range(3000, 3600))              # 600, frozen
FSEEDS = list(range(3600, 3660))             # 60, falsification
CSEEDS = list(range(3700, 3800))             # 100, CNN architecture control
B_BOOT = 10000
T0 = time.time()

out = {'meta': {'prereg': 'PREREGISTRATION_W3_MAMBA600.md v0.3 (frozen)',
                'run_type': 'CONFIRMATORY', 'arch': 'diagonal selective SSM (Mamba-1 S6 approx.)',
                'main_seeds': [3000, 3599, 600], 'falsification_seeds': [3600, 3659, 60],
                'cnn_control_seeds': [3700, 3799, 100],
                'T_grid': [0.4, 8.0, 241], 'tau_grid': [0.05, 10.0, 161],
                'bootstrap_B': B_BOOT, 'date': '2026-11-05',
                'history_retained': ['W1 PARI falsified', 'W2 v1.0 H1=False',
                                     'W2 v1.1 F-B FAIL / graph removed', 'T1 v0.2 GST']}}

print('[MAIN] 600 independent Mamba seeds 3000-3599 ...', flush=True)
rows = []
for i, s in enumerate(SEEDS):
    rows.append(run_seed(s, arch='mamba', T_GRID=T_GRID, TAU_GRID=TAU_GRID))
    if (i + 1) % 100 == 0:
        d = np.array([r['delta'] for r in rows])
        print(f'   {i+1}/600  mean={d.mean():.4f}  neg={(d<0).sum()}/{len(d)}  '
              f'elapsed={time.time()-T0:.0f}s', flush=True)

dlt = np.array([r['delta'] for r in rows])
man = np.array([r['manipulation_check'] for r in rows])
taus = np.array([r['tau_s'] for r in rows])

# ---- F0 ----
orc_nll = np.array([r['sc']['ORACLE']['NLL'] for r in rows])
best_nll = np.array([min(r['sc'][k]['NLL'] for k in ['SOURCE','GLOBAL','GST','SHRINK']) for r in rows])
f0_nll_pass = bool(np.all(orc_nll <= best_nll + 1e-6))
orc_ece = np.array([r['sc']['ORACLE']['ECE'] for r in rows])
best_ece = np.array([min(r['sc'][k]['ECE'] for k in ['SOURCE','GLOBAL','GST','SHRINK']) for r in rows])
ece_reversals = orc_ece - best_ece
man_pass = bool(man.mean() > 0.02 and (man > 0).mean() >= 0.90)
f0 = {'nll_gate_per_seed_pass': f0_nll_pass, 'n_seeds_failing_nll': int((orc_nll > best_nll + 1e-6).sum()),
      'ece_oracle_reversals': int((ece_reversals > 0.001).sum()),
      'max_ece_reversal_gap': float(ece_reversals.max()),
      'manipulation_check_mean': float(man.mean()),
      'manipulation_positive_frac': float((man > 0).mean()),
      'manipulation_min': float(man.min()), 'manipulation_pass': man_pass,
      'PASS': bool(f0_nll_pass and man_pass)}
out['F0_validity_gate'] = f0
print('   F0:', {k: v for k, v in f0.items() if k != 'PASS'}, 'PASS =', f0['PASS'], flush=True)
if not f0['PASS']:
    (HERE / 'mamba600_results.json').write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding='utf-8')
    raise SystemExit('F0 FAILED — all results discarded.')

# ---- aggregates ----
KEYS = ['SOURCE', 'GLOBAL', 'GST', 'SHRINK', 'ORACLE', 'TRUE-T']
A = {}
for k in KEYS:
    A[k] = {}
    for m in ['ECE', 'NLL', 'Brier']:
        v = np.array([r['sc'][k][m] for r in rows])
        A[k][m] = {'mean': float(v.mean()), 'sd': float(v.std(ddof=1))}

# ---- H1 ----
rng = np.random.default_rng(20261105)
bm = np.array([dlt[rng.integers(0, len(dlt), len(dlt))].mean() for _ in range(B_BOOT)])
ci = [float(np.percentile(bm, 2.5)), float(np.percentile(bm, 97.5))]
h1 = {'mean_delta_ECE': float(dlt.mean()), 'sd': float(dlt.std(ddof=1)),
      'n_negative_of_600': int((dlt < 0).sum()), 'negative_fraction': float((dlt < 0).mean()),
      'median': float(np.median(dlt)), 'q25': float(np.percentile(dlt, 25)),
      'q75': float(np.percentile(dlt, 75)), 'min': float(dlt.min()), 'max': float(dlt.max()),
      'cross_seed_bootstrap_CI95': ci, 'bootstrap_p': float((bm >= 0).mean()),
      'conditions': {'mean_le_-0.020': bool(dlt.mean() <= -0.020),
                     'ge_540_of_600_negative': bool((dlt < 0).sum() >= 540),
                     'CI_upper_lt_0': bool(ci[1] < 0)},
      'threshold': -0.020}
h1['PASS'] = all(h1['conditions'].values())
out['H1_primary'] = h1
out['aggregate'] = A
out['per_seed_deltas'] = dlt.tolist()          # ALL 600, nothing trimmed
out['per_seed_manipulation'] = man.tolist()
out['tau_s_distribution'] = {'mean': float(taus.mean()), 'sd': float(taus.std(ddof=1)),
                              'min': float(taus.min()), 'max': float(taus.max())}
worst = np.argsort(dlt)[-10:][::-1]
out['worst_10_seeds'] = [{'seed': int(SEEDS[i]), 'delta': float(dlt[i]),
                           'SOURCE_ECE': rows[i]['sc']['SOURCE']['ECE'],
                           'GLOBAL_ECE': rows[i]['sc']['GLOBAL']['ECE'],
                           'GST_ECE': rows[i]['sc']['GST']['ECE']} for i in worst]

print('   H1:', {k: v for k, v in h1.items() if k not in ('conditions',)}, flush=True)
(HERE / 'mamba600_main_partial.json').write_text(
    json.dumps({k: out[k] for k in ('meta', 'F0_validity_gate', 'H1_primary',
                                    'aggregate', 'per_seed_deltas',
                                    'per_seed_manipulation', 'tau_s_distribution',
                                    'worst_10_seeds')}, indent=2, ensure_ascii=False),
    encoding='utf-8')
for k in KEYS:
    print(f'   {k:8s} ECE={A[k]["ECE"]["mean"]:.4f}±{A[k]["ECE"]["sd"]:.4f}  '
          f'NLL={A[k]["NLL"]["mean"]:.4f}', flush=True)

# ---- falsification ----
print('[F] falsification 60 seeds 3600-3659 ...', flush=True)
fm1 = [run_seed(s, merge_groups=True, T_GRID=T_GRID, TAU_GRID=TAU_GRID) for s in FSEEDS]
fm2 = [run_seed(s, shuffle_groups=True, T_GRID=T_GRID, TAU_GRID=TAU_GRID) for s in FSEEDS]
fm3 = [run_seed(s, homogeneous=True, T_GRID=T_GRID, TAU_GRID=TAU_GRID) for s in FSEEDS]
d1 = np.array([r['delta'] for r in fm1]); d2 = np.array([r['delta'] for r in fm2])
d3 = np.array([r['delta'] for r in fm3])
out['F'] = {
    'FM1_merge_groups': {'mean_delta': float(d1.mean()), 'abs': float(abs(d1.mean())),
                          'PASS': bool(abs(d1.mean()) < 0.005)},
    'FM2_shuffle_group_id': {'mean_delta': float(d2.mean()), 'abs': float(abs(d2.mean())),
                              'PASS': bool(abs(d2.mean()) < 0.010)},
    'FM3_homogeneous': {'mean_delta': float(d3.mean()), 'abs': float(abs(d3.mean())),
                         'PASS': bool(abs(d3.mean()) < 0.010)}}
print('   F-M1', round(d1.mean(), 5), '| F-M2', round(d2.mean(), 5),
      '| F-M3', round(d3.mean(), 5), flush=True)

# ---- architecture control ----
print('[C] CNN-1D control 100 seeds 3700-3799 ...', flush=True)
cnn = [run_seed(s, arch='cnn', T_GRID=T_GRID, TAU_GRID=TAU_GRID) for s in CSEEDS]
dc = np.array([r['delta'] for r in cnn])
cnn_keys = ['SOURCE', 'GLOBAL', 'GST', 'SHRINK', 'ORACLE', 'TRUE-T']
CA = {k: {'ECE': float(np.mean([r['sc'][k]['ECE'] for r in cnn])),
          'NLL': float(np.mean([r['sc'][k]['NLL'] for r in cnn]))} for k in cnn_keys}
out['CNN_control'] = {'mean_delta_ECE': float(dc.mean()), 'sd': float(dc.std(ddof=1)),
                      'n_negative_of_100': int((dc < 0).sum()),
                      'same_sign_as_mamba': bool(dc.mean() < 0 and dlt.mean() < 0),
                      'abs_mean_gap': float(abs(dc.mean() - dlt.mean())),
                      'aggregate': CA, 'per_seed_deltas': dc.tolist()}
print('   CNN mean delta', round(dc.mean(), 4), 'neg', int((dc < 0).sum()), '/100', flush=True)

# ---- verdict ----
checks = {'F0': f0['PASS'], 'H1': h1['PASS'],
          'FM1': out['F']['FM1_merge_groups']['PASS'],
          'FM2': out['F']['FM2_shuffle_group_id']['PASS'],
          'FM3': out['F']['FM3_homogeneous']['PASS'],
          'ARCH': out['CNN_control']['same_sign_as_mamba']}
out['verdict'] = {
    'checks': checks, 'all_pass': bool(all(checks.values())),
    'citable': bool(all(checks.values())),
    'note': ('Only seeds 3000-3599 (main), 3600-3659 (falsification), '
             '3700-3799 (CNN control) are used. No v0.4 exists.'),
    'honesty': ('Synthetic 12-lead toy waveforms + diagonal selective SSM approx. '
                'NOT official Mamba kernel, NOT pretrained, NOT real 1.15M ECG. '
                'Real-data forward pass still requires PhysioNet DUA + T1 preflight.')}
print('\n=== W3 FINAL VERDICT ===', flush=True)
print(checks, '| all_pass =', out['verdict']['all_pass'], flush=True)
print('elapsed', round(time.time() - T0, 1), 's', flush=True)

# ---- figures ----
fig, axes = plt.subplots(1, 3, figsize=(14.5, 4.2))
ax = axes[0]
ax.hist(dlt, bins=60, color='#1f6feb', alpha=.88)
ax.axvline(0, color='#d1242f', lw=2, ls='--', label='零效应')
ax.axvline(dlt.mean(), color='#2da44e', lw=2, ls='-', label=f'均值 {dlt.mean():.4f}')
ax.set_xlabel('ΔECE = GST − GLOBAL'); ax.set_ylabel('种子数')
ax.set_title('600 个独立 Mamba 种子的主终点分布'); ax.legend(fontsize=9); ax.grid(alpha=.3)

ax = axes[1]
cols = ['#8c959f', '#d1242f', '#bf8700', '#8250df', '#1f6feb', '#2da44e']
v = [A[k]['ECE']['mean'] for k in KEYS]; e = [A[k]['ECE']['sd'] for k in KEYS]
b = ax.bar(range(6), v, yerr=e, color=cols, alpha=.9, capsize=3)
ax.bar_label(b, fmt='%.3f', fontsize=8, padding=2)
ax.set_xticks(range(6)); ax.set_xticklabels(KEYS, rotation=25, ha='right', fontsize=8)
ax.set_ylabel('ECE'); ax.set_title('Mamba 前向 logits 上的六种估计器'); ax.grid(alpha=.3, axis='y')
ax.set_ylim(0, max(np.array(v) + np.array(e)) * 1.2)

ax = axes[2]
conds = ['主设定\n600', 'F-M1\n合并群', 'F-M2\n置换群', 'F-M3\n群同质', 'CNN-1D\n对照']
means = [dlt.mean(), d1.mean(), d2.mean(), d3.mean(), dc.mean()]
ax.bar(range(5), means, color=['#1f6feb', '#d1242f', '#d1242f', '#d1242f', '#8250df'], alpha=.9)
ax.axhline(0, color='#333', lw=1)
ax.axhline(-0.020, color='#2da44e', ls=':', lw=1.5, label='阈值 −0.020')
ax.set_xticks(range(5)); ax.set_xticklabels(conds, fontsize=9)
ax.set_ylabel('mean ΔECE'); ax.set_title('证伪与架构对照：优势应只在主设定出现')
ax.legend(fontsize=8); ax.grid(alpha=.3, axis='y')
fig.tight_layout(); fig.savefig(HERE / 'fig_w3_main.png'); plt.close(fig)

fig, ax = plt.subplots(figsize=(7.4, 4.0))
ax.hist(bm, bins=60, color='#2da44e', alpha=.88)
ax.axvline(0, color='#d1242f', lw=2, ls='--', label='零效应')
ax.axvline(ci[0], color='#1f6feb', lw=1.5, ls=':')
ax.axvline(ci[1], color='#1f6feb', lw=1.5, ls=':', label='95% CI')
ax.set_xlabel('跨种子 mean ΔECE'); ax.set_ylabel('bootstrap 频次')
ax.set_title(f'跨种子 paired bootstrap (B={B_BOOT}, 单位=种子)'); ax.legend(fontsize=9); ax.grid(alpha=.3)
fig.tight_layout(); fig.savefig(HERE / 'fig_w3_bootstrap.png'); plt.close(fig)

(HERE / 'mamba600_results.json').write_text(
    json.dumps(out, indent=2, ensure_ascii=False), encoding='utf-8')
print('DONE', flush=True)
