"""Calibration primitives: temperature scaling / Platt scaling / ECE / Brier Score.

1. Temperature fitting uses L-BFGS-B (gradient method) instead of Nelder-Mead.
2. Multiclass calibration support (single global temperature).
3. Bootstrap confidence intervals.
4. ECE binning strategy.
5. Reliability-diagram visualization.
"""

import warnings
import numpy as np
from scipy.optimize import minimize, minimize_scalar
from typing import Tuple, List, Optional

EPS = 1e-7
T_MIN = 0.01
T_MAX = 100.0


def _validate_n_bins(n_bins, upper_bound=10**4):
    """Validate the n_bins argument (shared guard).

    Called by 6 guards inside calibration.py and 4 n_bins functions in scripts/ so
    the guard logic is not duplicated. The upper bound is 10**4 (down from 10**6) to
    match the O(n_bins) Python-loop implementation (a single ece call stays under ~50ms).

    Args:
        n_bins: number of bins to validate
        upper_bound: upper bound (default 10000)

    Returns:
        int(n_bins)

    Raises:
        ValueError: if n_bins is not a positive int/np.integer, is a bool, <1, or > upper_bound
    """
    if isinstance(n_bins, bool) or not isinstance(n_bins, (int, np.integer)) or n_bins < 1 or n_bins > upper_bound:
        raise ValueError(f"n_bins must be a positive integer in [1, {upper_bound}], got {n_bins!r}")
    return int(n_bins)


def to_logit(p: np.ndarray) -> np.ndarray:
    """Probability to logit, with numerical protection."""
    p = np.clip(p, EPS, 1 - EPS)
    return np.log(p / (1 - p))


def sigmoid(x: np.ndarray) -> np.ndarray:
    """Logit to probability, with numerical protection."""
    x = np.clip(x, -30, 30)
    return 1.0 / (1.0 + np.exp(-x))


def nll(a: float, b: float, lg: np.ndarray, y: np.ndarray) -> float:
    """Negative log-likelihood: objective for Platt scaling."""
    z = a * lg + b
    z = np.clip(z, -30, 30)
    return float(-np.mean(y * z - np.log1p(np.exp(z))))


def fit_temperature(val_p, val_y, method: str = "L-BFGS-B") -> float:
    """Fit temperature-scaling parameter T on a validation set.

    1. Uses L-BFGS-B (gradient method) by default, not Nelder-Mead.
    2. Temperature range [0.01, 100.0].
    3. Single global temperature for multiclass (standard practice; Guo et al., 2017).

    Args:
        val_p: validation probabilities, shape (n_samples,) or (n_samples, n_classes)
        val_y: validation labels, shape (n_samples,) or one-hot (n_samples, n_classes)
        method: optimizer ('L-BFGS-B', 'Brent', 'Nelder-Mead')

    Returns:
        optimal temperature T
    """
    val_p = np.asarray(val_p)
    val_y = np.asarray(val_y)

    # Multiclass: single global temperature (standard practice).
    # Reference: Guo et al., 2017 "On Calibration of Modern Neural Networks"
    if val_p.ndim == 2:
        # log-sum-exp trick for numerical stability
        logits = np.log(np.clip(val_p, EPS, 1 - EPS))

        def objective(T_arr):
            T = T_arr[0]
            if T < T_MIN or T > T_MAX:
                return 1e10
            scaled_logits = logits / T
            log_sum_exp = np.max(scaled_logits, axis=1, keepdims=True)
            log_probs = scaled_logits - log_sum_exp - np.log(np.sum(np.exp(scaled_logits - log_sum_exp), axis=1, keepdims=True))
            nll_val = -np.mean(np.sum(val_y * log_probs, axis=1))
            return nll_val

        res = minimize(
            objective,
            x0=np.array([1.0]),
            method="L-BFGS-B",
            bounds=[(T_MIN, T_MAX)],
            options={"maxiter": 100}
        )
        return float(np.clip(res.x[0], T_MIN, T_MAX))

    lg = to_logit(val_p)

    if method == "L-BFGS-B":
        def objective(T_arr):
            T = T_arr[0]
            if T < T_MIN or T > T_MAX:
                return 1e10
            return nll(1.0 / T, 0.0, lg, val_y)

        res = minimize(
            objective,
            x0=np.array([1.0]),
            method="L-BFGS-B",
            bounds=[(T_MIN, T_MAX)],
            options={"maxiter": 100}
        )
        T = float(np.clip(res.x[0], T_MIN, T_MAX))

    elif method == "Brent":
        def objective(T):
            return nll(1.0 / T, 0.0, lg, val_y)

        res = minimize_scalar(
            objective,
            bounds=(T_MIN, T_MAX),
            method='bounded'
        )
        T = float(np.clip(res.x, T_MIN, T_MAX))

    else:
        def objective(T_arr):
            T = T_arr[0]
            if T < T_MIN or T > T_MAX:
                return 1e10
            return nll(1.0 / T, 0.0, lg, val_y)

        res = minimize(
            objective,
            x0=np.array([1.0]),
            method="Nelder-Mead",
            options={"xatol": 1e-4, "fatol": 1e-8, "maxiter": 100}
        )
        T = float(np.clip(res.x[0], T_MIN, T_MAX))

    if not res.success:
        warnings.warn(f"Temperature optimization failed: {res.message}")

    return T


