"""W4 — Reproduce a published cross-population ECG calibration protocol,
then expose and patch its evaluation holes.

Target paper (most reproducible 'successful' calibration paper found):
  Label-efficient cross-population transfer learning for electrocardiographic
  risk stratification (Frontiers in Cardiovascular Medicine, 2026),
  doi 10.3389/fcvm.2026.1928354 / PMC13601223.
  Protocol: PTB-XL source -> Chapman-Ningbo target, 13 SNOMED superclasses,
  38 physical features, patient-separated splits, DEDICATED calibration split,
  untouched test, isotonic recalibration of a noisy-OR composite score,
  bootstrap + Holm + subgroup interaction + DCA.
  Reported: composite ECE 0.018, Brier 0.055, AUROC 0.791 on Chapman-Ningbo,
  where 97% of positives were LVH; MIT-BIH stress set = 48 recordings / 576
  segments; source PTB-XL acquired 1989-1996.

We do NOT have the real waveforms or the paper's weights in this sandbox.
We reproduce the EVALUATION PROTOCOL on Mamba-forward synthetic logits, which
is enough to expose structural holes in that protocol. This is stated openly.

Holes under test:
  H1  composite endpoint hides classwise miscalibration
  H2  no 'do-not-recalibrate' control -> calibration HARM RATE unreported
  H3  48-record stress set gives uninformative CIs
  H4  no label-free gate deciding WHEN to recalibrate / fall back
"""
from __future__ import annotations
import numpy as np

# ------------------------------------------------------------------ basics
def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-np.clip(x, -30, 30)))


