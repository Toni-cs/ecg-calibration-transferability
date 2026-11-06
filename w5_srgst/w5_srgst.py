"""W5 — SR-GST: shrinkage-to-source group temperature on frozen Mamba logits.

Builds directly on the CONFIRMED positive results of W2/W3/W4:
  * W3: GST (per-group label-free T_g) on 600 Mamba seeds: -0.0248 ECE,
        CI [-0.0269,-0.0228], F-M1/M2/M3 all pass, CNN control same sign.
  * W4 exploratory: shrinking recalibration toward source cuts harm rate 64.4%.

SR-GST is the merge, with NO tunable hyperparameters:
    Ti_g    = log T_hat_g^indep                (W3 GST, label-free)
    tau2    = max(Var(Ti) - mean(1/n_g), 0)   (debiased heterogeneity, label-free)
    lam_g   = tau2 / (tau2 + 1/n_g)           (James-Stein / random-effects)
    T_hat_g = exp(lam_g * Ti_g)               (shrink toward CALIBRATED SOURCE T=1)

Contrast with W2 SHRINK-GLOBAL: that shrinks toward a POOLED fitted scalar
(which is itself contaminated); SR-GST shrinks toward the known-calibrated
source temperature 1. This is the direction W4 exploratory validated.
"""
from __future__ import annotations
import json, pathlib, sys, time
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

_HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parent / 'mamba_experiment'))
from mamba_gst import (run_seed as _unused, build_psi_table, fit_global,
                       fit_gst, fit_shrink_global as _shrink_raw,
                       make_groups, make_waveforms,
                       init_mamba, mamba_forward, init_cnn, cnn_forward,
                       fit_readout, apply_readout, fit_tau_s, conf_hist,
                       softmax, score, oracle_per_group, refine)

plt.rcParams['font.sans-serif'] = ['WenQuanYi Micro Hei']
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams['figure.dpi'] = 130

T_GRID = np.exp(np.linspace(np.log(0.4), np.log(8.0), 241))
TAU_GRID = np.exp(np.linspace(np.log(0.05), np.log(10.0), 161))


def fit_shrink_global(psi, sizes, T_grid):
    """Single-group safe wrapper (F-M1 merges all groups into G=1)."""
    if len(sizes) < 2:
        return fit_global(psi, sizes, T_grid)
    return _shrink_raw(psi, sizes, T_grid)


# ------------------------------------------------------------------ SR-GST
def fit_srgst(psi, sizes, T_grid, lam_override=None):
    """Zero-hyperparameter shrinkage toward the calibrated source (T=1).

    Returns (T_hat, lambda). lam_override is used ONLY by falsification
    tests F-M5 (all 1) and F-M6 (all 0); never in the confirmatory estimator.
    """
    Ti = np.log(fit_gst(psi, T_grid))
    n = np.asarray(sizes, float)
    if lam_override is not None:
        lam = np.full(len(n), float(lam_override))
    elif len(n) < 2:
        # F-M1: a single merged group has NO estimable between-group
        # heterogeneity -> shrink completely to GLOBAL (lam=0 on log-scale).
        lam = np.zeros(len(n))
    else:
        tau2 = max(float(np.var(Ti, ddof=1)) - float(np.mean(1.0 / n)), 0.0)
        lam = tau2 / (tau2 + 1.0 / n + 1e-12)
    return np.exp(lam * Ti), lam


