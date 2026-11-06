"""Mamba backbone + GST calibration, self-contained.

IMPORTANT HONESTY NOTE
----------------------
This is a NUMPY implementation of a DIAGONAL SELECTIVE STATE-SPACE BLOCK
(Mamba-1 / S6 diagonal-state approximation): input-dependent delta, B, C,
gated conv + SSM scan. It is NOT the official Mamba CUDA kernel, NOT a
pretrained checkpoint, and NOT real 1.15M ECG waveforms. It exists so that
the 600-seed experiment's logits come from an actual Mamba forward pass
instead of an analytic Gaussian logit generator.

The deployment protocol mirrors the real setting:
  * source domain HAS labels -> fit the readout (ridge) and tau_s (TS/NLL)
  * target domain has NO labels -> only confidence histograms are used to fit T_g
  * labels of the target are used ONLY for final ECE/NLL/Brier scoring
"""
from __future__ import annotations

import numpy as np

N_BINS = 15          # fixed-scale confidence histogram for Psi
K_CLASSES = 4
L_SEQ = 48           # synthetic downsampled 10-s ECG toy length
C_LEADS = 12
D_SSM = 16


# ------------------------------------------------------------------ basics
def silu(x):
    return x / (1.0 + np.exp(-np.clip(x, -30, 30)))


def softplus(x):
    return np.log1p(np.exp(np.clip(x, -30, 30)))


def softmax(logits, T):
    z = np.asarray(logits, float) / float(T)
    z -= z.max(axis=-1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=-1, keepdims=True)


def conf_hist(probs, n_bins=N_BINS):
    c = np.asarray(probs).max(axis=-1)
    idx = np.clip((c * n_bins).astype(int), 0, n_bins - 1)
    h = np.bincount(idx.ravel(), minlength=n_bins).astype(float)
    return h / max(h.sum(), 1e-12)


def ece(probs, y, n_bins=10):
    c = np.asarray(probs).max(axis=-1)
    pred = np.asarray(probs).argmax(axis=-1)
    ok = (pred == np.asarray(y)).astype(float)
    idx = np.clip((c * n_bins).astype(int), 0, n_bins - 1)
    tot = 0.0
    for b in range(n_bins):
        m = idx == b
        if m.any():
            tot += m.mean() * abs(ok[m].mean() - c[m].mean())
    return float(tot)


def nll(probs, y):
    p = np.clip(np.asarray(probs)[np.arange(len(y)), np.asarray(y)], 1e-12, 1.0)
    return float(-np.log(p).mean())


def brier(probs, y):
    K = np.asarray(probs).shape[-1]
    oh = np.eye(K)[np.asarray(y)]
    return float(np.mean(np.sum((np.asarray(probs) - oh) ** 2, axis=-1)))


# ------------------------------------------------------------------ waveforms
def make_waveforms(rng, n, K=K_CLASSES, L=L_SEQ, C=C_LEADS, noise=0.35):
    """Synthetic 12-lead ECG-like toy. Class c controls QRS amplitude/width,
    ST offset and T-wave; a fixed lead-projection matrix mimics the lead field.
    Labels are SAMPLED from p_i (true conditional), never fixed to argmax.
    """
    c = rng.integers(0, K, n)
    p = np.full((n, K), 0.12)
    p[np.arange(n), c] = 0.55 + rng.uniform(0, 0.25, n)
    p /= p.sum(1, keepdims=True)
    y = np.array([rng.choice(K, p=p[i]) for i in range(n)])

    t = np.linspace(0.0, 1.0, L)[None, :]
    amp = (0.55 + 0.30 * c / (K - 1))[:, None]
    wid = (0.030 + 0.020 * c / (K - 1))[:, None]
    qrs = amp * np.exp(-((t - 0.35) / wid) ** 2)
    pw = 0.30 * np.exp(-((t - 0.15) / 0.040) ** 2)
    tw = 0.40 * np.exp(-((t - 0.65) / 0.070) ** 2)
    st = (0.10 * (c - (K - 1) / 2) / K)[:, None] * np.exp(-((t - 0.50) / 0.10) ** 2)
    sig = pw + qrs + tw + st                                    # (n, L)

    lw = rng.uniform(0.4, 1.0, (1, C, 1))
    X = sig[:, None, :] * lw
    X += 0.08 * (c[:, None, None] - (K - 1) / 2)             # class-specific lead offset
    X += rng.normal(0, noise, X.shape)
    X = np.transpose(X, (0, 2, 1))                 # (N, L, C)
    return np.ascontiguousarray(X, dtype=np.float32), y.astype(int), p


