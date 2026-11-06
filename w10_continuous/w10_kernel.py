"""W10 kernel — continuous-endpoint comparison of three zero-hyperparameter
candidates, plus group-level LOCO external validation.

PREREGISTRATION_W10.md v1.0 (frozen BEFORE execution).

Endpoints (per seed, relative to GLOBAL):
    dECE_k     = ECE_k - ECE_GLOBAL
    loss_k     = max(0, dECE_k + 0.002)          # continuous deployment loss
    CVaR_0.1%  = mean of each method's OWN 20 worst dECE (N=20,000)
    harm_k     = 1{dECE_k > 0.002}               # secondary, descriptive

Candidates:
    CERT  = Proposition-1 gate + homoscedastic shrinkage lambda_bar
    HB    = heteroscedastic BLUP lambda_g = tau2/(tau2 + 1/n_g)
    M1    = DEFF-BLUP   sigma2_g = deff/n_g     (patient clustering)
    M2    = REL-BLEND   continuous mixture weighted by lambda_LB/lambda_bar
    M3    = STRAT-CERT  site-stratified tau2_h; pooled T fitted on train fold

Synthetic toy waveforms + diagonal selective SSM numpy approximation.
NOT official Mamba-2, NOT pretrained weights, NOT real 1.15M ECG.
"""
from __future__ import annotations
import numpy as np
import sys, pathlib

_HERE = pathlib.Path(__file__).resolve().parent
for p in [_HERE, _HERE.parent / 'mamba_experiment',
          _HERE.parent / 'w6_tier1', _HERE.parent / 'w7_60k',
          _HERE.parent / 'w9_lbst']:
    sys.path.insert(0, str(p))

from mamba_gst import (init_mamba, mamba_forward, init_cnn, cnn_forward,
                       fit_readout, apply_readout, fit_tau_s, conf_hist,
                       build_psi_table, fit_global, fit_gst, make_waveforms,
                       softmax)
from tier1_kernel import hierarchical_groups, HARM_MARGIN, SITES, CARTS, YEARS
from w7_kernel import (ece_groups_fast, T_GRID, TAU_GRID, N_TOTAL, L_SEQ, N_REF)
from w9_kernel import jackknife_lambda_lb

K, Z_JACK, MARGIN = 4, 1.96, 0.002

COLS = ['seed', 'spread', 'arch', 'cert', 'lam_bar', 'tau2', 'noise',
        'ece_GLOBAL', 'ece_SOURCE', 'ece_GST',
        'ece_CERT', 'ece_HB', 'ece_M1', 'ece_M2', 'ece_M3',
        'dECE_CERT', 'dECE_HB', 'dECE_M1', 'dECE_M2', 'dECE_M3',
        'loss_CERT', 'loss_HB', 'loss_M1', 'loss_M2', 'loss_M3',
        'harm_CERT', 'harm_HB', 'harm_M1', 'harm_M2', 'harm_M3',
        'deff', 'icc', 'rel', 'lam_lb', 'se_jack',
        'lam_g_range', 'tau2_strat_sd', 'n_min', 'n_max', 'n_rec', 'n_groups']
NCOLS = len(COLS)


