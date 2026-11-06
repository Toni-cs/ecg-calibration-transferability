"""W3 stage 1/2 — 600 independent Mamba seeds (3000-3599).

Split into two stages only because the sandbox killed the single long run at
the falsification phase. Design, seeds, thresholds and estimators are BYTE-
IDENTICAL to PREREGISTRATION_W3_MAMBA600.md; only execution is split.
"""
from __future__ import annotations
import json, pathlib, sys, time
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
SEEDS = list(range(3000, 3600))
B_BOOT = 10000
T0 = time.time()

out = {'meta': {'prereg': 'PREREGISTRATION_W3_MAMBA600.md v0.3 (frozen)',
                'run_type': 'CONFIRMATORY', 'stage': '1/2 main',
                'arch': 'diagonal selective SSM (Mamba-1 S6 approx.)',
                'main_seeds': [3000, 3599, 600],
                'falsification_seeds': [3600, 3659, 60],
                'cnn_control_seeds': [3700, 3799, 100],
                'T_grid': [0.4, 8.0, 241], 'tau_grid': [0.05, 10.0, 161],
                'bootstrap_B': B_BOOT, 'date': '2026-11-05',
                'history_retained': ['W1 PARI falsified', 'W2 v1.0 H1=False',
                                     'W2 v1.1 F-B FAIL / graph removed', 'T1 v0.2 GST']}}

print('[MAIN] 600 independent Mamba seeds 3000-3599 ...', flush=True)
rows = []
for i, s in enumerate(SEEDS):
    rows.append(run_seed(s, arch='mamba', T_GRID=T_GRID, TAU_GRID=TAU_GRID))
    if (i + 1) % 150 == 0:
        d = np.array([r['delta'] for r in rows])
        print(f'   {i+1}/600 mean={d.mean():.4f} neg={(d<0).sum()}/{len(d)} '
              f'elapsed={time.time()-T0:.0f}s', flush=True)

dlt = np.array([r['delta'] for r in rows])
man = np.array([r['manipulation_check'] for r in rows])
taus = np.array([r['tau_s'] for r in rows])

orc_nll = np.array([r['sc']['ORACLE']['NLL'] for r in rows])
best_nll = np.array([min(r['sc'][k]['NLL'] for k in ['SOURCE','GLOBAL','GST','SHRINK']) for r in rows])
f0_nll_pass = bool(np.all(orc_nll <= best_nll + 1e-6))
orc_ece = np.array([r['sc']['ORACLE']['ECE'] for r in rows])
best_ece = np.array([min(r['sc'][k]['ECE'] for k in ['SOURCE','GLOBAL','GST','SHRINK']) for r in rows])
ece_rev = orc_ece - best_ece
man_pass = bool(man.mean() > 0.02 and (man > 0).mean() >= 0.90)
f0 = {'nll_gate_per_seed_pass': f0_nll_pass,
      'n_seeds_failing_nll': int((orc_nll > best_nll + 1e-6).sum()),
      'ece_oracle_reversals': int((ece_rev > 0.001).sum()),
      'max_ece_reversal_gap': float(ece_rev.max()),
      'ece_reversal_note': ('ORACLE is fitted by NLL; ECE is a binning estimate '
                            'and need not share its optimum. No ECE gate was '
                            'pre-registered. Observed max gap exceeds the 20-seed '
                            'pilot (~0.005); reported as-is.'),
      'manipulation_check_mean': float(man.mean()),
      'manipulation_positive_frac': float((man > 0).mean()),
      'manipulation_min': float(man.min()), 'manipulation_pass': man_pass,
      'PASS': bool(f0_nll_pass and man_pass)}
out['F0_validity_gate'] = f0
print('   F0 PASS =', f0['PASS'], '| ece_reversals =', f0['ece_oracle_reversals'],
      '| max gap =', round(f0['max_ece_reversal_gap'], 4), flush=True)

KEYS = ['SOURCE', 'GLOBAL', 'GST', 'SHRINK', 'ORACLE', 'TRUE-T']
A = {}
for k in KEYS:
    A[k] = {}
    for m in ['ECE', 'NLL', 'Brier']:
        v = np.array([r['sc'][k][m] for r in rows])
        A[k][m] = {'mean': float(v.mean()), 'sd': float(v.std(ddof=1))}

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
out['per_seed_deltas'] = dlt.tolist()
out['per_seed_manipulation'] = man.tolist()
out['tau_s_distribution'] = {'mean': float(taus.mean()), 'sd': float(taus.std(ddof=1)),
                              'min': float(taus.min()), 'max': float(taus.max())}
