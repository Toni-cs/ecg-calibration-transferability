#!/usr/bin/env python3
"""T2 grid planner. Pure Python (stdlib only), REAL execution on CPU.

Computes: corpus totals, Stage A/B grid sizes, seed-range disjointness,
GPU-hour budget under EXPLICIT placeholder throughput assumptions, and the
acceptance-gate count. Produces results/grid_plan.json.

HONESTY: every GPU-hour number is `assumption_driven: true`. No measurement,
no GPU, no real waveform is involved here.
"""
from __future__ import annotations
import json, pathlib, itertools

HERE = pathlib.Path(__file__).resolve().parent
CFG = json.loads((HERE / 'configs' / 'tier1_grid.json').read_text(encoding='utf-8'))
OUT = HERE / 'results'
OUT.mkdir(exist_ok=True)

cat = CFG['catalog']
open_ids = [c['id'] for c in cat if c['tier'] in ('open', 'open-subset')]
req_ids = [c['id'] for c in cat if c['tier'] == 'academic-request']

open_rec = sum(c['records'] for c in cat if c['tier'] in ('open', 'open-subset'))
open_pat = sum(c['patients'] for c in cat if c['tier'] in ('open', 'open-subset'))
req_rec = sum(c['records'] for c in cat if c['tier'] == 'academic-request')
req_pat = sum(c['patients'] for c in cat if c['tier'] == 'academic-request')

main_rec = open_rec + req_rec
main_pat = open_pat + req_pat

# ---- Stage A / B grid ----
A = CFG['stage_a']; B = CFG['stage_b']; C = CFG['stage_c']
nA = len(A['corpora']) * len(A['architectures']) * len(A['seeds'])
nB = (len(B['foundation_models']) * len(B['modes']) *
      len(B['external_corpora']) * len(B['seeds']))
nC = len(C['estimators']) * CFG['external_validation']['loco_corpora']

# ---- seed ranges: disjointness against W1-W12 (known ranges) ----
known = [
    ('W3_main',          3000,   3599),
    ('W5_main',          7000,   7599),
    ('W7_main_60k',     21000,  80999),
    ('W9_main',        110000, 119999),
    ('W9_falsify',     120000, 120599),
    ('W10_main',       130000, 149999),
    ('W10_loco',       150000, 150599),
    ('W10_falsify',    151000, 151599),
    ('W11_theory_MC',  20261106, 20261681),
]
t2_ranges = [('T2-A', *A['seed_range']), ('T2-B', *B['seed_range']),
             ('T2-C', *C['seed_range']), ('T2-FWD', 930000, 930001)]
conflicts = []
for name, lo, hi in t2_ranges:
    for kn, kl, kh in known:
        if lo <= kh and kl <= hi:
            conflicts.append((name, kn))
seed_ok = not conflicts

# ---- GPU-hour budget (assumption-driven) ----
# CORRECT accounting: each of the 150 Stage-A runs trains on ONE of the 6
# training corpora (not on the whole 3.3M queue). Each of the 108 Stage-B runs
# adapts on ONE of the 3 external corpora. Sum per-run cost.
assume = CFG['compute_assumptions']
by_id = {c['id']: c for c in cat}
a_ep = assume['stage_a_effective_epochs']
b_ep = assume['stage_b_effective_epochs']
a_records_per_epoch = sum(by_id[c]['records'] for c in A['corpora'])
b_records_per_epoch = sum(by_id[c]['records'] for c in B['external_corpora'])
# 150 runs = 6 corpora x 5 arch x 5 seeds -> each corpus used 25 times
a_total_records_epochs = a_records_per_epoch * a_ep * len(A['architectures']) * len(A['seeds'])
# 108 runs = 4 models x 3 modes x 3 corpora x 3 seeds -> each corpus used 36 times
b_total_records_epochs = (b_records_per_epoch * b_ep *
                          len(B['foundation_models']) * len(B['modes']) * len(B['seeds']))
budget = []
for sps in assume['throughput_candidates_sps']:
    a_h = a_total_records_epochs / sps / 3600
    b_h = b_total_records_epochs / sps / 3600
    f_h = main_rec * assume['forward_only_epochs'] / sps / 3600
    budget.append({
        'throughput_samples_per_s': sps,
        'stage_a_150runs_gpu_h': round(a_h, 1),
        'stage_b_108runs_gpu_h': round(b_h, 1),
        'forward_only_3_3M_gpu_h': round(f_h, 3),
        'stage_a_records_x_epochs': a_total_records_epochs,
        'stage_b_records_x_epochs': b_total_records_epochs,
        'assumption_driven': True,
    })

