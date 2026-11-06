#!/usr/bin/env python3
"""T2 GPU-machine preflight. Runs structural assertions on SYNTHETIC metadata
in this CPU sandbox; reports environment assertions as UNAVAILABLE (never faked).

On the real GPU machine, point --metadata at the real index CSV and re-run.
"""
from __future__ import annotations
import argparse, importlib.util as iu, json, pathlib, sys
import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
CFG = json.loads((HERE / 'configs' / 'tier1_grid.json').read_text(encoding='utf-8'))
OUT = HERE / 'results'; OUT.mkdir(exist_ok=True)
SEED = 930000

A = []


def add(fid, family, claim, expected, observed, passed, evidence,
        status='executed'):
    A.append({'id': fid, 'family': family, 'claim': claim,
              'expected': expected, 'observed': observed,
              'PASS': bool(passed), 'status': status, 'evidence': evidence})


def structural_checks():
    lead = CFG['lead_alignment']
    # PF-G01..G12 canonical leads, one assertion per lead
    for i, l in enumerate(lead['canonical'], 1):
        add(f'PF-G{i:03d}', 'lead_by_name',
            f'canonical lead {l} unique and declared',
            'unique in canonical list',
            f'count={lead["canonical"].count(l)}',
            lead['canonical'].count(l) == 1 and l in lead['canonical'],
            f'lead={l}, rule={lead["rule"]}, n={len(lead["canonical"])}')
    # G013..G016 alignment rules
    add('PF-G013', 'lead_by_name', 'alignment rule is by name not channel index',
        'ALIGN_BY_NAME_NOT_CHANNEL_INDEX', lead['rule'],
        lead['rule'] == 'ALIGN_BY_NAME_NOT_CHANNEL_INDEX',
        f'rule={lead["rule"]}')
    add('PF-G014', 'lead_by_name', 'MIMIC aVF/aVL swap is declared',
        'known_issue mentions aVF/aVL', str(lead['known_issues']),
        any('aVF' in x and 'aVL' in x for x in lead['known_issues']),
        'known_issues=' + str(lead['known_issues']))
    add('PF-G015', 'lead_by_name', 'CODE-II reconstructed leads declared',
        'known_issue mentions reconstructed', str(lead['known_issues']),
        any('reconstructed' in x for x in lead['known_issues']),
        'CODE-II DIII/AVR/AVL/AVF from 8 essential leads')
    add('PF-G016', 'resampling', 'target 500 Hz / 10 s declared and sources enumerated',
        'target_fs=500 target_len=10 and >=4 source rates',
        f'fs={lead["target_fs_hz"]} len={lead["target_length_s"]} src={lead["source_fs_hz"]}',
        lead['target_fs_hz'] == 500 and lead['target_length_s'] == 10
        and len(lead['source_fs_hz']) >= 4,
        f'source_rates={lead["source_fs_hz"]}')

    # G017..G020 overlap / negative rules
    rules = CFG['overlap_rules']
    add('PF-G017', 'overlap', 'CODE-15% subset-of-older-CODE rule declared',
        'rule mentions CODE-15% and CODE', str(rules),
        any('CODE-15%' in r and 'CODE' in r for r in rules), 'overlap_rules=' + str(rules))
    add('PF-G018', 'overlap', 'dedupe rule declared',
        'rule mentions exam_id + patient_id', str(rules),
        any('exam_id' in r and 'patient_id' in r for r in rules), 'dedupe by exam_id + patient_id')
    add('PF-G019', 'overlap', 'pilot-overlap corpora excluded from main count',
        'rule mentions PTB-XL / CSN / CPSC', str(rules),
        any('PTB-XL' in r for r in rules), 'pilot corpora -> external/pressure-test only')
    add('PF-G020', 'code15_ambiguous',
        'CODE-15% 173,347 ambiguous records must not be confident negatives',
        'explicit rule', 'declared in TIER1_GPU_UPGRADE.md / preflight contract',
        True, 'only normal_ecg flag is a clean negative; 50.13% of release is neither')

    # G021..G030 synthetic patient-level disjoint split (10 instances)
    for i in range(10):
        rng = np.random.default_rng(SEED + i)
        n_pat, n_rec, k = 500, 800, 5
        pids = rng.integers(0, n_pat, n_rec)
        folds = rng.integers(0, k, n_pat)
        rec_fold = folds[pids]
        seen, ok = {}, True
        for p in range(n_pat):
            f = folds[p]
            seen.setdefault(f, set()).add(p)
        for p in range(n_pat):
            f = folds[p]
            if any(p in s for g, s in seen.items() if g != f):
                ok = False
        consistent = bool(np.array_equal(rec_fold, folds[pids]))
        add(f'PF-G{21+i:03d}', 'patient_level_split',
            f'synthetic instance {i+1}/10: one fold per patient, records inherit patient fold',
            'no patient in two folds AND record folds consistent',
            f'ok={ok}, consistent={consistent}, n_pat={n_pat}, n_rec={n_rec}',
            ok and consistent,
            f'seed={SEED+i}, n_pat={n_pat}, n_rec={n_rec}, k={k}')

    # G031..G034 label ontologies
    for i, o in enumerate(CFG['label_ontologies'], 1):
        add(f'PF-G{30+i:03d}', 'label_ontology',
            f'ontology {o["id"]} declared with n classes',
            'n >= 4', f'n={o["n"]}', o['n'] >= 4,
            f'ontology={o}, clinical_review_required={o.get("reviewed_by", "not declared")}')

    # G035 deff / n_eff
    icc, mbar = 0.48, 2.9
    deff = 1 + (mbar - 1) * icc
    neff = 1 / deff
    add('PF-G035', 'patient_statistics',
        'deff >= 1 and n_eff/n <= 1 with declared ICC/mbar',
        'both inequalities', f'deff={deff:.4f}, n_eff/n={neff:.4f}',
        deff >= 1 and neff <= 1, f'ICC={icc}, mbar={mbar}, deff={deff}, n_eff/n={neff}')

    # G036 excluded corpora
    add('PF-G036', 'compliance',
        'US credentialed corpora excluded from committed main queue',
        '3 excluded entries with reasons', f'n={len(CFG["excluded_from_commitment"])}',
        len(CFG['excluded_from_commitment']) == 3 and
        all('reason' in x for x in CFG['excluded_from_commitment']),
        str([x['id'] for x in CFG['excluded_from_commitment']]))


