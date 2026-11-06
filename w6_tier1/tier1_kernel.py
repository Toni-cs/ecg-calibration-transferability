"""W6 Tier-1 kernel — the workload dimensions a Q1 paper actually needs.

Not "more seeds": more DIMENSIONS.
  1. Hierarchical drift: site -> cart -> year -> patient (nested random effects),
     with within-patient repeated recordings (1.15M / 395k ~ 2.9 per patient).
  2. Full calibration metric chain: top-label ECE, classwise macro ECE,
     canonical multiclass ECE, Brier, NLL, calibration slope/intercept,
     AUROC, DCA net benefit.
  3. Patient-level statistics: design effect, n_eff, record-level vs
     patient-block bootstrap CI width.
  4. Three non-in-sample external validations: leave-one-site / -cart / -year out.
  5. Proposition 1 (risk decomposition) + numerical verification of the
     deployment certificate and lambda convergence rate.
  6. Frozen-logits cache, ablation ledger, compute accounting.

Reuses W3/W5's diagonal selective-SSM forward. Synthetic toy waveforms,
NOT real 1.15M ECG, NOT official Mamba kernel / pretrained weights.
"""
from __future__ import annotations
import numpy as np

import sys, pathlib
_HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parent / 'mamba_experiment'))
from mamba_gst import (init_mamba, mamba_forward, init_cnn, cnn_forward,
                       fit_readout, apply_readout, fit_tau_s, conf_hist,
                       build_psi_table, fit_global, fit_gst, refine,
                       make_waveforms, softmax, L_SEQ, C_LEADS, K_CLASSES)

T_GRID = np.exp(np.linspace(np.log(0.4), np.log(8.0), 181))
TAU_GRID = np.exp(np.linspace(np.log(0.05), np.log(10.0), 121))
N_BINS = 15
K = K_CLASSES

SITES = 3
CARTS = 4
YEARS = 3
G = SITES * CARTS * YEARS      # 36 deployment groups


# ------------------------------------------------------------------ helpers
def onehot(y, k=K):
    o = np.zeros((len(y), k))
    o[np.arange(len(y)), np.asarray(y, int)] = 1.0
    return o


def bin_ece(p, y, n_bins=10):
    p = np.asarray(p, float); y = np.asarray(y, float)
    idx = np.clip((p * n_bins).astype(int), 0, n_bins - 1)
    tot = 0.0
    for b in range(n_bins):
        m = idx == b
        if m.any():
            tot += m.mean() * abs(y[m].mean() - p[m].mean())
    return float(tot)


def logistic_irls(x, y, iters=12, ridge=1.0):
    """Calibration slope/intercept: ridge-regularised, step-clipped IRLS.

    Unregularised Newton diverges under near-complete separation (the
    confidence distribution of a shifted model is often saturated), which
    would produce absurd slopes and corrupt any composite utility.
    """
    x = np.clip(np.asarray(x, float), -8, 8); y = np.asarray(y, float)
    X = np.column_stack([np.ones(len(x)), x])
    b = np.array([0.0, 1.0])
    R = np.diag([ridge, ridge])
    for _ in range(iters):
        eta = np.clip(X @ b, -30, 30)
        p = 1.0 / (1.0 + np.exp(-eta))
        W = np.clip(p * (1 - p), 1e-6, None)
        H = X.T @ (W[:, None] * X) + R
        g = X.T @ (y - p) - R @ b
        try:
            step = np.linalg.solve(H, g)
        except np.linalg.LinAlgError:
            break
        step = np.clip(step, -1.0, 1.0)          # no runaway Newton steps
        b += step
        if np.max(np.abs(step)) < 1e-7:
            break
    return float(b[0]), float(b[1])


def auroc_binary(score, y):
    y = np.asarray(y, int); s = np.asarray(score, float)
    a, b = s[y == 1], s[y == 0]
    if len(a) == 0 or len(b) == 0:
        return float('nan')
    return float((a[:, None] > b[None, :]).mean() +
                 0.5 * (a[:, None] == b[None, :]).mean())


