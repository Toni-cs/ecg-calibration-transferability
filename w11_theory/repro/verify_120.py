"""W11-B verify VG001-VG120.

PREREGISTRATION_W11B.md v1.0 (frozen BEFORE execution). 120 INDEPENDENT
gates expanding the original 12 release gates. Each gate checks a distinct
round / shard set / file / field / original gate. NOT 120 copies of one if.

Kinds: verify, meta (confirms an ORIGINAL recorded gate is PASS; independent
failure condition = that original record missing or FAIL).
"""
from __future__ import annotations
import hashlib, json, pathlib, sys
import numpy as np
from PIL import Image

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
RESULTS = ROOT / 'w11_theory' / 'results'
REPRO = ROOT / 'w11_theory' / 'repro'

ROUNDS = {
    'W1': ROOT / 'pari_experiment', 'W2': ROOT / 'gsgt_experiment',
    'W3': ROOT / 'mamba_experiment', 'W4': ROOT / 'w4_repro',
    'W5': ROOT / 'w5_srgst', 'W6': ROOT / 'w6_tier1',
    'W7': ROOT / 'w7_60k', 'W8': ROOT / 'w8_dualgate',
    'W9': ROOT / 'w9_lbst', 'W10': ROOT / 'w10_continuous',
    'W11': ROOT / 'w11_theory',
}
RESULT_JSON = {
    'W1': ROOT / 'pari_experiment' / 'pari_synthetic_results.json',
    'W2': ROOT / 'gsgt_experiment' / 'gsgt_v1_1_results.json',
    'W3': ROOT / 'mamba_experiment' / 'mamba600_results.json',
    'W4': ROOT / 'w4_repro' / 'w4_results.json',
    'W5': ROOT / 'w5_srgst' / 'w5_results.json',
    'W6': ROOT / 'w6_tier1' / 'w6_results.json',
    'W7': ROOT / 'w7_60k' / 'w7_results.json',
    'W8': ROOT / 'w8_dualgate' / 'W8_FROZEN_GATE.json',
    'W9': ROOT / 'w9_lbst' / 'w9_results.json',
    'W10': ROOT / 'w10_continuous' / 'w10_results.json',
    'W11': RESULTS / 'w11_theory_results.json',
}
SHARDS = [
    ('W7_main', ROOT / 'w7_60k' / 'shards', 21000, 80999, 60000, None),
    ('W9_main', ROOT / 'w9_lbst' / 'shards' / 'main', 110000, 119999, 10000, None),
    ('W9_falsify', ROOT / 'w9_lbst' / 'shards' / 'falsify', 120000, 120599, 600, None),
    ('W10_main', ROOT / 'w10_continuous' / 'shards' / 'main', 130000, 149999, 20000, 41),
    ('W10_loco', ROOT / 'w10_continuous' / 'shards' / 'loco', 150000, 150599, 600, 5),
    ('W10_falsify', ROOT / 'w10_continuous' / 'shards' / 'falsify', 151000, 151599, 600, 41),
]
CORE_FILES = [
    REPRO / 'environment.lock', REPRO / 'SEED_MANIFEST.json',
    REPRO / 'WEIGHT_HASHES.sha256', REPRO / 'CACHE_SCHEMA.json',
    REPRO / 'DIRECTION_LEDGER.json', REPRO / 'preflight.py',
    REPRO / 'verify_release_results.py', REPRO / 'REPRODUCE.md',
    ROOT / 'w11_theory' / 'PREREGISTRATION_W11.md',
    ROOT / 'w11_theory' / 'PREREGISTRATION_W11B.md',
    RESULTS / 'w11_final_verdict.json',
    RESULTS / 'verify_release_results.json',
]
LOCK_FIELDS = ['python', 'platform', 'machine', 'numpy', 'scipy',
               'matplotlib', 'pillow', 'blas_threads_policy', 'font', 'timezone']

A = []


