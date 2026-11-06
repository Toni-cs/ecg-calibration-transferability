"""W11-B theoretical assertions TH001-TH120.

PREREGISTRATION_W11B.md v1.0 (frozen BEFORE execution). 120 INDEPENDENT
assertions over 4 theorem families. Every assertion has its own parameter
cell / RNG seed / object and its own failure condition. NOT 120 copies of
one check.

Kinds: verify (condition must hold), falsify (expected anomaly MUST be
detected; PASS means the negative fact was correctly observed).
"""
from __future__ import annotations
import json, pathlib, sys
import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / 'theory'))
from w11_theory import (f, theory_quantities, t1_exact, t1_direct,
                        t3_exact, t3_closed, bound_V, mc_fail_rates,
                        build_grid, GRID_G, GRID_TAU2, GRID_DEFF, GRID_CV,
                        MC_SEED_BASE, T1_TOL, T3_TOL)

RESULTS = ROOT / 'results'
RESULTS.mkdir(exist_ok=True)
SEED = MC_SEED_BASE
TAUS = [0.05, 0.2, 0.5, 1.0, 2.0]
GS = [4, 8, 16, 32, 64, 128]
CS = [0.5, 1.0, 1.5, 1.9442294978193473, 3.0]
TAUS3 = [0.05, 0.5, 1.0]

A = []


def add(fid, family, claim, kind, expected, observed, passed, evidence):
    A.append({'id': fid, 'family': family, 'claim': claim, 'kind': kind,
              'expected': expected, 'observed': observed,
              'PASS': bool(passed), 'evidence': evidence})


# ------------------------------------------------- TH001-TH030  T1 identity
idx = 1
for ti, tau2 in enumerate(TAUS):
    for gi, G in enumerate(GS):
        seed = SEED + 1000 + ti * 100 + gi
        Q = theory_quantities(G, tau2, 1.944, 1.0, seed)
        rng = np.random.default_rng(seed)
        ths = rng.uniform(0.0, 2.0 * tau2 + 1.0, 20)
        errs = [float(np.abs(t1_exact(Q['s'], tau2, th) -
                             t1_direct(Q['s'], tau2, th)).max() /
                      max(np.abs(t1_direct(Q['s'], tau2, th)).max(), 1e-30))
                for th in ths]
        mx = max(errs)
        add(f'TH{idx:03d}', 'T1_exact_identity',
            f'T1 closed form equals direct risk at tau2={tau2}, G={G}, 20 random tau2hat',
            'verify', f'max relative error < {T1_TOL}',
            f'{mx:.3e}', mx < T1_TOL,
            f'seed={seed}, n_groups={G}, n_draws=20, max_rel_err={mx:.3e}')
        idx += 1

# ------------------------------------------------- TH031-TH050  T1 bound chain
pairs = []
for i in range(20):
    rng = np.random.default_rng(SEED + 2000 + i)
    tau2 = float(rng.uniform(0.05, 2.0))
    s = float(rng.uniform(0.01, 3.0))
    e2 = float(rng.uniform(1e-4, 1.0))
    pairs.append((tau2, s, e2))
for i, (tau2, s, e2) in enumerate(pairs):
    th = tau2 + np.sqrt(e2)          # tau2hat s.t. (tau2hat-tau2)^2 = e2
    exact = float(t1_exact(np.array([s]), tau2, th)[0])
    mid = e2 / (tau2 + s)
    coarse = e2 / tau2
    ok = bool(exact <= mid + 1e-12 <= coarse + 1e-12)
    add(f'TH{idx:03d}', 'T1_two_step_bound',
        f'exact <= e^2/(tau2+s) <= e^2/tau2 at (tau2={tau2:.4f}, s={s:.4f}, e2={e2:.4f})',
        'verify', 'both inequalities hold',
        f'exact={exact:.6e} mid={mid:.6e} coarse={coarse:.6e}', ok,
        f'seed={SEED+2000+i}, exact={exact:.6e}, mid={mid:.6e}, coarse={coarse:.6e}')
    idx += 1

# ------------------------------------------------- TH051-TH070  Var(S2hat) closed form
vgrid = []
for i in range(20):
    rng = np.random.default_rng(SEED + 3000 + i)
    G = int(rng.choice(GRID_G))
    tau2 = float(rng.choice(GRID_TAU2))
    deff = float(rng.choice(GRID_DEFF))
    cv = float(rng.choice(GRID_CV))
    vgrid.append((G, tau2, deff, cv))