def fit_platt(val_p, val_y):
    """Fit Platt scaling parameters (a, b) on a validation set.

    Platt scaling: p' = sigmoid(a * logit(p) + b)

    Args:
        val_p: validation probabilities, shape (n_samples,)
        val_y: validation labels, shape (n_samples,)

    Returns:
        (a, b) parameter pair
    """
    val_p = np.asarray(val_p)
    val_y = np.asarray(val_y)
    lg = to_logit(val_p)

    def objective(ab):
        a, b = ab
        if a < 0.05 or a > 20.0 or b < -10.0 or b > 10.0:
            return 1e10
        return nll(a, b, lg, val_y)  # No regularization term

    res = minimize(objective, x0=np.array([1.0, 0.0]), method="L-BFGS-B",
                   bounds=[(0.05, 20.0), (-10.0, 10.0)])

    if not res.success:
        warnings.warn(f"Platt optimization failed: {res.message}")

    return float(res.x[0]), float(res.x[1])


def apply_cal(p, a, b) -> np.ndarray:
    """Apply Platt scaling."""
    return sigmoid(a * to_logit(p) + b)


def apply_temperature(p, T) -> np.ndarray:
    """Apply temperature scaling.

    - 1-D input (binary probability): sigmoid(logit(p)/T), equivalent to renormalized p^(1/T).
    - 2-D input (multiclass probability matrix): softmax(log(p)/T), i.e. p^(1/T) normalized per row.

    In both cases the output is strictly normalized (sums to 1).
    """
    T = float(np.clip(T, T_MIN, T_MAX))
    p = np.asarray(p, dtype=float)
    if p.ndim == 1:
        return sigmoid(to_logit(p) / T)
    # Multiclass: normalize log p / T (numerically p^(1/T) / sum).
    p = np.clip(p, EPS, 1.0)
    log_p = np.log(p) / T
    log_p -= log_p.max(axis=-1, keepdims=True)  # Numerically stable
    out = np.exp(log_p)
    return out / out.sum(axis=-1, keepdims=True)


def ece(probs, labels, n_bins: int = 10, adaptive: bool = False) -> float:
    """Expected Calibration Error


    1. Supports adaptive (equal-mass) binning.
    2. Corrects the last-bin boundary.

    Args:
        probs: predicted probabilities
        labels: ground-truth labels
        n_bins: number of bins
        adaptive: whether to use adaptive binning

    Returns:
        ECE value (lower is better)

    Raises:
        ValueError: raised by _validate_n_bins for invalid n_bins. Callers should let
            it propagate rather than swallow it, to surface programming errors.
    """
    n_bins = _validate_n_bins(n_bins)
    probs = np.asarray(probs, dtype=float)
    labels = np.asarray(labels, dtype=float)

    if adaptive:
        # Adaptive binning (equal mass)
        quantiles = np.linspace(0, 1, n_bins + 1)
        bin_boundaries = np.quantile(probs, quantiles)
        bin_boundaries[0] = 0.0
        bin_boundaries[-1] = 1.0
    else:
        bin_boundaries = np.linspace(0, 1, n_bins + 1)

    ece_val = 0.0

    for i in range(n_bins):
        # Boundary fix: all bins are left-closed/right-open; the last bin includes 1.0.
        if i == n_bins - 1:
            mask = (probs >= bin_boundaries[i]) & (probs <= bin_boundaries[i + 1])
        else:
            mask = (probs >= bin_boundaries[i]) & (probs < bin_boundaries[i + 1])

        if mask.sum() == 0:
            continue

        avg_prob = probs[mask].mean()
        avg_label = labels[mask].mean()
        ece_val += mask.sum() / len(probs) * abs(avg_prob - avg_label)

    return float(ece_val)