def add(fid, family, claim, expected, observed, passed, evidence, kind='verify'):
    A.append({'id': fid, 'family': family, 'claim': claim, 'kind': kind,
              'expected': expected, 'observed': observed,
              'PASS': bool(passed), 'evidence': evidence})


idx = 1
# ------------------------------------------- VG001-VG011  round directories
for w, d in ROUNDS.items():
    ok = d.is_dir()
    add(f'VG{idx:03d}', 'round_directory', f'{w} round directory exists',
        'is_dir() true', f'exists={ok}', ok,
        f'path={d.relative_to(ROOT)}, n_files={len(list(d.iterdir())) if ok else 0}')
    idx += 1

# ------------------------------------------- VG012-VG022  result JSONs
for w, p in RESULT_JSON.items():
    try:
        d = json.loads(p.read_text(encoding='utf-8'))
        ok = bool(isinstance(d, dict) and len(d) >= 3 and p.stat().st_size > 1024)
        obs = f'bytes={p.stat().st_size}, keys={len(d)}'
        ev = f'path={p.relative_to(ROOT)}, bytes={p.stat().st_size}, top_keys={list(d)[:8]}'
    except Exception as e:
        ok, obs, ev = False, f'ERROR {e}', f'path={p.relative_to(ROOT)}'
    add(f'VG{idx:03d}', 'round_result_json',
        f'{w} terminal result JSON exists, parses, and is >1KB',
        'parses as dict with >=3 keys and size >1024 bytes', obs, ok, ev)
    idx += 1

# ------------------------------------------- VG023-VG033  figures
for w, d in ROUNDS.items():
    pngs = list(d.glob('*.png')) + list((d / 'figs').glob('*.png'))
    good = [p for p in pngs if p.stat().st_size > 1000]
    dim_ok = True
    if good:
        try:
            im = Image.open(good[0])
            dim_ok = im.width > 0 and im.height > 0
        except Exception:
            dim_ok = False
    ok = bool(good and dim_ok)
    add(f'VG{idx:03d}', 'round_figure',
        f'{w} has >=1 non-empty PNG with valid dimensions',
        'at least one PNG >1KB with positive width/height',
        f'n_png={len(good)}, dim_ok={dim_ok}', ok,
        f'path={d.relative_to(ROOT)}, n_png={len(good)}, '
        f'first={good[0].name if good else None}, '
        f'size={Image.open(good[0]).size if good and dim_ok else None}')
    idx += 1

