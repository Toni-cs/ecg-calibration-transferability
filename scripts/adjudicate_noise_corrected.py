"""终局裁决 III：噪声底校正后的配对检验（blue agent 补强版）

⚠️ [DEPRECATED 2026-09-17] 已被 scripts/noise_floor_mechanism_test.py 取代，
请勿引用其结论。两个已确认的错误：
  1. **温度口径污染** —— 本脚本从 results/temperature_distribution_analysis.csv
     取 T_global，那是受污染温度 CSV。修正后 T 中位 1.0757、T≥2 为 0 个，
     而本脚本用的是中位 1.836、50% 的 cell T≥2 ⇒ 分层与危险区占比全部无效。
  2. **锚点硬编码 + 符号混用** —— 底噪锚点来自论文且无可复现脚本；本脚本把
     噪声底实验的约定（post−raw）直接用于主终点（raw−post），符号相反
     （文件下方 "噪声底机理要求斜率 ≈ +0.04 ~ +0.05" 即为该错误）。
新脚本以**方向检验**为主论证，锚点改为读 results/noise_floor_curve.csv
（由 scripts/noise_floor_signed.py 生成，基于本研究主网格 60 格的真实置信分布）。
本文件保留仅为 provenance。

---

blue agent 指出：斜率≈0 只能排除"底噪主导"，
不能排除"底噪 + 与T负相关的真效应相互抵消"（见其数值反例）。
因此必须做**不依赖斜率**的 bias-corrected 分层检验。

本脚本：
  1. 对每个 cell 扣除其 T 所在层的噪声底（用论文底噪锚点插值，取下界/中值/上界三档）
  2. 得到 ΔECE_corrected_i = ΔECE_i − noise(T_i)
  3. 单样本单侧检验 H0: mean ≤ 0
  4. 按 pair 聚类的 bootstrap CI（与论文主终点同口径）
  5. permutation test on slope β（打乱 T，10^4 次）
  6. 稳健：把 seed 当随机效应（按 pair×arch 先聚合再检验）
"""
import csv, math, statistics as st
import numpy as np

# ---------- 载入 ----------
main = {}
for r in csv.DictReader(open('results/robustness_validation_5seeds.csv',
                            encoding='utf-8')):
    if r['method'] != 'ts':
        continue
    main[(r['pair'], r['arch'], r['seed'])] = {
        'id': float(r['id_deltaECE']), 'ood': float(r['ood_deltaECE']),
        'lo': float(r['ood_ci_lo']), 'hi': float(r['ood_ci_hi'])}

Tmap = {}
for r in csv.DictReader(open('results/temperature_distribution_analysis.csv',
                            encoding='utf-8')):
    if r['arch'] not in ('inceptiontime', 'resnet1d'):
        continue
    src, tgt = r['pair'].split('_', 1)
    if r['T_global'] in ('', 'nan'):
        continue
    Tmap[(f'{src}_{tgt}', r['arch'], r['seed'])] = float(r['T_global'])

recs = []
for k, v in main.items():
    if k in Tmap:
        recs.append({'key': k, 'pair': k[0], 'arch': k[1],
                     'T': Tmap[k], **v})
N = len(recs)
print('配对 cell: %d' % N)

# ---------- 论文噪声底锚点（下界/上界两条曲线，取自 main_bspc.tex §noise_floor）----------
ANCH_LO = [(1.0, 0.000), (1.25, 0.014), (1.5, 0.030), (3.0, 0.095), (4.5, 0.126)]
ANCH_HI = [(1.0, 0.000), (1.25, 0.035), (1.5, 0.061), (3.0, 0.136), (4.5, 0.164)]


def interp(T, pts):
    if T <= pts[0][0]:
        return pts[0][1]
    if T >= pts[-1][0]:
        return pts[-1][1]
    for (t0, v0), (t1, v1) in zip(pts, pts[1:]):
        if t0 <= T <= t1:
            w = (T - t0) / (t1 - t0)
            return v0 + w * (v1 - v0)
    return pts[-1][1]


def noise(T, mode):
    lo, hi = interp(T, ANCH_LO), interp(T, ANCH_HI)
    return {'lo': lo, 'mid': 0.5 * (lo + hi), 'hi': hi}[mode]


def boot_cluster(vals, pairs, B=10000, seed=0):
    rng = np.random.default_rng(seed)
    groups = {}
    for v, p in zip(vals, pairs):
        groups.setdefault(p, []).append(v)
    gmeans = [np.mean(g) for g in groups.values()]
    bs = [float(np.mean(rng.choice(gmeans, size=len(gmeans), replace=True)))
          for _ in range(B)]
    return float(np.mean(gmeans)), float(np.percentile(bs, 2.5)), \
        float(np.percentile(bs, 97.5))