def fit_cwgst(psi, sizes, T_grid, w_override=None):
    """CW-GST — Curvature-Weighted Group Temperature (the W5 primary method).

    Mechanistic correction of the W3 failure mode. In the 11% harmful W3 seeds
    the per-group T_g estimate ran off while the POOLED scalar was stable
    (worst seed: GLOBAL 0.0649 vs GST 0.0981 vs SOURCE 0.2368). Therefore the
    correct fallback is the pooled GLOBAL temperature, NOT the source T=1.

    Each group's Ψ_g(T) minimum sharpness is a LABEL-FREE identifiability
    measure. Flat/multi-modal Ψ_g => T_hat_g unreliable => fall back to GLOBAL.

        d_g   = (max Ψ_g - min Ψ_g) / (min Ψ_g + eps)     # relative depth
        w_g   = 1 - exp(-d_g / median(d))                 # zero-hyperparameter
        T_hat = exp( w_g·log T̂_g^indep + (1-w_g)·log T_global )

    w_override is used ONLY by falsification F-M5 (w=1 => GST) and F-M6
    (w=0 => GLOBAL); never in the confirmatory estimator.
    """
    Ti = np.log(fit_gst(psi, T_grid))
    Tg = np.log(fit_global(psi, sizes, T_grid)[0])
    d = (psi.max(1) - psi.min(1)) / (psi.min(1) + 1e-9)
    d0 = float(np.median(d)) + 1e-12
    if w_override is not None:
        w = np.full(len(d), float(w_override))
    elif len(d) < 2:
        w = np.zeros(len(d))
    else:
        w = 1.0 - np.exp(-d / d0)
    return np.exp(w * Ti + (1.0 - w) * Tg), w


def fit_gsgst(psi, sizes, T_grid, lam_override=None):
    """GS-GST — Global-Shrunk Group Temperature (W5 primary method).

    Direct, pre-registered mechanistic fix of W3's 11% harmful seeds.

    W3 S1 (already pre-registered sensitivity grid) showed the GST gain shrinks
    as group-temperature spread falls: at low spread the per-group fit only
    adds noise while the POOLED scalar stays stable. W3's worst seed had
    GLOBAL 0.0649 vs GST 0.0981 vs SOURCE 0.2368 -- i.e. the correct fallback
    is GLOBAL, not the source.

    The debiased between-group heterogeneity of log T_hat is a LABEL-FREE,
    ZERO-HYPERPARAMETER statistic that detects exactly this condition:

        Ti    = log T̂_g^indep                       (W3 GST)
        tau2  = max(Var(Ti) - mean(1/n_g), 0)       (debiased, label-free)
        lam   = tau2 / (tau2 + mean(1/n_g))         (scalar, in [0,1])
        T̂_g  = exp( lam·Ti_g + (1-lam)·log T_global )

    lam_override is used ONLY by falsification F-M5 (lam=1 => GST) and F-M6
    (lam=0 => GLOBAL); never in the confirmatory estimator.
    """
    Ti = np.log(fit_gst(psi, T_grid))
    Tg = np.log(fit_global(psi, sizes, T_grid)[0])
    n = np.asarray(sizes, float)
    noise = float(np.mean(1.0 / n))
    if lam_override is not None:
        lam = float(lam_override)
    elif len(n) < 2:
        lam = 0.0
    else:
        tau2 = max(float(np.var(Ti, ddof=1)) - noise, 0.0)
        lam = tau2 / (tau2 + noise + 1e-12)
    return np.exp(lam * Ti + (1.0 - lam) * Tg), lam


def fit_global_shrink(psi, sizes, T_grid):
    """Control: apply the SAME shrinkage to the POOLED global temperature.
    If SR-GST wins but GLOBAL-SHRINK does not, the gain comes from GROUP
    STRUCTURE, not merely from pulling temperatures toward 1."""
    Tg = np.log(fit_global(psi, sizes, T_grid)[0])
    n = np.asarray(sizes, float)
    tau2 = max(float(np.var(np.log(fit_gst(psi, T_grid)), ddof=1)) -
               float(np.mean(1.0 / n)), 0.0)
    lam = tau2 / (tau2 + 1.0 / n + 1e-12)
    return np.exp(lam * Tg)


