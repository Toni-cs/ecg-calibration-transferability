"""W4 EXPLORATORY (NOT CONFIRMATORY) — what actually fixes the harm?

W4 confirmatory found: F4 (no drift, T=1) still gives harm rate 0.715, i.e.
the harm is NOT caused by group drift but by isotonic overfitting a small
dedicated calibration split. The label-free gate therefore fails (pilot AUC
0.510). This script tests three concrete remedies on FRESH seeds 5500-5559.

STATUS: exploratory only. No confirmatory claim. Results are used solely to
motivate a NEW preregistration. Nothing here rescues W4's H1/H4/F4.
"""
from __future__ import annotations
import json, pathlib, sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / 'mamba_experiment'))
from w4_protocol import (init_mamba, augmented_features, make_waveforms_multi,
                         sigmoid, logit, noisy_or, composite_label,
                         isotonic_pava, apply_isotonic, ece_binary,
                         brier_binary, auroc, K)

plt.rcParams['font.sans-serif'] = ['WenQuanYi Micro Hei']
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams['figure.dpi'] = 130

SEEDS = list(range(5500, 5560))     # fresh, disjoint from all confirmatory sets
METHODS = ['PAPER-ISOTONIC', 'SHRINK-0.5', 'BIG-CAL-400', 'GROUP-ISOTONIC']


def run(seed, cal_size=240, spread=0.9):
    rng = np.random.default_rng(seed)
    prm = init_mamba(rng)
    G, fam = 4, np.array([0, 0, 1, 1])
    if spread == 0:
        T_true = np.ones(G)
    else:
        fm = np.array([np.log(2.4), np.log(0.55)]) + rng.uniform(-spread, spread, 2) * .35
        T_true = np.exp(fm[fam] + rng.normal(0, .08, G))
    gp = np.array([.45, .30, .18, .07])

    Xs, ys, ps = make_waveforms_multi(rng, 1200, lvhdominant=True)
    Hs = augmented_features(Xs, prm); hmu, hsd = Hs.mean(0), Hs.std(0) + 1e-6
    proj = rng.normal(0, 1, (Hs.shape[1], K)) / np.sqrt(Hs.shape[1])

    def mk(X, p, Tv):
        H = augmented_features(X, prm)
        return (logit(np.clip(p, .02, .98)) + .45 * ((H - hmu) / hsd) @ proj) * \
               np.asarray(Tv, float)[:, None]

    Xt, yt, pt = make_waveforms_multi(rng, 800, lvhdominant=True)
    gid = rng.choice(G, 800, p=gp)
    zt = mk(Xt, pt, T_true[gid])
    comp = noisy_or(sigmoid(zt)); yc = composite_label(yt)
    demo = rng.integers(0, 2, 800); sub = gid * 2 + demo

    idx = rng.permutation(800)
    cal, test = idx[:cal_size], idx[-400:]
    assert not (set(cal.tolist()) & set(test.tolist()))
    pos = float(yc[test].mean())
    if not (0.05 < pos < 0.95):
        return None

    ux, fy = isotonic_pava(comp[cal], yc[cal])
    iso_t = apply_isotonic(ux, fy, comp[test])

    out = {}
    # --- 1. paper: global isotonic ---
    out['PAPER-ISOTONIC'] = (iso_t, comp[test])

    # --- 2. shrink toward identity (do-not-recalibrate) ---
    out['SHRINK-0.5'] = (0.5 * iso_t + 0.5 * comp[test], comp[test])

    # --- 3. per-group isotonic (group-stratified calibration split) ---
    gi_t = np.empty_like(comp[test])
    for g in range(G):
        mg_cal, mg_test = gid[cal] == g, gid[test] == g
        if mg_cal.sum() >= 8 and mg_test.any():
            u, f = isotonic_pava(comp[cal][mg_cal], yc[cal][mg_cal])
            gi_t[mg_test] = apply_isotonic(u, f, comp[test][mg_test])
        elif mg_test.any():
            gi_t[mg_test] = iso_t[mg_test]
    out['GROUP-ISOTONIC'] = (gi_t, comp[test])

    # --- 4. bigger calibration split (re-fit with 400) ---
    cal2 = idx[:400]
    u2, f2 = isotonic_pava(comp[cal2], yc[cal2])
    out['BIG-CAL-400'] = (apply_isotonic(u2, f2, comp[test]), comp[test])

    res = {}
    for m, (p_iso, p_src) in out.items():
        harm, ds, ws = [], [], []
        for s in np.unique(sub[test]):
            mask = sub[test] == s
            if mask.sum() < 5:
                continue
            d = brier_binary(p_iso[mask], yc[test][mask]) - \
                brier_binary(p_src[mask], yc[test][mask])
            harm.append(int(d > 0)); ds.append(float(d)); ws.append(int(mask.sum()))
        res[m] = {'harm_rate': float(np.mean(harm)),
                  'mean_dBrier': float(np.average(ds, weights=ws)),
                  'ECE': float(ece_binary(p_iso, yc[test])),
                  'Brier': float(brier_binary(p_iso, yc[test])),
                  'n_subgroups': len(harm)}
    res['_pos'] = pos
    res['_AUROC'] = float(auroc(comp[test], yc[test]))
    return res


