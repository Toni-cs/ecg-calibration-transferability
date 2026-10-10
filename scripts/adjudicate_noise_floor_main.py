"""终局裁决 II：把噪声底与【主结果】对齐（不是消融文件）

数据来源：
  results/robustness_validation_5seeds.csv  → 主结果 ΔECE (method=ts)
  results/temperature_distribution_analysis.csv → 该 cell 的拟合 T_global

质疑（Con agent）：主效应 +0.0159 小于 T≥2 时的噪声底(0.095~0.164)，
                  因此主发现可能是 SmoothECE 度量噪声。
本检验：
  A. 主结果 cells 的 T 分布 → 多少比例落在"噪声底>效应"的危险区
  B. 逐 cell 回归 ΔECE_OOD ~ T → 若斜率为正，则与噪声底机理同向(危险)
  C. 分层：低T区(底噪小)的 ΔECE vs 高T区(底噪大)的 ΔECE
     若高T区效应不显著更大 → 主发现不是噪声底造成的
"""
import csv, statistics as st

main = {}
for r in csv.DictReader(open('results/robustness_validation_5seeds.csv',
                            encoding='utf-8')):
    if r['method'] != 'ts':
        continue
    key = (r['pair'], r['arch'], r['seed'])
    main[key] = {'id': float(r['id_deltaECE']),
                 'ood': float(r['ood_deltaECE']),
                 'decay': float(r['decay'])}

Tmap = {}
for r in csv.DictReader(open('results/temperature_distribution_analysis.csv',
                            encoding='utf-8')):
    if r['arch'] not in ('inceptiontime', 'resnet1d'):
        continue
    pair = r['pair']            # 形如 ptbxl_chapman
    src, tgt = pair.split('_', 1)
    key = (f'{src}_{tgt}', r['arch'], r['seed'])
    if r['T_global'] in ('', 'nan'):
        continue
    Tmap[key] = float(r['T_global'])

recs = []
for k, v in main.items():
    if k in Tmap:
        recs.append({'key': k, 'T': Tmap[k], **v})
print('配对成功 cell 数: %d (主结果 TS=%d, 温度表=%d)' % (len(recs), len(main), len(Tmap)))

# ---- A. T 分布 vs 噪声底危险区 ----
# 论文底噪: T=1.0→0; 1.25→0.014-0.035; 1.5→0.030-0.061; 3.0→0.095-0.136; 4.5→0.126-0.164
def floor_lo(T):
    pts = [(1.0, 0.0), (1.25, 0.014), (1.5, 0.030), (3.0, 0.095), (4.5, 0.126)]
    return _interp(T, pts)

def floor_hi(T):
    pts = [(1.0, 0.0), (1.25, 0.035), (1.5, 0.061), (3.0, 0.136), (4.5, 0.164)]
    return _interp(T, pts)

def _interp(T, pts):
    if T <= pts[0][0]:
        return pts[0][1]
    if T >= pts[-1][0]:
        return pts[-1][1]
    for (t0, v0), (t1, v1) in zip(pts, pts[1:]):
        if t0 <= T <= t1:
            w = (T - t0) / (t1 - t0)
            return v0 + w * (v1 - v0)
    return pts[-1][1]

EFFECT = st.mean([r['ood'] for r in recs])
print('\n主效应 mean ΔECE_OOD = %+.4f\n' % EFFECT)

print('=== A. 危险区占比（底噪上界 >= 主效应 即为危险）===')
danger = [r for r in recs if floor_hi(r['T']) >= EFFECT]
safe = [r for r in recs if floor_hi(r['T']) < EFFECT]
print('  危险区 (floor_hi >= %.4f): %d/%d = %.0f%%'
      % (EFFECT, len(danger), len(recs), 100 * len(danger) / len(recs)))
print('  安全区 (floor_hi <  %.4f): %d/%d = %.0f%%'
      % (EFFECT, len(safe), len(recs), 100 * len(safe) / len(recs)))
# 用下界更严格
danger2 = [r for r in recs if floor_lo(r['T']) >= EFFECT]
print('  严格危险区 (floor_lo >= 效应): %d/%d = %.0f%%'
      % (len(danger2), len(recs), 100 * len(danger2) / len(recs)))

# ---- B. 回归 ----
Ts = [r['T'] for r in recs]
ds = [r['ood'] for r in recs]
di = [r['id'] for r in recs]
n = len(Ts)
mT, md = st.mean(Ts), st.mean(ds)
cov = sum((a - mT) * (b - md) for a, b in zip(Ts, ds)) / n
vT = sum((a - mT) ** 2 for a in Ts) / n
vd = sum((b - md) ** 2 for b in ds) / n
slope = cov / vT
corr = cov / (vT ** 0.5 * vd ** 0.5)
print('\n=== B. 逐 cell 回归 ΔECE_OOD ~ T ===')
print('  斜率 %+.5f   Pearson r = %+.3f' % (slope, corr))
print('  噪声底机理要求斜率 ≈ +0.04 ~ +0.05/单位T (0.014->0.164 over 1.25->4.5)')
print('  实测斜率 %+.5f -> %s' % (
    slope, '同向(需警惕)' if slope > 0.01 else '反向或不显著(主发现非底噪所致)'))

# ID 对照
cov_i = sum((a - mT) * (b - st.mean(di)) for a, b in zip(Ts, di)) / n
print('  ID 对照斜率 %+.5f' % (cov_i / vT))

# ---- C. 分层 ----
print('\n=== C. 按 T 分层（噪声底大小）===')
bins = [(0, 1.25), (1.25, 1.6), (1.6, 2.2), (2.2, 10)]
for lo, hi in bins:
    sub = [r for r in recs if lo <= r['T'] < hi]
    if not sub:
        continue
    d = [r['ood'] for r in sub]
    dl = [r['id'] for r in sub]
    fl = st.mean([floor_lo(r['T']) for r in sub])
    fh = st.mean([floor_hi(r['T']) for r in sub])
    print('  T∈[%.2f,%.2f) n=%2d | ΔECE_OOD %+.4f (正值%2d/%2d) | ΔECE_ID %+.4f | 底噪 %.3f-%.3f'
          % (lo, hi, len(sub), st.mean(d), sum(1 for v in d if v > 0), len(d),
             st.mean(dl), fl, fh))

print('\n--- 判读 ---')
lo_sub = [r['ood'] for r in recs if r['T'] < 1.25]
hi_sub = [r['ood'] for r in recs if r['T'] >= 2.2]
print('低T区(T<1.25, 底噪<=0.035) ΔECE_OOD = %+.4f  n=%d' % (st.mean(lo_sub), len(lo_sub)))
print('高T区(T>=2.2, 底噪>=0.06)  ΔECE_OOD = %+.4f  n=%d' % (st.mean(hi_sub), len(hi_sub)))
print('若高T区显著更大 → 疑似底噪污染；若相当或更小 → 主发现真实')
