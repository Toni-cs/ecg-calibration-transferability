"""PARI — Patient-Anchored Repeated-measure Invariance.

Reusable core for the W1 synthetic identification experiment and the later
T1 (1.15M-record) run.

Design contract (must be preserved in the paper):
  * phi() must live on a FIXED probability scale (equal-width confidence bins
    or moment features). Rank/order statistics are invariant to any monotone
    temperature T and therefore CARRY NO IDENTIFYING INFORMATION about T.
  * The statistical unit is the patient orbit (paired source/target records of
    the same patient), not the individual record.
"""
from __future__ import annotations

import numpy as np

N_BINS = 15


def softmax(logits: np.ndarray, T: float) -> np.ndarray:
    z = np.asarray(logits, dtype=float) / float(T)
    z = z - z.max(axis=-1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=-1, keepdims=True)


def confidence_hist(probs: np.ndarray, n_bins: int = N_BINS) -> np.ndarray:
    """Equal-width histogram of top-label confidence on a FIXED [0,1] scale."""
    conf = np.asarray(probs).max(axis=-1)
    idx = np.clip((conf * n_bins).astype(int), 0, n_bins - 1)
    h = np.bincount(idx.ravel(), minlength=n_bins).astype(float)
    s = h.sum()
    return h / s if s > 0 else h


def confidence_hist_per_patient(logits: np.ndarray, T: float,
                                n_bins: int = N_BINS) -> np.ndarray:
    """Per-patient confidence histogram.

    logits: (n_pat, n_rec, K) -> (n_pat, n_bins)
    Vectorised: one bincount over patient-offset bin indices.
    """
    logits = np.asarray(logits, dtype=float)
    n_pat, n_rec, _ = logits.shape
    conf = softmax(logits, T).max(axis=-1)                  # (n_pat, n_rec)
    idx = np.clip((conf * n_bins).astype(int), 0, n_bins - 1)
    off = np.arange(n_pat)[:, None] * n_bins
    flat = (idx + off).ravel()
    h = np.bincount(flat, minlength=n_pat * n_bins).reshape(n_pat, n_bins).astype(float)
    return h / np.clip(h.sum(1, keepdims=True), 1e-12, None)


def psi_pari(logits_src: np.ndarray, logits_tgt: np.ndarray,
             T_grid: np.ndarray, tau_s: float = 1.0,
             shuffle_pairs: bool = False,
             n_bins: int = N_BINS) -> np.ndarray:
    """PARI objective.

        Delta_i(T) = mean_j phi(softmax(z_tgt_ij / T))
                     - mean_j phi(softmax(z_src_ij / tau_s))
        Psi_P(T)   = || mean_i Delta_i(T) ||^2

    The within-patient pairing cancels the patient's chronic state p_i, which
    is the variance-reduction mechanism that 1M-scale repeated ECGs enable.
    """
    ref = confidence_hist_per_patient(logits_src, tau_s, n_bins)
    if shuffle_pairs:                       # F1: destroy the pairing
        ref = np.roll(ref, shift=1, axis=0)
    out = np.zeros(len(T_grid), dtype=float)
    for k, T in enumerate(T_grid):
        obs = confidence_hist_per_patient(logits_tgt, T, n_bins)
        d = (obs - ref).mean(axis=0)
        out[k] = float(d @ d)
    return out


def psi_pooled(logits_src: np.ndarray, logits_tgt: np.ndarray,
               T_grid: np.ndarray, tau_s: float = 1.0,
               n_bins: int = N_BINS) -> np.ndarray:
    """Unpaired control: mix all records, match one pooled reference histogram."""
    K = logits_src.shape[-1]
    ref = confidence_hist(softmax(logits_src.reshape(-1, K), tau_s), n_bins)
    z = logits_tgt.reshape(-1, K)
    out = np.zeros(len(T_grid), dtype=float)
    for k, T in enumerate(T_grid):
        d = confidence_hist(softmax(z, T), n_bins) - ref
        out[k] = float(d @ d)
    return out