# sanity checks (structural, real)
checks = {
    'catalog_n': len(cat),
    'open_corpora_n': len(open_ids),
    'request_corpora_n': len(req_ids),
    'stage_a_runs': nA,
    'stage_b_runs': nB,
    'stage_c_eval_cells': nC,
    'acceptance_gates': CFG['acceptance_gates'],
    'stage_a_runs_match_seed_range_width': nA == (A['seed_range'][1] - A['seed_range'][0] + 1),
    'stage_b_runs_match_seed_range_width': nB == (B['seed_range'][1] - B['seed_range'][0] + 1),
    'all_t2_seed_ranges_disjoint_from_W1_W12': seed_ok,
    'lead_alignment_by_name': CFG['lead_alignment']['rule'] == 'ALIGN_BY_NAME_NOT_CHANNEL_INDEX',
    'canonical_leads_n': len(CFG['lead_alignment']['canonical']),
    'label_ontologies_n': len(CFG['label_ontologies']),
    'statistical_unit_is_patient': CFG['statistics']['unit'] == 'patient',
    'primary_queue_records': main_rec,
    'primary_queue_patients': main_pat,
    'excluded_from_commitment_n': len(CFG['excluded_from_commitment']),
}

verdict = {
    'prereg': 'PREREGISTRATION_T2.md v1.0 (frozen before any real waveform forward)',
    'executed_on': 'CPU / stdlib only',
    'real_gpu_training_performed': False,
    'real_waveform_forward_performed': False,
    'assumption_driven': True,
    'open_layer': {'corpora': open_ids, 'records': open_rec, 'patients': open_pat},
    'academic_request_layer': {'corpora': req_ids, 'records': req_rec, 'patients': req_pat},
    'main_queue': {'records': main_rec, 'patients': main_pat,
                   'countries_ge': 8, 'note': 'CODE-II is BR / SciLifeLab academic request, not US DSP'},
    'excluded_from_commitment': [x['id'] for x in CFG['excluded_from_commitment']],
    'grid': {'stage_a_runs': nA, 'stage_b_runs': nB,
             'stage_c_eval_cells': nC, 'total_gpu_runs': nA + nB},
    'seed_ranges': {n: [lo, hi] for n, lo, hi in t2_ranges},
    'seed_conflicts_with_W1_W12': conflicts,
    'gpu_hour_budget_sensitivity': budget,
    'compute_assumption_references': assume['external_references'],
    'checks': checks,
    'honesty': [
        'GPU-hour numbers are formula outputs from PLACEHOLDER throughput; must be replaced by measured throughput',
        'Corpus counts come from published pages and require per-source re-verification',
        'CODE-II access requires a PI-submitted academic request; not yet granted',
        'No GPU, no torch, no wfdb, no real waveform exists in this sandbox',
        'This planner verifies SPEC internals only; it is not a scientific result',
    ],
}
dest = OUT / 'grid_plan.json'
dest.write_text(json.dumps(verdict, indent=2, ensure_ascii=False), encoding='utf-8')

print('=== T2 GRID PLANNER (CPU, spec self-check) ===')
print(f'  catalog               : {len(cat)} corpora ({len(open_ids)} open + {len(req_ids)} academic-request)')
print(f'  open layer            : {open_rec:,} records / {open_pat:,} patients')
print(f'  main queue (+CODE-II) : {main_rec:,} records / {main_pat:,} patients')
print(f'  Stage A / B / C       : {nA} / {nB} / {nC} cells   (total GPU runs {nA+nB})')
print(f'  seed disjointness     : {"PASS" if seed_ok else "FAIL"} {conflicts}')
print(f'  gates / ontologies    : {CFG["acceptance_gates"]} / {len(CFG["label_ontologies"])}')
print('  GPU-hour sensitivity (ASSUMPTION-DRIVEN, not measured):')
for b in budget:
    print(f'    {b["throughput_samples_per_s"]:5d} sps -> A≈{b["stage_a_150runs_gpu_h"]:8.1f} h | '
          f'B≈{b["stage_b_108runs_gpu_h"]:7.1f} h | fwd≈{b["forward_only_3_3M_gpu_h"]:.2f} h')
print('  structural checks     :', 'ALL PASS' if all(
    v for k, v in checks.items() if isinstance(v, bool)) else 'SEE JSON')
print('written', dest)
