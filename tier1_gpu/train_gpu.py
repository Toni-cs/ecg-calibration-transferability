#!/usr/bin/env python3
"""T2 GPU training / forward skeleton — TEMPLATE FOR THE GPU MACHINE.

*** THIS FILE IS NOT EXECUTED IN THIS SANDBOX ***
The sandbox has no GPU, no torch, no wfdb and no real waveforms. This module is
delivered as a syntactically-validated template (`python -m py_compile`) that
you copy to the GPU machine, install requirements, point at the real data index,
and run. Heavy deps are imported INSIDE functions so py_compile works here.

Contract (PREREGISTRATION_T2.md §2/§3):
  * lead alignment BY NAME, never channel index
  * patient-level disjoint splits
  * CODE-15% ambiguous records are NEVER confident negatives
  * every produced logits cache carries a SHA256 and the environment lock
  * seed ranges 900000-900149 / 910000-910107 frozen

Usage on the GPU machine:
  python train_gpu.py --stage A      --config configs/tier1_grid.json --out ./cache
  python train_gpu.py --stage B      --config configs/tier1_grid.json --out ./cache
  python train_gpu.py --stage forward --config configs/tier1_grid.json --out ./cache
"""
from __future__ import annotations
import argparse, hashlib, json, pathlib, random, sys

CANONICAL = ["I", "II", "III", "aVR", "aVL", "aVF",
             "V1", "V2", "V3", "V4", "V5", "V6"]


def load_config(p):
    return json.loads(pathlib.Path(p).read_text(encoding='utf-8'))


def assert_lead_alignment(header_leads, cfg):
    """BY NAME. Raises on any mismatch. Call for EVERY record."""
    canon = cfg['lead_alignment']['canonical']
    missing = [l for l in canon if l not in header_leads]
    if missing:
        raise ValueError(f'lead-by-name mismatch, missing={missing}, '
                         f'header={header_leads}. NEVER fall back to channel index.')


def assert_patient_disjoint(train_pids, eval_pids):
    overlap = set(train_pids) & set(eval_pids)
    if overlap:
        raise ValueError(f'patient leakage: {len(overlap)} shared patient_ids')
    return True


def assert_code15_negative(row):
    """Only normal_ecg is a clean negative. The 173,347 'neither' rows are NOT."""
    if row.get('normal_ecg') is True:
        return True
    if any(row.get(k) for k in ('1dAVb', 'RBBB', 'LBBB', 'SB', 'ST', 'AF')):
        return True   # explicit positive, allowed
    raise ValueError('CODE-15% ambiguous record used as confident negative')


def set_seed(seed):
    random.seed(seed)
    try:
        import numpy as np
        np.random.seed(seed)
    except ImportError:
        pass
    try:
        import torch
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
    except ImportError:
        pass


def build_model(arch, n_classes):
    """Placeholder factory. REPLACE with real architecture implementations.

    Supported arch ids (T2 §3): InceptionTime, ResNet1D, MambaPyRepo
    ECGFounderRegNet_scratch, CNN_SSM_Attention.
    """
    try:
        import torch
        import torch.nn as nn
    except ImportError as e:
        raise RuntimeError('torch required on the GPU machine') from e
    if arch in ('InceptionTime', 'ResNet1D', 'ECGFounderRegNet_scratch',
                'CNN_SSM_Attention', 'MambaPyRepo'):
        # A tiny conv stub keeps this template importable; REPLACE IT.
        return nn.Sequential(
            nn.Conv1d(12, 64, 15, padding=7), nn.ReLU(),
            nn.AdaptiveAvgPool1d(1), nn.Flatten(),
            nn.Linear(64, n_classes))
    raise ValueError(f'unknown architecture {arch}')


def make_dataloaders(cfg, stage, data_root):
    """Replace with WFDB/HDF5 readers + patient-level GroupShuffleSplit.

    Required preprocessing (frozen): bandpass 0.5-50 Hz, 60 Hz notch,
    z-score, resample to 500 Hz, fixed 10 s, lead-by-name alignment.
    ECGFounder weights additionally REQUIRE its own dataset.py pipeline.
    """
    raise NotImplementedError(
        'Implement on the GPU machine: wfdb.rdrecord / h5py, '
        'assert_lead_alignment per record, patient-level splits, '
        'assert_code15_negative on CODE-15% rows.')