def build_scenario(seed, *, spread_override=None, homogeneous=False,
                   arch_override=None):
    """One independent DGP draw + one forward pass. Shared by run_one/run_loco."""
    spread = (float(np.random.default_rng(seed + 10_000_000).uniform(0.05, 1.50))
              if spread_override is None else float(spread_override))
    if homogeneous:
        spread = 0.0
    arch = (1 if seed % 10 == 0 else 0) if arch_override is None else arch_override
    rng = np.random.default_rng(seed)

    T_true, sizes, meta, pids, per_patient = hierarchical_groups(rng, N_TOTAL, spread)
    Xs, ys, _ = make_waveforms(rng, N_REF, L=L_SEQ)
    prm = init_mamba(rng) if arch == 0 else init_cnn(rng)
    fwd = mamba_forward if arch == 0 else cnn_forward
    Hs = fwd(Xs, prm)
    ro = fit_readout(Hs, ys)
    zs = apply_readout(Hs, ro)
    tau = fit_tau_s(zs, ys, TAU_GRID)
    href = conf_hist(softmax(zs, tau))

    X, y, _ = make_waveforms(rng, int(sizes.sum()), L=L_SEQ)
    H = fwd(X, prm)
    zr = apply_readout(H, ro)
    z = np.empty_like(zr)
    gid = np.empty(len(y), int)
    pmap = np.empty(len(y), int)
    off = pid_off = 0
    for g, n_ in enumerate(sizes):
        d = rng.normal(0, 0.06, len(per_patient[g]))
        pz = np.repeat(d, per_patient[g])[:n_]
        z[off:off + n_] = T_true[g] * zr[off:off + n_] + \
            pz[:, None] * rng.normal(0, 1, (1, K))
        gid[off:off + n_] = g
        pmap[off:off + n_] = pids[g] + pid_off
        off += n_
        pid_off += len(per_patient[g])
    zg = [z[gid == g] for g in range(len(sizes))]
    yg = [y[gid == g] for g in range(len(sizes))]
    pg = [pmap[gid == g] for g in range(len(sizes))]
    n = np.asarray(sizes, float)

    psi = build_psi_table(zg, tau, href, T_GRID)
    Ti = np.log(fit_gst(psi, T_GRID))
    noise = float(np.mean(1.0 / n))
    tau2 = max(float(np.var(Ti, ddof=1)) - noise, 0.0)
    lam_bar = tau2 / (tau2 + noise + 1e-12)
    T_pool = float(np.asarray(fit_global(psi, sizes, T_GRID))[0])
    cert = 1 if tau2 > noise else 0
    logT_pool = np.log(T_pool)

    # deff from GLOBAL confidence (independent of any candidate estimator)
    conf_g = [softmax(zz, tau * T_pool).max(1) for zz in zg]
    vw, vb = [], []
    for cc, pp in zip(conf_g, pg):
        for q in np.unique(pp):
            m = pp == q
            if m.sum() > 1:
                vw.append(float(np.var(cc[m], ddof=1)))
        vb.append(float(np.var(cc, ddof=1)))
    vw = float(np.mean(vw)) if vw else 1e-6
    vb = float(np.mean(vb)) if vb else 1e-6
    icc = float(np.clip(vb / (vb + vw + 1e-9), 0.0, 0.95))
    mbar = float(n.sum() / max(pid_off, 1))
    deff = 1.0 + (mbar - 1.0) * icc

    return dict(seed=seed, spread=spread, arch=arch, meta=meta,
                sizes=sizes, n=n, zg=zg, yg=yg, pg=pg, psi=psi,
                Ti=Ti, tau=tau, T_pool=T_pool, logT_pool=logT_pool,
                tau2=tau2, noise=noise, lam_bar=lam_bar, cert=cert,
                deff=deff, icc=icc, T_GRID=T_GRID)


