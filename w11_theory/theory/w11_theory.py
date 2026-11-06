"""W11 theory core — exact risk identities, non-asymptotic bound, grid.

Implements PREREGISTRATION_W11.md v1.0 VERBATIM (frozen before execution).

Model (A1-A5):
    theta_g = mu + a_g,      a_g ~ N(0, tau2)
    X_g     = theta_g + e_g, e_g ~ N(0, s_g),  s_g = deff/n_g
    v_g     = tau2 + s_g
    S2hat   = var(X, ddof=1);  tau2hat = max(S2hat - sbar, 0)
    lambda_g = tau2hat/(tau2hat + s_g)

Risk with known pooled centre (A4):
    R_g(lam) = lam^2 s_g + (1-lam)^2 tau2
             = R*_g + (tau2+s_g)(lam-lam*_g)^2
    R*_g = f(s_g) = tau2*s_g/(tau2+s_g)
    R*_hetero = mean f(s_g) <= f(sbar) = R_homo   (Jensen, f strictly concave)

T1  exact excess risk identity
T2  P(R_hetero(lamhat) > R*_hetero + delta) <= min(1, V/(delta*tau2))
    V = Var(S2hat) = 2[(G-2)*M2 + vbar^2]/(G-1)^2
T3  misspecified noise scale c: deterministic excess risk
T4  gap(deff) non-monotone; rigorous Jensen-gap lower bound

Synthetic theory only. NO real ECG, NO official Mamba-2, NO pretrained weights.
"""
from __future__ import annotations
import json, math, pathlib
import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
MC_SEED_BASE = 20261106
B_MC = 2000
GRID_G = [4, 8, 16, 32, 64, 128]
GRID_TAU2 = [0.05, 0.2, 0.5, 1.0]
GRID_DEFF = [1.0, 1.5, 1.944, 3.0]       # 1.944 = W10 H6 mean_deff
GRID_CV = [0.0, 0.2, 0.5, 1.0, 1.5, 2.0]
DELTAS = {'half_gap': 0.5, 'gap': 1.0, 'double_gap': 2.0}
T1_TOL = 1e-10
T3_TOL = 1e-10


# -------------------------------------------------------------------- basics
def f(s, tau2):
    """f(x) = tau2*x/(tau2+x); f'' = -2 tau2^2/(tau2+x)^3 < 0."""
    return tau2 * s / (tau2 + s)


def group_sizes(G, cv, seed):
    rng = np.random.default_rng(seed)
    n = np.clip(rng.lognormal(3.5, cv, G), 1.0, None)
    return n


def theory_quantities(G, tau2, deff, cv, seed):
    n = group_sizes(G, cv, seed)
    s = deff / n                       # A3: patient repeated-measure noise
    sbar = float(s.mean())
    v = tau2 + s
    M2 = float(np.mean(v ** 2))
    vbar = float(v.mean())
    V = 2.0 * ((G - 2) * M2 + vbar ** 2) / (G - 1) ** 2   # Var(S2hat)
    gap = float(f(sbar, tau2) - np.mean(f(s, tau2)))        # Jensen gap > 0
    gap = max(gap, 0.0)
    # rigorous lower bound: gap >= tau2^2 * Var(S)/(tau2+S_max)^3
    gap_lb = float(tau2 ** 2 * np.var(s) / (tau2 + s.max()) ** 3)
    lam_bar = tau2 / (tau2 + sbar)
    R_homo = float(lam_bar ** 2 * sbar + (1 - lam_bar) ** 2 * tau2)
    R_star = float(np.mean(f(s, tau2)))
    return dict(G=G, tau2=tau2, deff=deff, cv=cv, seed=seed,
                n=n, s=s, sbar=sbar, M2=M2, vbar=vbar, V=V,
                gap=gap, gap_lb=gap_lb, R_homo=R_homo, R_star=R_star,
                lam_bar=lam_bar, smax=float(s.max()),
                var_s=float(np.var(s)))


def bound_V(V, gap, tau2, delta_mult=1.0):
    """T2: min(1, V/(delta*tau2)); gap<=0 -> trivial bound 1."""
    denom = max(delta_mult * gap, 0.0) * tau2
    if denom <= 1e-15:
        return 1.0
    return float(min(1.0, V / denom))


# -------------------------------------------------------------------- T1 exact
def t1_exact(s, tau2, tau2hat):
    """Closed form of R_g(lamhat)-R*_g."""
    return s ** 2 * (tau2hat - tau2) ** 2 / (
        (tau2hat + s) ** 2 * (tau2 + s))