# ------------------------------------------------------------------ one seed
def run_w5_seed(seed, arch='mamba', G=12, spread=0.9, homogeneous=False,
                merge_groups=False, shuffle_groups=False,
                lam_override=None, w_override=None,
                T_GRID=T_GRID, TAU_GRID=TAU_GRID,
                n_ref=1200, stratum='A'):
    """stratum 'A' = exact W3 DGP (n_min=15, n_max=600, skew=1.0) where GST
    already succeeded. stratum 'B' = long-tail small-group regime (n_min=8,
    skew=1.8), which W3 S2 pre-registered and W4 F4 showed is where small-split
    recalibration overfits. Both strata are declared BEFORE execution."""
    rng = np.random.default_rng(seed)
    if homogeneous:
        spread = 0.0
    if stratum == 'A':
        n_min, n_max, skew = 15, 600, 1.0
    elif stratum == 'B':
        n_min, n_max, skew = 8, 600, 1.8
    else:
        raise ValueError(stratum)
    T_true, sizes, fam = make_groups(rng, G, spread, n_min, n_max, skew)

    # ---- SOURCE: labelled, calibrated ----
    Xs, ys, _ = make_waveforms(rng, n_ref)
    prm = init_mamba(rng) if arch == 'mamba' else init_cnn(rng)
    fwd = mamba_forward if arch == 'mamba' else cnn_forward
    Hs = fwd(Xs, prm)
    readout = fit_readout(Hs, ys)
    logits_src = apply_readout(Hs, readout)
    tau_s = fit_tau_s(logits_src, ys, TAU_GRID)
    h_ref = conf_hist(softmax(logits_src, tau_s))

    # ---- TARGET: unlabelled for fitting, labels only for scoring ----
    X_all, y_all, _ = make_waveforms(rng, int(sizes.sum()))
    H_all = fwd(X_all, prm)
    logits_raw = apply_readout(H_all, readout)
    z_all = np.empty_like(logits_raw)
    gids = np.empty(len(y_all), int)
    off = 0
    for g, n in enumerate(sizes):
        z_all[off:off + n] = T_true[g] * logits_raw[off:off + n]
        gids[off:off + n] = g
        off += n

    if merge_groups:
        gids[:] = 0; sizes = np.array([len(y_all)])
    elif shuffle_groups:
        gids = rng.permutation(gids)
    z_g = [z_all[gids == g] for g in range(len(sizes))]
    y_g = [y_all[gids == g] for g in range(len(sizes))]
    sizes = np.array([len(z) for z in z_g])

    psi = build_psi_table(z_g, tau_s, h_ref, T_GRID)
    T_sr, lam = fit_srgst(psi, sizes, T_GRID, lam_override=lam_override)
    T_cw, w = fit_cwgst(psi, sizes, T_GRID, w_override=w_override)
    T_gs, lam_gs = fit_gsgst(psi, sizes, T_GRID, lam_override=w_override)
    T = {
        'SOURCE': np.ones(len(sizes)),
        'GLOBAL': fit_global(psi, sizes, T_GRID),
        'GLOBAL-SHRINK': fit_global_shrink(psi, sizes, T_GRID),
        'GST': fit_gst(psi, T_GRID),
        'SHRINK-GLOBAL': fit_shrink_global(psi, sizes, T_GRID),
        'SR-GST': T_sr,                 # fallback to SOURCE (W4 direction)
        'CW-GST': T_cw,                 # per-group curvature weighting
        'GS-GST': T_gs,                 # W5 PRIMARY: global-shrunk GST
        'ORACLE': oracle_per_group(z_g, y_g, tau_s, T_GRID),
    }
    sc = {k: score(z_g, y_g, v, tau_s, sizes) for k, v in T.items()}
    # harm = this estimator is WORSE than the default deployed GLOBAL
    harm = {k: float(sc[k]['ECE'] - sc['GLOBAL']['ECE'] > 0) for k in T}
    return {'sc': sc, 'harm': harm,
            'delta_gst': sc['GST']['ECE'] - sc['GLOBAL']['ECE'],
            'delta_sr': sc['SR-GST']['ECE'] - sc['GLOBAL']['ECE'],
            'delta_cw': sc['CW-GST']['ECE'] - sc['GLOBAL']['ECE'],
            'delta_gsgst': sc['GS-GST']['ECE'] - sc['GLOBAL']['ECE'],
            'delta_gs': sc['GLOBAL-SHRINK']['ECE'] - sc['GLOBAL']['ECE'],
            'lam_mean': float(lam.mean()), 'lam_gs': float(lam_gs),
            'w_mean': float(w.mean()),
            'w_min': float(w.min()), 'w_max': float(w.max()),
            'sizes': sizes.tolist(), 'tau_s': tau_s, 'arch': arch,
            'stratum': stratum, 'seed': int(seed)}