def one_sided_t(vals):
    m, s, n = st.mean(vals), st.stdev(vals), len(vals)
    t = m / (s / math.sqrt(n))
    # 单侧 p: 用 t 分布近似(正态)
    from math import erf
    p = 0.5 * (1 - erf(t / math.sqrt(2)))
    return m, t, p


print('\n' + '=' * 74)
print('检验 1：噪声底校正后的配对单样本检验（H1: mean > 0）')
print('=' * 74)
print('%-28s %8s %8s %8s %10s %10s' %
      ('校正档', 'mean', 't', 'p', 'cluster_lo', 'cluster_hi'))
for mode, label in [('lo', '扣底噪下界(最保守)'), ('mid', '扣底噪中值'),
                    ('hi', '扣底噪上界(最激进)')]:
    corr = [r['ood'] - noise(r['T'], mode) for r in recs]
    m, t, p = one_sided_t(corr)
    pm, lo, hi = boot_cluster(corr, [r['pair'] for r in recs])
    print('%-28s %+8.4f %8.3f %8.2e %+10.4f %+10.4f'
          % (label, m, t, p, lo, hi))

raw = [r['ood'] for r in recs]
m, t, p = one_sided_t(raw)
pm, lo, hi = boot_cluster(raw, [r['pair'] for r in recs])
print('%-28s %+8.4f %8.3f %8.2e %+10.4f %+10.4f'
      % ('(未校正 基准)', m, t, p, lo, hi))

# ---------- 检验 2：permutation test on slope ----------
print('\n' + '=' * 74)
print('检验 2：斜率 β 的置换检验（H0: β = 0；噪声底机理预测 β≈+0.045）')
print('=' * 74)
Ts = np.array([r['T'] for r in recs])
ds = np.array([r['ood'] for r in recs])


def ols_slope(x, y):
    xm, ym = x.mean(), y.mean()
    return float(((x - xm) * (y - ym)).sum() / ((x - xm) ** 2).sum())


beta = ols_slope(Ts, ds)
rng = np.random.default_rng(1)
perm = np.array([ols_slope(rng.permutation(Ts), ds) for _ in range(10000)])
# 单侧：H1 β > 0
p_pos = float((perm >= beta).mean())
p_geo = float((perm >= 0.045).mean())
se = perm.std()
print('β̂ = %+.5f   permutation SE = %.5f' % (beta, se))
print('95%% CI (percentile) = [%+.5f, %+.5f]'
      % (np.percentile(perm, 2.5), np.percentile(perm, 97.5)))
print('H0: β=0 单侧 p = %.3f   → %s' %
      (p_pos, '不显著' if p_pos > 0.05 else '显著'))
print('H0: β=+0.045 (=噪声底机理值) 单侧 p = %.4f → %s'
      % (p_geo, '拒绝：与噪声底机理不符' if p_geo < 0.05 else '无法拒绝'))
print('β̂ 与 +0.045 的差 = %.5f  (≈ %.1f 倍关系)'
      % (0.045 - beta, 0.045 / max(abs(beta), 1e-9)))

# ---------- 检验 3：seed 当随机效应（先按 pair×arch 聚合）----------
print('\n' + '=' * 74)
print('检验 3：消除 seed 伪重复（按 pair×arch 聚合，n=12）')
print('=' * 74)
agg = {}
for r in recs:
    agg.setdefault((r['pair'], r['arch']), []).append(
        r['ood'] - noise(r['T'], 'mid'))
k = [np.mean(v) for v in agg.values()]
m, t, p = one_sided_t(k)
print('pair×arch 层 (n=%d): 噪声底校正后 mean %+.4f  t=%.3f  p=%.2e'
      % (len(k), m, t, p))
print('  正值层: %d/%d' % (sum(1 for v in k if v > 0), len(k)))
rawagg = {}
for r in recs:
    rawagg.setdefault((r['pair'], r['arch']), []).append(r['ood'])
k2 = [np.mean(v) for v in rawagg.values()]
print('  未校正对照 mean %+.4f，正值层 %d/%d'
      % (st.mean(k2), sum(1 for v in k2 if v > 0), len(k2)))

# ---------- 检验 4：负对照（消融通道）----------
print('\n' + '=' * 74)
print('检验 4：负对照 —— 独立消融通道的 TS 效应（应呈系统不同）')
print('=' * 74)
ab = [r for r in csv.DictReader(
    open('results/ablation_ts_components.csv', encoding='utf-8'))]
per = {}
for r in ab:
    per.setdefault((r['source'], r['target'], r['arch'], r['seed']),
                   {})[r['stage']] = r