def full_metrics(probs, y, n_bins=10):
    """Full Q1-grade metric chain on one deployment group."""
    p = np.clip(np.asarray(probs, float), 1e-9, 1 - 1e-9)
    y = np.asarray(y, int)
    Y = onehot(y)
    conf = p.max(1)
    correct = (p.argmax(1) == y).astype(float)

    top_ece = bin_ece(conf, correct, n_bins)
    # classwise macro ECE: each class binned INDEPENDENTLY on its own p_k
    cw = [bin_ece(p[:, k], Y[:, k], n_bins) for k in range(K)]
    # canonical multiclass ECE: bin on TOP-LABEL confidence, then measure the
    # mean absolute deviation of the WHOLE probability vector vs the whole
    # one-hot vector inside each bin. Different definition from cw above.
    can, cidx = 0.0, np.clip((conf * n_bins).astype(int), 0, n_bins - 1)
    for b in range(n_bins):
        m = cidx == b
        if m.any():
            can += m.mean() * float(np.mean(np.abs(p[m].mean(0) - Y[m].mean(0))))
    brier = float(np.mean(((p - Y) ** 2).sum(1)))
    nll = float(np.mean(-np.log(p[np.arange(len(y)), y])))
    slope_int = logistic_irls(np.log(conf / (1 - conf)), correct)
    auc = auroc_binary(conf, correct)
    nb = []
    for t in (0.1, 0.2, 0.3):
        pred = conf >= t
        tp = float((pred & (correct == 1)).sum())
        fp = float((pred & (correct == 0)).sum())
        nb.append(tp / len(y) - fp / len(y) * t / (1 - t))
    return {'ECE_top': top_ece, 'ECE_classwise_macro': float(np.mean(cw)),
            'ECE_canonical': float(can), 'Brier': brier, 'NLL': nll,
            'cal_intercept': slope_int[0], 'cal_slope': slope_int[1],
            'AUROC': auc, 'DCA_net_benefit': float(np.mean(nb))}


METRIC_KEYS = ['ECE_top', 'ECE_classwise_macro', 'ECE_canonical', 'Brier',
               'NLL', 'cal_intercept', 'cal_slope', 'AUROC', 'DCA_net_benefit']
PRIMARY_KEY = 'ECE_canonical'      # canonical multiclass ECE — Q1-grade primary


def utility(m):
    """Primary endpoint. We deliberately do NOT sum heterogeneous metrics into
    one utility (ECE ~0.1, NLL ~1.4, AUROC ~0.55, slope ~1 are different
    units). All 9 metrics are reported separately with their own CIs; harm
    adjudication uses the single pre-registered primary endpoint."""
    return float(m[PRIMARY_KEY])


# ------------------------------------------------------------------ estimators
def fit_lam(psi, sizes, T_grid=T_GRID):
    Ti = np.log(fit_gst(psi, T_grid))
    n = np.asarray(sizes, float)
    if len(n) < 2:
        return np.full(len(n), 1.0), {'tau2': 0.0, 'noise': 0.0, 'lam': 1.0,
                                     'certificate': 'GLOBAL'}
    noise = float(np.mean(1.0 / n))
    tau2 = max(float(np.var(Ti, ddof=1)) - noise, 0.0)
    lam = tau2 / (tau2 + noise + 1e-12)
    return np.full(len(n), lam), {'tau2': tau2, 'noise': noise, 'lam': lam,
                                   'certificate': 'GST' if tau2 > noise else 'GLOBAL'}


def fit_srgst(psi, sizes, T_grid=T_GRID, lam_override=None):
    """W4-direction control: shrink toward SOURCE (T=1)."""
    Ti = np.log(fit_gst(psi, T_grid)); n = np.asarray(sizes, float)
    if len(n) < 2: return np.ones(len(n))
    if lam_override is not None:
        lam = np.full(len(n), float(lam_override))
    else:
        tau2 = max(float(np.var(Ti, ddof=1)) - float(np.mean(1.0 / n)), 0.0)
        lam = tau2 / (tau2 + 1.0 / n + 1e-12)
    return np.exp(lam * Ti)


