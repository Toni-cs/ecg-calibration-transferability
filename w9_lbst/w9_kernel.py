"""W9 kernel — Heteroscedastic BLUP Shrinkage (HB-GST), zero hyperparameters.

W8 proved that a hard second gate is the wrong shape (see W8_诊断报告.md).
W9 generalises Proposition 1 from homoscedastic noise sigma2 = mean(1/n_g)
to HETEROSCEDASTIC per-group noise sigma2_g = 1/n_g:

    tau2_hat = max(Var(log T_g_indep) - mean(1/n_g), 0)
    lambda_g = tau2_hat / (tau2_hat + 1/n_g)          # per-group BLUP weight
    T_g      = exp(lambda_g * log(T_g_indep)
                   + (1 - lambda_g) * log(T_global))

Small deployment groups (large 1/n_g) automatically shrink toward GLOBAL;
large groups keep their split benefit. This targets W7-P5 (residual harm in
small groups) WITHOUT sacrificing the average calibration gain, because it
does not shrink everyone. tau2_hat <= mean(1/n_g) sets all lambda_g = 0,
so Gate 1 of Proposition 1 is contained.

A global jackknife lower-bound variant (LB) is computed as an EXPLORATORY
control only; it is never a primary endpoint (PREREGISTRATION_W9.md).

Reuses W7's DGP, waveforms, diagonal SSM forward and vectorised ECE.
Synthetic toy waveforms + numpy diagonal selective SSM approximation.
NOT official Mamba-2, NOT pretrained weights, NOT real 1.15M ECG.
"""
from __future__ import annotations
import numpy as np
import sys, pathlib

_HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parent / 'mamba_experiment'))
sys.path.insert(0, str(_HERE.parent / 'w6_tier1'))
sys.path.insert(0, str(_HERE.parent / 'w7_60k'))
from mamba_gst import (init_mamba, mamba_forward, init_cnn, cnn_forward,
                       fit_readout, apply_readout, fit_tau_s, conf_hist,
                       build_psi_table, fit_global, fit_gst, make_waveforms,
                       softmax)
from tier1_kernel import hierarchical_groups, HARM_MARGIN
from w7_kernel import (ece_groups_fast, T_GRID, TAU_GRID, N_TOTAL, L_SEQ,
                       N_REF, COLS as W7_COLS)
import w7_kernel  # for monkeypatch-free optional switches

K = 4
Z_JACK = 1.96
EXTRA = ['ece_HB', 'dECE_HB', 'harm_HB',
         'ece_LB', 'dECE_LB', 'harm_LB',
         'lam_pt', 'se_jack', 'lam_lb', 'lam_g_min', 'lam_g_max',
         'lam_g_mean', 'n_groups']
COLS = list(W7_COLS) + EXTRA
NCOLS = len(COLS)


def jackknife_lambda_lb(Ti, sizes, z=Z_JACK):
    """Leave-one-group-out jackknife lower bound of lambda.

    Ti     = log(T_g_indep) for each group (G,)
    sizes  = group record counts (G,)
    sigma2_g = 1/n_g ; sigma2 = mean(sigma2_g)
    tau2_hat = max(Var(Ti) - sigma2, 0)
    lambda   = tau2_hat/(tau2_hat+sigma2)

    LOO variance has a closed form (no O(G^2) recomputation):
        mu'   = (G*mu - x_j)/(G-1)
        S'    = S - (x_j-mu)^2 * G/(G-1)
        Var'  = S'/(G-2)
    """
    G = len(Ti)
    if G < 4:
        return 0.0, 0.0, 0.0, 0.0
    n = np.asarray(sizes, float)
    s2g = 1.0 / np.maximum(n, 1.0)
    s2 = float(s2g.mean())
    mu = float(Ti.mean())
    S = float(((Ti - mu) ** 2).sum())
    var = S / (G - 1)
    tau2 = max(var - s2, 0.0)
    lam = tau2 / (tau2 + s2 + 1e-12)

    mu_j = (G * mu - Ti) / (G - 1)
    S_j = S - ((Ti - mu) ** 2) * (G / (G - 1))
    var_j = S_j / (G - 2)
    s2_j = (s2g.sum() - s2g) / (G - 1)
    tau2_j = np.maximum(var_j - s2_j, 0.0)
    lam_j = tau2_j / (tau2_j + s2_j + 1e-12)
    # standard jackknife SE: sqrt((G-1)/G * sum (theta_j - theta_bar)^2)
    lam_bar = float(lam_j.mean())
    se = float(np.sqrt((G - 1) / G * ((lam_j - lam_bar) ** 2).sum()))
    lb = float(np.clip(lam - z * se, 0.0, 1.0))
    return lam, se, lb, lam_bar


