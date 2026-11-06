"""T2 overview figure. Reads only frozen JSON results; no new claims."""
from __future__ import annotations
import json, pathlib
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / 'figs'; OUT.mkdir(exist_ok=True)
plt.rcParams['font.sans-serif'] = ['WenQuanYi Micro Hei']
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams['figure.dpi'] = 130

G = json.loads((HERE / 'results' / 'grid_plan.json').read_text(encoding='utf-8'))
P = json.loads((HERE / 'results' / 'preflight_gpu_smoke.json').read_text(encoding='utf-8'))
A = json.loads((HERE / 'results' / 'acceptance_gates_smoke.json').read_text(encoding='utf-8'))

fig, ax = plt.subplots(2, 2, figsize=(13.6, 8.8))

# (a) data scale
a = ax[0, 0]
labels = ['原 60 格\npilot', 'W12-open\n公开层', 'T2 主队列\n(+CODE-II)']
recs = [52050, G['open_layer']['records'], G['main_queue']['records']]
pats = [52050, G['open_layer']['patients'], G['main_queue']['patients']]
x = np.arange(3); w = 0.36
a.bar(x - w/2, [v/1e6 for v in recs], w, label='记录 (百万)', color='#1f6feb')
a.bar(x + w/2, [v/1e6 for v in pats], w, label='独立患者 (百万)', color='#8250df')
for i, (r, p) in enumerate(zip(recs, pats)):
    a.text(i - w/2, r/1e6 + .04, f'{r/1e6:.2f}', ha='center', fontsize=9)
    a.text(i + w/2, p/1e6 + .04, f'{p/1e6:.2f}', ha='center', fontsize=9)
a.set_xticks(x); a.set_xticklabels(labels, fontsize=9)
a.set_ylabel('百万'); a.set_ylim(0, 3.75)
a.set_title('语料规模：3 个库 → 13 个语料\n主队列 ≈331 万记录 / ≈248 万独立患者')
a.legend(fontsize=8); a.grid(alpha=.3, axis='y')

# (b) compute ladder
a = ax[0, 1]
stages = ['(a) 原仓库\nGPU 训练', '(b) W12\n冻结前向', 'Stage A\n150 次真训练',
          'Stage B\n108 次适配', 'Stage C\n校准层 CPU']
vals = [1, 1, 150, 108, 108]
cols = ['#57606a', '#57606a', '#1f6feb', '#8250df', '#2da44e']
b = a.bar(stages, vals, color=cols, alpha=.9, width=.6)
a.bar_label(b, fmt='%d', fontsize=10, padding=3, weight='bold')
a.set_ylabel('独立运行 / 格数')
a.set_title('三级计算阶梯：补上真训练端\n「零 GPU」只指 Stage C')
a.tick_params(axis='x', labelsize=8); a.grid(alpha=.3, axis='y')

# (c) GPU-hour sensitivity (assumption-driven)
a = ax[1, 0]
sps = [x['throughput_samples_per_s'] for x in G['gpu_hour_budget_sensitivity']]
ah = [x['stage_a_150runs_gpu_h'] for x in G['gpu_hour_budget_sensitivity']]
bh = [x['stage_b_108runs_gpu_h'] for x in G['gpu_hour_budget_sensitivity']]
a.plot(sps, ah, 'o-', color='#d1242f', lw=2, label='Stage A 150 次')
a.plot(sps, bh, 's-', color='#1f6feb', lw=2, label='Stage B 108 次')
for xx, yy in zip(sps, ah):
    a.annotate(f'{yy:.0f}h', (xx, yy), textcoords='offset points',
               xytext=(0, 8), ha='center', fontsize=9, color='#d1242f')
a.set_xlabel('占位吞吐假设 (samples/s)')
a.set_ylabel('GPU·小时')
a.set_title('算力敏感性（公式粗估，非实测）\n须用你机器实测吞吐替换')
a.legend(fontsize=9); a.grid(alpha=.3)

# (d) honest self-check status
a = ax[1, 1]; a.axis('off')
rows = [
    ['语料 catalog', '13 (12 公开 + 1 学术申请)', 'PASS'],
    ['种子与 W1–W12 冲突', '0', 'PASS'],
    ['preflight 结构断言', f"{P['n_pass']}/{P['n_executed']}", 'PASS'],
    ['preflight 环境断言', f"{P['n_unavailable']} UNAVAILABLE", '如实报'],
    ['12 门逻辑自检', f"{A['n_pass']}/12 (G12 必 FAIL)", '非结果'],
    ['真实 GPU 训练', '0 次', '未做'],
]
t = a.table(cellText=rows,
            colLabels=['检查项', '观测', '判定'],
            cellLoc='left', colLoc='left', colWidths=[0.38, 0.40, 0.22],
            loc='center')
t.auto_set_font_size(False); t.set_fontsize(9); t.scale(1, 1.8)
for (r, c), cell in t.get_celld().items():
    if r == 0:
        cell.set_facecolor('#24292f')
        cell.set_text_props(color='white', weight='bold')
    elif c == 2:
        v = rows[r-1][2]
        cell.set_facecolor('#dafbe1' if v == 'PASS' else '#fff8c5')
a.set_title('本轮真实自检（CPU，规格级）\n所有 GPU 训练结果均不存在',
            fontsize=10, pad=12)

fig.tight_layout()
fig.savefig(OUT / 'fig_t2_upgrade.png')
plt.close(fig)
print('fig_t2_upgrade.png written')