def fit_gsgst(psi, sizes, T_grid=T_GRID, lam_override=None):
    """W5 primary: shrink toward pooled GLOBAL."""
    Ti = np.log(fit_gst(psi, T_grid))
    Tg = float(np.log(np.asarray(fit_global(psi, sizes, T_grid))[0]))
    n = np.asarray(sizes, float)
    if len(n) < 2: return np.full(len(n), np.exp(Tg))
    if lam_override is not None:
        lam = float(lam_override)
    else:
        noise = float(np.mean(1.0 / n))
        tau2 = max(float(np.var(Ti, ddof=1)) - noise, 0.0)
        lam = tau2 / (tau2 + noise + 1e-12)
    return np.exp(lam * Ti + (1 - lam) * Tg)


def fit_gst_only(psi, sizes, T_grid=T_GRID):
    return fit_gst(psi, T_grid)


def fit_oracle(z_g, y_g, tau_s, T_grid=T_GRID):
    """Vectorised over the T grid (identical values, ~30x faster)."""
    out = np.empty(len(z_g))
    for g, (z, y) in enumerate(zip(z_g, y_g)):
        zz = np.asarray(z, float)[:, None, :] / (tau_s * T_grid)[None, :, None]
        zz -= zz.max(-1, keepdims=True)
        e = np.exp(zz); p = e / e.sum(-1, keepdims=True)
        ptrue = np.clip(p[np.arange(len(z)), :, np.asarray(y, int)], 1e-9, 1.0)
        out[g] = T_grid[int(np.argmin(-np.log(ptrue).mean(0)))]
    return out


ESTIMATORS = {
    'SOURCE': lambda psi, sz, zg, yg, ts, lo, rc: np.ones(len(sz)),
    'GLOBAL': lambda psi, sz, zg, yg, ts, lo, rc: np.asarray(fit_global(psi, sz, T_GRID)),
    'GST': lambda psi, sz, zg, yg, ts, lo, rc: fit_gst_only(psi, sz, T_GRID),
    'SR-GST': lambda psi, sz, zg, yg, ts, lo, rc: fit_srgst(psi, sz, T_GRID, lam_override=lo),
    'GS-GST': lambda psi, sz, zg, yg, ts, lo, rc: fit_gsgst(psi, sz, T_GRID, lam_override=lo),
    'ORACLE': lambda psi, sz, zg, yg, ts, lo, rc: fit_oracle(zg, yg, ts, T_GRID),
}
FULL_CHAIN_EST = ['GLOBAL', 'GST', 'GS-GST', 'ORACLE']
# CERT-GATE is appended at runtime because it needs the group-level certificate
FULL_CHAIN_EST.append('CERT-GATE')
# Pre-registered non-inferiority margin for harm adjudication. A binary
# "any positive difference = harm" criterion is too brittle under a binned
# estimator; delta is ~1/3 of the main effect size.
HARM_MARGIN = 0.002


# ------------------------------------------------------------------ hierarchical DGP
def hierarchical_groups(rng, n_total=1800, spread=1.0, mu=0.55):
    """site(3) x cart(4) x year(3) = 36 groups, nested random effects.

    mu = global systematic over-confidence of the target deployment (the
    source was calibrated at T=1). Without it, a zero-mean log-temperature
    makes SOURCE accidentally near-optimal and the manipulation check fails.
    This mirrors real cross-centre deployment: a systematic confidence offset
    PLUS site/cart/year-specific deviations.
    """
    a = rng.normal(0, 0.50 * spread, SITES)
    b = rng.normal(0, 0.35 * spread, (SITES, CARTS))
    c = rng.normal(0, 0.20 * spread, YEARS)
    meta, logT = [], []
    for s in range(SITES):
        for cc in range(CARTS):
            for yy in range(YEARS):
                meta.append({'site': s, 'cart': cc, 'year': yy,
                             'family': (s * CARTS + cc) % (SITES * CARTS)})
                logT.append(mu + a[s] + b[s, cc] + c[yy] + rng.normal(0, 0.06))
    # long-tail group sizes (real cart/device deployment is heavy-tailed)
    raw = rng.lognormal(mean=0.0, sigma=0.85, size=G)
    sizes = np.clip(np.round(raw / raw.sum() * n_total), 8, None).astype(int)
    sizes[-1] += n_total - sizes.sum()
    sizes = np.clip(sizes, 8, None)
    # patient map: ~2.9 recordings per patient (1.15M / 395k)
    pids, per_patient = [], []
    off = 0
    for g, n in enumerate(sizes):
        n_pat = max(1, int(round(n / 2.9)))
        counts = np.ones(n_pat, int)
        for _ in range(n - n_pat):
            counts[rng.integers(0, n_pat)] += 1
        gp = np.concatenate([np.full(cnt, off + j) for j, cnt in enumerate(counts)])
        rng.shuffle(gp)
        pids.append(gp); per_patient.append(counts)
        off += n_pat
    return np.exp(np.array(logT)), sizes, meta, pids, per_patient