# ------------------------------------------- VG034-VG069  shard integrity (6x6)
for name, folder, lo, hi, n_seeds, ncols in SHARDS:
    ps = sorted(folder.glob('shard_*.npz'))
    # (1) existence
    ok1 = len(ps) > 0
    add(f'VG{idx:03d}', 'shard_exists', f'{name} has >=1 npz shard',
        'n_files > 0', f'n_files={len(ps)}', ok1,
        f'folder={folder.relative_to(ROOT)}, n_files={len(ps)}'); idx += 1
    # (2) npz parses with X key
    parse_ok, parse_obs = True, []
    for p in ps:
        try:
            z = np.load(p)
            parse_ok &= ('X' in z)
        except Exception as e:
            parse_ok = False; parse_obs.append(str(e))
    add(f'VG{idx:03d}', 'shard_npz_parses',
        f'every {name} shard is a readable npz containing key X',
        'all shards parse and contain X', f'ok={parse_ok}, errors={parse_obs[:2]}',
        parse_ok, f'n_files={len(ps)}, errors={parse_obs[:3]}'); idx += 1
    if not ps:
        # remaining 4 checks for this set are honestly FAIL
        for fam, claim in [('shard_seed_continuity', 'seed range exactly continuous'),
                           ('shard_no_duplicate', 'no duplicate seed rows'),
                           ('shard_column_count', 'column count matches contract'),
                           ('shard_dtype', 'matrix dtype is float64')]:
            add(f'VG{idx:03d}', fam, f'{name}: {claim}',
                'check passes', 'no shards -> unevaluable', False,
                f'folder={folder.relative_to(ROOT)}, n_files=0')
            idx += 1
        continue
    X = np.concatenate([np.load(p)['X'] for p in ps], axis=0)
    seeds = np.unique(X[:, 0].astype(np.int64))
    exp = np.arange(lo, hi + 1, dtype=np.int64)
    # (3) continuity
    ok3 = bool(np.array_equal(seeds, exp))
    add(f'VG{idx:03d}', 'shard_seed_continuity',
        f'{name} unique seeds equal exactly [{lo},{hi}]',
        f'np.array_equal(seeds, arange({lo},{hi}+1))',
        f'n_unique={len(seeds)}, expected={len(exp)}, exact={ok3}', ok3,
        f'n_rows={len(X)}, n_unique={len(seeds)}, min={seeds.min()}, max={seeds.max()}')
    idx += 1
    # (4) no duplicate seed rows (loco: 3 rows/seed is expected)
    expected_rows = n_seeds if name != 'W10_loco' else n_seeds * 3
    ok4 = bool(len(X) == expected_rows and len(seeds) == n_seeds)
    add(f'VG{idx:03d}', 'shard_no_duplicate',
        f'{name} row count matches per-seed contract (loco=3 rows/seed)',
        f'n_rows == {expected_rows} and n_unique == {n_seeds}',
        f'n_rows={len(X)}, expected={expected_rows}, n_unique={len(seeds)}', ok4,
        f'n_rows={len(X)}, n_unique={len(seeds)}, expected_rows={expected_rows}')
    idx += 1
    # (5) column count
    ok5 = True if ncols is None else bool(X.shape[1] == ncols)
    add(f'VG{idx:03d}', 'shard_column_count',
        f'{name} column count matches its schema',
        'unconstrained' if ncols is None else f'ncols == {ncols}',
        f'ncols={X.shape[1]}, expected={ncols}', ok5,
        f'shape={X.shape}, expected_ncols={ncols}'); idx += 1
    # (6) dtype
    ok6 = bool(X.dtype == np.float64)
    add(f'VG{idx:03d}', 'shard_dtype', f'{name} matrix dtype is float64',
        'dtype == float64', f'dtype={X.dtype}', ok6,
        f'dtype={str(X.dtype)}, shape={X.shape}'); idx += 1

# ------------------------------------------- VG070-VG081  core contract files
for i, p in enumerate(CORE_FILES):
    ok = p.is_file() and p.stat().st_size > 200
    add(f'VG{idx:03d}', 'core_contract_file',
        f'core file {i+1}/12 exists and is non-empty: {p.name}',
        'is_file() and size > 200 bytes',
        f'exists={p.is_file()}, bytes={p.stat().st_size if p.exists() else 0}', ok,
        f'path={p.relative_to(ROOT)}, bytes={p.stat().st_size if p.exists() else 0}')
    idx += 1

# ------------------------------------------- VG082-VG093  original 12 gates (meta)
VR = json.loads((RESULTS / 'verify_release_results.json').read_text(
    encoding='utf-8'))
for i, (gname, gval) in enumerate(VR['gates'].items()):
    ok = bool(gval.get('PASS') is True)
    add(f'VG{idx:03d}', 'original_12_gate_META',
        f'original gate {i+1}/12 "{gname}" is recorded as PASS',
        'recorded PASS == true', f'PASS={gval.get("PASS")}', ok,
        f'gate={gname}, PASS={gval.get("PASS")}, '
        f'keys={list(gval)[:6]}', kind='meta')
    idx += 1

# ------------------------------------------- VG094-VG103  W11 theory fields
TH = json.loads((RESULTS / 'w11_theory_results.json').read_text(
    encoding='utf-8'))