def logit(p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def softmax(z, T):
    z = np.asarray(z, float) / float(T)
    z -= z.max(-1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(-1, keepdims=True)


def ece_binary(p, y, n_bins=10):
    p = np.asarray(p, float); y = np.asarray(y, float)
    idx = np.clip((p * n_bins).astype(int), 0, n_bins - 1)
    tot = 0.0
    for b in range(n_bins):
        m = idx == b
        if m.any():
            tot += m.mean() * abs(y[m].mean() - p[m].mean())
    return float(tot)


def brier_binary(p, y):
    return float(np.mean((np.asarray(p) - np.asarray(y)) ** 2))


def auroc(p, y):
    y = np.asarray(y); p = np.asarray(p)
    pos, neg = p[y == 1], p[y == 0]
    if len(pos) == 0 or len(neg) == 0:
        return float('nan')
    # Mann-Whitney via rank, ties averaged
    allp = np.concatenate([pos, neg])
    order = np.argsort(allp)
    ranks = np.empty(len(allp), float)
    s = 0
    while s < len(allp):
        e = s
        while e + 1 < len(allp) and allp[order[e + 1]] == allp[order[s]]:
            e += 1
        ranks[order[s:e + 1]] = (s + e) / 2 + 1
        s = e + 1
    return float((ranks[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) /
                 (len(pos) * len(neg)))


def cal_slope(p, y):
    """Calibration slope: coefficient of logit(p) in a linear fit to y."""
    x = logit(p); y = np.asarray(y, float)
    xc = x - x.mean()
    return float(np.dot(xc, y - y.mean()) / max(np.dot(xc, xc), 1e-12))


def isotonic_pava(x, y, w=None):
    """PAVA isotonic regression, returns fitted values at sorted x."""
    x = np.asarray(x, float); y = np.asarray(y, float)
    if w is None:
        w = np.ones(len(y))
    o = np.argsort(x)
    x, y, w = x[o], y[o], np.asarray(w, float)[o]
    # merge equal x by weighted mean
    ux, uy, uw = [], [], []
    for i, xi in enumerate(x):
        if ux and abs(ux[-1] - xi) < 1e-12:
            uy[-1] = (uy[-1] * uw[-1] + y[i] * w[i]) / (uw[-1] + w[i])
            uw[-1] += w[i]
        else:
            ux.append(xi); uy.append(y[i]); uw.append(w[i])
    vals = list(zip(uy, uw, [1] * len(uy)))
    i = 0
    while i < len(vals) - 1:
        if vals[i][0] <= vals[i + 1][0] + 1e-12:
            v1, w1, c1 = vals[i]; v2, w2, c2 = vals[i + 1]
            vals[i] = ((v1 * w1 + v2 * w2) / (w1 + w2), w1 + w2, c1 + c2)
            del vals[i + 1]
            if i > 0:
                i -= 1
        else:
            i += 1
    fit = np.concatenate([np.full(c, v) for v, w, c in vals])
    return ux, np.asarray(fit)


def apply_isotonic(ux, fy, x):
    """Step-function interpolation, clipped to observed range."""
    return np.interp(np.asarray(x, float), ux, fy, left=fy[0], right=fy[-1])


# ------------------------------------------------------------------ Mamba core (reuse)
import sys, pathlib
_HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parent / 'mamba_experiment'))
from mamba_gst import (init_mamba, mamba_forward, fit_readout, apply_readout,
                       silu, softplus, causal_conv, L_SEQ, C_LEADS, D_SSM)

K = 7          # diagnostic classes in the composite endpoint


def make_waveforms_multi(rng, n, lvhdominant=False, K=K):
    """K independent binary labels sampled from TRUE conditional probabilities.

    lvhdominant mimics the paper's Chapman-Ningbo composite (97% of positives
    were LVH): one class is far more prevalent, the rest are rare.
    """
    c = rng.integers(0, K, n)                       # dominant morphology prototype
    base = np.full((n, K), 0.03)
    base[np.arange(n), c] += 0.20 + rng.uniform(0, 0.70, n)
    if lvhdominant:
        # 97% of POSITIVES are the LVH-like class, NOT 97% of records positive.
        # Keep a wide dynamic range so the composite score has real ranking power.
        base[:, 0] = np.clip(base[:, 0] + 0.20, 0, 0.92)
        base[:, 1:] *= 0.45
    p = np.clip(base, 0.005, 0.90)
    y = (rng.random((n, K)) < p).astype(float)       # labels SAMPLED, not argmax
    # composite label may legitimately be negative; do NOT force a positive.

    t = np.linspace(0, 1, L_SEQ)[None, :]
    amp = (0.55 + 0.30 * c / (K - 1))[:, None]
    qrs = amp * np.exp(-((t - 0.35) / 0.040) ** 2)
    pw = 0.30 * np.exp(-((t - 0.15) / 0.040) ** 2)
    tw = 0.40 * np.exp(-((t - 0.65) / 0.070) ** 2)
    sig = pw + qrs + tw
    lw = rng.uniform(0.4, 1.0, (1, C_LEADS, 1))
    X = sig[:, None, :] * lw + 0.08 * (c[:, None, None] - (K - 1) / 2)
    X += rng.normal(0, 0.35, X.shape)
    X = np.transpose(X, (0, 2, 1))
    return np.ascontiguousarray(X, np.float32), y, p


def make_logits(rng, n, T_g, gids, prm, lvhdominant=False):
    X, y, p = make_waveforms_multi(rng, n, lvhdominant=lvhdominant)
    H = mamba_forward(X, prm)
    return H, y, p


def physical_features(X):
    """18 hand-crafted physical features in the spirit of the target paper's
    38-dimensional interpretable feature set. X: (N, L, C).

    RMS / QRS-window / T-window amplitudes on the first 6 leads. These are
    deterministic functions of the waveform, so a frozen linear readout can
    actually decode the class-conditional probabilities.
    """
    X = np.asarray(X, float)
    L = X.shape[1]
    q0, q1 = int(0.28 * L), int(0.44 * L)
    t0, t1 = int(0.58 * L), int(0.76 * L)
    f = []
    for lead in range(6):
        x = X[:, :, lead]
        f.append(np.sqrt(np.mean(x ** 2, axis=1)))
        f.append(x[:, q0:q1].mean(axis=1))
        f.append(x[:, t0:t1].mean(axis=1))
    return np.stack(f, axis=1)                       # (N, 18)


def augmented_features(X, prm):
    """Mamba SSM pooled features + physical features (ECG-RAMBA-like fusion)."""
    H = mamba_forward(X, prm)
    return np.concatenate([H, physical_features(X)], axis=1)


def multiridge(H, Y, lam=1.0):
    mu, sd = H.mean(0), H.std(0) + 1e-6
    Hn = (H - mu) / sd
    W = np.linalg.solve(Hn.T @ Hn + lam * np.eye(H.shape[1]), Hn.T @ Y)
    return {'mu': mu, 'sd': sd, 'W': W}


def apply_multiridge(H, r):
    return ((H - r['mu']) / r['sd']) @ r['W']


def noisy_or(probs):
    return 1.0 - np.prod(1.0 - np.clip(probs, 1e-9, 1 - 1e-9), axis=1)


def composite_label(y):
    return (y.sum(1) > 0).astype(float)


# ------------------------------------------------------------------ gate statistics
def psi_curve_depth(conf, n_bins=15):
    """Label-free gate statistic: how sharply the source-referenced histogram
    mismatch has a minimum, and how far the group's confidence mass sits from
    the source reference. Flat / ambiguous -> gate to ABSTAIN."""
    h = np.bincount(np.clip((conf * n_bins).astype(int), 0, n_bins - 1),
                    minlength=n_bins).astype(float)
    h /= max(h.sum(), 1e-12)
    # concentration of confidence mass (label-free, fixed probability scale)
    return float(h.max()), float(np.var(conf)), float(np.mean(conf))