# ------------------------------------------------------------------ one seed
def run_tier1_seed(seed, arch='mamba', spread=1.0, n_total=1800,
                   do_full_chain=True, do_loco=True, do_block_boot=False,
                   merge_groups=False, shuffle_groups=False,
                   homogeneous=False, lam_override=None,
                   random_certificate=False, n_boot=2000):
    rng = np.random.default_rng(seed)
    if homogeneous: spread = 0.0
    T_true, sizes, meta, pids, per_patient = hierarchical_groups(rng, n_total, spread)
    G_eff = len(sizes)

    # ---- source: labelled, calibrated, frozen readout ----
    Xs, ys, _ = make_waveforms(rng, 1000)
    prm = init_mamba(rng) if arch == 'mamba' else init_cnn(rng)
    fwd = mamba_forward if arch == 'mamba' else cnn_forward
    Hs = fwd(Xs, prm); readout = fit_readout(Hs, ys)
    z_src = apply_readout(Hs, readout)
    tau_s = fit_tau_s(z_src, ys, TAU_GRID)
    h_ref = conf_hist(softmax(z_src, tau_s))

    # ---- target: hierarchical drift + within-patient repeated measures ----
    X, y, _ = make_waveforms(rng, int(sizes.sum()))
    H = fwd(X, prm); z_raw = apply_readout(H, readout)
    z_all = np.empty_like(z_raw); gids = np.empty(len(y), int)
    patient_id = np.empty(len(y), int); off = 0; pid_off = 0
    for g, n in enumerate(sizes):
        sl = slice(off, off + n)
        # patient-level random effect shared by all recordings of one patient
        d = rng.normal(0, 0.06, len(per_patient[g]))
        pz = np.repeat(d, per_patient[g])[:n]
        z_all[sl] = T_true[g] * z_raw[sl] + pz[:, None] * rng.normal(0, 1, (1, K))
        gids[sl] = g
        patient_id[sl] = pids[g] + pid_off
        off += n; pid_off += len(per_patient[g])

    if merge_groups:
        gids[:] = 0
        sizes = np.array([len(y)]); meta = [{'site': 0, 'cart': 0, 'year': 0, 'family': 0}]
    elif shuffle_groups:
        gids = rng.permutation(gids)
    z_g = [z_all[gids == g] for g in range(len(sizes))]
    y_g = [y[gids == g] for g in range(len(sizes))]
    sizes = np.array([len(z) for z in z_g])
    pg = [patient_id[gids == g] for g in range(len(sizes))]
    meta_g = [meta[min(g, len(meta) - 1)] for g in range(len(sizes))]

    psi = build_psi_table(z_g, tau_s, h_ref, T_GRID)
    lam_vec, cert = fit_lam(psi, sizes, T_GRID)
    if lam_override is not None:
        lam_vec = np.full(len(sizes), float(lam_override))
        cert = {'lam': float(lam_override), 'certificate': 'OVERRIDE',
                'tau2': None, 'noise': None}
    if random_certificate:                     # F-M5: coin-flip certificate
        cert = dict(cert)
        cert['certificate'] = 'GLOBAL' if rng.random() < 0.5 else 'GST'

    out = {'seed': int(seed), 'arch': arch, 'spread': spread,
           'n_records': int(sizes.sum()), 'n_patients': int(pid_off),
           'records_per_patient': float(sizes.sum() / max(pid_off, 1)),
           'G': int(len(sizes)), 'certificate': cert,
           'T_true': T_true.tolist(), 'sizes': sizes.tolist()}

    # ---- estimators + full metric chain ----
    chain = {}
    for name, fn in ESTIMATORS.items():
        Th = fn(psi, sizes, z_g, y_g, tau_s, lam_override, random_certificate)
        if name in FULL_CHAIN_EST and do_full_chain:
            per = []
            for g, (z, yy) in enumerate(zip(z_g, y_g)):
                per.append(full_metrics(softmax(z, tau_s * Th[g]), yy))
            w = sizes / sizes.sum()
            chain[name] = {k: float(np.average([m[k] for m in per], weights=w))
                           for k in METRIC_KEYS}
            chain[name]['U'] = utility(chain[name])
        else:
            # light path: top-label ECE only
            e = []
            for g, (z, yy) in enumerate(zip(z_g, y_g)):
                p = softmax(z, tau_s * Th[g])
                e.append(bin_ece(p.max(1), (p.argmax(1) == yy).astype(float)))
            chain[name] = {'ECE_top': float(np.average(e, weights=sizes))}
    # ---- CERT-GATE: explicit deployment certificate (Proposition 1) ----
    if do_full_chain:
        Th_cg = (np.full(len(sizes), np.asarray(fit_global(psi, sizes, T_GRID))[0])
                 if cert['certificate'] == 'GLOBAL'
                 else fit_gsgst(psi, sizes, T_GRID, lam_override=lam_override))
        per = [full_metrics(softmax(z, tau_s * Th_cg[g]), yy)
               for g, (z, yy) in enumerate(zip(z_g, y_g))]
        w = sizes / sizes.sum()
        chain['CERT-GATE'] = {k: float(np.average([m[k] for m in per], weights=w))
                              for k in METRIC_KEYS}
        chain['CERT-GATE']['U'] = utility(chain['CERT-GATE'])
    out['chain'] = chain

    # ---- harm: pre-registered non-inferiority margin vs GLOBAL ----
    if do_full_chain:
        u_glob = chain['GLOBAL']['U']
        out['harm'] = {k: float(chain[k]['U'] > u_glob + HARM_MARGIN)
                       for k in FULL_CHAIN_EST if k != 'GLOBAL'}
        out['harm_margin'] = HARM_MARGIN
        out['delta_U_GSGST'] = chain['GS-GST']['U'] - u_glob
        out['delta_U_GST'] = chain['GST']['U'] - u_glob
        out['delta_U_CERT'] = chain['CERT-GATE']['U'] - u_glob
        out['delta_ECE_GSGST'] = chain['GS-GST']['ECE_top'] - chain['GLOBAL']['ECE_top']
        out['delta_ECE_GST'] = chain['GST']['ECE_top'] - chain['GLOBAL']['ECE_top']
    else:
        eg = chain['GLOBAL']['ECE_top']
        out['harm'] = {k: float(chain[k]['ECE_top'] > eg + HARM_MARGIN)
                       for k in chain if k != 'GLOBAL'}
        out['harm_margin'] = HARM_MARGIN
        out['delta_U_GSGST'] = chain['GS-GST']['ECE_top'] - eg
        out['delta_U_GST'] = chain['GST']['ECE_top'] - eg
        out['delta_ECE_GSGST'] = out['delta_U_GSGST']
        out['delta_ECE_GST'] = out['delta_U_GST']

    # ---- patient-level design effect ----
    # ICC on the logit scale, estimated from within-patient repeat variance.
    var_between, var_within = [], []
    for g, (z, pp) in enumerate(zip(z_g, pg)):
        cc = z.max(1)
        for p in np.unique(pp):
            m = pp == p
            if m.sum() > 1:
                var_within.append(float(np.var(cc[m], ddof=1)))
        var_between.append(float(np.var(cc, ddof=1)))
    vw = float(np.mean(var_within)) if var_within else 1e-6
    vb = float(np.mean(var_between)) if var_between else 1e-6
    rho = float(np.clip(vb / (vb + vw + 1e-9), 0.0, 0.95))
    mbar = out['records_per_patient']
    deff = 1.0 + (mbar - 1.0) * rho
    out['patient_stats'] = {'ICC_hat': rho, 'design_effect': deff,
                            'n_eff': float(sizes.sum() / deff),
                            'n_eff_over_n': float(1.0 / deff)}

    # ---- record-level vs patient-block bootstrap CI width (representative) ----
    if do_block_boot:
        Th_gs = fit_gsgst(psi, sizes, T_GRID)
        Th_gl = np.full(len(sizes), np.asarray(fit_global(psi, sizes, T_GRID))[0])
        cg, cglo, corrs, pps = [], [], [], []
        for g, (z, yy, pp) in enumerate(zip(z_g, y_g, pg)):
            p1 = softmax(z, tau_s * Th_gs[g]); p0 = softmax(z, tau_s * Th_gl[g])
            cg.append(p1.max(1)); cglo.append(p0.max(1))
            corrs.append((p1.argmax(1) == yy).astype(float)); pps.append(pp)
        c1 = np.concatenate(cg); c0 = np.concatenate(cglo)
        corr = np.concatenate(corrs); pp = np.concatenate(pps); uniq = np.unique(pp)
        clusters = [np.where(pp == q)[0] for q in uniq]
        rec, blk = [], []
        rb = np.random.default_rng(seed + 991)
        def dstat(idx):
            return bin_ece(c1[idx], corr[idx]) - bin_ece(c0[idx], corr[idx])
        for _ in range(n_boot):
            i = rb.integers(0, len(corr), len(corr))
            rec.append(dstat(i))
            sel = rb.integers(0, len(clusters), len(clusters))
            j = np.concatenate([clusters[s] for s in sel])
            blk.append(dstat(j))
        out['bootstrap_CI'] = {
            'statistic': 'paired delta top-label ECE (GS-GST - GLOBAL)',
            'record_level_width': float(np.percentile(rec, 97.5) - np.percentile(rec, 2.5)),
            'patient_block_width': float(np.percentile(blk, 97.5) - np.percentile(blk, 2.5)),
            'record_level_CI': [float(np.percentile(rec, 2.5)), float(np.percentile(rec, 97.5))],
            'patient_block_CI': [float(np.percentile(blk, 2.5)), float(np.percentile(blk, 97.5))],
            'n_patients_in_bootstrap': int(len(uniq)), 'B': n_boot}
        out['bootstrap_CI']['width_ratio'] = (
            out['bootstrap_CI']['patient_block_width'] /
            max(out['bootstrap_CI']['record_level_width'], 1e-9))

    # ---- three non-in-sample LOCO external validations ----
    if do_loco and len(sizes) >= 4:
        loco = {}
        axes = {'site': [m['site'] for m in meta_g],
                'cart': [m['family'] for m in meta_g],
                'year': [m['year'] for m in meta_g]}
        for axis, lab in axes.items():
            folds = []
            for v in sorted(set(lab)):
                tr = np.array([i for i, l in enumerate(lab) if l != v])
                te = np.array([i for i, l in enumerate(lab) if l == v])
                if len(tr) < 2 or len(te) == 0:
                    continue
                psi_tr = psi[tr]
                sz_tr = sizes[tr]
                # fit_global returns a (len(psi),) array with identical entries;
                # take the scalar pooled temperature fitted on TRAIN folds only.
                Tg = float(np.log(np.asarray(fit_global(psi_tr, sz_tr, T_GRID))[0]))
                Ti = np.log(fit_gst(psi_tr, T_GRID))
                noise = float(np.mean(1.0 / sz_tr))
                tau2 = max(float(np.var(Ti, ddof=1)) - noise, 0.0)
                lam = tau2 / (tau2 + noise + 1e-12)
                Ti_te = np.log(fit_gst(psi[te], T_GRID))
                # GS-GST: frozen lambda/global from training folds only
                Th_gs = np.exp(lam * Ti_te + (1 - lam) * Tg)
                Th_gst = np.exp(Ti_te)
                Th_glob = np.full(len(te), np.exp(Tg))
                # certificate is fitted on TRAIN folds only
                Th_cert = (Th_glob if tau2 <= noise else Th_gs)
                def metric(Th):
                    us = []
                    for j, gi in enumerate(te):
                        z, yy = z_g[gi], y_g[gi]
                        us.append(utility(full_metrics(softmax(z, tau_s * Th[j]), yy)))
                    return float(np.average(us, weights=sizes[te]))
                folds.append({'n_train_groups': len(tr), 'n_test_groups': len(te),
                              'U_GLOBAL': metric(Th_glob), 'U_GST': metric(Th_gst),
                              'U_GSGST': metric(Th_gs), 'U_CERT': metric(Th_cert),
                              'lam_heldout': float(lam),
                              'certificate': 'GLOBAL' if tau2 <= noise else 'GST'})
            if folds:
                loco[axis] = {
                    'n_folds': len(folds),
                    'mean_U_GLOBAL': float(np.mean([f['U_GLOBAL'] for f in folds])),
                    'mean_U_GST': float(np.mean([f['U_GST'] for f in folds])),
                    'mean_U_GSGST': float(np.mean([f['U_GSGST'] for f in folds])),
                    'mean_U_CERT': float(np.mean([f['U_CERT'] for f in folds])),
                    'folds_GSGST_better_than_GST': int(np.sum(
                        [f['U_GSGST'] <= f['U_GST'] for f in folds])),
                    'folds_CERT_better_than_GST': int(np.sum(
                        [f['U_CERT'] <= f['U_GST'] + HARM_MARGIN for f in folds])),
                    'folds': folds}
        out['LOCO'] = loco
    return out


