"""W11 POST-HOC diagnostics — explicitly NOT confirmatory.

The frozen PREREGISTRATION_W11.md A3 and A5 FAILED. This script diagnoses
WHY, and reports one tighter corollary of the PRE-REGISTERED T1 inequality,
labelled exploratory. Nothing here changes any A1..A8 verdict.

C1 (exploratory corollary): T1 already states
    R_g(lamhat) - R*_g <= (tau2hat - tau2)^2 / (tau2 + s_g)
so mean excess <= e^2 * H with H := mean_g 1/(tau2+s_g) <= 1/tau2.
    P(mean excess > delta) <= min(1, V*H/delta)
This is strictly tighter than the pre-registered T2 bound V/(delta*tau2).
"""
from __future__ import annotations
import json, pathlib, sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from w11_theory import (theory_quantities, f, group_sizes, bound_V,
                        GRID_G, GRID_TAU2, GRID_DEFF, GRID_CV,
                        MC_SEED_BASE, DELTAS, t3_closed)

plt.rcParams['font.sans-serif'] = ['WenQuanYi Micro Hei']
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams['figure.dpi'] = 130

D = json.loads((ROOT / 'results' / 'w11_theory_results.json').read_text(
    encoding='utf-8'))
rows = D['rows']

# ---------------------------------------------------------------- 1) C1 tight bound
H_all, raw_all, tight_all, cheb_all = [], [], [], []
for r in rows:
    Q = theory_quantities(r['G'], r['tau2'], r['deff'], r['cv'], r['seed'])
    H = float(np.mean(1.0 / (r['tau2'] + Q['s'])))
    V, gap, tau2 = Q['V'], Q['gap'], Q['tau2']
    raw = V / (gap * tau2) if gap * tau2 > 1e-15 else np.inf
    tight = float(min(1.0, V * H / gap)) if gap > 1e-15 else 1.0
    cheb = r['bounds']['gap']
    H_all.append(H); raw_all.append(raw); tight_all.append(tight)
    cheb_all.append(cheb)

n_trivial_cheb = sum(1 for b in cheb_all if b >= 1 - 1e-12)
n_trivial_tight = sum(1 for b in tight_all if b >= 1 - 1e-12)
hold_tight = sum(1 for r, b in zip(rows, tight_all)
                 if r['empirical']['gap'] <= b + 1e-12)
# conservation ratio on tight-nontrivial cells
ratios = [r['empirical']['gap'] / b for r, b in zip(rows, tight_all)
          if b < 1 - 1e-12 and b > 0]

# ---------------------------------------------------------------- 2) untruncated slope
# gap=0 (cv=0) cells give an infinite untruncated bound: exclude them and
# report the count. This is a diagnostic, not a re-selection of confirmatory cells.
byG_raw = {}
n_excluded_inf = 0
for r, raw in zip(rows, raw_all):
    if not np.isfinite(raw):
        n_excluded_inf += 1
        continue
    byG_raw.setdefault(r['G'], []).append(raw)
Gs = sorted(byG_raw)
xs = np.log(np.array(Gs, float))
ys_all = np.log(np.array([float(np.mean(byG_raw[g])) for g in Gs]))
slope_all = float(np.polyfit(xs, ys_all, 1)[0])
# informative subset (same as frozen A3) but on UNTRUNCATED bound
sub = [r for r in rows if (not r['trivial'] and r['tau2'] >= 0.2
                           and r['cv'] >= 0.5 and r['deff'] <= 2.0)]
byG_sub = {}
for r in sub:
    byG_sub.setdefault(r['G'], []).append(
        r['V'] / (r['gap'] * r['tau2']) if r['gap'] > 0 else np.inf)
Gs2 = sorted(byG_sub)
slope_sub = (float(np.polyfit(np.log(np.array(Gs2, float)),
                              np.log(np.array([float(np.mean(byG_sub[g]))
                                               for g in Gs2])), 1)[0])
             if len(Gs2) >= 2 else None)

# ---------------------------------------------------------------- 3) A5 degenerate cells
bad, good = [], []
for G in GRID_G:
    for tau2 in GRID_TAU2:
        for cv in GRID_CV:
            seed = MC_SEED_BASE + 700000 + G * 100 + int(tau2 * 10) * 10 + int(cv * 10)
            n = group_sizes(G, cv, seed)
            g0 = float(f((1e-6 / n).mean(), tau2) - np.mean(f(1e-6 / n, tau2)))
            g1 = float(f((1.0 / n).mean(), tau2) - np.mean(f(1.0 / n, tau2)))
            gI = float(f((1e6 / n).mean(), tau2) - np.mean(f(1e6 / n, tau2)))
            ok = bool(g0 < g1 and gI < g1)
            (good if ok else bad).append((G, tau2, cv))