for i, (G, tau2, deff, cv) in enumerate(vgrid):
    seed = SEED + 3000 + i
    Q = theory_quantities(G, tau2, deff, cv, seed)
    v = tau2 + Q['s']
    rng = np.random.default_rng(seed + 500000)
    vals = []
    done = 0
    B = 20000
    while done < B:
        m = min(2000, B - done)
        X = rng.normal(0, 1, (m, G)) * np.sqrt(v)[None, :]
        vals.append(X.var(axis=1, ddof=1))
        done += m
    allv = np.concatenate(vals)
    emp = float(allv.var(ddof=1))
    ratio = emp / Q['V'] if Q['V'] > 0 else np.inf
    ok = bool(0.97 <= ratio <= 1.03)
    add(f'TH{idx:03d}', 'T2_V_closed_form',
        f'analytic Var(S2hat) matches 20,000-sample MC at (G={G},tau2={tau2},deff={deff},cv={cv})',
        'verify', 'analytic/empirical ratio in [0.97,1.03]',
        f'ratio={ratio:.5f}', ok,
        f'seed={seed}, analytic_V={Q["V"]:.8f}, MC_V={emp:.8f}, B=20000, ratio={ratio:.5f}')
    idx += 1

# ------------------------------------------------- TH071-TH085  T2 bound coverage
# FROZEN (pre-execution corrected): take the FIRST 15 nontrivial cells in
# ascending grid_index order. No selection after looking at results.
rows_all = json.loads((RESULTS / 'w11_theory_results.json').read_text(
    encoding='utf-8'))['rows']
pre_index = sorted(r['grid_index'] for r in rows_all if not r['trivial'])[:15]
by_gi = {r['grid_index']: r for r in rows_all}
for k, gi in enumerate(pre_index):
    r = by_gi[gi]
    emp = r['empirical']['gap']; bnd = r['bounds']['gap']
    ok = bool(emp <= bnd + 1e-12)
    add(f'TH{idx:03d}', 'T2_bound_coverage',
        f'T2 bound covers empirical failure at grid_index={gi} (rank {k+1}/15)',
        'verify', 'empirical_fail_rate <= bound',
        f'emp={emp:.5f} bound={bnd:.5f}', ok,
        f'grid_index={gi}, G={r["G"]}, tau2={r["tau2"]}, deff={r["deff"]}, '
        f'cv={r["cv"]}, V={r["V"]:.6f}, gap={r["gap"]:.6f}, '
        f'emp={emp:.5f}, bound={bnd:.5f}')
    idx += 1

# ------------------------------------------------- TH086-TH095  T2 expected failure (FALSIFY)
nid = [r for r in rows_all if r['tau2'] <= 0.05 or r['gap'] < 1e-4]
frozen_nid_idx = [r['grid_index'] for r in nid[:10]]
for k, gi in enumerate(frozen_nid_idx):
    r = rows_all[gi]
    bnd = r['bounds']['gap']
    denom = r['gap'] * r['tau2']
    triggered = bool(bnd >= 1.0 - 1e-12 or denom < 1e-8)
    add(f'TH{idx:03d}', 'T2_expected_failure_FALSIFY',
        f'non-identifiable regime at grid_index={gi} must produce a trivial/divergent bound',
        'falsify', 'trivial or divergent bound IS detected',
        f'bound={bnd:.4f}, gap*tau2={denom:.3e}, triggered={triggered}',
        triggered,
        f'grid_index={gi}, G={r["G"]}, tau2={r["tau2"]}, gap={r["gap"]:.3e}, '
        f'V={r["V"]:.6f}, bound={bnd:.4f}, denom={denom:.3e}. '
        'PASS here means the negative fact was correctly detected, NOT hidden.')
    idx += 1