def t1_direct(s, tau2, tau2hat):
    lam = tau2hat / (tau2hat + s)
    lam_star = tau2 / (tau2 + s)
    return (tau2 + s) * (lam - lam_star) ** 2


def check_T1(s, tau2, rng, n_draw=10):
    """Relative error of the exact identity; returns list of errors."""
    errs = []
    for _ in range(n_draw):
        th = float(rng.uniform(0.0, 2.0 * tau2 + 1.0))
        a = t1_exact(s, tau2, th)
        b = t1_direct(s, tau2, th)
        denom = max(np.abs(b).max(), 1e-30)
        errs.append(float(np.abs(a - b).max() / denom))
    return errs


# -------------------------------------------------------------------- T3 exact
def t3_exact(s, tau2, c):
    """Excess risk from using c*s instead of s in the BLUP weight."""
    lam_tilde = tau2 / (tau2 + c * s)
    lam_star = tau2 / (tau2 + s)
    return (tau2 + s) * (lam_tilde - lam_star) ** 2


def t3_closed(s, tau2, c):
    return tau2 ** 2 * s ** 2 * (c - 1.0) ** 2 / (
        (tau2 + c * s) ** 2 * (tau2 + s))


def check_T3(s, tau2, c_values=(0.5, 1.0, 1.5, 1.944, 3.0)):
    out = {}
    for c in c_values:
        a, b = t3_closed(s, tau2, c), t3_exact(s, tau2, c)
        out[str(c)] = float(np.abs(a - b).max() / max(np.abs(b).max(), 1e-30))
    return out


# -------------------------------------------------------------------- T2 Monte Carlo
def mc_fail_rates(Q, B=B_MC, seed=None):
    """Empirical P(R_hetero(lamhat) > R*_hetero + delta) for 3 deltas.

    Shared resamples across deltas (strictly paired). Vectorised in chunks.
    """
    G, tau2, s = Q['G'], Q['tau2'], Q['s']
    v = tau2 + s
    sbar, R_star, R_homo, gap = Q['sbar'], Q['R_star'], Q['R_homo'], Q['gap']
    rng = np.random.default_rng(seed if seed is not None else Q['seed'])
    R_all = []
    done = 0
    chunk = 500
    while done < B:
        m = min(chunk, B - done)
        X = rng.normal(0.0, 1.0, (m, G)) * np.sqrt(v)[None, :]  # mu=0 wlog
        S2 = X.var(axis=1, ddof=1)
        th = np.maximum(S2 - sbar, 0.0)
        lam = th[:, None] / (th[:, None] + s[None, :])
        R = (lam ** 2 * s[None, :] + (1 - lam) ** 2 * tau2).mean(axis=1)
        R_all.append(R)
        done += m
    R = np.concatenate(R_all)
    rates = {}
    for name, mult in DELTAS.items():
        thr = R_star + mult * gap
        rates[name] = float((R > thr).mean())
    rates['domination_vs_R_homo'] = float((R > R_homo).mean())
    rates['mean_R'] = float(R.mean())
    rates['mean_R_minus_Rstar'] = float(R.mean() - R_star)
    return rates


# -------------------------------------------------------------------- grid
def build_grid():
    cells = []
    idx = 0
    for G in GRID_G:
        for tau2 in GRID_TAU2:
            for deff in GRID_DEFF:
                for cv in GRID_CV:
                    seed = MC_SEED_BASE + idx
                    Q = theory_quantities(G, tau2, deff, cv, seed)
                    Q['grid_index'] = idx
                    cells.append(Q)
                    idx += 1
    return cells