def run_one(seed: int, *, spread_override=None, homogeneous=False,
            random_lb=False, lb_zero=False, lb_upper=False,
            se_zero=False, arch_override=None):
    """One independent deployment scenario -> one compact float row."""
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
    lam_pt = tau2 / (tau2 + noise + 1e-12)
    Tg = float(np.asarray(fit_global(psi, sizes, T_GRID))[0])
    cert = 1 if tau2 > noise else 0
    logTg = np.log(Tg)

    # ---- primary: heteroscedastic per-group BLUP weights ----
    s2g = 1.0 / np.maximum(n, 1.0)
    lam_g = np.full(len(n), 0.0) if cert == 0 else tau2 / (tau2 + s2g + 1e-12)
    if se_zero:                       # F1: flatten heteroscedasticity
        lam_g = np.full(len(n), lam_pt) if cert == 1 else np.zeros(len(n))
    if lb_zero:                       # F2: force full fallback
        lam_g = np.zeros(len(n))
    if lb_upper:                      # F5: REVERSE the weight direction
        lam_g = (s2g / (tau2 + s2g + 1e-12)) if cert == 1 else np.zeros(len(n))
    if random_lb:                     # F3: random per-group weights
        lam_g = rng.uniform(0.0, 1.0, len(n))
    lam_g = np.clip(lam_g, 0.0, 1.0)

    # ---- exploratory control: global jackknife lower bound ----
    _, se, lam_lb, _ = jackknife_lambda_lb(Ti, sizes)
    if cert == 0:
        lam_lb = 0.0

    Th = {
        'SOURCE': np.ones(len(n)),
        'GLOBAL': np.full(len(n), Tg),
        'GST': np.exp(Ti),
        'SR-GST': np.exp(lam_pt * Ti),
        'GS-GST': np.exp(lam_pt * Ti + (1 - lam_pt) * logTg),
        'CERT': (np.full(len(n), Tg) if cert == 0
                 else np.exp(lam_pt * Ti + (1 - lam_pt) * logTg)),
        'HB': np.exp(lam_g * Ti + (1 - lam_g) * logTg),
        'LB': np.exp(lam_lb * Ti + (1 - lam_lb) * logTg),
    }
    ece = {k: ece_groups_fast(zg, yg, n, t, tau) for k, t in Th.items()}

    eg = ece['GLOBAL']
    harm = {k: float(ece[k] > eg + HARM_MARGIN)
            for k in ['GST', 'GS-GST', 'CERT', 'HB', 'LB']}

    cert_conf = [softmax(zz, tau * Th['HB'][g]).max(1)
                 for g, zz in enumerate(zg)]
    vw, vb = [], []
    for g, (cc, pp) in enumerate(zip(cert_conf, pg)):
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

    return np.array([
        seed, spread, arch, cert, lam_pt, tau2, noise,
        ece['SOURCE'], ece['GLOBAL'], ece['GST'], ece['SR-GST'],
        ece['GS-GST'], ece['CERT'],
        harm['GST'], harm['CERT'], harm['GS-GST'],
        int(n.min()), int(n.max()), int(n.sum()), icc, deff, 1.0 / deff,
        ece['GST'] - eg, ece['CERT'] - eg,
        # ---- W9 extras ----
        ece['HB'], ece['HB'] - eg, harm['HB'],
        ece['LB'], ece['LB'] - eg, harm['LB'],
        lam_pt, se, lam_lb, float(lam_g.min()), float(lam_g.max()),
        float(lam_g.mean()), len(n),
    ], dtype=np.float64)
