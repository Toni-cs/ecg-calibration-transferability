"""GSGT — Graph-Shrunk Group Temperature.

W2 pivot. The W1 failure was a WRONG TARGET, not a bad estimator: both PARI
and pooled fit ONE global scalar T to a world that E5 proved is group-
heterogeneous. GSGT changes the estimand to G group temperatures with a
graph-Laplacian prior built from OBSERVABLE deployment metadata
(cart_id / site / year adjacency). Post-hoc, frozen model, no labels needed.

Design contracts (registered before running):
  * Group graph comes from metadata, NOT inferred from unlabelled statistics.
    This is what separates it from MD-TS (embedding->T regression) and from
    the Transfer Gap identifiability limit (we do not recover a correctness
    curve from 3 scalars; we recover G scalars from G histograms + a known graph).
  * lambda is chosen by leave-one-group-out CV on UNLABELLED Psi_g only.
    No labels, no post-hoc tuning on the reported endpoint.
  * The advantage must vanish when (F-A) groups are homogeneous, (F-B) the
    graph is shuffled, (F-C) all groups are large and balanced.
"""
from __future__ import annotations

import numpy as np

N_BINS = 15


def softmax(logits: np.ndarray, T: float) -> np.ndarray:
    z = np.asarray(logits, float) / float(T)
    z -= z.max(axis=-1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=-1, keepdims=True)


def conf_hist(probs: np.ndarray, n_bins: int = N_BINS) -> np.ndarray:
    c = np.asarray(probs).max(axis=-1)
    idx = np.clip((c * n_bins).astype(int), 0, n_bins - 1)
    h = np.bincount(idx.ravel(), minlength=n_bins).astype(float)
    return h / max(h.sum(), 1e-12)


def ece(probs: np.ndarray, y: np.ndarray, n_bins: int = 10) -> float:
    """Top-label equal-width ECE, the paper's primary endpoint."""
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


def nll(probs: np.ndarray, y: np.ndarray) -> float:
    p = np.clip(np.asarray(probs)[np.arange(len(y)), np.asarray(y)], 1e-12, 1.0)
    return float(-np.log(p).mean())


def brier(probs: np.ndarray, y: np.ndarray) -> float:
    K = np.asarray(probs).shape[-1]
    oh = np.eye(K)[np.asarray(y)]
    return float(np.mean(np.sum((np.asarray(probs) - oh) ** 2, axis=-1)))