def train_one_epoch(model, loader, optimizer, scaler, device):
    try:
        import torch
    except ImportError as e:
        raise RuntimeError('torch required') from e
    model.train()
    total = 0.0
    for x, y in loader:
        x, y = x.to(device), y.to(device)
        optimizer.zero_grad(set_to_none=True)
        with torch.autocast('cuda', dtype=torch.bfloat16):
            out = model(x)
            loss = torch.nn.functional.binary_cross_entropy_with_logits(out, y)
        scaler.scale(loss).backward()
        scaler.step(optimizer)
        scaler.update()
        total += float(loss.detach()) * len(x)
    return total


def export_logits_cache(model, loader, out_path, cfg, meta):
    """Freeze-and-export. Produces the CPU-side cache that Stage C consumes."""
    try:
        import torch
        import numpy as np
    except ImportError as e:
        raise RuntimeError('torch + numpy required') from e
    model.eval()
    chunks = []
    with torch.no_grad():
        for x, _ in loader:
            with torch.autocast('cuda', dtype=torch.bfloat16):
                chunks.append(model(x.to('cuda')).float().cpu().numpy())
    arr = np.concatenate(chunks, axis=0).astype('float32')
    np.savez_compressed(out_path, logits=arr,
                        patient_id=np.asarray(meta['patient_id']),
                        group_meta=np.asarray(meta['group_meta']),
                        split=np.asarray(meta['split']),
                        lead_names=np.asarray(CANONICAL))
    h = hashlib.sha256(pathlib.Path(out_path).read_bytes()).hexdigest()
    record = {'file': str(out_path), 'sha256': h, 'n_records': int(arr.shape[0]),
              'n_classes': int(arr.shape[1]), 'config_schema': cfg['schema_version'],
              'lead_alignment': cfg['lead_alignment']['rule'],
              'statistical_unit': cfg['statistics']['unit']}
    return record


def run_stage_a(cfg, out_dir):
    """150 runs = 6 corpora x 5 architectures x 5 seeds (seeds 900000-900149)."""
    A = cfg['stage_a']
    plan = []
    for i, (corpus, arch, seed) in enumerate(
            [(c, a, s) for c in A['corpora'] for a in A['architectures']
             for s in A['seeds']]):
        plan.append({'run_id': f'T2-A-{i:04d}', 'corpus': corpus,
                     'arch': arch, 'seed': seed, 'epochs': A['epochs'],
                     'batch': A['batch'], 'precision': A['precision'],
                     'status': 'PLANNED_NOT_EXECUTED'})
    assert len(plan) == 150
    return plan


def run_stage_b(cfg, out_dir):
    """108 runs = 4 models x 3 modes x 3 corpora x 3 seeds (910000-910107)."""
    B = cfg['stage_b']
    plan = []
    for i, (m, mode, c, s) in enumerate(
            [(m, mo, c, s) for m in B['foundation_models'] for mo in B['modes']
             for c in B['external_corpora'] for s in B['seeds']]):
        plan.append({'run_id': f'T2-B-{i:04d}', 'model': m, 'mode': mode,
                     'corpus': c, 'seed': s, 'status': 'PLANNED_NOT_EXECUTED'})
    assert len(plan) == 108
    return plan


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--stage', choices=['A', 'B', 'forward'], required=True)
    ap.add_argument('--config', default='configs/tier1_grid.json')
    ap.add_argument('--out', default='./cache')
    ap.add_argument('--data-root', default='./data')
    ap.add_argument('--plan-only', action='store_true',
                    help='only emit the frozen run plan; no GPU needed')
    a = ap.parse_args()
    cfg = load_config(a.config)
    out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)

    if a.stage == 'A':
        plan = run_stage_a(cfg, out)
    elif a.stage == 'B':
        plan = run_stage_b(cfg, out)
    else:
        plan = [{'run_id': 'T2-FWD-0000', 'corpus': 'main_queue',
                 'n_records': sum(c['records'] for c in cfg['catalog']
                                  if c['tier'] in ('open', 'open-subset',
                                                   'academic-request')),
                 'status': 'PLANNED_NOT_EXECUTED'}]
    dest = out / f'run_plan_stage_{a.stage}.json'
    dest.write_text(json.dumps({'prereg': 'T2 v1.0', 'plan': plan,
                                'gpu_training_executed': False},
                               indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'stage {a.stage}: {len(plan)} runs PLANNED (not executed) -> {dest}')
    if a.plan_only:
        return 0
    print('Real GPU execution requires torch + CUDA + wfdb + real waveforms.')
    print('This sandbox has none of them; nothing was trained.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