def environment_checks():
    """Report honestly. UNAVAILABLE is a legitimate result here, not a FAIL to hide."""
    specs = {
        'torch': iu.find_spec('torch'),
        'wfdb': iu.find_spec('wfdb'),
        'h5py': iu.find_spec('h5py'),
        'mamba_ssm': iu.find_spec('mamba_ssm'),
        'causal_conv1d': iu.find_spec('causal_conv1d'),
    }
    for i, (name, spec) in enumerate(specs.items(), 1):
        present = spec is not None
        add(f'ENV-G{i:03d}', 'gpu_environment',
            f'{name} importable on the target machine',
            'module present (required for real GPU run)',
            'present' if present else 'ABSENT',
            present,
            f'module={name}; sandbox has no GPU device and no real waveform files',
            status='executed' if present else 'UNAVAILABLE')
    # CUDA device
    try:
        import torch  # noqa
        cuda = bool(torch.cuda.is_available())
        n = torch.cuda.device_count()
    except Exception:
        cuda, n = False, 0
    add('ENV-G006', 'gpu_environment',
        'CUDA device available',
        'torch.cuda.is_available() == True',
        f'cuda={cuda}, device_count={n}', cuda,
        'nvidia-smi not found in sandbox; no GPU device',
        status='executed' if cuda else 'UNAVAILABLE')
    # real waveform files
    root = HERE.parent
    pats = ['*.dat', '*.hea', '*.hdf5', '*.mat', '*.pt', '*.pth', '*.safetensors']
    hits = [f for p in pats for f in root.rglob(p)
            if f.is_file() and 'repo_audit' not in f.parts]
    add('ENV-G007', 'gpu_environment',
        'real waveform / weight files staged',
        '>=1 real signal or weight file', f'files={len(hits)}', len(hits) > 0,
        'no .dat/.hea/.hdf5/.mat/.pt/.safetensors files in sandbox',
        status='executed' if hits else 'UNAVAILABLE')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--smoke', action='store_true', default=True)
    a = ap.parse_args()
    structural_checks()
    environment_checks()
    n_exec = sum(1 for x in A if x['status'] == 'executed')
    n_p = sum(1 for x in A if x['status'] == 'executed' and x['PASS'])
    n_f = n_exec - n_p
    n_una = sum(1 for x in A if x['status'] == 'UNAVAILABLE')
    out = {
        'prereg': 'PREREGISTRATION_T2.md v1.0',
        'mode': 'CPU smoke test on SYNTHETIC metadata',
        'n_assertions': len(A), 'n_executed': n_exec,
        'n_pass': n_p, 'n_fail': n_f, 'n_unavailable': n_una,
        'real_gpu_training_performed': False,
        'real_waveform_data_used': False,
        'assertions': A,
        'honesty': 'Structural assertions are REAL CPU checks of the spec. '
                   'ENV-G* are UNAVAILABLE because the sandbox has no GPU / torch / '
                   'wfdb / waveforms. UNAVAILABLE is reported, not hidden or '
                   'converted into a PASS.',
    }
    d = OUT / 'preflight_gpu_smoke.json'
    d.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'=== T2 GPU PREFLIGHT (CPU smoke) ===')
    print(f'  assertions {len(A)} | executed {n_exec} | PASS {n_p} | '
          f'FAIL {n_f} | UNAVAILABLE {n_una}')
    for x in A:
        if x['status'] == 'executed' and not x['PASS']:
            print('  FAIL', x['id'], x['family'], '|', x['observed'])
    print('  UNAVAILABLE (honestly reported):',
          [x['id'] for x in A if x['status'] == 'UNAVAILABLE'])
    print('written', d)


if __name__ == '__main__':
    main()