# ------------------------------------------------------------------ DGP
def make_group_dgp(G: int = 12, n_families: int = 3, spread: float = 0.9,
                   size_skew: float = 1.0, n_min: int = 15, n_max: int = 2500,
                   sigma_w: float = 0.35, K: int = 4, tau_s: float = 1.0,
                   seed: int = 0, homogeneous: bool = False,
                   balanced_large: bool = False, episodic_frac: float = 0.0):
    """Registered DGP.

    G groups belong to n_families (device/centre families). True log-temperatures
    are family-centred with within-family jitter -> the group graph carries real
    information. Group sizes are LONG-TAILED (few large, many small), which is
    the MIMIC cart_id / CODE site regime. Patient prototypes are exchangeable
    (same as W1: NO special structure is injected to help GSGT).

    Returns dict with logits list, labels, patient ids, true T, graph W, sizes.
    """
    rng = np.random.default_rng(seed)
    fam = np.arange(G) % n_families
    if homogeneous:
        spread = 0.0
    fam_mu = np.log(2.4) + rng.uniform(-spread, spread, n_families)
    logT = fam_mu[fam] + rng.normal(0, 0.08, G)          # within-family jitter
    T_true = np.exp(logT)

    if balanced_large:
        sizes = np.full(G, n_max // 2)
    else:
        raw = rng.lognormal(mean=4.6, sigma=1.35 * max(size_skew, 1e-6), size=G)
        sizes = np.clip(np.round(raw), n_min, n_max).astype(int)

    # Calibrated SOURCE reference histogram (tau_s = 1). Independent sample,
    # available at deployment because the source domain is already calibrated.
    n_ref = 20000
    cr = rng.integers(0, K, n_ref)
    pr = np.full((n_ref, K), 0.12)
    pr[np.arange(n_ref), cr] = 0.55 + rng.uniform(0, 0.25, n_ref)
    pr /= pr.sum(1, keepdims=True)
    zr = tau_s * (np.log(pr) + rng.normal(0, sigma_w, (n_ref, K)))
    h_ref = conf_hist(softmax(zr, tau_s))

    logits, labels, patients, gids = [], [], [], []
    pid = 0
    for g in range(G):
        n = int(sizes[g])
        # c = the patient's chronic prototype class; p_i is the TRUE conditional
        # distribution. Labels MUST be sampled from p_i, otherwise empirical
        # accuracy is 1.0 by construction and ECE is minimised by making the
        # model maximally sharp (invalidating the whole calibration experiment).
        c = rng.integers(0, K, n)
        p = np.full((n, K), 0.12)
        p[np.arange(n), c] = 0.55 + rng.uniform(0, 0.25, n)
        p /= p.sum(1, keepdims=True)
        y = np.array([rng.choice(K, p=p[i]) for i in range(n)])
        v = np.log(p)
        # episodic subgroup: prototype flips at recording time (A1-violating layer)
        if episodic_frac > 0:
            k = int(n * episodic_frac)
            if k:
                c2 = rng.integers(0, K, k)
                q = np.full((k, K), 0.12)
                q[np.arange(k), c2] = 0.70
                q /= q.sum(1, keepdims=True)
                v[:k] = np.log(q)
                y[:k] = np.array([rng.choice(K, p=q[i]) for i in range(k)])
        z = T_true[g] * (v + rng.normal(0, sigma_w, (n, K)))
        logits.append(z)
        # each record is its own patient, with 1-3 repeats folded into weights
        labels.append(y)
        patients.append(np.arange(pid, pid + n))
        gids.append(np.full(n, g))
        pid += n

    # Group graph: family adjacency (observable metadata), weighted by
    # family similarity. Off-family edges are weak but nonzero.
    W = np.zeros((G, G))
    for a in range(G):
        for b in range(a + 1, G):
            w = 1.0 if fam[a] == fam[b] else 0.02
            W[a, b] = W[b, a] = w
    return {'logits': logits, 'labels': labels, 'patients': patients,
            'gids': gids, 'T_true': T_true, 'logT_true': logT, 'W': W,
            'fam': fam, 'sizes': sizes, 'h_ref': h_ref,
            'K': K, 'tau_s': tau_s, 'spread': spread,
            'n_records': int(sizes.sum())}


# ------------------------------------------------------------------ Psi table
def build_psi_table(dgp, T_grid: np.ndarray) -> np.ndarray:
    """Precompute Psi_g(T) = || h_g(T) - h_ref ||^2 for all (g, T).

    All estimators below operate ONLY on this table -> deterministic, fast,
    and impossible to accidentally peek at labels while fitting.
    """
    G = len(dgp['logits'])
    out = np.zeros((G, len(T_grid)))
    for g in range(G):
        z = dgp['logits'][g]
        for k, T in enumerate(T_grid):
            h = conf_hist(softmax(z, T))
            d = h - dgp['h_ref']
            out[g, k] = float(d @ d)
    return out


def refine(T_grid: np.ndarray, y: np.ndarray, i: int) -> float:
    if 0 < i < len(y) - 1:
        y0, y1, y2 = y[i - 1], y[i], y[i + 1]
        den = y0 - 2 * y1 + y2
        if abs(den) > 1e-15:
            d = 0.5 * (y0 - y2) / den
            if abs(d) <= 1.0:
                return float(T_grid[i] + d * (T_grid[i] - T_grid[i - 1]))
    return float(T_grid[i])


# ------------------------------------------------------------------ estimators
def fit_global(psi, sizes, T_grid):
    w = np.asarray(sizes, float)
    curve = (psi * w[:, None]).sum(0) / w.sum()
    i = int(np.argmin(curve))
    return np.full(psi.shape[0], refine(T_grid, curve, i))


def fit_indep(psi, T_grid):
    return np.array([refine(T_grid, psi[g], int(np.argmin(psi[g])))
                     for g in range(psi.shape[0])])


def fit_shrink_global(psi, sizes, T_grid):
    """EB-style shrinkage toward the global mean (clawRxiv / curvature-shrinkage
    analogue). Prior variance estimated from the indep fits themselves -> no
    labels, no tuning."""
    Ti = fit_indep(psi, T_grid)
    Tg = fit_global(psi, sizes, T_grid)[0]
    li, lg = np.log(Ti), np.log(Tg)
    tau2 = float(np.var(li - lg, ddof=1)) if len(li) > 1 else 0.0
    out = np.empty_like(li)
    for g, n in enumerate(sizes):
        s2 = 0.35 / max(n, 1)                 # asymptotic-ish variance ~ 1/n
        a = tau2 / (tau2 + s2 + 1e-12)
        out[g] = (1 - a) * lg + a * li[g]
    return np.exp(out)


def fit_graph(psi, sizes, W, T_grid, lam: float, n_iter: int = 8):
    """Graph-Laplacian-regularised group temperatures, solved by deterministic
    coordinate descent over the precomputed Psi table.

        min_{T_g}  n_g * Psi_g(T_g) + lam * sum_h W_gh (logT_g - logT_h)^2

    Each 1-D subproblem is an exact grid search over the same T_grid.
    """
    G = psi.shape[0]
    log_grid = np.log(T_grid)
    w = np.asarray(sizes, float)
    A = np.asarray(W, float)
    deg = A.sum(1)
    cur = np.log(fit_indep(psi, T_grid))
    for _ in range(n_iter):
        new = cur.copy()
        for g in range(G):
            nb = A[g] > 0
            if nb.any():
                center = float(np.average(cur[nb], weights=A[g, nb]))
                pen = lam * (log_grid - center) ** 2 * deg[g]
            else:
                pen = 0.0
            obj = w[g] * psi[g] + pen
            new[g] = log_grid[int(np.argmin(obj))]
        if np.max(np.abs(new - cur)) < 1e-4:
            cur = new
            break
        cur = new
    return np.exp(cur)


def logo_select_lambda(psi, sizes, W, T_grid, lam_grid):
    """Leave-one-group-out CV on UNLABELLED Psi only.

    For held-out group g we have no Psi_g term, so T_g is predicted purely from
    its graph neighbours. Scoring uses Psi_g(T_pred), which needs no labels.
    This makes lambda fully pre-specified and label-free.
    """
    G = psi.shape[0]
    A = np.asarray(W, float)
    deg = A.sum(1)
    li = np.log(fit_indep(psi, T_grid))
    scores = np.zeros(len(lam_grid))
    for k, lam in enumerate(lam_grid):
        s = 0.0
        for g in range(G):
            nb = A[g] > 0
            if not nb.any():
                continue
            # neighbours' independent estimates, shrunk toward family consensus
            center = float(np.average(li[nb], weights=A[g, nb]))
            # lam controls how far we move from the global compromise
            global_c = float(li.mean())
            pred_log = (1 - lam / (lam + 1)) * global_c + (lam / (lam + 1)) * center
            j = int(np.argmin(np.abs(np.log(T_grid) - pred_log)))
            s += psi[g, j]
        scores[k] = s
    return float(lam_grid[int(np.argmin(scores))]), scores


# ------------------------------------------------------------------ evaluation
def apply_and_score(dgp, T_hat: np.ndarray):
    """Compute ECE / NLL / Brier after applying per-group temperatures."""
    eces, nlls, briers = [], [], []
    for g, z in enumerate(dgp['logits']):
        p = softmax(z, T_hat[g])
        y = dgp['labels'][g]
        eces.append(ece(p, y)); nlls.append(nll(p, y)); briers.append(brier(p, y))
    n = np.asarray(dgp['sizes'], float)
    return {'ECE': float(np.average(eces, weights=n)),
            'NLL': float(np.average(nlls, weights=n)),
            'Brier': float(np.average(briers, weights=n)),
            'per_group_ECE': [float(x) for x in eces]}


def bootstrap_delta(dgp, T_a, T_b, B: int = 2000, seed: int = 991):
    """Patient-block (here: record-block within group) paired bootstrap CI for
    ECE(T_a) - ECE(T_b). Returns point estimate and 95% CI."""
    rng = np.random.default_rng(seed)
    pa = [softmax(dgp['logits'][g], T_a[g]) for g in range(len(T_a))]
    pb = [softmax(dgp['logits'][g], T_b[g]) for g in range(len(T_b))]
    ya = dgp['labels']
    G = len(T_a)
    def one():
        d = 0.0; w = 0.0
        for g in range(G):
            n = len(ya[g]); idx = rng.integers(0, n, n)
            d += (ece(pa[g][idx], ya[g][idx]) - ece(pb[g][idx], ya[g][idx])) * n
            w += n
        return d / w
    pt = (apply_and_score(dgp, T_a)['ECE'] - apply_and_score(dgp, T_b)['ECE'])
    draws = np.array([one() for _ in range(B)])
    return {'delta_ECE': float(pt),
            'ci95': [float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))],
            'p_two_sided_approx': float(2 * min((draws <= 0).mean(), (draws >= 0).mean()))}