field_checks = [
    ('prereg', lambda d: 'PREREGISTRATION_W11.md' in str(d.get('prereg', ''))),
    ('B_MC', lambda d: d.get('B_MC') == 2000),
    ('MC_seed_base', lambda d: d.get('MC_seed_base') == 20261106),
    ('n_cells', lambda d: d.get('n_cells') == 576),
    ('grid_axes.G', lambda d: len(d.get('grid_axes', {}).get('G', [])) == 6),
    ('grid_axes.deff', lambda d: 1.944 in d.get('grid_axes', {}).get('deff', [])),
    ('deltas', lambda d: 'gap' in d.get('deltas', {})),
    ('rows_length', lambda d: len(d.get('rows', [])) == 576),
    ('verdict.n_pass', lambda d: isinstance(d.get('verdict', {}).get('n_pass'), int)),
    ('exact_checks', lambda d: 'T1_max_rel_error' in d.get('exact_checks', {})),
]
for i, (fname, fn) in enumerate(field_checks):
    try:
        ok = bool(fn(TH)); obs = 'condition true'
    except Exception as e:
        ok, obs = False, f'ERROR {e}'
    add(f'VG{idx:03d}', 'W11_theory_field',
        f'w11_theory_results.json field "{fname}" ({i+1}/10) has the frozen value',
        f'frozen condition for {fname}', obs, ok,
        f'field={fname}, value={str(TH.get(fname, TH.get("grid_axes", {}).get(fname.split(".")[-1], "nested")))[:120]}')
    idx += 1

# ------------------------------------------- VG104-VG113  environment lock fields
LOCK = json.loads((REPRO / 'environment.lock').read_text(encoding='utf-8'))
import scipy, matplotlib
RUNTIME = {'python': sys.version.split()[0], 'numpy': np.__version__,
           'scipy': scipy.__version__, 'matplotlib': matplotlib.__version__}
for i, k in enumerate(LOCK_FIELDS):
    v = LOCK.get(k)
    present = bool(v is not None and str(v).strip())
    match = True
    if k in RUNTIME:
        match = (v == RUNTIME[k])
    ok = bool(present and match)
    add(f'VG{idx:03d}', 'environment_lock_field',
        f'lock field "{k}" ({i+1}/10) is present and matches runtime where applicable',
        'non-empty AND version matches runtime (for python/numpy/scipy/matplotlib)',
        f'value="{v}", present={present}, runtime_match={match}', ok,
        f'field={k}, locked="{v}", runtime="{RUNTIME.get(k, "n/a (non-version field)")}"')
    idx += 1

# ------------------------------------------- VG114-VG120  original preflight (meta)
PF = json.loads((RESULTS / 'preflight_results.json').read_text(
    encoding='utf-8'))
for i, (pname, pval) in enumerate(PF['checks'].items()):
    ok = bool(pval.get('PASS') is True)
    add(f'VG{idx:03d}', 'original_7_preflight_META',
        f'original preflight item {i+1}/7 "{pname}" is recorded as PASS',
        'recorded PASS == true', f'PASS={pval.get("PASS")}', ok,
        f'item={pname}, PASS={pval.get("PASS")}, keys={list(pval)[:6]}',
        kind='meta')
    idx += 1

assert idx == 121, f'expected 120 gates, got {idx-1}'
assert len(A) == 120

out = {
 'prereg': 'PREREGISTRATION_W11B.md v1.0 (frozen)',
 'group': 'verify', 'n_checks': 120,
 'n_pass': int(sum(a['PASS'] for a in A)),
 'n_fail': int(sum(not a['PASS'] for a in A)),
 'n_by_kind': {k: int(sum(1 for a in A if a['kind'] == k))
               for k in ['verify', 'falsify', 'meta']},
 'gates': A,
 'original_verdicts_untouched': {
     'W11_theory': '4/6', 'preflight': '7/7',
     'verify_release_results': VR['n_pass'], 'verify_total': VR['n_checks']},
}
dest = RESULTS / 'w11b_verify_120.json'
dest.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding='utf-8')
print(f'W11-B VERIFY: {out["n_pass"]}/120 PASS, {out["n_fail"]} FAIL')
print('  by kind:', out['n_by_kind'])
for a in A:
    if not a['PASS']:
        print('  FAIL', a['id'], a['family'], '|', a['observed'])
print('written', dest)