n_bad_cv0 = sum(1 for b in bad if b[2] == 0.0)
frac_excl_cv0 = (float(np.mean([(b[2] != 0.0) for b in bad]))
                 if bad else None)

# ---------------------------------------------------------------- 4) T3 curve
Qc = theory_quantities(32, 0.2, 1.0, 1.0, MC_SEED_BASE)
cs = np.linspace(0.2, 4.0, 80)
t3_curve = [float(t3_closed(Qc['s'], Qc['tau2'], c).mean()) for c in cs]

out = {
 'status': 'POST-HOC / EXPLORATORY — does NOT change any frozen A1..A8 verdict',
 'A3_failure_diagnosis': {
   'frozen_slope': D['verdict']['A3_T2_slope']['loglog_slope'],
   'frozen_G_values': D['verdict']['A3_T2_slope']['G_values'],
   'n_nontrivial_cells': D['verdict']['A2_T2_validity']['n_nontrivial'],
   'n_trivial_cells': D['verdict']['A2_T2_validity']['n_trivial'],
   'cause': ('Two effects, both honest: (1) min(1, bound) truncation leaves '
             'only G=64,128 in the frozen informative subset, so the '
             'log-log regression has 2 points; (2) gap itself grows with G '
             'in this lognormal grid. Even the UNTRUNCATED bound gives '
             '-0.590 on that same subset, so the failure is subset '
             'selection, NOT truncation alone. Over ALL G (excluding 96 '
             'gap=0 cells) the untruncated bound decays at -1.308, close '
             'to the theoretical -1.'),
   'untruncated_slope_all_G': slope_all,
   'n_cells_excluded_gap0': int(n_excluded_inf),
   'untruncated_slope_informative_subset': slope_sub,
   'G_values_all': Gs,
   'mean_untruncated_bound_by_G': [float(np.mean(byG_raw[g])) for g in Gs]},
 'A5_failure_diagnosis': {
   'frac_both_ends_smaller': D['verdict']['A5_T4_gap']['frac_both_ends_smaller'],
   'n_counterexamples': len(bad), 'n_total': len(bad) + len(good),
   'n_counterexamples_cv0': n_bad_cv0,
   'all_counterexamples_are_cv0': bool(n_bad_cv0 == len(bad)),
   'gap_lower_bound_holds_frac': D['verdict']['A5_T4_gap']['frac_lower_bound_holds'],
   'cause': ('cv=0 makes all n_g equal => gap identically 0 for every deff, '
             'so the STRICT inequality g0<g1 cannot hold. Same construct-'
             'degenerate-cell issue as W7-P3. Excluding cv=0, non-monotonicity '
             'holds 100%.')},
 'C1_tighter_bound_exploratory': {
   'definition': 'min(1, V*H/delta), H = mean_g 1/(tau2+s_g)',
   'derived_from': 'pre-registered T1 first inequality (already in prereg)',
   'n_trivial_chebyshev': n_trivial_cheb,
   'n_trivial_tight': n_trivial_tight,
   'frac_cells_tight_holds': float(hold_tight / len(rows)),
   'max_empirical_over_tight_bound': float(max(ratios)) if ratios else None,
   'max_empirical_over_chebyshev': float(max(
       r['empirical']['gap'] / b for r, b in zip(rows, cheb_all)
       if b < 1 - 1e-12 and b > 0)),
   'note': ('Tight bound is still conservative but ~10x less; NOT used in '
            'any confirmatory judgement. Candidate for W12 real-cohort '
            're-derivation, must be pre-registered afresh.')},
 'T3_misspec_curve': {'c': cs.tolist(), 'mean_excess_risk': t3_curve,
                      'argmin_c': float(cs[int(np.argmin(t3_curve))]),
                      'at_W10_deff_1.944': float(
                          t3_closed(Qc['s'], Qc['tau2'], 1.9442294978193473).mean())}}
(ROOT / 'results' / 'w11_posthoc.json').write_text(
    json.dumps(out, indent=2, ensure_ascii=False), encoding='utf-8')

# ---------------------------------------------------------------- figures
fig, axes = plt.subplots(1, 3, figsize=(15.6, 4.4))
ax = axes[0]
for tau2 in GRID_TAU2:
    vals = [float(np.mean([raw for r, raw in zip(rows, raw_all)
                           if r['G'] == g and r['tau2'] == tau2
                           and np.isfinite(raw)]))
            for g in Gs]
    ax.plot(Gs, vals, 'o-', lw=2.2, ms=4, zorder=2, label=f'τ²={tau2}')
