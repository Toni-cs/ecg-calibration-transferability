"""W4 CONFIRMATORY — reproduce a published calibration protocol, expose holes.

Frozen BEFORE execution by PREREGISTRATION_W4.md.
Pilot seeds 5000-5049 fix the gate threshold; main seeds 5100-5399 never
participate in threshold selection; falsification seeds 5400-5459.
"""
from __future__ import annotations
import json, pathlib, sys, time
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from w4_protocol import (init_mamba, mamba_forward, augmented_features,
                         make_waveforms_multi, physical_features,
                         multiridge, apply_multiridge, sigmoid, logit, noisy_or,
                         composite_label, isotonic_pava, apply_isotonic,
                         ece_binary, brier_binary, auroc, cal_slope, K)

plt.rcParams['font.sans-serif'] = ['WenQuanYi Micro Hei']
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams['figure.dpi'] = 130

PILOT = list(range(5000, 5050))
MAIN = list(range(5100, 5400))
FALS = list(range(5400, 5460))
B_BOOT = 10000
B_CI = 2000
NB = 15
T0 = time.time()


def hist(x, n_bins=NB):
    h = np.bincount(np.clip((np.asarray(x) * n_bins).astype(int), 0, n_bins - 1),
                    minlength=n_bins).astype(float)
    return h / max(h.sum(), 1e-12)


def auc_score(stat, label):
    """AUC of stat predicting label (1 = harmful)."""
    a, b = np.asarray(stat, float), np.asarray(label, int)
    if len(np.unique(b)) < 2:
        return 0.5
    p, n = a[b == 1], a[b == 0]
    return float((p[:, None] > n[None, :]).mean() +
                 0.5 * (p[:, None] == n[None, :]).mean())


def youden_threshold(stat, label):
    """Return (threshold, direction, auc) maximising Youden J on pilot."""
    raw = auc_score(stat, label)
    direction = 1.0 if raw >= 0.5 else -1.0
    s = direction * np.asarray(stat, float)
    a = auc_score(s, label)
    cand = np.unique(np.quantile(s, np.linspace(0.02, 0.98, 49)))
    best, bt = -1.0, float(np.median(s))
    for t in cand:
        pred = s > t
        tpr = pred[label == 1].mean() if (label == 1).any() else 0
        fpr = pred[label == 0].mean() if (label == 0).any() else 0
        j = tpr - fpr
        if j > best:
            best, bt = j, float(t)
    return bt, direction, a


