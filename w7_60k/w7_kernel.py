"""W7 Rare-Failure Atlas — 60,000 independent deployment scenarios.

This is NOT a repeat of W6's confirmatory 600 seeds. It answers a question
600 seeds cannot statistically answer: what happens in the 0.1%-level rare
failure regimes of the deployment certificate, across a CONTINUOUS span of
group heterogeneity rather than two pre-set strata.

Scientific payload (pre-registered in PREREGISTRATION_W7.md):
  P1  harm-rate CI half-width <= 0.0015
  P2  harm(CERT-GATE) <= 0.025 and >=50% below harm(GST)
  P3  a pre-declared high-risk cell with >=3x baseline harm
  P4  60k CI covers W6's 600-seed point estimate 0.0133
  P5  tail-0.1% worst seeds: certificate does not favour splitting more
  P6  6,000 CNN-1D seeds same sign as Mamba
  P7  certificate accuracy monotone in spread (Spearman rho >= 0.8)

Stress-test regime (declared BEFORE execution, different from W6 confirmatory):
  n_total=1000, L=32, n_ref=700, T_GRID=101, TAU_GRID=61
  spread ~ Uniform(0.05, 1.50) continuous
  36 hierarchical groups, 2.9 recordings/patient
  every 10th seed uses CNN-1D instead of Mamba
Synthetic toy waveforms + diagonal selective SSM numpy approximation.
NOT official Mamba kernel, NOT pretrained weights, NOT real 1.15M ECG.
"""
from __future__ import annotations
import numpy as np
import sys, pathlib

_HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parent / 'mamba_experiment'))
sys.path.insert(0, str(_HERE.parent / 'w6_tier1'))
from mamba_gst import (init_mamba, mamba_forward, init_cnn, cnn_forward,
                       fit_readout, apply_readout, fit_tau_s, conf_hist,
                       build_psi_table, fit_global, fit_gst, make_waveforms,
                       softmax)
from tier1_kernel import hierarchical_groups, HARM_MARGIN


def ece_groups_fast(zg, yg, sizes, t, tau, n_bins=10):
    """Vectorised equivalent of looping bin_ece over groups.

    For each group: ECE = sum_b (n_b/n_g) |mean(correct)_b - mean(conf)_b|,
    binned on conf on the FIXED probability scale. All 36 groups and all
    bins are computed with a single bincount over key = gid*n_bins + bin.
    Numerically identical to tier1_kernel.bin_ece up to fp summation order.
    """
    n = np.asarray(sizes, float)
    conf_all, corr_all, gid_all = [], [], []
    for g, (z, yy) in enumerate(zip(zg, yg)):
        p = softmax(z, tau * t[g])
        c = p.max(1)
        conf_all.append(c)
        corr_all.append((p.argmax(1) == yy).astype(float))
        gid_all.append(np.full(len(c), g, dtype=np.int64))
    conf = np.concatenate(conf_all)
    corr = np.concatenate(corr_all)
    gid = np.concatenate(gid_all)
    binid = np.clip((conf * n_bins).astype(np.int64), 0, n_bins - 1)
    key = gid * n_bins + binid
    L = len(n) * n_bins
    cnt = np.bincount(key, minlength=L).astype(float)
    s_conf = np.bincount(key, weights=conf, minlength=L)
    s_corr = np.bincount(key, weights=corr, minlength=L)
    safe = np.where(cnt > 0, cnt, 1.0)
    dev = np.abs(s_corr / safe - s_conf / safe)
    dev[cnt == 0] = 0.0
    # (cnt / n_g) weighting, summed within each group
    per_bin = (cnt / np.repeat(n, n_bins)) * dev
    return float(per_bin.reshape(len(n), n_bins).sum(1) @ (n / n.sum()))

T_GRID = np.exp(np.linspace(np.log(0.4), np.log(8.0), 101))
TAU_GRID = np.exp(np.linspace(np.log(0.05), np.log(10.0), 61))
N_TOTAL, L_SEQ, N_REF = 1000, 32, 700
K = 4

COLS = ['seed', 'spread', 'arch', 'cert', 'lam', 'tau2', 'noise',
        'ece_SOURCE', 'ece_GLOBAL', 'ece_GST', 'ece_SRGST',
        'ece_GSGST', 'ece_CERT',
        'harm_GST', 'harm_CERT', 'harm_GSGST',
        'n_min', 'n_max', 'n_rec', 'icc', 'deff', 'neff_over_n',
        'dECE_GST', 'dECE_CERT']
NCOLS = len(COLS)


def run_one(seed: int):
    """One independent deployment scenario -> one compact float row."""
    # spread is drawn from an INDEPENDENT rng stream so the DGP stream is
    # not coupled to the design variable (avoids hidden correlation).
    spread = float(np.random.default_rng(seed + 10_000_000).uniform(0.05, 1.50))
    arch = 1 if seed % 10 == 0 else 0            # 6,000 CNN-1D control seeds
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
    off = 0
    pid_off = 0
    for g, n in enumerate(sizes):
        d = rng.normal(0, 0.06, len(per_patient[g]))
        pz = np.repeat(d, per_patient[g])[:n]
        z[off:off + n] = T_true[g] * zr[off:off + n] + \
            pz[:, None] * rng.normal(0, 1, (1, K))
        gid[off:off + n] = g
        pmap[off:off + n] = pids[g] + pid_off
        off += n
        pid_off += len(per_patient[g])
    zg = [z[gid == g] for g in range(len(sizes))]
    yg = [y[gid == g] for g in range(len(sizes))]
    pg = [pmap[gid == g] for g in range(len(sizes))]
    n = np.asarray(sizes, float)

    psi = build_psi_table(zg, tau, href, T_GRID)
    Ti = np.log(fit_gst(psi, T_GRID))
    noise = float(np.mean(1.0 / n))
    tau2 = max(float(np.var(Ti, ddof=1)) - noise, 0.0)
    lam = tau2 / (tau2 + noise + 1e-12)
    Tg = float(np.asarray(fit_global(psi, sizes, T_GRID))[0])
    cert = 1 if tau2 > noise else 0             # 1 = GST, 0 = GLOBAL
    logTg = np.log(Tg)

    Th = {
        'SOURCE': np.ones(len(n)),
        'GLOBAL': np.full(len(n), Tg),
        'GST': np.exp(Ti),
        'SR-GST': np.exp(lam * Ti),
        'GS-GST': np.exp(lam * Ti + (1 - lam) * logTg),
        'CERT': (np.full(len(n), Tg) if cert == 0
                 else np.exp(lam * Ti + (1 - lam) * logTg)),
    }
    ece = {k: ece_groups_fast(zg, yg, n, t, tau) for k, t in Th.items()}

    eg = ece['GLOBAL']
    harm = {k: float(ece[k] > eg + HARM_MARGIN)
            for k in ['GST', 'GS-GST', 'CERT']}

    # patient-level ICC / design effect on the CERT confidence scale
    cert_conf = [softmax(zz, tau * Th['CERT'][g]).max(1)
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
        seed, spread, arch, cert, lam, tau2, noise,
        ece['SOURCE'], ece['GLOBAL'], ece['GST'], ece['SR-GST'],
        ece['GS-GST'], ece['CERT'],
        harm['GST'], harm['CERT'], harm['GS-GST'],
        int(n.min()), int(n.max()), int(n.sum()), icc, deff, 1.0 / deff,
        ece['GST'] - eg, ece['CERT'] - eg,
    ], dtype=np.float64)