# ------------------------------------------------------------------ Mamba block
def init_mamba(rng, D=D_SSM, C=C_LEADS, scale=0.18):
    """Per-seed INDEPENDENT weights. Diagonal selective SSM (S6 approximation)."""
    return {
        'Win': rng.normal(0, scale, (C, 2 * D)),
        'conv': rng.normal(0, scale / 2, (4, D)),
        'Wd': rng.normal(0, scale / 3, (D, D)),
        'bd': np.full(D, -0.8),
        'Wb': rng.normal(0, scale / 2, (D, D)),
        'Wc': rng.normal(0, scale / 2, (D, D)),
        'A_log': np.log(rng.uniform(0.15, 1.2, D)),           # A = -exp(A_log) < 0
        'Dskip': np.ones(D) * 0.5,
        'Wout': rng.normal(0, scale, (D, D)),
        'D': D,
    }


def causal_conv(x, w):
    """Depthwise causal conv, kernel 4, zero left pad. x: (N,L,D)."""
    N, L, D = x.shape
    out = np.zeros_like(x)
    for k in range(4):
        if k == 0:
            out += x * w[k][None, None, :]
        else:
            out[:, k:, :] += x[:, :-k, :] * w[k][None, None, :]
    return out


def mamba_forward(X, prm):
    """Diagonal selective scan. Returns pooled feature H: (N, D)."""
    N, L, C = X.shape
    D = prm['D']
    U = X @ prm['Win']                                          # (N,L,2D)
    xb, gate = U[..., :D], U[..., D:]
    xc = silu(causal_conv(xb, prm['conv']))
    delta = softplus(xc @ prm['Wd'] + prm['bd'])                # input-dependent step
    B = xc @ prm['Wb']                                          # input-dependent B
    Cc = xc @ prm['Wc']                                         # input-dependent C
    A = -np.exp(prm['A_log'])
    a = np.exp(np.clip(delta * A[None, None, :], -30, 0))       # (N,L,D) in (0,1)
    q = np.clip(delta * B * xc, -20, 20)
    h = np.zeros((N, D), dtype=float)
    ys = np.empty((N, L, D), dtype=float)
    for t in range(L):
        h = a[:, t, :] * h + q[:, t, :]
        ys[:, t, :] = Cc[:, t, :] * h
    Y = (ys + prm['Dskip'][None, None, :] * xc) * silu(gate)
    Y = Y @ prm['Wout']
    return Y.mean(axis=1).astype(np.float64)                    # (N,D)


# ------------------------------------------------------------------ CNN control
def init_cnn(rng, D=D_SSM, C=C_LEADS, scale=0.18):
    return {'W': rng.normal(0, scale, (5, C, D)), 'b': rng.normal(0, scale / 2, D)}


def cnn_forward(X, prm):
    N, L, C = X.shape
    D = prm['b'].size
    out = np.zeros((N, L, D))
    for k in range(5):
        if k == 0:
            out += X @ prm['W'][k]
        else:
            out[:, k:, :] += X[:, :L - k, :] @ prm['W'][k]
    out = np.maximum(out + prm['b'][None, None, :], 0)
    return out.mean(axis=1).astype(np.float64)


# ------------------------------------------------------------------ readout
def fit_readout(H, y, K=K_CLASSES, lam=1.0):
    """Fit a frozen source-domain readout (ridge + fixed input standardisation).

    The standardisation uses SOURCE statistics only and is frozen at deploy,
    exactly like a BN running-stat layer. Without it a randomly initialised
    encoder produces near-uniform logits, NLL collapses T to the grid edge,
    and every estimator becomes indistinguishable -- a broken experiment,
    not a scientific result.
    """
    mu, sd = H.mean(0), H.std(0) + 1e-6
    Hn = (H - mu) / sd
    Y = np.eye(K)[y]
    G = Hn.T @ Hn + lam * np.eye(H.shape[1])
    W = np.linalg.solve(G, Hn.T @ Y)
    return {'mu': mu, 'sd': sd, 'W': W}