def confidence_hist_per_patient_masked(logits: np.ndarray, valid: np.ndarray,
                                       T: float, n_bins: int = N_BINS) -> np.ndarray:
    """Per-patient histogram when each patient has a DIFFERENT number of
    valid records (unbalanced orbit — the realistic 1M-data regime).

    logits: (n_pat, n_rec, K); valid: (n_pat, n_rec) bool.
    """
    n_pat, n_rec, _ = logits.shape
    conf = softmax(logits, T).max(axis=-1)
    idx = np.clip((conf * n_bins).astype(int), 0, n_bins - 1)
    off = np.arange(n_pat)[:, None] * n_bins
    flat = (idx + off)[np.asarray(valid, dtype=bool)]
    h = np.bincount(flat, minlength=n_pat * n_bins).reshape(n_pat, n_bins).astype(float)
    return h / np.clip(h.sum(1, keepdims=True), 1e-12, None)


def psi_pari_ragged(logits_src, logits_tgt, mask_src, mask_tgt,
                    T_grid, tau_s: float = 1.0, shuffle_pairs: bool = False,
                    n_bins: int = N_BINS) -> np.ndarray:
    """PARI objective for unbalanced orbits (one vote per patient, not per record)."""
    ref = confidence_hist_per_patient_masked(logits_src, mask_src, tau_s, n_bins)
    if shuffle_pairs:
        ref = np.roll(ref, shift=1, axis=0)
    out = np.zeros(len(T_grid))
    for k, T in enumerate(T_grid):
        obs = confidence_hist_per_patient_masked(logits_tgt, mask_tgt, T, n_bins)
        d = (obs - ref).mean(axis=0)
        out[k] = float(d @ d)
    return out


def psi_pooled_ragged(logits_src, logits_tgt, mask_src, mask_tgt,
                      T_grid, tau_s: float = 1.0,
                      n_bins: int = N_BINS) -> np.ndarray:
    """Unpaired control for unbalanced orbits: record-weighted, not patient-weighted."""
    K = logits_src.shape[-1]
    ms, mt = np.asarray(mask_src, bool), np.asarray(mask_tgt, bool)
    ref = confidence_hist(softmax(logits_src[ms].reshape(-1, K), tau_s), n_bins)
    z = logits_tgt[mt].reshape(-1, K)
    out = np.zeros(len(T_grid))
    for k, T in enumerate(T_grid):
        d = confidence_hist(softmax(z, T), n_bins) - ref
        out[k] = float(d @ d)
    return out


