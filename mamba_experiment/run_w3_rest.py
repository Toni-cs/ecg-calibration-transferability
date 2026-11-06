"""W3 stage 2/2 — falsification + CNN architecture control + final verdict.

Reads the frozen stage-1 output; does NOT recompute or reselect any main seed.
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
FSEEDS = list(range(3600, 3660))
CSEEDS = list(range(3700, 3800))
T0 = time.time()

out = json.loads((HERE / 'mamba600_main_partial.json').read_text(encoding='utf-8'))
out['meta']['stage'] = '2/2 complete (stage 1 main + stage 2 falsification/control)'
dlt = np.array(out['per_seed_deltas'])

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
      '| F-M3', round(d3.mean(), 5), '| elapsed', round(time.time()-T0), 's', flush=True)

print('[C] CNN-1D control 100 seeds 3700-3799 ...', flush=True)
cnn = [run_seed(s, arch='cnn', T_GRID=T_GRID, TAU_GRID=TAU_GRID) for s in CSEEDS]
dc = np.array([r['delta'] for r in cnn])
KEYS = ['SOURCE', 'GLOBAL', 'GST', 'SHRINK', 'ORACLE', 'TRUE-T']
CA = {k: {'ECE': float(np.mean([r['sc'][k]['ECE'] for r in cnn])),
          'NLL': float(np.mean([r['sc'][k]['NLL'] for r in cnn]))} for k in KEYS}
out['CNN_control'] = {'mean_delta_ECE': float(dc.mean()), 'sd': float(dc.std(ddof=1)),
                      'n_negative_of_100': int((dc < 0).sum()),
                      'same_sign_as_mamba': bool(dc.mean() < 0 and dlt.mean() < 0),
                      'abs_mean_gap': float(abs(dc.mean() - dlt.mean())),
                      'aggregate': CA, 'per_seed_deltas': dc.tolist()}
print('   CNN mean delta', round(dc.mean(), 4), 'neg', int((dc < 0).sum()), '/100', flush=True)

checks = {'F0': out['F0_validity_gate']['PASS'], 'H1': out['H1_primary']['PASS'],
          'FM1': out['F']['FM1_merge_groups']['PASS'],
          'FM2': out['F']['FM2_shuffle_group_id']['PASS'],
          'FM3': out['F']['FM3_homogeneous']['PASS'],
          'ARCH': out['CNN_control']['same_sign_as_mamba']}
out['verdict'] = {
    'checks': checks, 'all_pass': bool(all(checks.values())),
    'citable': bool(all(checks.values())),
    'H1_failure_detail': ('mean -0.0248 PASSES threshold -0.020; cross-seed '
                          'bootstrap CI [-0.0269,-0.0228] PASSES; but 534/600 '
                          '(89.0%) negative vs the pre-registered >=540 (90%). '
                          'SHORT BY 6 SEEDS. Threshold NOT changed, no v0.4.'),
    'disposition': ('Per frozen failure clause: GST-on-Mamba is DOWNGRADED to '
                    'exploratory. T1 main line returns to BCC certificate + '
                    '1.15M systematic validation + E5 problem conclusion. '
                    'The 11% harmful-seed regime MOTIVATES a gated-GST hypothesis '
                    'to be registered separately (T1), NOT rescued here.'),
    'honesty': ('Synthetic 12-lead toy waveforms + diagonal selective SSM approx. '
                'NOT official Mamba kernel, NOT pretrained, NOT real 1.15M ECG. '
                'Real-data forward requires PhysioNet DUA + T1 preflight.'),
    'note': ('Seeds 3000-3599 main, 3600-3659 falsification, 3700-3799 CNN '
             'control. All 600 main deltas saved untrimmed. No v0.4 exists.')}
print('\n=== W3 FINAL VERDICT ===', flush=True)
print(checks, '| all_pass =', out['verdict']['all_pass'], flush=True)
print(out['verdict']['H1_failure_detail'], flush=True)
print('elapsed', round(time.time()-T0, 1), 's', flush=True)

fig, ax = plt.subplots(figsize=(8.0, 4.3))
conds = ['主设定\n600', 'F-M1\n合并群', 'F-M2\n置换群', 'F-M3\n群同质', 'CNN-1D\n对照']
means = [dlt.mean(), d1.mean(), d2.mean(), d3.mean(), dc.mean()]
errs = [dlt.std(ddof=1)/np.sqrt(600), d1.std(ddof=1)/np.sqrt(60),
        d2.std(ddof=1)/np.sqrt(60), d3.std(ddof=1)/np.sqrt(60),
        dc.std(ddof=1)/np.sqrt(100)]
b = ax.bar(range(5), means, yerr=errs, capsize=4,
           color=['#1f6feb', '#d1242f', '#d1242f', '#d1242f', '#8250df'], alpha=.9)
ax.bar_label(b, fmt='%.4f', fontsize=9, padding=3)
ax.axhline(0, color='#333', lw=1)
ax.axhline(-0.020, color='#2da44e', ls=':', lw=1.6, label='阈值 −0.020')
ax.set_xticks(range(5)); ax.set_xticklabels(conds, fontsize=9)
ax.set_ylabel('mean ΔECE'); ax.set_title('W3｜证伪与架构对照（600 Mamba 种子）')
ax.legend(fontsize=9); ax.grid(alpha=.3, axis='y')
fig.tight_layout(); fig.savefig(HERE / 'fig_w3_falsification.png'); plt.close(fig)

(HERE / 'mamba600_results.json').write_text(
    json.dumps(out, indent=2, ensure_ascii=False), encoding='utf-8')
print('STAGE 2 DONE', flush=True)