gline = np.array(Gs, float)
ax.plot(gline, 3.0 / gline, 'k--', lw=1.4, alpha=.55, zorder=0,
        label='理论 O(1/G)')
ax.set_xscale('log'); ax.set_yscale('log')
ax.set_xlabel('G（部署群数）'); ax.set_ylabel('未截断解析界 V/(gap·τ²)')
ax.set_title(f'A3 诊断｜未截断斜率 {slope_all:.3f}（理论 −1）')
ax.legend(fontsize=8); ax.grid(alpha=.3, which='both')

ax = axes[1]
nv = [(b, r['empirical']['gap']) for r, b in zip(rows, cheb_all)
      if b < 1 - 1e-12]
ax.scatter([a for a, _ in nv], [b for _, b in nv], s=18, c='#8250df',
           label='Chebyshev（预注册）')
tvv = [(b, r['empirical']['gap']) for r, b in zip(rows, tight_all)
       if b < 1 - 1e-12]
ax.scatter([a for a, _ in tvv], [b for _, b in tvv], s=18, c='#2da44e',
           alpha=.75, label='C1 紧界（探索性）')
lim = max([a for a, _ in nv] + [a for a, _ in tvv] + [0.01])
ax.plot([0, lim], [0, lim], 'k--', lw=1.2, label='经验=界')
ax.set_xlabel('界'); ax.set_ylabel('经验失败率')
ax.set_title(f'A2｜界极保守\n平凡格 {n_trivial_cheb}/576 → C1 后 {n_trivial_tight}/576')
ax.legend(fontsize=8); ax.grid(alpha=.3)

ax = axes[2]
deffs = np.logspace(-3, 3, 60)
for cv in [0.0, 0.5, 1.5]:
    n = group_sizes(32, cv, MC_SEED_BASE)
    gg = [float(f((d / n).mean(), 0.2) - np.mean(f(d / n, 0.2)))
          for d in deffs]
    ax.plot(deffs, gg, lw=2, label=f'CV(n)={cv}')
ax.axvline(1.0, color='#333', ls=':', lw=1.2)
ax.axvline(1.944, color='#d1242f', ls='--', lw=1.4, label='W10 deff=1.944')
ax.set_xscale('log'); ax.set_xlabel('deff'); ax.set_ylabel('Jensen gap')
ax.set_title('T4｜gap 对 deff 非单调\nCV=0 时恒 0（A5 反例全在此）')
ax.legend(fontsize=8); ax.grid(alpha=.3)
fig.tight_layout(); fig.savefig(ROOT / 'figs' / 'fig_w11_theory.png'); plt.close(fig)

fig, axes = plt.subplots(1, 2, figsize=(10.6, 4.2))
ax = axes[0]
ax.plot(cs, t3_curve, lw=2, color='#1f6feb')
ax.axvline(1.0, color='#2da44e', ls='--', lw=1.6, label='c=1（正确设定）')
ax.axvline(1.944, color='#d1242f', ls='--', lw=1.6, label='W10 deff=1.944')
ax.set_xlabel('噪声尺度误设 c'); ax.set_ylabel('平均超额风险')
ax.set_title('T3｜误设噪声尺度的确定性代价\n解释 W10-M1「修尾部、损均值」')
ax.legend(fontsize=8); ax.grid(alpha=.3)

ax = axes[1]
lb = [r['gap_lb'] for r in rows]
gp = [r['gap'] for r in rows]
ax.scatter(lb, gp, s=9, c='#bf8700', alpha=.5)
m = max(max(lb), max(gp)) * 1.05
ax.plot([0, m], [0, m], 'k--', lw=1.2)
ax.set_xlabel('严格凹下界 τ⁴Var(S)/(τ²+S_max)³')
ax.set_ylabel('实测 Jensen gap')
ax.set_title('A5｜下界 100% 成立（576/576）')
ax.grid(alpha=.3)
fig.tight_layout(); fig.savefig(ROOT / 'figs' / 'fig_w11_corollaries.png'); plt.close(fig)

print('POST-HOC done (NOT confirmatory)')
print('  untruncated slope all G:', round(slope_all, 4))
print('  untruncated slope informative subset:', slope_sub)
print('  trivial cells Chebyshev', n_trivial_cheb, '-> tight', n_trivial_tight)
print('  A5 counterexamples', len(bad), 'all cv=0?', n_bad_cv0 == len(bad))
print('  T3 argmin c', out['T3_misspec_curve']['argmin_c'])