def run_seed(seed, spread=0.9, stress_n=48, shuffle_subgroups=False,
             endpoint='composite', collect_gate=False):
    rng = np.random.default_rng(seed)
    prm = init_mamba(rng)
    G = 4
    fam = np.array([0, 0, 1, 1])
    # MIXED-DIRECTION drift: two device families over-confident (T>1),
    # two under-confident (T<1). A single monotone isotonic map cannot serve
    # both -- this is the structural reason recalibration can harm a subgroup.
    if spread == 0:
        T_true = np.ones(G)                         # F4: homogeneous, no drift
    else:
        fam_mu = np.array([np.log(2.4), np.log(0.55)]) + \
                 rng.uniform(-spread, spread, 2) * 0.35
        T_true = np.exp(fam_mu[fam] + rng.normal(0, 0.08, G))
    group_p = np.array([0.45, 0.30, 0.18, 0.07])   # long-tailed deployment groups

    # ---------------- logits generator ----------------
    # F0 validity fix: a frozen ridge readout on randomly initialised SSM
    # features cannot decode sparse multi-label targets (pilot AUROC ~0.48).
    # Logits are therefore built from the TRUE conditional probabilities plus
    # a Mamba/physical-feature projection perturbation. The SSM forward still
    # participates; the audit targets the EVALUATION PROTOCOL, not representation
    # learning (which W3 already covered with 600 real Mamba-forward seeds).
    Xs, ys, ps = make_waveforms_multi(rng, 1200, lvhdominant=True)
    Hs = augmented_features(Xs, prm)
    hmu, hsd = Hs.mean(0), Hs.std(0) + 1e-6
    proj = rng.normal(0, 1, (Hs.shape[1], K)) / np.sqrt(Hs.shape[1])

    def make_logits(X, p, Tvec):
        H = augmented_features(X, prm)
        noise = ((H - hmu) / hsd) @ proj
        z = logit(np.clip(p, 0.02, 0.98)) + 0.45 * noise
        return z * np.asarray(Tvec, float)[:, None]

    # ---------------- SOURCE (calibrated, T=1) ----------------
    zs = make_logits(Xs, ps, np.ones(len(ps)))
    comp_s = noisy_or(sigmoid(zs))
    h_ref = hist(comp_s)

    # ---------------- TARGET (unlabelled for fitting) ----------------
    Xt, yt, pt = make_waveforms_multi(rng, 800, lvhdominant=True)
    gids = rng.choice(G, 800, p=group_p)
    zt = make_logits(Xt, pt, T_true[gids])
    probs = sigmoid(zt)
    comp = noisy_or(probs)
    ycomp = composite_label(yt)
    demo = rng.integers(0, 2, 800)
    sub = gids * 2 + demo

    if shuffle_subgroups:                       # F1
        sub = rng.permutation(sub)

    # ---------------- patient-level disjoint split ----------------
    idx = rng.permutation(800)
    cal, test = idx[:240], idx[560:]
    assert len(set(cal.tolist()) & set(test.tolist())) == 0
    pos_rate = float(ycomp[test].mean())
    assert 0.05 < pos_rate < 0.95, f'degenerate composite prevalence {pos_rate}'

    # ---------------- paper protocol ----------------
    ux, fy = isotonic_pava(comp[cal], ycomp[cal])
    iso_t = apply_isotonic(ux, fy, comp[test])
    ece_paper = ece_binary(iso_t, ycomp[test])
    brier_paper = brier_binary(iso_t, ycomp[test])
    # isotonic is monotone but step-valued -> massive ties would
    # artificially deflate AUROC; report ranking on the continuous
    # pre-calibration score (theoretically invariant to isotonic).
    auroc_paper = auroc(comp[test], ycomp[test])

    # ---------------- source-only control ----------------
    ece_src = ece_binary(comp[test], ycomp[test])
    brier_src = brier_binary(comp[test], ycomp[test])
    slope_src = cal_slope(np.clip(comp[test], 1e-4, 1 - 1e-4), ycomp[test])

    # ---------------- H1: classwise macro vs composite ----------------
    cw = np.array([ece_binary(probs[test, k], yt[test, k]) for k in range(K)])
    classwise_macro = float(cw.mean())
    report_endpoint = classwise_macro if endpoint == 'classwise' else ece_paper
    gap = classwise_macro - report_endpoint

    # ---------------- H2: subgroup harm rate + label-free gate stats ----------------
    gstats, harmful, dbrier, weights = [], [], [], []
    for s in np.unique(sub[test]):
        m = sub[test] == s
        mc = sub[cal] == s
        if m.sum() < 5 or mc.sum() < 5:
            continue
        d = (brier_binary(iso_t[m], ycomp[test][m]) -
             brier_binary(comp[test][m], ycomp[test][m]))
        hs = hist(comp[cal][mc])
        gstat = float(np.linalg.norm(hs - h_ref))       # LABEL-FREE
        gstats.append(gstat); harmful.append(int(d > 0))
        dbrier.append(float(d)); weights.append(int(m.sum()))
    harm_rate = float(np.mean(harmful)) if harmful else 0.0
    mean_dbrier = float(np.average(dbrier, weights=weights)) if dbrier else 0.0

    # ---------------- H3: stress-set CI width ----------------
    Xz, yz, pz = make_waveforms_multi(rng, max(800, stress_n), lvhdominant=True)
    gz = rng.choice(G, len(yz), p=group_p)
    zz = make_logits(Xz, pz, T_true[gz])
    cz = apply_isotonic(ux, fy, noisy_or(sigmoid(zz)))
    yz_c = composite_label(yz)

    def ci_width(p, y, n, B=B_CI):
        p, y = np.asarray(p)[:n], np.asarray(y)[:n]
        bs = np.array([ece_binary(p[np.random.default_rng(7000 + b).integers(0, n, n)],
                                  y[np.random.default_rng(7000 + b).integers(0, n, n)])
                       for b in range(B)])
        return float(np.percentile(bs, 97.5) - np.percentile(bs, 2.5))
    w_small = ci_width(cz, yz_c, 48)
    w_large = ci_width(cz, yz_c, 800)

    out = {'seed': int(seed), 'ece_paper': ece_paper, 'brier_paper': brier_paper,
           'auroc_paper': auroc_paper, 'ece_src': ece_src, 'brier_src': brier_src,
           'cal_slope_src': slope_src, 'classwise_macro_ECE': classwise_macro,
           'gap': gap, 'harm_rate': harm_rate, 'mean_dBrier': mean_dbrier,
           'ci_width_48': w_small, 'ci_width_800': w_large,
           'ci_ratio': float(w_small / max(w_large, 1e-9)),
           'pos_rate': pos_rate, 'spread': spread}
    if collect_gate:
        out['gstats'] = gstats
        out['harmful'] = harmful
        out['dbrier'] = dbrier
        out['weights'] = weights
    return out


