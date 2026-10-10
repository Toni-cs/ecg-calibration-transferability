"""终局裁决实验：噪声底 vs 主效应，按实测拟合温度分层

关键质疑（Con agent）：
  ΔECE_OOD = +0.0159，而 T=1.25 时底噪 +0.014~+0.035，
  即"效应量 < 底噪"，主发现可能是度量噪声。
本脚本检验：
  (1) 实测 ΔECE_OOD 是否随拟合 T 增大而增大（噪声底预测应增大）
  (2) 若正效应与 T 无关甚至反向，则噪声底不能解释主发现
"""
import csv, sys, statistics as st
from collections import defaultdict

rows = [r for r in csv.DictReader(
    open('results/ablation_ts_components.csv', encoding='utf-8'))]

# 收集每个 cell 的 (T_global, delta_smooth_ece)
per_cell = {}
for r in rows:
    key = (r['source'], r['target'], r['arch'], r['seed'])
    per_cell.setdefault(key, {})[r['stage']] = r

recs = []
for key, stg in per_cell.items():
    if 'raw' not in stg or 'stage1_ts' not in stg:
        continue
    T = stg['stage1_ts']['T_global']
    if T in ('', 'nan'):
        continue
    T = float(T)
    d = float(stg['stage1_ts']['smooth_ece']) - float(stg['raw']['smooth_ece'])
    recs.append({'key': key, 'T': T, 'delta': d,
                 'raw_ece': float(stg['raw']['smooth_ece'])})

print('可配对 cell 数:', len(recs))

# 按拟合温度分层
bins = [(0, 1.10), (1.10, 1.40), (1.40, 1.80), (1.80, 2.50), (2.50, 10.0)]
print()
print('%-14s %5s %10s %10s %8s' % ('T 分层', 'n', 'mean ΔECE', 'median', '正值率'))
for lo, hi in bins:
    sub = [r['delta'] for r in recs if lo <= r['T'] < hi]
    if not sub:
        continue
    pos = sum(1 for v in sub if v > 0)
    print('%-14s %5d %+10.4f %+10.4f %7.0f%%'
          % ('[%.2f,%.2f)' % (lo, hi), len(sub), st.mean(sub),
             st.median(sub), 100 * pos / len(sub)))

# 相关性与回归
Ts = [r['T'] for r in recs]
ds = [r['delta'] for r in recs]
n = len(Ts)
mT, md = st.mean(Ts), st.mean(ds)
cov = sum((a - mT) * (b - md) for a, b in zip(Ts, ds)) / n
vT = sum((a - mT) ** 2 for a in Ts) / n
vd = sum((b - md) ** 2 for b in ds) / n
slope = cov / vT
corr = cov / (vT ** 0.5 * vd ** 0.5)
print()
print('整体 mean ΔECE = %+.4f  (median %+.4f)' % (md, st.median(ds)))
print('拟合 T 范围 %.3f - %.3f  中位 %.3f' % (min(Ts), max(Ts), st.median(Ts)))
print('回归 ΔECE ~ T : 斜率 %+.5f  Pearson r = %+.3f' % (slope, corr))
print()
print('--- 判读 ---')
print('噪声底预测：底噪随 T 单调上升（T=1:0, 1.25:0.014~0.035, 1.5:0.030~0.061,')
print('            3.0:0.095~0.136, 4.5:0.126~0.164）')
print('若主发现由噪声底驱动 → 斜率应显著为正且量级≈底噪增速。')
print('实测斜率 %+.5f → %s' % (slope, '与噪声底机理一致(危险)'
      if slope > 0.008 else '与噪声底机理不一致(安全)'))

# 高 T 组是否反而效应更小
hi = [r['delta'] for r in recs if r['T'] >= 2.0]
lo = [r['delta'] for r in recs if r['T'] < 1.4]
print()
print('低T组(<1.4) n=%d mean %+.4f | 高T组(>=2.0) n=%d mean %+.4f'
      % (len(lo), st.mean(lo), len(hi), st.mean(hi)))