worst = np.argsort(dlt)[-10:][::-1]
out['worst_10_seeds'] = [{'seed': int(SEEDS[i]), 'delta': float(dlt[i]),
                           'SOURCE_ECE': rows[i]['sc']['SOURCE']['ECE'],
                           'GLOBAL_ECE': rows[i]['sc']['GLOBAL']['ECE'],
                           'GST_ECE': rows[i]['sc']['GST']['ECE'],
                           'manipulation': float(man[i])} for i in worst]

print('   H1:', {k: v for k, v in h1.items() if k != 'conditions'}, flush=True)
print('   conditions:', h1['conditions'], '=> PASS =', h1['PASS'], flush=True)
for k in KEYS:
    print(f'   {k:8s} ECE={A[k]["ECE"]["mean"]:.4f}±{A[k]["ECE"]["sd"]:.4f} '
          f'NLL={A[k]["NLL"]["mean"]:.4f}', flush=True)
print('   elapsed', round(time.time() - T0, 1), 's', flush=True)

# ---------- exploratory, clearly labelled, NOT a confirmatory endpoint ----------
# Pre-registered failure clause says do not change thresholds. This analysis
# only characterises WHICH seeds fail, to motivate a gate hypothesis in a NEW
# preregistration (T1). It is NOT used to rescue H1.
q = np.quantile(man, [0.25, 0.5, 0.75])
bands = [('low', man <= q[0]), ('mid', (man > q[0]) & (man <= q[2])), ('high', man > q[2])]
gate_expl = {'status': 'EXPLORATORY / NOT CONFIRMATORY / NOT USED FOR H1',
             'bands_by_manipulation_strength': {}}
for nm, msk in bands:
    gate_expl['bands_by_manipulation_strength'][nm] = {
        'n': int(msk.sum()), 'mean_delta': float(dlt[msk].mean()),
        'frac_negative': float((dlt[msk] < 0).mean()),
        'mean_manipulation': float(man[msk].mean())}
out['EXPLORATORY_gate_motivation'] = gate_expl

(HERE / 'mamba600_main_partial.json').write_text(
    json.dumps(out, indent=2, ensure_ascii=False), encoding='utf-8')

# figures 1 & 2
fig, axes = plt.subplots(1, 2, figsize=(11.2, 4.2))
ax = axes[0]
ax.hist(dlt, bins=60, color='#1f6feb', alpha=.88)
ax.axvline(0, color='#d1242f', lw=2, ls='--', label='零效应')
ax.axvline(dlt.mean(), color='#2da44e', lw=2, label=f'均值 {dlt.mean():.4f}')
ax.set_xlabel('ΔECE = GST − GLOBAL'); ax.set_ylabel('种子数')
ax.set_title('600 个独立 Mamba 种子的主终点分布'); ax.legend(fontsize=9); ax.grid(alpha=.3)
ax = axes[1]
cols = ['#8c959f', '#d1242f', '#bf8700', '#8250df', '#1f6feb', '#2da44e']
v = [A[k]['ECE']['mean'] for k in KEYS]; e = [A[k]['ECE']['sd'] for k in KEYS]
b = ax.bar(range(6), v, yerr=e, color=cols, alpha=.9, capsize=3)
ax.bar_label(b, fmt='%.3f', fontsize=8, padding=2)
ax.set_xticks(range(6)); ax.set_xticklabels(KEYS, rotation=25, ha='right', fontsize=8)
ax.set_ylabel('ECE'); ax.set_title('Mamba 前向 logits 上的六种估计器')
ax.grid(alpha=.3, axis='y'); ax.set_ylim(0, max(np.array(v) + np.array(e)) * 1.2)
fig.tight_layout(); fig.savefig(HERE / 'fig_w3_main.png'); plt.close(fig)

fig, ax = plt.subplots(figsize=(7.4, 4.0))
ax.hist(bm, bins=60, color='#2da44e', alpha=.88)
ax.axvline(0, color='#d1242f', lw=2, ls='--', label='零效应')
ax.axvline(ci[0], color='#1f6feb', lw=1.5, ls=':')
ax.axvline(ci[1], color='#1f6feb', lw=1.5, ls=':', label='95% CI')
ax.set_xlabel('跨种子 mean ΔECE'); ax.set_ylabel('bootstrap 频次')
ax.set_title(f'跨种子 paired bootstrap (B={B_BOOT}, 单位=种子)')
ax.legend(fontsize=9); ax.grid(alpha=.3)
fig.tight_layout(); fig.savefig(HERE / 'fig_w3_bootstrap.png'); plt.close(fig)
print('STAGE 1 DONE', flush=True)
