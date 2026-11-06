"""W11-B summary figure (2x2). Reads only the frozen result JSONs."""
from __future__ import annotations
import json, pathlib, re
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
R = ROOT / 'w11_theory' / 'results'
OUT = ROOT / 'w11_theory' / 'figs'
OUT.mkdir(exist_ok=True)
plt.rcParams['font.sans-serif'] = ['WenQuanYi Micro Hei']
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams['figure.dpi'] = 130

V = json.loads((R / 'w11b_final_verdict.json').read_text(encoding='utf-8'))
TH = json.loads((R / 'w11b_theory_120.json').read_text(encoding='utf-8'))
G = V['groups']

fig, axes = plt.subplots(2, 2, figsize=(13.6, 8.6))

# ---- (a) three groups stacked
ax = axes[0, 0]
names = ['理论 TH', 'preflight PF', 'verify VG']
passv = [G[k]['n_pass'] for k in ['theory', 'preflight', 'verify']]
failv = [G[k]['n_fail'] for k in ['theory', 'preflight', 'verify']]
x = np.arange(3)
ax.bar(x, passv, 0.55, color='#2da44e', alpha=.9, label='PASS')
ax.bar(x, failv, 0.55, bottom=passv, color='#d1242f', alpha=.9, label='FAIL')
for i, (p, f) in enumerate(zip(passv, failv)):
    ax.text(i, p + f + 2, f'{p}/120', ha='center', fontsize=11, weight='bold')
    if f:
        ax.text(i, p + f / 2, str(f), ha='center', va='center',
                color='white', fontsize=10, weight='bold')
ax.set_xticks(x); ax.set_xticklabels(names, fontsize=9)
ax.set_ylim(0, 132); ax.set_ylabel('断言数')
ax.set_title(f'W11-B｜三组各 120 条，合计 {V["total_pass"]}/{V["total_checks"]}\n'
             f'6 条 FAIL 全部如实保留')
ax.legend(fontsize=9); ax.grid(alpha=.3, axis='y')

# ---- (b) granularity + kinds
ax = axes[0, 1]
labels = ['W11 原始\n(理论6+PF7+VG12)', 'W11-B\n(120+120+120)']
vals = [25, 360]
b = ax.bar(labels, vals, color=['#8250df', '#1f6feb'], alpha=.9, width=.5)
ax.bar_label(b, fmt='%d', fontsize=12, padding=3, weight='bold')
ax.set_ylabel('独立检查项数')
ax.set_title('检查粒度：25 → 360（14.4×）\n'
             '但检查项变多 ≠ 更严谨 ≠ 更接近一区')
ax.grid(alpha=.3, axis='y')
ax.text(0.5, 0.55,
        f'kind 分布：verify {V["n_by_kind_total"]["verify"]} · '
        f'falsify {V["n_by_kind_total"]["falsify"]} · '
        f'meta {V["n_by_kind_total"]["meta"]}',
        transform=ax.transAxes, ha='center', fontsize=9,
        bbox=dict(boxstyle='round', fc='#f6f8fa', ec='#d0d7de'))

# ---- (c) TH051-TH070 MC ratios vs frozen interval
ax = axes[1, 0]
ratios = []
for a in TH['assertions']:
    if a['family'] == 'T2_V_closed_form':
        m = re.search(r'ratio=([0-9.]+)', str(a['observed']))
        if m:
            ratios.append((a['id'], float(m.group(1))))
ys = [r for _, r in ratios]
xs = np.arange(1, len(ys) + 1)
cols = ['#d1242f' if (y < 0.97 or y > 1.03) else '#1f6feb' for y in ys]
ax.axhspan(0.97, 1.03, color='#2da44e', alpha=.13,
           label='冻结容差 [0.97, 1.03]')
ax.axhline(1.0, color='#333', ls='--', lw=1.2)
ax.scatter(xs, ys, c=cols, s=42, zorder=3)
for (tid, y), xx in zip(ratios, xs):
    if y < 0.97 or y > 1.03:
        ax.annotate(f'{tid}\n{y:.4f}', (xx, y), textcoords='offset points',
                    xytext=(6, 10 if y < 0.97 else -14), fontsize=8,
                    color='#d1242f')
ax.set_ylim(0.958, 1.042)
ax.set_xlabel('TH051–TH070 逐条（20 组独立参数格）')
ax.set_ylabel('解析 V / MC 估计 V')
ax.set_title('TH054 / TH064｜B=20,000 的 MC 抽样波动\n'
             '越出事先冻结的固定容差（如实判 FAIL，不放宽）')
ax.legend(fontsize=8); ax.grid(alpha=.3)

# ---- (d) FAIL ledger as a table
ax = axes[1, 1]
ax.axis('off')
rows = [
    ['TH054', 'T2-V 闭式', 'ratio 0.9650', 'MC 抽样波动'],
    ['TH064', 'T2-V 闭式', 'ratio 1.0307', 'MC 抽样波动'],
    ['TH099', 'T3 单调性', 'monotone=False', '断言写窄：c=1 两侧不对称'],
    ['PF041', '缓存字段', 'logits 缺 note', '预注册要求 note 齐备'],
    ['PF048', '缓存字段', 'n_rec 缺 note', '预注册要求 note 齐备'],
    ['PF049', '缓存字段', 'n_patient 缺 note', '预注册要求 note 齐备'],
]
t = ax.table(cellText=rows,
             colLabels=['ID', '族', '观测值', '性质（未修改）'],
             cellLoc='left', colLoc='left',
             colWidths=[0.11, 0.20, 0.24, 0.45],
             loc='center')
t.auto_set_font_size(False); t.set_fontsize(8.2); t.scale(1, 1.75)
for (r, c), cell in t.get_celld().items():
    if r == 0:
        cell.set_facecolor('#24292f'); cell.set_text_props(color='white',
                                                          weight='bold')
    elif c == 0:
        cell.set_facecolor('#ffebe9'); cell.set_text_props(color='#d1242f',
                                                            weight='bold')
ax.set_title('6 条 FAIL 逐条留痕\n按 §6：不改断言、不删条目、不放宽阈值、不存在 v1.1',
             fontsize=10, pad=12)

fig.tight_layout()
fig.savefig(OUT / 'fig_w11b_overview.png')
plt.close(fig)
print('fig_w11b_overview.png written')