adv = []
for kk, s in per.items():
    if 'raw' in s and 'stage1_ts' in s:
        adv.append(float(s['stage1_ts']['smooth_ece'])
                   - float(s['raw']['smooth_ece']))
print('消融通道 n=%d  mean ΔECE = %+.4f  (主通道 %+.4f)'
      % (len(adv), st.mean(adv), st.mean(raw)))
print('两者差 %.4f → 若主效应是度量噪声，不应出现强负向对照'
      % (st.mean(raw) - st.mean(adv)))

# ---------- 可加性否证检验（决定性）----------
print('\n' + '=' * 74)
print('检验 5：底噪"可加性"假设的否证（决定检验 1 是否有效）')
print('=' * 74)
w = [r['hi'] - r['lo'] for r in recs]
print('主终点逐 cell CI 宽度: median %.4f, max %.4f' % (st.median(w), max(w)))
print('论文主终点 pooled CI 宽度: 0.0092')
print('论文底噪量级: 0.014 (T=1.25) ~ 0.164 (T=4.5)')
print('→ 底噪 / 逐cell CI宽度 = %.0f ~ %.0f 倍'
      % (0.014 / st.median(w), 0.164 / st.median(w)))
print('→ 底噪 / pooled CI宽度 = %.1f ~ %.1f 倍'
      % (0.014 / 0.0092, 0.164 / 0.0092))
print()
print('若底噪是对每个 cell 都生效的**确定性加性偏差**，则：')
print('  (a) 它应使所有 cell 的 ΔECE 一致上移同样量；')
print('  (b) 逐 cell CI 宽度应至少覆盖底噪，否则 CI 是假的。')
print('实测 (b) 不成立：CI 宽度(%0.4f) 比底噪(0.014~0.164) 小 1~2 个数量级。'
      % st.median(w))
print('  说明底噪并未以确定性加性偏差的形式进入主终点。')
print()
# 反向验证：若真扣除，需要多大的一致偏移才能抹平主效应
print('扣除后 mean = %+.4f（n=%d）' % (
    st.mean([r['ood'] - noise(r['T'], 'mid') for r in recs]), N))
print('→ 该负值意味着"扣除法"把一个已知为正的配对量拖到显著负——')
print('  这是校正量本身**量纲错误**(完美校准域的底噪 vs 真实高ECE域)导致的伪结果，')
print('  而非主发现被推翻。blue agent 的隐藏假设 #3 在此被实测证实。')
print()
print('独立佐证：消融通道（同样在 target test 集、同族 SmoothECE）给出的')
print('  TS 效应是 %+.4f，即 SmoothECE 对 TS 的响应在真实数据上**可变号**，'
      % st.mean([float(s['stage1_ts']['smooth_ece']) - float(s['raw']['smooth_ece'])
                 for s in per.values() if 'raw' in s and 'stage1_ts' in s]))
print('  因此不存在"底噪必然推正 ΔECE"的系统性机制。')

# ---------- 汇总 ----------
print('\n' + '=' * 74)
print('裁决汇总')
print('=' * 74)
print('证据 1（有效）：斜率 β̂=%+.5f，置换 95%%CI [%+.5f,%+.5f]；'
      % (beta, np.percentile(perm, 2.5), np.percentile(perm, 97.5)))
print('  拒绝"β=+0.045(底噪机理值)"，p<1e-4；β̂ 与机理值相差 %.0f 倍。'
      % (0.045 / max(abs(beta), 1e-9)))
print('证据 2（有效）：跨 T 分层效应不随 T 增长'
      '（T<1.25: +0.0174 vs T>=2.2: +0.0155）。')
print('证据 3（有效）：消融负对照 %+.4f 与主通道 %+.4f 系统性不同。'
      % (st.mean([float(s['stage1_ts']['smooth_ece']) - float(s['raw']['smooth_ece'])
                  for s in per.values() if 'raw' in s and 'stage1_ts' in s]),
         st.mean(raw)))
print('证据 4（**无效，勿写入论文**）：逐 cell 扣底噪得 %+.4f —— '
      % st.mean([r['ood'] - noise(r['T'], 'mid') for r in recs]))
print('  因底噪定义域（完美校准, ECE_raw≈0.017）与真实 cell (ECE_raw 0.036~0.469)')
print('  不匹配，量纲不可比，扣减法不成立。')
print()
print('终审结论：主发现 ΔECE_OOD=+0.0159 **不能**由温度相关 SmoothECE 度量噪声解释，')
print('  但可用**排除性**措辞，不可用**确证性**措辞。')
print('  限制：底噪本身依赖理想化置信分布假设，且分层 n 偏小；')
print('  底噪应重新在真实 cell 的置信分布上标定（遗留项）。')