def run_grid(verbose=True):
    cells = build_grid()
    rows = []
    t1_errs, t3_errs, a5_lb, a5_nm = [], [], [], []
    for Q in cells:
        r = mc_fail_rates(Q, seed=Q['seed'])
        bounds = {name: bound_V(Q['V'], Q['gap'], Q['tau2'], mult)
                  for name, mult in DELTAS.items()}
        bounds['domination_vs_R_homo'] = bounds['gap']
        row = {
            'grid_index': Q['grid_index'], 'G': Q['G'], 'tau2': Q['tau2'],
            'deff': Q['deff'], 'cv': Q['cv'], 'seed': Q['seed'],
            'sbar': Q['sbar'], 'V': Q['V'], 'gap': Q['gap'],
            'gap_lb': Q['gap_lb'], 'R_homo': Q['R_homo'], 'R_star': Q['R_star'],
            'bounds': bounds, 'empirical': r,
            'trivial': bool(bounds['gap'] >= 1.0 - 1e-12),
            'bound_holds_gap': bool(r['gap'] <= bounds['gap'] + 1e-12),
        }
        rows.append(row)

        # --- A1 / A4 exact-identity checks (10 random tau2hat per cell) ---
        rng = np.random.default_rng(Q['seed'] + 999_000)
        t1_errs.extend(check_T1(Q['s'], Q['tau2'], rng))
        e3 = check_T3(Q['s'], Q['tau2'])
        t3_errs.extend(e3.values())
        # --- A5 lower bound ---
        a5_lb.append(bool(Q['gap'] + 1e-15 >= Q['gap_lb']))
        if verbose and Q['grid_index'] % 100 == 0:
            print(f'  grid {Q["grid_index"]:3d}/576 '
                  f'G={Q["G"]:3d} tau2={Q["tau2"]:.2f} '
                  f'deff={Q["deff"]:.3f} cv={Q["cv"]:.1f} '
                  f'gap={Q["gap"]:.5f} bound={bounds["gap"]:.4f} '
                  f'emp={r["gap"]:.4f}', flush=True)

    # --- A5 non-monotonicity of gap in deff (independent of MC) ---
    for G in GRID_G:
        for tau2 in GRID_TAU2:
            for cv in GRID_CV:
                seed = MC_SEED_BASE + 700000 + G * 100 + int(tau2 * 10) * 10 + int(cv * 10)
                n = group_sizes(G, cv, seed)
                g0 = float(f((1e-6 / n).mean(), tau2) - np.mean(f(1e-6 / n, tau2)))
                g1 = float(f((1.0 / n).mean(), tau2) - np.mean(f(1.0 / n, tau2)))
                gI = float(f((1e6 / n).mean(), tau2) - np.mean(f(1e6 / n, tau2)))
                a5_nm.append({'G': G, 'tau2': tau2, 'cv': cv,
                              'gap_deff_0': g0, 'gap_deff_1': g1,
                              'gap_deff_inf': gI,
                              'both_ends_smaller': bool(g0 < g1 and gI < g1)})

    return rows, dict(t1=t1_errs, t3=t3_errs, a5_lb=a5_lb, a5_nm=a5_nm)