def make_dgp_unbalanced(n_pat: int, m_max: int, imbalance: float = 1.0,
                        tau_t: float = 2.4, tau_s: float = 1.0,
                        sigma_w: float = 0.35, K: int = 4, seed: int = 0,
                        informative: bool = False):
    """Each patient gets a DIFFERENT orbit length (1..m_max), split into
    source/target groups. imbalance=0 -> identical lengths (balanced control).

    Returns (src (n_pat,m_max,K), tgt (n_pat,m_max,K), mask_src, mask_tgt)
    """
    rng = np.random.default_rng(seed)
    y = rng.integers(0, K, n_pat)
    p = np.full((n_pat, K), 0.12)
    p[np.arange(n_pat), y] = 0.55 + rng.uniform(0.0, 0.25, n_pat)
    p = p / p.sum(1, keepdims=True)
    v = np.log(p)
    if imbalance <= 0:
        lens = np.full(n_pat, m_max)
    elif informative:
        # INFORMATIVE orbit size: patients with more extreme (confident)
        # prototypes get more recordings — realistic for sicker patients.
        # Record-weighted estimators are then biased; patient-weighted PARI is not.
        c = p.max(axis=1)
        lens = np.clip(np.round(1 + (m_max - 1) * (c - c.min()) /
                                max(c.max() - c.min(), 1e-9) * imbalance),
                       1, m_max).astype(int)
    else:
        # skewed orbit lengths: many patients with 1-2 records, few with many
        raw = rng.pareto(1.0 + 2.0 / max(imbalance, 1e-6), n_pat) + 1.0
        lens = np.clip(np.round(1 + (m_max - 1) * (raw - raw.min()) /
                                max(raw.max() - raw.min(), 1e-9)), 1, m_max).astype(int)
    src = np.zeros((n_pat, m_max, K)); tgt = np.zeros((n_pat, m_max, K))
    ms = np.zeros((n_pat, m_max), bool); mt = np.zeros((n_pat, m_max), bool)
    for i in range(n_pat):
        L = int(lens[i]); ns = max(1, L // 2); nt = max(1, L - ns)
        es = rng.normal(0, sigma_w, (ns, K)); et = rng.normal(0, sigma_w, (nt, K))
        src[i, :ns] = tau_s * (v[i] + es); ms[i, :ns] = True
        tgt[i, :nt] = tau_t * (v[i] + et); mt[i, :nt] = True
    return src, tgt, ms, mt


def estimate_T(T_grid: np.ndarray, psi: np.ndarray) -> float:
    """Grid argmin + parabolic (three-point) refinement. Deterministic."""
    i = int(np.argmin(psi))
    if 0 < i < len(psi) - 1:
        x0, x1, x2 = T_grid[i - 1], T_grid[i], T_grid[i + 1]
        y0, y1, y2 = psi[i - 1], psi[i], psi[i + 1]
        denom = (y0 - 2 * y1 + y2)
        if abs(denom) > 1e-15:
            delta = 0.5 * (y0 - y2) / denom
            if abs(delta) <= 1.0:
                return float(x1 + delta * (x1 - x0))
    return float(T_grid[i])


def make_dgp(n_pat: int, m: int, tau_t: float = 2.4, tau_s: float = 1.0,
             sigma_w: float = 0.35, K: int = 4, seed: int = 0,
             episodic: bool = False, shuffle_group_labels: bool = False):
    """Synthetic DGP satisfying A1-A4.

    Patient i has a stable chronic prototype p_i (A1). Record j gets
    within-patient physiological noise eps. Source group g=0 is calibrated
    (tau_s). Target group g=1 is over-confident (tau_t): A2 says the group
    acts only through a monotone confidence distortion. Every patient has
    >=1 record in each group (A3).

    Returns (logits_src (n_pat,n_src,K), logits_tgt (n_pat,n_tgt,K), tau_t)
    """
    rng = np.random.default_rng(seed)
    y = rng.integers(0, K, n_pat)
    p = np.full((n_pat, K), 0.12)
    p[np.arange(n_pat), y] = 0.55 + rng.uniform(0.0, 0.25, n_pat)
    p = p / p.sum(1, keepdims=True)
    v = np.log(p)                                   # calibrated logits at T=1

    n_src = max(1, m // 2)
    n_tgt = max(1, m - n_src)

    def build(tau, n, tgt=False):
        vv = np.broadcast_to(v[:, None, :], (n_pat, n, K)).copy()
        if episodic and tgt:                         # F4: break A1 on target records
            y2 = rng.integers(0, K, (n_pat, n))
            q = np.full((n_pat, n, K), 0.12)
            q[np.arange(n_pat)[:, None], np.arange(n)[None, :], y2] = 0.70
            q = q / q.sum(-1, keepdims=True)
            vv = np.log(q)
        eps = rng.normal(0.0, sigma_w, (n_pat, n, K))
        return tau * (vv + eps)

    src = build(tau_s, n_src, tgt=False)
    tgt = build(tau_t, n_tgt, tgt=True)

    if shuffle_group_labels:                        # F2: destroy group identity
        # Reassign source/target labels at the record level while preserving
        # each patient's group sizes (A3 still holds but the labels are noise).
        allz = np.concatenate([src, tgt], axis=1)          # (n_pat, n_src+n_tgt, K)
        for i in range(n_pat):
            allz[i] = allz[i, rng.permutation(allz.shape[1])]
        src, tgt = allz[:, :n_src], allz[:, n_src:]
    return src, tgt, tau_t