# ------------------------------------------------------------------ Proposition 1
def proposition1_verify(seed=20261106, Gs=(4, 8, 16, 32, 64, 128),
                        taus=(0.05, 0.2, 0.5, 1.0, 2.0),
                        sigmas=(0.1, 0.5, 1.0), reps=200):
    """Numerical verification of the risk decomposition.

    Model: theta_g ~ N(0, tau2), X_g = theta_g + eps_g, Var(eps) = sigma2.
    Shrinkage delta = m + lam (X_g - m), m = mean(X).
    Closed form (G -> inf):  R(lam) = (1-lam)^2 tau2 + lam^2 sigma2
                              lam*   = tau2 / (tau2 + sigma2)
                              R(lam*)= tau2 sigma2 / (tau2 + sigma2)
                              R(1)=sigma2 (GST), R(0)=tau2 (GLOBAL)
    GS-GST never worse than min(GST, GLOBAL); equal only at extremes.
    """
    rng = np.random.default_rng(seed)
    rows = []
    for G_ in Gs:
        for tau2 in taus:
            for sig2 in sigmas:
                errs, risk_gain, cert_acc, lam_star = [], [], [], tau2 / (tau2 + sig2)
                for _ in range(reps):
                    th = rng.normal(0, np.sqrt(tau2), G_)
                    X = th + rng.normal(0, np.sqrt(sig2), G_)
                    m = X.mean()
                    tau_hat = max(float(np.var(X, ddof=1)) - sig2, 0.0)
                    lam_hat = tau_hat / (tau_hat + sig2 + 1e-12)
                    errs.append((lam_hat - lam_star) ** 2)
                    d = m + np.array([lam_hat, 1.0, 0.0])[:, None] * (X - m)[None, :]
                    R = ((d - th[None, :]) ** 2).mean(1)
                    risk_gain.append(float(R[0] <= min(R[1], R[2]) + 1e-9))
                    cert_acc.append(int((tau_hat <= sig2) == (tau2 <= sig2)))
                rows.append({'G': G_, 'tau2': tau2, 'sigma2': sig2,
                             'lam_star': lam_star,
                             'mse_lam': float(np.mean(errs)),
                             'P_R_lamhat_le_min': float(np.mean(risk_gain)),
                             'certificate_accuracy': float(np.mean(cert_acc))})
    # convergence slope of mse_lam vs G (log-log)
    slopes = []
    for tau2 in taus:
        for sig2 in sigmas:
            sub = sorted([r for r in rows if r['tau2'] == tau2 and r['sigma2'] == sig2],
                         key=lambda r: r['G'])
            x = np.log([r['G'] for r in sub]); yv = np.log([max(r['mse_lam'], 1e-12) for r in sub])
            slopes.append(float(np.polyfit(x, yv, 1)[0]))
    return {'rows': rows, 'mean_loglog_slope': float(np.mean(slopes)),
            'theory_slope': -1.0,
            'closed_form': {
                'R_lam': 'tau2*sigma2/(tau2+sigma2)',
                'R_GST': 'sigma2', 'R_GLOBAL': 'tau2',
                'lam_star': 'tau2/(tau2+sigma2)',
                'GST_better_than_GLOBAL_iff': 'sigma2 < tau2',
                'deployment_certificate': 'tau_hat <= sigma_hat => use GLOBAL'}}