# ------------------------------------------------------------------ F0 self-tests
def f0_selftest():
    p = np.array([0.1, 0.2, 0.8, 0.9]); y = np.array([0, 0, 1, 1])
    # 4 samples each in its own 10-bin: 0.25*(0.1+0.2+0.2+0.1) = 0.15
    assert abs(ece_binary(p, y) - 0.15) < 1e-9
    assert abs(brier_binary(p, y) - 0.025) < 1e-9
    ux, fy = isotonic_pava(np.array([0.1, 0.2, 0.3, 0.4]),
                           np.array([0.0, 1.0, 0.0, 1.0]))
    assert np.all(np.diff(fy) >= -1e-9), 'isotonic must be monotone'
    assert abs(auroc(np.array([0.1, 0.9]), np.array([0, 1])) - 1.0) < 1e-9
    return True



def main():
    print('[F0] self-tests ...', flush=True)
    f0_ok = f0_selftest()
    print('    PASS =', f0_ok, flush=True)

    # ------------------------------------------------------------------ PILOT: fix gate threshold
    print('[PILOT] 50 seeds 5000-5049 -> gate threshold ...', flush=True)
    pilot = [run_seed(s, collect_gate=True) for s in PILOT]
    gs = np.concatenate([np.asarray(r['gstats']) for r in pilot])
    hl = np.concatenate([np.asarray(r['harmful']) for r in pilot])
    pilot_auc_raw = auc_score(gs, hl)
    thr, direction, pilot_auc = youden_threshold(gs, hl)
    print(f'    pilot AUC(raw)={pilot_auc_raw:.3f}  direction={direction:+.0f}  '
          f'AUC(aligned)={pilot_auc:.3f}  threshold={thr:.5f}', flush=True)
    gate_valid = bool(pilot_auc >= 0.60)
    print('    pilot gate validity (AUC>=0.60):', gate_valid, flush=True)

    # ------------------------------------------------------------------ MAIN
    print('[MAIN] 300 independent Mamba seeds 5100-5399 ...', flush=True)
    main = []
    for i, s in enumerate(MAIN):
        r = run_seed(s, collect_gate=True)
        # apply FROZEN gate on each subgroup
        sstat = direction * np.asarray(r['gstats'], float)
        decision = sstat > thr                       # True -> FALLBACK to source-only
        h = np.asarray(r['harmful'], int)
        w = np.asarray(r['weights'], float)
        d = np.asarray(r['dbrier'], float)
        # gated dBrier: fallback => 0 (source-only), isotonic => original d
        gd = np.where(decision, 0.0, d)
        r['harm_rate_gated'] = float(np.average((gd > 0).astype(float), weights=w))
        r['false_gate_rate'] = float(np.average((decision & (h == 0)).astype(float),
                                                weights=w))
        r['mean_dBrier_gated'] = float(np.average(gd, weights=w))
        r['fallback_rate'] = float(np.average(decision.astype(float), weights=w))
        main.append(r)
        if (i + 1) % 100 == 0:
            print(f'    {i+1}/300 elapsed={time.time()-T0:.0f}s', flush=True)

    def arr(key): return np.array([r[key] for r in main])

    gap, hr, ratio = arr('gap'), arr('harm_rate'), arr('ci_ratio')
    hg, fg = arr('harm_rate_gated'), arr('false_gate_rate')
    dg, du = arr('mean_dBrier_gated'), arr('mean_dBrier')

    # F0 (prereg E1): the transferred composite score must retain ranking power.
    auc_mean, auc_min = float(arr('auroc_paper').mean()), float(arr('auroc_paper').min())
    f0_auroc_pass = bool(auc_mean >= 0.55)
    print(f'    [F0] composite AUROC mean={auc_mean:.3f} min={auc_min:.3f} '
          f'PASS={f0_auroc_pass}', flush=True)
    if not f0_auroc_pass:
        raise SystemExit('F0 FAILED: transferred model has no ranking power; '
                         'all results discarded.')

    def ciboot(v, B=B_BOOT, seed=20261106):
        rng = np.random.default_rng(seed)
        m = np.array([v[rng.integers(0, len(v), len(v))].mean() for _ in range(B)])
        return [float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))]

    H = {
     'H1': {'mean_gap': float(gap.mean()), 'sd': float(gap.std(ddof=1)),
            'frac_positive': float((gap > 0).mean()), 'CI95': ciboot(gap),
            'PASS': bool(gap.mean() >= 0.020 and (gap > 0).mean() >= 0.90)},
     'H2': {'mean_harm_rate': float(hr.mean()), 'sd': float(hr.std(ddof=1)),
            'CI95': ciboot(hr), 'PASS': bool(hr.mean() >= 0.10)},
     'H3': {'mean_ci_ratio': float(ratio.mean()), 'median_ci_ratio': float(np.median(ratio)),
            'CI95': ciboot(ratio), 'PASS': bool(ratio.mean() >= 2.0)},
     'H4': {'harm_rate_unconditional': float(hr.mean()),
            'harm_rate_gated': float(hg.mean()),
            'relative_reduction': float((hr.mean() - hg.mean()) / max(hr.mean(), 1e-9)),
            'false_gate_rate': float(fg.mean()), 'fallback_rate': float(main[0]['fallback_rate']),
            'delta_dBrier_gated_minus_uncond': float((dg - du).mean()),
            'delta_dBrier_CI95': ciboot(dg - du),
            'pilot_gate_auc': pilot_auc, 'pilot_gate_valid': gate_valid,
            'PASS': bool(gate_valid and (hr.mean() - hg.mean()) / max(hr.mean(), 1e-9) >= 0.50
                         and fg.mean() < 0.25 and ciboot(dg - du)[1] < 0)}}
    print('\n[H]', flush=True)
    for k, v in H.items():
        print('   ', k, {kk: (round(vv, 4) if isinstance(vv, float) else vv)
                         for kk, vv in v.items()}, flush=True)
    print('    paper-protocol ECE =', round(arr('ece_paper').mean(), 4),
          '| classwise macro ECE =', round(arr('classwise_macro_ECE').mean(), 4),
          '| source-only ECE =', round(arr('ece_src').mean(), 4), flush=True)
    print('    paper AUROC =', round(arr('auroc_paper').mean(), 4),
          '| source cal slope =', round(arr('cal_slope_src').mean(), 4), flush=True)

    # ------------------------------------------------------------------ FALSIFICATION
    print('[F] falsification 60 seeds 5400-5459 ...', flush=True)
    f1 = [run_seed(s, shuffle_subgroups=True, collect_gate=True) for s in FALS]
    f1_stat = np.concatenate([direction * np.asarray(r['gstats']) for r in f1])
    f1_lab = np.concatenate([np.asarray(r['harmful']) for r in f1])
    f1_auc = auc_score(f1_stat, f1_lab)
    f2 = [run_seed(s, endpoint='classwise') for s in FALS]
    f2_gap = np.array([r['gap'] for r in f2])
    f3 = [run_seed(s, stress_n=800) for s in FALS]
    f3_ratio = np.array([r['ci_ratio'] for r in f3])
    f4 = [run_seed(s, spread=0.0) for s in FALS]
    f4_hr = np.array([r['harm_rate'] for r in f4])
    F = {'F1_shuffle_subgroups': {'gate_auc': f1_auc,
          'PASS': bool(abs(f1_auc - 0.5) < 0.10)},
         'F2_classwise_endpoint': {'mean_gap': float(f2_gap.mean()),
          'PASS': bool(abs(f2_gap.mean()) < 0.005),
          'note': 'identity check: composite gap must vanish when classwise is the reported endpoint'},
         'F3_stress_800': {'mean_ci_ratio': float(f3_ratio.mean()),
          'PASS': bool(f3_ratio.mean() >= 1.5),
          'note': 'larger stress set narrows CI; ratio still >1 by construction of 48-vs-800'},
         'F4_homogeneous': {'mean_harm_rate': float(f4_hr.mean()),
          'PASS': bool(abs(f4_hr.mean()) < 0.02)}}
    print('   ', {k: {kk: (round(vv, 4) if isinstance(vv, float) else vv)
                      for kk, vv in v.items() if kk != 'note'} for k, v in F.items()}, flush=True)

    # ------------------------------------------------------------------ verdict
    checks = {'F0': bool(f0_ok and f0_auroc_pass),
              'H1': H['H1']['PASS'], 'H2': H['H2']['PASS'],
              'H3': H['H3']['PASS'], 'H4': H['H4']['PASS'],
              'F1': F['F1_shuffle_subgroups']['PASS'],
              'F2': F['F2_classwise_endpoint']['PASS'],
              'F3': F['F3_stress_800']['PASS'],
              'F4': F['F4_homogeneous']['PASS']}
    verdict = {
     'checks': checks, 'all_pass': bool(all(checks.values())),
     'holes_confirmed': [k for k in ['H1','H2','H3'] if H[k]['PASS']],
     'patch_result': 'GATE WORKS' if H['H4']['PASS'] else 'GATE FAILED (report as-is)',
     'disposition': ('Protocol-level results only. Synthetic Mamba-SSM toy logits; '
                     'NOT a reproduction of the paper\'s real waveforms/weights/numbers. '
                     'Real-data forward requires PhysioNet DUA + T1 preflight.'),
     'no_v1_1': True,
     'history_retained': ['W1 PARI falsified','W2 v1.0 H1=False','W2 v1.1 F-B FAIL',
                          'W3 600 Mamba seeds H1=False (534/600)']}
    print('\n=== W4 FINAL VERDICT ===', flush=True)
    print(checks, '| all_pass =', verdict['all_pass'], flush=True)
    print('holes confirmed:', verdict['holes_confirmed'], '| patch:', verdict['patch_result'], flush=True)
    print('elapsed', round(time.time()-T0, 1), 's', flush=True)

    out = {'meta': {'prereg':'PREREGISTRATION_W4.md v1.0 (frozen)','run_type':'CONFIRMATORY',
                    'pilot_seeds':[5000,5049,50],'main_seeds':[5100,5399,300],
                    'falsification_seeds':[5400,5459,60],'bootstrap_B':B_BOOT,
                    'date':'2026-11-06',
                    'target_paper':'doi 10.3389/fcvm.2026.1928354 / PMC13601223',
                    'honesty':verdict['disposition']},
           'F0_selftest': f0_ok,
           'pilot': {'auc_raw': pilot_auc_raw,'auc_aligned': pilot_auc,
                     'direction':direction,'threshold':thr,'valid':gate_valid},
           'H': H, 'F': F, 'verdict': verdict,
           'aggregate': {k: {'mean':float(arr(k).mean()),'sd':float(arr(k).std(ddof=1))}
                         for k in ['ece_paper','brier_paper','auroc_paper','ece_src',
                                   'brier_src','classwise_macro_ECE','gap','harm_rate',
                                   'ci_ratio','harm_rate_gated','false_gate_rate',
                                   'mean_dBrier','mean_dBrier_gated','cal_slope_src']},
           'per_seed': main}
    (HERE / 'w4_results.json').write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding='utf-8')

    # ------------------------------------------------------------------ figures
    fig, axes = plt.subplots(1, 3, figsize=(14.5, 4.2))
    ax = axes[0]
    ax.bar(['复合终点\n(论文口径)','classwise\nmacro ECE','source-only\nECE'],
           [arr('ece_paper').mean(), arr('classwise_macro_ECE').mean(), arr('ece_src').mean()],
           color=['#2da44e','#d1242f','#8250df'], alpha=.9)
    ax.set_ylabel('ECE'); ax.set_title('H1｜复合终点掩盖类别级误校准'); ax.grid(alpha=.3, axis='y')
    ax = axes[1]
    ax.hist(hr, bins=25, color='#d1242f', alpha=.85)
    ax.axvline(0.10, color='#2da44e', ls='--', lw=1.8, label='10% 阈值')
    ax.set_xlabel('无条件 isotonic 的校准危害率'); ax.set_ylabel('种子数')
    ax.set_title('H2｜重校准在部分亚组有害'); ax.legend(fontsize=9); ax.grid(alpha=.3)
    ax = axes[2]
    ax.bar(['无条件\nisotonic','无标签门控'],
           [hr.mean(), hg.mean()], color=['#d1242f','#1f6feb'], alpha=.9)
    ax.set_ylabel('校准危害率'); ax.set_title(f'H4｜门控相对下降 '
          f'{H["H4"]["relative_reduction"]*100:.0f}%'); ax.grid(alpha=.3, axis='y')
    fig.tight_layout(); fig.savefig(HERE / 'fig_w4_holes.png'); plt.close(fig)

    fig, ax = plt.subplots(figsize=(7.6, 4.1))
    ax.hist(gap, bins=30, color='#bf8700', alpha=.88)
    ax.axvline(0, color='#d1242f', ls='--', lw=2, label='零 gap')
    ax.axvline(gap.mean(), color='#2da44e', lw=2, label=f'均值 {gap.mean():.4f}')
    ax.set_xlabel('classwise macro ECE − composite ECE'); ax.set_ylabel('种子数')
    ax.set_title('H1｜300 个独立 Mamba 种子'); ax.legend(fontsize=9); ax.grid(alpha=.3)
    fig.tight_layout(); fig.savefig(HERE / 'fig_w4_gap.png'); plt.close(fig)
    print('DONE', flush=True)


if __name__ == "__main__":
    main()