def evaluate(rows, checks):
    """Apply the FROZEN A1..A7 criteria (PREREGISTRATION_W11.md section 3)."""
    n_cells = len(rows)
    # A1
    A1 = {'n_checks': len(checks['t1']),
          'max_rel_error': float(max(checks['t1'])),
          'frac_within_tol': float(np.mean(np.array(checks['t1']) < T1_TOL)),
          'tol': T1_TOL}
    A1['PASS'] = bool(A1['frac_within_tol'] >= 1.0)
    # A2 (exclude trivial cells)
    nontrivial = [r for r in rows if not r['trivial']]
    holds = [r['bound_holds_gap'] for r in nontrivial]
    A2 = {'n_cells': n_cells, 'n_trivial': n_cells - len(nontrivial),
          'n_nontrivial': len(nontrivial),
          'frac_bound_holds': float(np.mean(holds)) if holds else None,
          'threshold': 0.95}
    A2['PASS'] = bool(holds and np.mean(holds) >= 0.95)
    # A3 log-log slope on nontrivial informative subset
    sub = [r for r in rows if (not r['trivial'] and r['tau2'] >= 0.2
                               and r['cv'] >= 0.5 and r['deff'] <= 2.0)]
    # average bound per G over the subset (bounds are analytic, no MC noise)
    byG = {}
    for r in sub:
        byG.setdefault(r['G'], []).append(r['bounds']['gap'])
    Gs = sorted(byG)
    xs = np.log(np.array(Gs, float))
    ys = np.log(np.clip([float(np.mean(byG[g])) for g in Gs], 1e-300, None))
    slope = float(np.polyfit(xs, ys, 1)[0]) if len(Gs) >= 2 else None
    A3 = {'n_cells': len(sub), 'G_values': Gs,
          'mean_bound_by_G': [float(np.mean(byG[g])) for g in Gs],
          'loglog_slope': slope, 'interval': [-1.30, -0.70]}
    A3['PASS'] = bool(slope is not None and -1.30 <= slope <= -0.70)
    # A4
    A4 = {'n_checks': len(checks['t3']),
          'max_rel_error': float(max(checks['t3'])),
          'frac_within_tol': float(np.mean(np.array(checks['t3']) < T3_TOL)),
          'tol': T3_TOL}
    A4['PASS'] = bool(A4['frac_within_tol'] >= 1.0)
    # A5
    nm = checks['a5_nm']
    A5 = {'frac_lower_bound_holds': float(np.mean(checks['a5_lb'])),
          'n_gap_nonmonotone_checks': len(nm),
          'frac_both_ends_smaller': float(np.mean([x['both_ends_smaller'] for x in nm])),
          'examples': nm[:3]}
    A5['PASS'] = bool(np.mean(checks['a5_lb']) >= 1.0 and
                      np.mean([x['both_ends_smaller'] for x in nm]) >= 1.0)
    # A6 align with W10
    w10_path = HERE.parent.parent / 'w10_continuous' / 'w10_results.json'
    w10 = json.loads(w10_path.read_text(encoding='utf-8'))
    deff_w10 = float(w10['H']['H6_mechanism']['mean_deff'])
    c = deff_w10
    # T3 prediction at the W10 regime: excess risk of using c*s vs s is >=0
    # Use a representative group vector from the grid (G=36-ish -> 32, cv=1)
    Q = theory_quantities(32, 0.2, 1.0, 1.0, MC_SEED_BASE)
    pred_excess = float(t3_closed(Q['s'], Q['tau2'], c).mean())
    obs = float(w10['H']['H1_selection']['candidates']['M1']['point_A'])
    A6 = {'W10_mean_deff': deff_w10, 'c_used': c,
          'T3_predicted_mean_excess_risk': pred_excess,
          'T3_predicted_direction': 'M1 average dECE worse than HB (c=1)',
          'W10_observed_A_M1_minus_A_HB': obs,
          'W10_observed_direction': 'worse' if obs > 0 else 'better',
          'same_sign': bool(pred_excess > 0 and obs > 0)}
    A6['PASS'] = bool(A6['same_sign'] and pred_excess > 0)
    # A7 non-identifiable cells (descriptive, no PASS)
    nid = [r for r in rows if r['tau2'] <= 0.05 or r['gap'] < 1e-4]
    A7 = {'n_cells': len(nid),
          'frac_trivial_bound': float(np.mean([r['trivial'] for r in nid])) if nid else None,
          'note': 'descriptive only; NOT a pass/fail criterion per prereg',
          'PASS': None}
    out = {'A1_T1_exact': A1, 'A2_T2_validity': A2, 'A3_T2_slope': A3,
           'A4_T3_exact': A4, 'A5_T4_gap': A5, 'A6_W10_alignment': A6,
           'A7_nonidentifiable': A7,
           'n_pass': int(sum(bool(v['PASS']) for k, v in
                             [('A1', A1), ('A2', A2), ('A3', A3),
                              ('A4', A4), ('A5', A5), ('A6', A6)])),
           'n_checks': 6}
    return out


def main():
    print('W11 theory grid — PREREGISTRATION_W11.md v1.0 (frozen)', flush=True)
    print(f'grid: G{len(GRID_G)} x tau2{len(GRID_TAU2)} x '
          f'deff{len(GRID_DEFF)} x cv{len(GRID_CV)} = '
          f'{len(GRID_G)*len(GRID_TAU2)*len(GRID_DEFF)*len(GRID_CV)} cells, '
          f'B={B_MC} MC each', flush=True)
    rows, checks = run_grid()
    verdict = evaluate(rows, checks)
    out = {'prereg': 'PREREGISTRATION_W11.md v1.0 (frozen)',
           'B_MC': B_MC, 'MC_seed_base': MC_SEED_BASE,
           'grid_axes': {'G': GRID_G, 'tau2': GRID_TAU2,
                         'deff': GRID_DEFF, 'cv': GRID_CV},
           'deltas': DELTAS, 'n_cells': len(rows),
           'verdict': verdict, 'rows': rows,
           'exact_checks': {
               'T1_max_rel_error': float(max(checks['t1'])),
               'T3_max_rel_error': float(max(checks['t3'])),
               'A5_lower_bound_frac': float(np.mean(checks['a5_lb'])),
               'A5_nonmonotone_frac': float(np.mean(
                   [x['both_ends_smaller'] for x in checks['a5_nm']]))}}
    dest = HERE.parent / 'results' / 'w11_theory_results.json'
    dest.parent.mkdir(exist_ok=True)
    dest.write_text(json.dumps(out, indent=2, ensure_ascii=False),
                    encoding='utf-8')
    print('\n=== W11 THEORY VERDICT ===', flush=True)
    for k, v in verdict.items():
        if isinstance(v, dict):
            print('  ', k, 'PASS =', v.get('PASS'), flush=True)
    print('  pass', verdict['n_pass'], '/', verdict['n_checks'], flush=True)
    print('written', dest, flush=True)


if __name__ == '__main__':
    main()