def make_temperatures(S, *, deff_override=None, rel_override=None,
                      strat_random=False):
    """Return dict estimator -> per-group temperature vector."""
    n, Ti, tau2, noise = S['n'], S['Ti'], S['tau2'], S['noise']
    lam_bar, cert, lp = S['lam_bar'], S['cert'], S['logT_pool']
    deff = S['deff'] if deff_override is None else float(deff_override)
    G = len(n)

    # ---- CERT (W6/W7) & HB (W9) ----
    lam_cert = np.full(G, lam_bar) if cert == 1 else np.zeros(G)
    lam_hb = (tau2 / (tau2 + 1.0 / n + 1e-12)) if cert == 1 else np.zeros(G)
    T_cert = np.exp(lam_cert * Ti + (1 - lam_cert) * lp)
    T_hb = np.exp(lam_hb * Ti + (1 - lam_hb) * lp)

    # ---- M1 DEFF-BLUP ----
    s2_m1 = deff / np.maximum(n, 1.0)
    t2_m1 = max(float(np.var(Ti, ddof=1)) - float(s2_m1.mean()), 0.0)
    if t2_m1 <= float(s2_m1.mean()):
        lam_m1 = np.zeros(G)
    else:
        lam_m1 = t2_m1 / (t2_m1 + s2_m1 + 1e-12)
    T_m1 = np.exp(lam_m1 * Ti + (1 - lam_m1) * lp)

    # ---- M2 REL-BLEND ----
    _, se, lam_lb, _ = jackknife_lambda_lb(Ti, S['sizes'])
    rel = (np.clip(lam_lb / max(lam_bar, 1e-12), 0.0, 1.0)
           if lam_bar > 0 else 0.0)
    if rel_override is not None:
        rel = float(rel_override)
    T_m2 = np.exp(rel * np.log(T_hb) + (1 - rel) * np.log(T_cert))

    # ---- M3 STRAT-CERT (site strata, >=4 groups else global fallback) ----
    if strat_random:
        strata = np.random.default_rng(S['seed'] + 777).integers(0, SITES, G)
    else:
        strata = np.array([m['site'] for m in S['meta']])
    t2_h, lam_m3 = {}, np.zeros(G)
    for h in np.unique(strata):
        idx = np.where(strata == h)[0]
        if len(idx) < 4:
            t2_h[int(h)] = tau2
            lam_m3[idx] = lam_hb[idx]
            continue
        nh, tih = n[idx], Ti[idx]
        s2h = float(np.mean(1.0 / nh))
        t2 = max(float(np.var(tih, ddof=1)) - s2h, 0.0)
        t2_h[int(h)] = t2
        lam_m3[idx] = (t2 / (t2 + 1.0 / nh + 1e-12)
                       if t2 > s2h else 0.0)
    T_m3 = np.exp(lam_m3 * Ti + (1 - lam_m3) * lp)

    sd_strat = float(np.std(list(t2_h.values()), ddof=1)) if len(t2_h) > 1 else 0.0
    return (dict(GLOBAL=np.full(G, S['T_pool']),
                 SOURCE=np.ones(G), GST=np.exp(Ti),
                 CERT=T_cert, HB=T_hb, M1=T_m1, M2=T_m2, M3=T_m3),
            dict(rel=float(rel), lam_lb=float(lam_lb), se=float(se),
                 lam_g_range=float(lam_hb.max() - lam_hb.min()),
                 tau2_strat_sd=sd_strat, lam_m3=lam_m3))


def _ece_all(S, Th, keys):
    return {k: ece_groups_fast(S['zg'], S['yg'], S['n'], Th[k], S['tau'])
            for k in keys}


def run_one(seed, *, spread_override=None, homogeneous=False,
            deff_override=None, rel_override=None, strat_random=False,
            arch_override=None):
    S = build_scenario(seed, spread_override=spread_override,
                       homogeneous=homogeneous, arch_override=arch_override)
    Th, aux = make_temperatures(S, deff_override=deff_override,
                                rel_override=rel_override,
                                strat_random=strat_random)
    keys = ['GLOBAL', 'SOURCE', 'GST', 'CERT', 'HB', 'M1', 'M2', 'M3']
    e = _ece_all(S, Th, keys)
    eg = e['GLOBAL']
    d = {k: e[k] - eg for k in ['CERT', 'HB', 'M1', 'M2', 'M3']}
    loss = {k: max(0.0, d[k] + MARGIN) for k in d}
    harm = {k: float(d[k] > MARGIN) for k in d}

    return np.array([
        seed, S['spread'], S['arch'], S['cert'], S['lam_bar'],
        S['tau2'], S['noise'],
        eg, e['SOURCE'], e['GST'],
        e['CERT'], e['HB'], e['M1'], e['M2'], e['M3'],
        d['CERT'], d['HB'], d['M1'], d['M2'], d['M3'],
        loss['CERT'], loss['HB'], loss['M1'], loss['M2'], loss['M3'],
        harm['CERT'], harm['HB'], harm['M1'], harm['M2'], harm['M3'],
        S['deff'], S['icc'], aux['rel'], aux['lam_lb'], aux['se'],
        aux['lam_g_range'], aux['tau2_strat_sd'],
        int(S['n'].min()), int(S['n'].max()), int(S['n'].sum()), len(S['n']),
    ], dtype=np.float64)