def apply_readout(H, r):
    return ((H - r['mu']) / r['sd']) @ r['W']


def fit_tau_s(logits_src, y_src, grid):
    """Standard temperature scaling on the labelled SOURCE domain (NLL)."""
    vals = np.array([nll(softmax(logits_src, t), y_src) for t in grid])
    i = int(np.argmin(vals))
    return float(grid[i])


# ------------------------------------------------------------------ estimators
def build_psi_table(z_groups, tau_s, h_ref, T_grid):
    """Vectorised over the whole T grid. Numerically identical to the
    elementwise loop, but ~20x faster -- needed for 600 independent seeds.

    For each group: z (n,K), T_grid (Gt,) -> probs (n,Gt,K) -> confidence
    histograms (Gt,n_bins) on the FIXED probability scale.
    """
    Gt, nb = len(T_grid), N_BINS
    scale = tau_s * np.asarray(T_grid, float)
    off = np.arange(Gt)[None, :] * nb
    out = np.zeros((len(z_groups), Gt))
    for g, z in enumerate(z_groups):
        zz = np.asarray(z, float)[:, None, :] / scale[None, :, None]
        zz = zz - zz.max(axis=-1, keepdims=True)
        e = np.exp(zz)
        p = e / e.sum(axis=-1, keepdims=True)          # (n,Gt,K)
        conf = p.max(axis=-1)                          # (n,Gt)
        idx = np.clip((conf * nb).astype(int), 0, nb - 1)
        flat = (idx + off).ravel()
        h = np.bincount(flat, minlength=Gt * nb).reshape(Gt, nb).astype(float)
        h /= np.clip(h.sum(1, keepdims=True), 1e-12, None)
        d = h - h_ref
        out[g] = (d * d).sum(1)
    return out


def refine(T_grid, y, i):
    if 0 < i < len(y) - 1:
        y0, y1, y2 = y[i - 1], y[i], y[i + 1]
        den = y0 - 2 * y1 + y2
        if abs(den) > 1e-15:
            d = 0.5 * (y0 - y2) / den
            if abs(d) <= 1.0:
                return float(T_grid[i] + d * (T_grid[i] - T_grid[i - 1]))
    return float(T_grid[i])


def fit_global(psi, sizes, T_grid):
    w = np.asarray(sizes, float)
    c = (psi * w[:, None]).sum(0) / w.sum()
    return np.full(psi.shape[0], refine(T_grid, c, int(np.argmin(c))))


def fit_gst(psi, T_grid):
    return np.array([refine(T_grid, psi[g], int(np.argmin(psi[g])))
                     for g in range(psi.shape[0])])


def fit_shrink_global(psi, sizes, T_grid):
    Ti, Tg = np.log(fit_gst(psi, T_grid)), np.log(fit_global(psi, sizes, T_grid))
    tau2 = float(np.var(Ti - Tg, ddof=1)) if len(Ti) > 1 else 0.0
    return np.exp([(1 - tau2 / (tau2 + 0.35 / max(n, 1) + 1e-12)) * Tg[g]
                   + (tau2 / (tau2 + 0.35 / max(n, 1) + 1e-12)) * Ti[g]
                   for g, n in enumerate(sizes)])


def oracle_per_group(z_groups, y_groups, tau_s, T_grid):
    """Cheating skyline: per-group NLL-optimal temperature fitted on TARGET
    labels. Vectorised over T. Used ONLY as an upper bound / F0 gate.
    """
    scale = tau_s * np.asarray(T_grid, float)
    out = np.empty(len(z_groups))
    for g, z in enumerate(z_groups):
        zz = np.asarray(z, float)[:, None, :] / scale[None, :, None]
        zz = zz - zz.max(axis=-1, keepdims=True)
        e = np.exp(zz)
        p = e / e.sum(axis=-1, keepdims=True)          # (n,Gt,K)
        y = np.asarray(y_groups[g], int)
        pt = np.clip(p[np.arange(len(y)), :, y], 1e-12, 1.0)   # (n,Gt)
        v = -np.log(pt).mean(0)
        out[g] = refine(T_grid, v, int(np.argmin(v)))
    return out