print('[EXPLORATORY] 60 fresh seeds 5500-5559, NOT confirmatory ...', flush=True)
rows = [r for s in SEEDS if (r := run(s)) is not None]
print('valid seeds:', len(rows), flush=True)
summary = {}
for m in METHODS:
    h = np.array([r[m]['harm_rate'] for r in rows])
    d = np.array([r[m]['mean_dBrier'] for r in rows])
    e = np.array([r[m]['ECE'] for r in rows])
    b = np.array([r[m]['Brier'] for r in rows])
    summary[m] = {'harm_rate_mean': float(h.mean()), 'harm_rate_sd': float(h.std(ddof=1)),
                  'mean_dBrier': float(d.mean()), 'ECE_mean': float(e.mean()),
                  'Brier_mean': float(b.mean()),
                  'harm_rate_per_seed': h.tolist()}
    print(f'  {m:16s} harm={h.mean():.3f}±{h.std(ddof=1):.3f}  '
          f'dBrier={d.mean():+.4f}  ECE={e.mean():.4f}  Brier={b.mean():.4f}', flush=True)

base = summary['PAPER-ISOTONIC']['harm_rate_mean']
print('\nrelative harm reduction vs paper isotonic:', flush=True)
for m in METHODS[1:]:
    red = (base - summary[m]['harm_rate_mean']) / max(base, 1e-9)
    print(f'  {m:16s} {red*100:+.1f}%', flush=True)

# paired bootstrap on harm-rate difference (unit = seed)
def paired_ci(a, b, B=10000, seed=771106):
    rng = np.random.default_rng(seed)
    a, b = np.asarray(a), np.asarray(b)
    dr = np.array([(a - b)[rng.integers(0, len(a), len(a))].mean() for _ in range(B)])
    return [float(np.percentile(dr, 2.5)), float(np.percentile(dr, 97.5))]

ci = {m: paired_ci(summary['PAPER-ISOTONIC']['harm_rate_per_seed'],
                   summary[m]['harm_rate_per_seed']) for m in METHODS[1:]}
print('\npaired CI (paper - remedy) on harm rate:', flush=True)
for m, c in ci.items():
    print(f'  {m:16s} [{c[0]:.4f}, {c[1]:.4f}]  '
          f'excludes zero = {c[0] > 0 or c[1] < 0}', flush=True)

out = {'status': 'EXPLORATORY / NOT CONFIRMATORY / NOT USED TO RESCUE W4',
       'seeds': [SEEDS[0], SEEDS[-1], len(rows)],
       'motivation': ('W4 F4 showed harm rate 0.715 even with NO drift (T=1), '
                      'so harm comes from isotonic overfitting a small dedicated '
                      'calibration split, not from group drift. The label-free '
                      'gate failed (pilot AUC 0.510). We test split-size / '
                      'shrinkage / stratification remedies.'),
       'summary': summary, 'paired_CI_paper_minus_remedy': ci,
       'interpretation': 'For a NEW preregistration only; no v1.1 of W4 exists.',
       'W4_confirmatory_verdict_retained': {'H1': False, 'H2': True,
                                            'H3': True, 'H4': False, 'F4': False}}
(HERE / 'w4_exploratory_results.json').write_text(
    json.dumps(out, indent=2, ensure_ascii=False), encoding='utf-8')

fig, ax = plt.subplots(figsize=(8.2, 4.3))
names = ['论文\nisotonic', '向源域\n收缩 0.5', 'cal split\n400', '按群分层\nisotonic']
vals = [summary[m]['harm_rate_mean'] for m in METHODS]
errs = [summary[m]['harm_rate_sd'] / np.sqrt(len(rows)) for m in METHODS]
b = ax.bar(range(4), vals, yerr=errs, capsize=4,
           color=['#d1242f', '#bf8700', '#1f6feb', '#2da44e'], alpha=.9)
ax.bar_label(b, fmt='%.3f', fontsize=10, padding=3)
ax.set_xticks(range(4)); ax.set_xticklabels(names, fontsize=9)
ax.set_ylabel('校准危害率'); ax.set_title('探索性｜三种补救对危害率的影响（60 个全新种子）')
ax.grid(alpha=.3, axis='y')
fig.tight_layout(); fig.savefig(HERE / 'fig_w4_remedies.png'); plt.close(fig)
print('DONE (exploratory)', flush=True)