# ---------------------------------------------------------------- LOCO
def run_loco(seed):
    """Group-level non-in-sample external validation (10 folds / seed).

    site 3 folds, cart 4 folds, year 3 folds. Pooled T and tau2 are fitted on
    the TRAIN folds ONLY; held-out groups never enter any fit.
    Returns 3 rows (one per fold type): mean dECE for STRAT vs GLOBAL cert.
    """
    S = build_scenario(seed)
    n, Ti, psi, tau, T_GRID = S['n'], S['Ti'], S['psi'], S['tau'], S['T_GRID']
    meta = S['meta']
    out = []
    for dim, levels in [('site', SITES), ('cart', CARTS), ('year', YEARS)]:
        acc_strat, acc_glob = [], []
        for lv in range(levels):
            tr = np.array([i for i, m in enumerate(meta) if m[dim] != lv])
            ho = np.array([i for i, m in enumerate(meta) if m[dim] == lv])
            if len(tr) < 4 or len(ho) == 0:
                continue
            # pooled temperature fitted on TRAIN folds only
            T_pool_tr = float(np.asarray(fit_global(psi[tr], S['sizes'][tr],
                                                    T_GRID))[0])
            lp = np.log(T_pool_tr)
            noise_tr = float(np.mean(1.0 / n[tr]))
            t2_tr = max(float(np.var(Ti[tr], ddof=1)) - noise_tr, 0.0)

            # GLOBAL certificate (homoscedastic)
            lam_g = (t2_tr / (t2_tr + 1.0 / n[ho] + 1e-12)
                     if t2_tr > noise_tr else 0.0)
            # STRAT certificate: site strata within TRAIN folds only
            lam_s = np.zeros(len(ho))
            strata_tr = np.array([meta[i]['site'] for i in tr])
            for h in np.unique(strata_tr):
                idx = tr[strata_tr == h]
                if len(idx) < 4:
                    continue
                s2h = float(np.mean(1.0 / n[idx]))
                t2h = max(float(np.var(Ti[idx], ddof=1)) - s2h, 0.0)
                mask = np.array([meta[i]['site'] == h for i in ho])
                if mask.any():
                    lam_s[mask] = (t2h / (t2h + 1.0 / n[ho][mask] + 1e-12)
                                   if t2h > s2h else 0.0)
            zg_ho = [S['zg'][i] for i in ho]
            yg_ho = [S['yg'][i] for i in ho]
            n_ho = n[ho]
            e_glob = ece_groups_fast(zg_ho, yg_ho, n_ho,
                                     np.full(len(ho), T_pool_tr), tau)
            e_g = ece_groups_fast(zg_ho, yg_ho, n_ho,
                                  np.exp(lam_g * Ti[ho] + (1 - lam_g) * lp), tau)
            e_s = ece_groups_fast(zg_ho, yg_ho, n_ho,
                                  np.exp(lam_s * Ti[ho] + (1 - lam_s) * lp), tau)
            acc_glob.append(e_g - e_glob)
            acc_strat.append(e_s - e_glob)
        if acc_glob:
            out.append(np.array([seed, {'site': 0, 'cart': 1, 'year': 2}[dim],
                                 float(np.mean(acc_glob)), float(np.mean(acc_strat)),
                                 len(acc_glob)], dtype=np.float64))
    return np.asarray(out, dtype=np.float64)


LOCO_COLS = ['seed', 'dim', 'dECE_global_cert', 'dECE_strat_cert', 'n_folds']