# ------------------------------------------------- TH096-TH110  T3 misspecification
for ci, c in enumerate(CS):
    for ti, tau2 in enumerate(TAUS3):
        seed = SEED + 4000 + ci * 10 + ti
        Q = theory_quantities(32, tau2, 1.0, 1.0, seed)
        s = Q['s']
        err = float(np.abs(t3_closed(s, tau2, c) -
                           t3_exact(s, tau2, c)).max() /
                    max(np.abs(t3_exact(s, tau2, c)).max(), 1e-30))
        zero_at_1 = float(np.abs(t3_closed(s, tau2, 1.0)).max())
        # monotonic in |c-1| on a small local grid
        cc = np.linspace(max(0.05, c - 0.4), c + 0.4, 9)
        vals = np.array([float(t3_closed(s, tau2, x).mean()) for x in cc])
        mono_ok = bool(np.all(np.diff(vals[np.argsort(np.abs(cc - 1.0))]) >= -1e-12))
        ok = bool(err < T3_TOL and zero_at_1 < 1e-14 and mono_ok)
        add(f'TH{idx:03d}', 'T3_misspec_noise',
            f'T3 closed form / c=1 zero / |c-1| monotonicity at c={c:.4f}, tau2={tau2}',
            'verify', 'error<1e-10 AND c=1 identically 0 AND monotone in |c-1|',
            f'rel_err={err:.3e}, zero_c1={zero_at_1:.3e}, monotone={mono_ok}',
            ok,
            f'seed={seed}, c={c:.6f}, tau2={tau2}, rel_err={err:.3e}, '
            f'zero_at_c1={zero_at_1:.3e}, monotone={mono_ok}, '
            f'mean_excess={float(t3_closed(s,tau2,c).mean()):.6f}')
        idx += 1

# ------------------------------------------------- TH111-TH120  T4 gap
t4grid = []
for i in range(10):
    rng = np.random.default_rng(SEED + 5000 + i)
    G = int(rng.choice([8, 16, 32, 64]))
    cv = float(rng.choice([0.2, 0.5, 1.0, 1.5, 2.0]))   # CV=0 excluded by rule
    deff = float(rng.choice([1.0, 1.944, 3.0]))
    t4grid.append((G, cv, deff))
for i, (G, cv, deff) in enumerate(t4grid):
    seed = SEED + 5000 + i
    Q = theory_quantities(G, 0.2, deff, cv, seed)
    lb_ok = bool(Q['gap'] + 1e-15 >= Q['gap_lb'])
    # non-monotonicity excluding cv=0: gaps at deff -> 0 and -> inf both < deff=1
    n = Q['n']
    g0 = float(f((1e-6 / n).mean(), 0.2) - np.mean(f(1e-6 / n, 0.2)))
    g1 = float(f((1.0 / n).mean(), 0.2) - np.mean(f(1.0 / n, 0.2)))
    gI = float(f((1e6 / n).mean(), 0.2) - np.mean(f(1e6 / n, 0.2)))
    nm_ok = bool(g0 < g1 and gI < g1)
    ok = bool(lb_ok and nm_ok)
    add(f'TH{idx:03d}', 'T4_gap_nonmonotone',
        f'Jensen gap lower bound + two-end decay at (G={G},cv={cv},deff={deff})',
        'verify', 'lower bound holds AND both deff extremes < deff=1 gap',
        f'lb_ok={lb_ok}, nm_ok={nm_ok}', ok,
        f'seed={seed}, gap={Q["gap"]:.7f}, lower_bound={Q["gap_lb"]:.7f}, '
        f'gap(0)={g0:.3e}, gap(1)={g1:.7f}, gap(inf)={gI:.3e}, '
        f'Var(S)={Q["var_s"]:.6f}')
    idx += 1

assert idx == 121, f'expected 120 assertions, got {idx-1}'
assert len(A) == 120

out = {
 'prereg': 'PREREGISTRATION_W11B.md v1.0 (frozen)',
 'group': 'theory', 'n_checks': 120,
 'n_pass': int(sum(a['PASS'] for a in A)),
 'n_fail': int(sum(not a['PASS'] for a in A)),
 'n_by_kind': {k: int(sum(1 for a in A if a['kind'] == k))
               for k in ['verify', 'falsify', 'meta']},
 'TH071_TH085_frozen_indices': pre_index,
 'TH086_TH095_frozen_indices': frozen_nid_idx,
 'assertions': A,
 'honesty': '120 independent assertions, NOT 120 copies of one check. '
            'No new experiment, no new seeds, no change to W11 original verdict.',
}
dest = RESULTS / 'w11b_theory_120.json'
dest.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding='utf-8')
print(f'W11-B THEORY: {out["n_pass"]}/120 PASS, {out["n_fail"]} FAIL')
print('  by kind:', out['n_by_kind'])
for a in A:
    if not a['PASS']:
        print('  FAIL', a['id'], a['family'], '|', a['observed'])
print('written', dest)