def smooth_ece(probs, labels, bandwidth: Optional[float] = None) -> float:
    """SmoothECE: kernel-smoothed calibration error (binning-free primary estimator).

    Computation notes:
    - Previously: averaged over a uniform grid (empty grid points diluted the estimate) and bandwidth did not scale with n.
    - Correct implementation (Błasiok & Nakkiran, ICLR 2024): computed at every data point,
      kernel-weighted accuracy minus the point's predicted probability, in absolute value, averaged over data weights:

          smooth_ece = (1/n) * Σ_i | Σ_j w_ij*y_j / Σ_j w_ij − p_i |
          w_ij = exp(-0.5 ((logit(p_i) - logit(p_j))/h)²)

    - A logit-space kernel avoids endpoint saturation in probability space
      (resolution of p is far higher near p=1).
    - Bandwidth default h = 0.45*(n/2000)^(-0.2) (aligns with the preregistered protocol §11 "bandwidth n^(-0.2)"),
    and the calibration floor for perfectly calibrated data is roughly
    ECE ~ 0.028 at n=500, ~0.027 at n=2000, ~0.019 at n=20000,
    ~0.049 at n=200 (information limit).
    Corresponding bandwidths: n=500 -> h~0.594, n=2000 -> h=0.45, n=20000 -> h~0.284, n=200 -> h~0.713.
    Pass bandwidth=0.45 to reproduce the previous fixed-bandwidth behavior.

    Args:
        probs: predicted probabilities (n,)
        labels: ground-truth labels (n,)
        bandwidth: logit-space kernel bandwidth (default 0.45*(n/2000)^(-0.2)).

    Returns:
        SmoothECE value (converges to 0 for perfectly calibrated data).
    """
    probs = np.asarray(probs, dtype=float)
    labels = np.asarray(labels, dtype=float)
    n = len(probs)
    if bandwidth is None:
        # n^(-0.2) scaling (preregistered protocol §11); anchor n=2000 -> 0.45.
        bandwidth = 0.45 * (n / 2000.0) ** (-0.2)

    # logit-space Gaussian kernel
    p_clip = np.clip(probs, 1e-6, 1 - 1e-6)
    logit_p = np.log(p_clip / (1 - p_clip))

    # Block-wise kernel-weighted accuracy to avoid O(n^2) memory (n=10000 full matrix ~800MB)
    abs_err = np.empty(n)
    chunk = max(1, int(2e7 // max(n, 1)))  # ~20M floats per block
    for s in range(0, n, chunk):
        e = min(s + chunk, n)
        z = (logit_p[s:e, None] - logit_p[None, :]) / bandwidth
        w = np.exp(-0.5 * z ** 2)
        w_sum = w.sum(axis=1)
        acc_i = (w * labels[None, :]).sum(axis=1) / np.maximum(w_sum, 1e-12)
        abs_err[s:e] = np.abs(acc_i - probs[s:e])

    return float(abs_err.mean())


def smooth_ece_gpu(probs, labels, bandwidth=None, device=None):
    """PyTorch GPU implementation of smooth_ece (float64, numerically consistent with the CPU version).

    Accelerates many repeated bootstrap/jackknife calls: at n=4050, one CPU call ~0.59s,
    one GPU call ~10ms (measured on RTX 5060). Falls back to CPU automatically when CUDA is unavailable.

    Args/Returns: identical to smooth_ece (same bandwidth logic).
    """
    import torch
    probs = np.asarray(probs, dtype=np.float64)
    labels = np.asarray(labels, dtype=np.float64)
    n = len(probs)
    if bandwidth is None:
        bandwidth = 0.45 * (n / 2000.0) ** (-0.2)

    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
    if device == "cpu" or not torch.cuda.is_available():
        return smooth_ece(probs, labels, bandwidth=bandwidth)

    t_p = torch.from_numpy(probs).to(device)
    t_l = torch.from_numpy(labels).to(device)
    p_clip = torch.clamp(t_p, 1e-6, 1 - 1e-6)
    logit_p = torch.log(p_clip / (1 - p_clip))

    abs_err = torch.empty(n, dtype=torch.float64, device=device)
    chunk = max(1, int(2e7 // max(n, 1)))  # Same blocking strategy as the CPU version
    for s in range(0, n, chunk):
        e = min(s + chunk, n)
        z = (logit_p[s:e, None] - logit_p[None, :]) / bandwidth
        w = torch.exp(-0.5 * z ** 2)
        w_sum = w.sum(dim=1)
        acc_i = (w * t_l[None, :]).sum(dim=1) / torch.clamp(w_sum, min=1e-12)
        abs_err[s:e] = torch.abs(acc_i - t_p[s:e])

    return float(abs_err.mean().item())


def _bca_interval(theta_hat: float, boot_stats: np.ndarray,
                  jackknife_stats: np.ndarray, confidence: float) -> Tuple[float, float]:
    """BCa interval (bias-correction + acceleration).

    The preregistered protocol §7:116 requires BCa (previously the "CI" was only percentile).
    - bias-correction z0: median shift of the bootstrap distribution relative to the point estimate.
    - acceleration a: delete-group/delete-cluster jackknife (Efron 1987 standard formula).
    Returns percentile cut points.

    Known approximation (registered caveat):
    - delete-group jackknife (G groups removed) underestimates the acceleration term by ~sqrt(m)
      relative to delete-1 jackknife (m = mean group size), biasing the CI narrow; cluster
      scenarios use leave-one-cluster-out (one cluster per patient) to approximate delete-1.
    - When theta_hat lies at an extreme of the bootstrap distribution, z0 saturates -> equal cut points -> zero-width CI (warns when triggered).
    """
    from scipy.stats import norm
    boot_stats = np.asarray(boot_stats, dtype=float)
    boot_stats = boot_stats[np.isfinite(boot_stats)]
    B = len(boot_stats)
    if B < 10:
        return (float('nan'), float('nan'))

    prop_less = ((np.sum(boot_stats < theta_hat)
                  + 0.5 * np.sum(boot_stats == theta_hat)) / B)
    z0 = norm.ppf(np.clip(prop_less, 1e-6, 1 - 1e-6))

    j = np.asarray(jackknife_stats, dtype=float)
    j = j[np.isfinite(j)]
    d = j.mean() - j
    denom = 6.0 * float(np.sum(d ** 2)) ** 1.5
    a = float(np.sum(d ** 3)) / denom if denom > 0 else 0.0

    z_alpha = norm.ppf((1 - confidence) / 2)
    z_1alpha = norm.ppf(1 - (1 - confidence) / 2)

    def _adj(z):
        denom_adj = 1 - a * (z0 + z)
        if abs(denom_adj) < 1e-12:
            return 1 - (1 - confidence) / 2 if z > 0 else (1 - confidence) / 2
        return float(norm.cdf(z0 + (z0 + z) / denom_adj))

    a1 = np.clip(_adj(z_alpha), 1e-6, 1 - 1e-6)
    a2 = np.clip(_adj(z_1alpha), 1e-6, 1 - 1e-6)
    lo, hi = np.percentile(boot_stats, [a1 * 100, a2 * 100])
    # 2026-10-11: ordering guard. The BCa percentile mapping can invert exactly when
    # a*(z0+z) crosses 1 between the two cut points; without this guard a degenerate
    # run silently produced lo > hi and poisoned every downstream (lo<0<hi) check.
    if lo > hi:
        lo, hi = hi, lo
        warnings.warn("BCa percentile mapping inverted (a*(z0+z) crossed 1 between the two "
                      "cut points); endpoints swapped. This run is degenerate -- prefer the "
                      "percentile CI sensitivity check for this cell.")
    if lo == hi:
        warnings.warn("BCa interval degenerated to zero width (z0 saturated: point estimate lies at an extreme of the bootstrap distribution),"
                      " CI unavailable -- consider checking the effect size or using a percentile sensitivity check")
    return float(lo), float(hi)


def _group_jackknife_benefit(probs_raw, probs_cal, labels, metric, clusters,
                             n_groups=100, labels_raw=None, rng=None):
    """Jackknife influence values of ΔECE (for the BCa acceleration term).

    When clusters are provided, uses leave-one-cluster-out (patient-level, per protocol);
    otherwise delete-group jackknife (G=min(100,n) groups removed, approximating delete-m,
    to control cost under O(n^2) metrics). Returns ΔECE after each removal.

    labels_raw: correctness (0/1) for the RAW branch. None -> the shared `labels` are
    used on both branches (legacy pre-2026-10-11 semantics; per-branch correctness
    matters only for calibration methods that can flip the argmax, e.g. per-class Platt).
    """
    labels = np.asarray(labels, dtype=float)
    labels_r = np.asarray(labels_raw, dtype=float) if labels_raw is not None else labels
    n = len(labels)
    if clusters is not None:
        clusters = np.asarray(clusters)
        units = np.unique(clusters)
        member_idx = [np.where(clusters == u)[0] for u in units]
    else:
        g = min(n_groups, n)
        # 2026-10-11: consume the caller's rng (legacy behavior reproducible with rng=None);
        # the old code re-created default_rng(0) here, which silently ignored the caller's seed contract.
        perm = (rng if rng is not None else np.random.default_rng(0)).permutation(n)
        member_idx = np.array_split(perm, g)
    jacks = np.empty(len(member_idx))
    for k, idxs in enumerate(member_idx):
        keep = np.ones(n, dtype=bool)
        keep[idxs] = False
        if keep.sum() < 10:
            jacks[k] = np.nan
            continue
        r_b = float(metric(probs_raw[keep], labels_r[keep]))
        c_b = float(metric(probs_cal[keep], labels[keep]))
        jacks[k] = r_b - c_b
    return jacks


def benefit_inference(
    probs_raw: np.ndarray,
    probs_cal: np.ndarray,
    labels: np.ndarray,
    metric=ece,
    n_bootstrap: int = 10000,
    confidence: float = 0.95,
    clusters: Optional[np.ndarray] = None,
    rng: Optional[np.random.Generator] = None,
    bci_method: str = "bca",
    labels_raw: Optional[np.ndarray] = None,
) -> dict:
    """Paired bootstrap inference of calibration benefit (paper primary endpoint).

    Statistical notes:
    - Primary endpoint = absolute benefit ΔECE = metric(probs_raw) - metric(probs_cal), with paired CI.
      (the ratio ECE_raw/ECE_cal has floor-effect and estimator-bias artifacts, demoted to a secondary descriptive quantity).
    - before/after are strongly correlated on the same samples -> must be computed on the same resampling indices (paired).
    - Supports patient-level cluster resampling (clusters=patient id).
    - bci_method='bca' (default; preregistered protocol §7:116 requires BCa, with bias-correction and
      delete-group/leave-one-cluster-out jackknife acceleration); 'percentile' is a sensitivity check only.
    - n_bootstrap defaults to 10000 (preregistered B=10,000; previously train.py passed 2000).
    - Also returns ratio R (secondary) and its percentile CI (ratio may contain inf/nan, so BCa is unstable).

    Args:
        probs_raw: uncalibrated probabilities
        probs_cal: calibrated probabilities (same order as probs_raw)
        labels: ground-truth correctness for the CALIBRATED branch (0/1; top-label case =
            per-branch semantics). If None -> `labels` is used on both branches.
        labels_raw: 0/1 correctness vector for the RAW branch. Defaults to None (legacy:
            the calibrated-argmax correctness was shared across both branches). Pass the
            raw-branch correctness explicitly when the calibration method can flip the
            argmax (per-class Platt, isotonic, vector/matrix/dirichlet, prior rescaling).

    Returns:
        dict(benefit=ΔECE, benefit_ci=(lo,hi), ratio=R, ratio_ci=(lo,hi),
             raw=..., cal=..., method=...)
    """
    probs_raw = np.asarray(probs_raw, dtype=float)
    probs_cal = np.asarray(probs_cal, dtype=float)
    labels = np.asarray(labels, dtype=float)
    # 2026-10-11: per-branch correctness. labels is the calibrated-branch correctness;
    # labels_r is the raw-branch correctness (defaults to the shared vector for back-compat).
    labels_r = (np.asarray(labels_raw, dtype=float)
                if labels_raw is not None else labels)
    n = len(labels)
    if rng is None:
        rng = np.random.default_rng(0)

    raw_point = float(metric(probs_raw, labels_r))
    cal_point = float(metric(probs_cal, labels))
    benefit_point = raw_point - cal_point
    ratio_point = raw_point / cal_point if cal_point > 0 else np.inf

    # n_bootstrap=0: skip CI (fast path)
    if n_bootstrap <= 0:
        return {
            'raw': raw_point,
            'cal': cal_point,
            'benefit': benefit_point,
            'benefit_ci': (float('nan'), float('nan')),
            'ratio': float(ratio_point),
            'ratio_ci': (float('nan'), float('nan')),
            'method': 'none',
        }

    if clusters is not None:
        clusters = np.asarray(clusters)
        uniq = np.unique(clusters)
        cluster_indices = {c: np.where(clusters == c)[0] for c in uniq}
        def draw_indices():
            chosen = rng.choice(uniq, size=len(uniq), replace=True)
            return np.concatenate([cluster_indices[c] for c in chosen])
    else:
        def draw_indices():
            return rng.choice(n, n, replace=True)

    benefits = np.empty(n_bootstrap)
    ratios = np.empty(n_bootstrap)
    for b in range(n_bootstrap):
        idx = draw_indices()
        r_b = float(metric(probs_raw[idx], labels_r[idx]))
        c_b = float(metric(probs_cal[idx], labels[idx]))
        benefits[b] = r_b - c_b
        ratios[b] = r_b / c_b if c_b > 0 else np.nan

    alpha = (1 - confidence) / 2
    r_lo, r_hi = np.nanpercentile(ratios, [alpha * 100, (1 - alpha) * 100])

    if bci_method == "bca":
        jacks = _group_jackknife_benefit(probs_raw, probs_cal, labels,
                                         metric, clusters,
                                         labels_raw=labels_r, rng=rng)
        b_lo, b_hi = _bca_interval(benefit_point, benefits, jacks, confidence)
    else:
        b_lo, b_hi = np.percentile(benefits, [alpha * 100, (1 - alpha) * 100])

    return {
        'raw': raw_point,
        'cal': cal_point,
        'benefit': benefit_point,
        'benefit_ci': (float(b_lo), float(b_hi)),
        'ratio': float(ratio_point),
        'ratio_ci': (float(r_lo), float(r_hi)),
        'method': bci_method,
    }


def bootstrap_ece(
    probs: np.ndarray,
    labels: np.ndarray,
    n_bins: int = 10,
    n_bootstrap: int = 10000,
    confidence: float = 0.95,
    clusters: Optional[np.ndarray] = None,
    rng: Optional[np.random.Generator] = None,
) -> Tuple[float, float, float]:
    """Bootstrap confidence interval for ECE.

    Statistical notes:
    1. Point estimate = full-sample statistic (bootstrap mean used only for CI, not reported as point estimate).
    2. Explicit rng argument for reproducibility.
    3. Supports patient-level cluster resampling (cluster bootstrap, removing CI under-coverage from within-patient correlation).
    4. n_bootstrap defaults to 10000.

    Args:
        probs: predicted probabilities
        labels: ground-truth labels
        n_bins: number of bins
        n_bootstrap: number of bootstrap samples
        confidence: confidence level
        clusters: patient-id array (same length as probs); resample by cluster when provided
        rng: np.random.Generator

    Returns:
        (point_estimate, ci_lower, ci_upper); point_estimate is the full-sample ECE
    """
    n_bins = _validate_n_bins(n_bins)
    probs = np.asarray(probs, dtype=float)
    labels = np.asarray(labels, dtype=float)
    n = len(probs)
    if rng is None:
        rng = np.random.default_rng(0)

    point = ece(probs, labels, n_bins)

    # n_bootstrap=0: skip CI (early-stop fast path)
    if n_bootstrap <= 0:
        return float(point), float('nan'), float('nan')

    # Resampling indices (record-level or patient-level cluster)
    if clusters is not None:
        clusters = np.asarray(clusters)
        uniq = np.unique(clusters)
        cluster_indices = {c: np.where(clusters == c)[0] for c in uniq}
        def draw_indices():
            chosen = rng.choice(uniq, size=len(uniq), replace=True)
            return np.concatenate([cluster_indices[c] for c in chosen])
    else:
        def draw_indices():
            return rng.choice(n, n, replace=True)

    eces = np.empty(n_bootstrap)
    for b in range(n_bootstrap):
        idx = draw_indices()
        eces[b] = ece(probs[idx], labels[idx], n_bins)

    alpha = (1 - confidence) / 2
    ci_lower = np.percentile(eces, alpha * 100)
    ci_upper = np.percentile(eces, (1 - alpha) * 100)

    return float(point), float(ci_lower), float(ci_upper)


def brier_parts(probs, labels, n_bins: int = 10):
    """Brier Score Murphy decomposition (exact identity).

    Brier = Reliability - Resolution + Uncertainty

    Note: with raw mean((p-y)^2) the identity holds exactly only when probabilities are constant within bins;
    here brier_total = REL - RES + UNC (exact by construction),
    while raw Brier is computed separately by brier_raw(probs, labels).

    Args:
        probs: predicted probabilities
        labels: ground-truth labels
        n_bins: number of bins (default 10, matching the original implementation)

    Returns:
        (brier_total, reliability, resolution, uncertainty)
    """
    n_bins = _validate_n_bins(n_bins)
    probs = np.asarray(probs, dtype=float)
    labels = np.asarray(labels, dtype=float)
    n = len(probs)

    bins = np.linspace(0, 1, n_bins + 1)
    reliability = 0.0
    resolution = 0.0
    base_rate = labels.mean()
    uncertainty = base_rate * (1 - base_rate)

    for i in range(n_bins):
        if i == n_bins - 1:  # Last bin includes 1.0
            mask = (probs >= bins[i]) & (probs <= bins[i + 1])
        else:
            mask = (probs >= bins[i]) & (probs < bins[i + 1])

        if mask.sum() == 0:
            continue

        n_bin = mask.sum()
        avg_prob = probs[mask].mean()
        avg_label = labels[mask].mean()

        reliability += n_bin / n * (avg_prob - avg_label) ** 2
        resolution += n_bin / n * (avg_label - base_rate) ** 2

    brier_total = reliability - resolution + uncertainty
    return float(brier_total), float(reliability), float(resolution), float(uncertainty)


def brier_raw(probs, labels) -> float:
    """Empirical Brier Score: mean((p - y)^2)."""
    probs = np.asarray(probs, dtype=float)
    labels = np.asarray(labels, dtype=float)
    return float(np.mean((probs - labels) ** 2))


def mce(probs, labels, n_bins: int = 10) -> float:
    """Maximum Calibration Error

    Metric: calibration error of the worst bin.

    Args:
        probs: predicted probabilities
        labels: ground-truth labels
        n_bins: number of bins

    Returns:
        MCE value (lower is better)

    Raises:
        ValueError: raised by _validate_n_bins for invalid n_bins. Callers should let
            it propagate rather than swallow it, to surface programming errors.
    """
    n_bins = _validate_n_bins(n_bins)
    probs = np.asarray(probs, dtype=float)
    labels = np.asarray(labels, dtype=float)

    bin_boundaries = np.linspace(0, 1, n_bins + 1)
    max_error = 0.0

    for i in range(n_bins):
        if i == n_bins - 1:
            mask = (probs >= bin_boundaries[i]) & (probs <= bin_boundaries[i + 1])
        else:
            mask = (probs >= bin_boundaries[i]) & (probs < bin_boundaries[i + 1])

        if mask.sum() == 0:
            continue

        avg_prob = probs[mask].mean()
        avg_label = labels[mask].mean()
        error = abs(avg_prob - avg_label)
        max_error = max(max_error, error)

    return float(max_error)


def plot_reliability_diagram(
    probs: np.ndarray,
    labels: np.ndarray,
    n_bins: int = 10,
    title: str = "Reliability Diagram",
    save_path: Optional[str] = None
):
    """Plot the calibration (reliability) curve.

    Args:
        probs: predicted probabilities
        labels: ground-truth labels
        n_bins: number of bins
        title: plot title
        save_path: output path (optional)
    """
    n_bins = _validate_n_bins(n_bins)
    import matplotlib.pyplot as plt

    probs = np.asarray(probs)
    labels = np.asarray(labels)

    bin_boundaries = np.linspace(0, 1, n_bins + 1)
    bin_centers = []
    bin_means = []
    bin_counts = []

    for i in range(n_bins):
        if i == n_bins - 1:
            mask = (probs >= bin_boundaries[i]) & (probs <= bin_boundaries[i + 1])
        else:
            mask = (probs >= bin_boundaries[i]) & (probs < bin_boundaries[i + 1])

        if mask.sum() > 0:
            bin_centers.append((bin_boundaries[i] + bin_boundaries[i + 1]) / 2)
            bin_means.append(labels[mask].mean())
            bin_counts.append(mask.sum())

    fig, ax = plt.subplots(1, 1, figsize=(6, 6))

    ax.plot([0, 1], [0, 1], 'k--', label='Perfect calibration')

    ax.plot(bin_centers, bin_means, 's-', label='Model', color='blue')

    ax2 = ax.twinx()
    ax2.bar(bin_centers, bin_counts, width=0.05, alpha=0.3, color='gray', label='Sample count')
    ax2.set_ylabel('Sample count')

    ax.set_xlabel('Mean predicted probability')
    ax.set_ylabel('Fraction of positives')
    ax.set_title(title)
    ax.legend(loc='upper left')

    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')

    return fig


def compute_all_metrics(
    probs: np.ndarray,
    labels: np.ndarray,
    n_bins: int = 10,
    n_bootstrap: int = 1000
) -> dict:
    """Compute all calibration metrics.

    Args:
        probs: predicted probabilities
        labels: ground-truth labels
        n_bins: number of bins
        n_bootstrap: number of bootstrap samples

    Returns:
        dict containing all metrics
    """
    n_bins = _validate_n_bins(n_bins)
    probs = np.asarray(probs)
    labels = np.asarray(labels)

    ece_mean, ece_lower, ece_upper = bootstrap_ece(probs, labels, n_bins, n_bootstrap)

    brier, reliability, resolution, uncertainty = brier_parts(probs, labels, n_bins=n_bins)

    max_ce = mce(probs, labels, n_bins)

    return {
        'ece': ece_mean,
        'ece_ci_95': (ece_lower, ece_upper),
        'mce': max_ce,
        'brier': brier,
        'brier_raw': brier_raw(probs, labels),
        'brier_reliability': reliability,
        'brier_resolution': resolution,
        'brier_uncertainty': uncertainty,
    }


def two_layer_benefit_inference(
    probs_raw_test: np.ndarray,
    labels_test: np.ndarray,
    fit_probs: np.ndarray,
    fit_labels: np.ndarray,
    fit_fn,
    apply_fn,
    metric=ece,
    b_val: int = 200,
    b_test: int = 2000,
    confidence: float = 0.95,
    rng: Optional[np.random.Generator] = None,
) -> dict:
    """Two-layer joint bootstrap (preregistered protocol §7:117: "resample val -> fit T -> resample test -> metric").

    Temperature-fit-set uncertainty is propagated into the ΔECE CI:
    - Layer 1 (b_val times): resample the temperature-fit set with replacement -> refit via fit_fn -> T distribution.
    - Layer 2 (b_test times): resample the test set with replacement (idx) -> draw T_b from the T distribution -> apply_fn ->
      paired ΔECE_b.
    CI = joint percentile of T-uncertainty + resampling-uncertainty (non-nested implementation, tractable cost;
    protocol note: nested B=10000 x refit is infeasible under O(n^2) metrics, so this is an honest approximation and is registered).

    Args:
        probs_raw_test: uncalibrated test probabilities (1D max-prob or 2D matrix, consistent with fit/apply closures).
        labels_test: test labels (top-label case is the correct mask, consistent with the primary endpoint).
        fit_probs/fit_labels: temperature-fit-set probabilities/labels (protocol: cal split).
        fit_fn: fitting closure (probs, labels) -> T.
        apply_fn: application closure (probs, T) -> calibrated probabilities.
        metric: calibration error (primary endpoint = smooth_ece, passed by caller).
        b_val/b_test: repetition counts for the two layers.
        rng: Generator

    Returns:
        dict(t_hat, t_std, benefit, benefit_ci, benefit_ci_percentile_only)
    """
    probs_raw_test = np.asarray(probs_raw_test)
    labels_test = np.asarray(labels_test, dtype=float)
    fit_probs = np.asarray(fit_probs)
    fit_labels = np.asarray(fit_labels)
    if rng is None:
        rng = np.random.default_rng(0)

    t_hat = float(fit_fn(fit_probs, fit_labels))
    n_fit = len(fit_labels)
    n_test = len(labels_test)

    t_draws = np.empty(b_val)
    n_fit_failed = 0
    for b in range(b_val):
        idx = rng.choice(n_fit, n_fit, replace=True)
        try:
            t_draws[b] = float(fit_fn(fit_probs[idx], fit_labels[idx]))
        except Exception:
            # 2026-10-11: degenerate resample (e.g. all-one-class or rank-loss) used to
            # propagate a NaN straight into t_draws/t_std. Fall back to the full-set
            # temperature so the layer-2 draw stays finite.
            t_draws[b] = t_hat
            n_fit_failed += 1
    if n_fit_failed:
        warnings.warn(f"two_layer bootstrap: {n_fit_failed}/{b_val} layer-1 refits "
                      f"failed and fell back to the full-set temperature t_hat.")
    t_std = float(np.std(t_draws, ddof=1)) if b_val > 1 else 0.0

    benefits = np.empty(b_test)
    for b in range(b_test):
        idx = rng.choice(n_test, n_test, replace=True)
        t_b = float(rng.choice(t_draws)) if b_val > 0 else t_hat
        probs_cal_b = apply_fn(probs_raw_test[idx], t_b)
        mp_raw = (probs_raw_test[idx].max(axis=1)
                  if probs_raw_test.ndim == 2 else probs_raw_test[idx])
        mp_cal = probs_cal_b.max(axis=1) if probs_cal_b.ndim == 2 else probs_cal_b
        benefits[b] = float(metric(mp_raw, labels_test[idx])) \
            - float(metric(mp_cal, labels_test[idx]))

    alpha = (1 - confidence) / 2 * 100
    lo, hi = np.percentile(benefits, [alpha, 100 - alpha])

    mp_raw_full = (probs_raw_test.max(axis=1)
                   if probs_raw_test.ndim == 2 else probs_raw_test)
    cal_full = apply_fn(probs_raw_test, t_hat)
    mp_cal_full = cal_full.max(axis=1) if cal_full.ndim == 2 else cal_full
    benefit_point = (float(metric(mp_raw_full, labels_test))
                     - float(metric(mp_cal_full, labels_test)))

    return {
        't_hat': t_hat,
        't_std': t_std,
        'benefit': benefit_point,
        'benefit_ci': (float(lo), float(hi)),
        'b_val': b_val,
        'b_test': b_test,
    }