def score(z_groups, y_groups, T_hat, tau_s, sizes):
    es, ns, bs = [], [], []
    for g, z in enumerate(z_groups):
        p = softmax(z, tau_s * T_hat[g])
        es.append(ece(p, y_groups[g])); ns.append(nll(p, y_groups[g]))
        bs.append(brier(p, y_groups[g]))
    w = np.asarray(sizes, float)
    return {'ECE': float(np.average(es, weights=w)),
            'NLL': float(np.average(ns, weights=w)),
            'Brier': float(np.average(bs, weights=w))}


# ------------------------------------------------------------------ one seed
def make_groups(rng, G, spread, n_min, n_max, size_skew, K=K_CLASSES):
    fam = np.arange(G) % 3
    if spread == 0:
        fam_mu = np.full(3, np.log(2.4))
    else:
        fam_mu = np.log(2.4) + rng.uniform(-spread, spread, 3)
    T_true = np.exp(fam_mu[fam] + rng.normal(0, 0.08, G))
    raw = rng.lognormal(4.3, 1.25 * max(size_skew, 1e-6), G)
    sizes = np.clip(np.round(raw), n_min, n_max).astype(int)
    return T_true, sizes, fam


def run_seed(seed, arch='mamba', G=12, spread=0.9, homogeneous=False,
             merge_groups=False, shuffle_groups=False,
             T_GRID=None, TAU_GRID=None, n_ref=1200):
    rng = np.random.default_rng(seed)
    if homogeneous:
        spread = 0.0
    T_true, sizes, fam = make_groups(rng, G, spread, 15, 600, 1.0)

    # ---- SOURCE domain (labelled): build + fit readout + fit tau_s ----
    Xs, ys, _ = make_waveforms(rng, n_ref)
    prm = init_mamba(rng) if arch == 'mamba' else init_cnn(rng)
    fwd = mamba_forward if arch == 'mamba' else cnn_forward
    Hs = fwd(Xs, prm)
    readout = fit_readout(Hs, ys)
    logits_src = apply_readout(Hs, readout)
    tau_s = fit_tau_s(logits_src, ys, TAU_GRID)
    h_ref = conf_hist(softmax(logits_src, tau_s))

    # ---- TARGET domain (unlabelled for fitting; labels only for scoring) ----
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

    if merge_groups:                       # F-M1: collapse to one group
        gids[:] = 0
        sizes = np.array([len(y_all)])
    elif shuffle_groups:                   # F-M2: permute group labels
        gids = rng.permutation(gids)

    z_g = [z_all[gids == g] for g in range(len(sizes))]
    y_g = [y_all[gids == g] for g in range(len(sizes))]
    sizes = np.array([len(z) for z in z_g])

    psi = build_psi_table(z_g, tau_s, h_ref, T_GRID)
    T = {'SOURCE': np.ones(len(sizes)),
         'GLOBAL': fit_global(psi, sizes, T_GRID),
         'GST': fit_gst(psi, T_GRID),
         'SHRINK': fit_shrink_global(psi, sizes, T_GRID),
         'ORACLE': oracle_per_group(z_g, y_g, tau_s, T_GRID)}
    if (not merge_groups and not shuffle_groups and len(sizes) == G):
        T['TRUE-T'] = np.asarray(T_true)
    sc = {k: score(z_g, y_g, v, tau_s, sizes) for k, v in T.items()}
    return {'sc': sc, 'delta': sc['GST']['ECE'] - sc['GLOBAL']['ECE'],
            'manipulation_check': sc['SOURCE']['ECE'] - sc['GLOBAL']['ECE'],
            'sizes': sizes.tolist(), 'T_true': T_true.tolist(),
            'tau_s': tau_s, 'arch': arch, 'seed': int(seed)}
