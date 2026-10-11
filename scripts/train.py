"""ECG classifier training script.

Usage:
    python scripts/train.py --dataset synthetic --epochs 5
    python scripts/train.py --dataset ptbxl --data_dir ./data/ptbxl
"""

import os
import sys
import random
import argparse
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, Dataset
from pathlib import Path
from typing import Dict, Any, Optional

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.models.ecg_classifier import ECGClassifier
from src.utils.calibration import (
    compute_all_metrics, fit_temperature, apply_temperature, plot_reliability_diagram,
    smooth_ece, benefit_inference, two_layer_benefit_inference,
)
from src.data.datasets import ECGNPZDataset
from src.data.splits import patient_wise_split
from src.data.mapping import SUPERCLASSES

# N1-r2 fix: Explicit n_bins constant (kept consistent across metric calls).
N_BINS = 10


def set_seed(seed: int, deterministic: bool = False):
    import random
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    if deterministic:
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
        os.environ['CUBLAS_WORKSPACE_CONFIG'] = ':4096:8'


class ECGDataset(Dataset):
    """ECG dataset base class; subclasses implement __getitem__ and __len__."""

    def __init__(self, data_dir: str, split: str = 'train'):
        self.data_dir = Path(data_dir)
        self.split = split
        self.samples = []

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        raise NotImplementedError


class SyntheticECGDataset(ECGDataset):
    """Synthetic ECG dataset with a fixed seed; tensors are generated once in __init__ and cached.

    Caching the tensors (rather than re-sampling per __getitem__ call) keeps the
    validation set identical across epochs, so ECE-based early stopping does not
    select on freshly drawn noise.
    """

    def __init__(
        self,
        n_samples: int = 1000,
        n_leads: int = 12,
        seq_length: int = 1000,
        n_classes: int = 5,
        split: str = 'train',
        seed: int = 42,
    ):
        super().__init__(data_dir="", split=split)
        self.n_classes = n_classes
        g = torch.Generator().manual_seed(seed)
        self.X = torch.randn(n_samples, n_leads, seq_length, generator=g)
        self.y = torch.randint(0, n_classes, (n_samples,), generator=g)

    def __len__(self):
        return len(self.y)

    def __getitem__(self, idx):
        return self.X[idx], int(self.y[idx])


def create_dataloader(
    dataset: Dataset,
    batch_size: int = 32,
    num_workers: int = 0,
    shuffle: bool = True,
    drop_last: bool = False,  # Keep the last (partial) batch for val/test loaders
) -> DataLoader:
    """Build a DataLoader."""
    return DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=shuffle,
        num_workers=num_workers,
        pin_memory=True,
        drop_last=drop_last,
    )



def train_epoch(
    model: nn.Module,
    dataloader: DataLoader,
    optimizer: torch.optim.Optimizer,
    device: torch.device,
    epoch: int,
    max_grad_norm: float = 1.0,
) -> Dict[str, float]:
    """Run one training epoch (with gradient clipping and non-finite loss guarding)."""
    model.train()
    total_loss = 0.0
    total_samples = 0
    correct = 0

    for batch_idx, (x, y) in enumerate(dataloader):
        x, y = x.to(device), y.to(device)

        optimizer.zero_grad()
        logits, _ = model(x, return_probs=False)
        loss = F.cross_entropy(logits, y)

        if not torch.isfinite(loss):  # Guard against non-finite loss
            print(f"[WARN] Epoch {epoch} batch {batch_idx}: non-finite loss, skipped")
            optimizer.zero_grad()
            continue

        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_grad_norm)  # Gradient clipping
        optimizer.step()

        bs = y.size(0)
        total_loss += loss.item() * bs  # Weight batch loss by sample count
        total_samples += bs
        _, predicted = logits.max(1)
        correct += predicted.eq(y).sum().item()

    return {
        'train_loss': total_loss / max(total_samples, 1),
        'train_acc': 100. * correct / max(total_samples, 1),
    }


def evaluate(
    model: nn.Module,
    dataloader: DataLoader,
    device: torch.device,
    compute_calibration: bool = True,
) -> Dict[str, Any]:
    """Evaluate model; returns the prob matrix for later temperature fitting."""
    model.eval()
    total_loss = 0.0
    correct = 0
    total = 0

    all_probs, all_labels = [], []

    with torch.no_grad():
        for x, y in dataloader:
            x, y = x.to(device), y.to(device)
            logits, probs = model(x)
            loss = F.cross_entropy(logits, y)

            bs = y.size(0)
            total_loss += loss.item() * bs
            _, predicted = logits.max(1)
            correct += predicted.eq(y).sum().item()
            total += bs

            all_probs.append(probs.cpu().numpy())
            all_labels.append(y.cpu().numpy())

    all_probs = np.concatenate(all_probs, axis=0)
    all_labels = np.concatenate(all_labels, axis=0)

    results = {
        'loss': total_loss / max(total, 1),
        'acc': 100. * correct / max(total, 1),
        'probs': all_probs,
        'labels': all_labels,
    }

    if compute_calibration:
        if all_probs.ndim != 2:  # Expected a 2D probability matrix
            raise ValueError(f"evaluate expects a 2D probability matrix, got ndim={all_probs.ndim}")
        max_probs = all_probs.max(axis=1)
        correct_mask = (all_probs.argmax(axis=1) == all_labels).astype(float)
        cal_metrics = compute_all_metrics(max_probs, correct_mask, n_bins=N_BINS, n_bootstrap=0)  # N1-r2 fix: explicit n_bins
        results.update(cal_metrics)

    return results


def train_model(
    model: nn.Module,
    train_loader: DataLoader,
    val_loader: DataLoader,
    config: Dict[str, Any],
    device: torch.device,
) -> nn.Module:
    """Full training loop: ECE-based early stopping on the val set; temperature fit on cal and reported on test."""
    optimizer = torch.optim.Adam(
        model.parameters(),
        lr=config.get('lr', 1e-3),
        weight_decay=config.get('weight_decay', 1e-4),
    )
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
        optimizer,
        T_max=config.get('epochs', 100),
        eta_min=config.get('lr_min', 1e-6),
    )

    best_ece = float('inf')
    patience = config.get('patience', 10)
    patience_counter = 0

    save_dir = Path(config['save_dir'])
    save_dir.mkdir(parents=True, exist_ok=True)
    ckpt_path = save_dir / 'best_model.pt'

    epochs = config.get('epochs', 100)
    for epoch in range(epochs):
        train_metrics = train_epoch(model, train_loader, optimizer, device, epoch)
        val_metrics = evaluate(model, val_loader, device, compute_calibration=True)
        scheduler.step()

        print(f"Epoch {epoch+1}/{epochs} | "
              f"train_loss={train_metrics['train_loss']:.4f} "
              f"train_acc={train_metrics['train_acc']:.2f}% | "
              f"val_loss={val_metrics['loss']:.4f} "
              f"val_acc={val_metrics['acc']:.2f}% "
              f"ECE={val_metrics.get('ece', float('nan')):.4f}")

        current_ece = val_metrics.get('ece', float('inf'))
        if current_ece < best_ece:
            best_ece = current_ece
            patience_counter = 0
            torch.save({
                'epoch': epoch,
                'model_state_dict': model.state_dict(),
                'num_classes': getattr(model, 'num_classes', None),
                'val_acc': val_metrics['acc'],
                'val_ece': current_ece,
            }, ckpt_path)
        else:
            patience_counter += 1
            if patience_counter >= patience:
                print(f"Early stopping at epoch {epoch+1}")
                break

    if not ckpt_path.exists():
        torch.save({
            'epoch': epoch,
            'model_state_dict': model.state_dict(),
            'num_classes': getattr(model, 'num_classes', None),
            'val_acc': val_metrics['acc'],
            'val_ece': val_metrics.get('ece', float('nan')),
        }, ckpt_path)

    # Load self-saved checkpoint (weights_only=False to allow python scalars).
    checkpoint = torch.load(ckpt_path, weights_only=False)
    model.load_state_dict(checkpoint['model_state_dict'])

    return model


def _carve_val_patients(pat_label: dict, frac: float, seed: int) -> set:
    """Patient-level val carve: deterministically sample a frac of patients, stratified by patient majority label."""
    rng = np.random.default_rng(seed)
    val_patients: set = set()
    for lab in sorted(set(pat_label.values())):
        members = sorted(p for p, l in pat_label.items() if l == lab)
        members = list(np.asarray(members, dtype=object)[rng.permutation(len(members))])
        n_val = max(1, int(round(len(members) * frac)))
        val_patients.update(members[:n_val])
    return val_patients


def _pos_of_patients(meta: 'pd.DataFrame', patients) -> np.ndarray:
    return np.sort(np.flatnonzero(meta['patient_id'].isin(set(patients)).to_numpy()))


def _build_npz_datasets(meta: 'pd.DataFrame', meta_csv: Path, pos: dict,
                        label_map: dict):
    """Build ECGNPZDataset per row position; roles map train/val->cal, cal->cal, test->test."""
    from src.data.datasets import ECGNPZDataset
    roles = {'train': 'train', 'val': 'cal', 'cal': 'cal', 'test': 'test'}
    return {
        name: ECGNPZDataset(meta_csv, split_indices=p.tolist(),
                            label_map=label_map, split_role=roles[name])
        for name, p in pos.items()
    }


def build_ptbxl_datasets(data_dir: str, seed: int, limit: Optional[int] = None,
                         subspace: Optional[tuple] = None):
    """Real PTB-XL four-way split (preregistered protocol §2): folds 1-8 train (+ patient-level val carve) / fold 9 cal / fold 10 test.

    - Splitting uses src.data.splits.ptbxl_official_folds (official strat_fold; patients never cross folds).
    - Val carve: within folds 1-8, sample 12.5% of patients stratified by patient majority label (patient-level, avoids record-level leakage).
    - Fix (2026-10-05 lab tree; ported to this tree 2026-10-11): the carved val records are excluded from the
      training loader via np.setdiff1d, and assert_no_leakage is re-derived from the FINAL loader positions
      (pos) instead of the pre-carve patient lists -- previously the assertion checked a different, already-reduced
      variable and therefore passed while val records stayed in the train loader (early stopping was monitoring
      the training set; see docs/PTBXL_VAL_LEAK_RETRAIN_PLAN.md, 20/60 cells retrained 2026-10-07).
    - assert_no_leakage hard-asserts that train/val/cal/test patient sets are pairwise disjoint (protocol-mandated check).
    - Returns clusters_test (patient ids of test records, aligned to dataset order) for the patient-level cluster bootstrap in the primary endpoint.
      patient-level cluster bootstrap for the primary endpoint (via benefit_inference(clusters=)).
    - subspace: if provided (e.g. SUBSPACE_CPSC), filter to the subspace and remap label_map (protocol-symmetric recomputation).
    """
    from src.data.splits import ptbxl_official_folds, assert_no_leakage
    from src.data.mapping import SUPERCLASSES

    data_dir = Path(data_dir)
    meta_csv = data_dir / 'metadata_single_label.csv'
    if not meta_csv.exists():
        raise FileNotFoundError(
            f"{meta_csv} not found; run scripts/preprocess_ptbxl.py first to generate it")
    meta = pd.read_csv(meta_csv)
    missing = {'patient_id', 'strat_fold'} - set(meta.columns)
    if missing:
        raise KeyError(
            f"metadata missing columns {missing} (patient_id is required; re-run "
            "preprocess_ptbxl.py, the vendor cinc script does not emit this column)")

    if subspace is not None:
        from src.data.mapping import filter_subspace
        rep = filter_subspace(meta['label'].tolist(), subspace)
        if rep['n_dropped'] > 0:
            print(f"[ptbxl] subspace reduction: kept {rep['n_kept']} records "
                  f"(subspace {rep['allowed']}), dropped {rep['n_dropped']} records "
                  f"(distribution {rep['dropped_counts']})")
        kept_indices = rep['kept_indices']
        meta_f = meta.iloc[kept_indices].reset_index(drop=True)
        label_map = {c: i for i, c in enumerate(subspace)}
        split_meta = meta_f
    else:
        label_map = {c: i for i, c in enumerate(SUPERCLASSES)}  # NORM, MI, STTC, CD, HYP -> 0..4
        kept_indices = None
        split_meta = meta

    unknown = sorted(set(split_meta['label']) - set(label_map))
    if unknown:
        raise KeyError(f"labels outside the super-class taxonomy: {unknown}")

    folds_df = split_meta[['patient_id']].assign(fold=split_meta['strat_fold'])
    splits = ptbxl_official_folds(folds_df)

    # ---- Patient-level val carve within folds 1-8 (12.5% of patients, stratified by patient majority label) ----
    train_pos = np.sort(np.asarray(splits['train']['records'], dtype=int))
    meta18 = split_meta.loc[train_pos]
    pat_label = meta18.groupby('patient_id')['label'].agg(
        lambda s: s.mode().iat[0]).to_dict()
    val_patients = _carve_val_patients(pat_label, 0.125, seed + 100)
    train_patients = sorted(set(pat_label) - val_patients)

    cal_patients = sorted(set(np.asarray(splits['cal']['patients'], dtype=object).tolist()))
    test_patients = sorted(set(np.asarray(splits['test']['patients'], dtype=object).tolist()))

    def _pos_of(patients):
        return _pos_of_patients(split_meta, patients)

    # ---- Fix [VAL-LEAK-2026-10-05], ported from the lab tree on 2026-10-11 ----
    # Old behavior: pos['train'] took the FULL folds-1-8 train_pos, while train_patients
    # (already minus val) only fed assert_no_leakage -- the asserted object and the dataset
    # object were mismatched, so the assertion always passed while val-patient records
    # entered BOTH the train and val loaders (early stopping was monitoring the training
    # set -> model selection silently invalid; this is the leak documented in
    # docs/PTBXL_VAL_LEAK_RETRAIN_PLAN.md, 20/60 cells retrained on 2026-10-07).
    # The fix subtracts val records from train_pos and re-derives the assertion FROM pos,
    # so the asserted patient sets are exactly the records entering each loader.
    val_pos = _pos_of(val_patients)
    train_pos = np.setdiff1d(train_pos, val_pos)

    pos = {'train': np.sort(train_pos), 'val': val_pos,
           'cal': _pos_of(cal_patients), 'test': _pos_of(test_patients)}

    # Hard assertion: the four splits are pairwise disjoint by patient (protocol §2);
    # asserted sets are derived from pos (the final loader positions), not from the pre-carve lists.
    assert_no_leakage({
        k: sorted(set(split_meta.loc[v, 'patient_id'].tolist()))
        for k, v in pos.items()
    })
    if limit is not None:  # For debugging: truncate each split to the first limit//4 records (deterministic).
        pos = {k: v[:max(limit // 4, 20)] for k, v in pos.items()}

    # clusters_test must stay aligned to the test dataset order (split_indices preserve the given order).
    clusters_test = split_meta.loc[pos['test'], 'patient_id'].to_numpy().astype(int)

    if kept_indices is not None:
        pos_orig = {k: np.array([kept_indices[i] for i in v], dtype=int)
                    for k, v in pos.items()}
    else:
        pos_orig = pos
    datasets = _build_npz_datasets(meta, meta_csv, pos_orig, label_map)

    print(f"[ptbxl] patient-level 4-way split: train({len(train_patients)}p/{len(pos['train'])}r) "
          f"val({len(val_patients)}p/{len(pos['val'])}r) "
          f"cal({len(cal_patients)}p/{len(pos['cal'])}r) "
          f"test({len(test_patients)}p/{len(pos['test'])}r)")
    print(f"[ptbxl] label distribution (test): "
          f"{pd.Series(split_meta.loc[pos['test'], 'label']).value_counts().to_dict()}")
    return datasets, clusters_test


def build_chapman_datasets(data_dir: str, seed: int, limit: Optional[int] = None,
                           subspace: Optional[tuple] = None):
    """Real Chapman-Shaoxing four-way split (preregistered protocol §2: patient-level stratified 70/10/20 with fixed seed).

    - patient_wise_split(0.7, 0.1, 0.2) -> train/cal/test (stratified by patient majority label).
    - Val carve: within train, sample an additional 1/7 of patients (-> overall ~60/10/10/20, patient-level).
    - One ECG per patient (Zheng 2022); patient_id = record stem (preprocess output).
    - assert_no_leakage hard-asserts the four splits; clusters_test wired as in ptbxl.
    - subspace: if provided (e.g. SUBSPACE_CPSC), filter to the subspace and remap label_map (protocol-symmetric recomputation).
    """
    from src.data.splits import patient_wise_split, assert_no_leakage
    from src.data.mapping import SUPERCLASSES

    data_dir = Path(data_dir)
    meta_csv = data_dir / 'metadata_single_label.csv'
    if not meta_csv.exists():
        raise FileNotFoundError(
            f"{meta_csv} not found; run scripts/preprocess_chapman.py first to generate it")
    meta = pd.read_csv(meta_csv)
    if 'patient_id' not in meta.columns:
        raise KeyError("metadata missing patient_id column (run preprocess_chapman.py)")

    if subspace is not None:
        from src.data.mapping import filter_subspace
        rep = filter_subspace(meta['label'].tolist(), subspace)
        if rep['n_dropped'] > 0:
            print(f"[chapman] subspace reduction: kept {rep['n_kept']} records "
                  f"(subspace {rep['allowed']}), dropped {rep['n_dropped']} records "
                  f"(distribution {rep['dropped_counts']})")
        kept_indices = rep['kept_indices']
        meta_f = meta.iloc[kept_indices].reset_index(drop=True)
        label_map = {c: i for i, c in enumerate(subspace)}
        split_meta = meta_f
    else:
        label_map = {c: i for i, c in enumerate(SUPERCLASSES)}
        kept_indices = None
        split_meta = meta

    unknown = sorted(set(split_meta['label']) - set(label_map))
    if unknown:
        raise KeyError(f"labels outside the super-class taxonomy: {unknown}")

    patients = split_meta['patient_id'].unique().tolist()
    pat_label = split_meta.groupby('patient_id')['label'].agg(
        lambda s: s.mode().iat[0]).to_dict()
    t3 = patient_wise_split(patients, pat_label,
                            ratios=(0.7, 0.1, 0.2), seed=seed)
    train_patients = sorted(set(t3['train']))
    cal_patients = sorted(set(t3['cal']))
    test_patients = sorted(set(t3['test']))

    # Val carve within train: 1/7 of train patients -> overall ~60/10/10/20.
    sub = {p: pat_label[p] for p in train_patients}
    val_patients = _carve_val_patients(sub, 1 / 7, seed + 100)
    train_patients = sorted(set(train_patients) - val_patients)

    assert_no_leakage({
        'train': train_patients, 'val': sorted(val_patients),
        'cal': cal_patients, 'test': test_patients,
    })

    pos = {name: _pos_of_patients(split_meta, ps) for name, ps in
           {'train': train_patients, 'val': val_patients,
            'cal': cal_patients, 'test': test_patients}.items()}
    if limit is not None:
        pos = {k: v[:max(limit // 4, 20)] for k, v in pos.items()}

    clusters_test = split_meta.loc[pos['test'], 'patient_id'].to_numpy().astype(str)

    if kept_indices is not None:
        pos_orig = {k: np.array([kept_indices[i] for i in v], dtype=int)
                    for k, v in pos.items()}
    else:
        pos_orig = pos
    datasets = _build_npz_datasets(meta, meta_csv, pos_orig, label_map)

    print(f"[chapman] patient-level 4-way split: train({len(train_patients)}p/{len(pos['train'])}r) "
          f"val({len(val_patients)}p/{len(pos['val'])}r) "
          f"cal({len(cal_patients)}p/{len(pos['cal'])}r) "
          f"test({len(test_patients)}p/{len(pos['test'])}r)")
    print(f"[chapman] label distribution (test): "
          f"{pd.Series(split_meta.loc[pos['test'], 'label']).value_counts().to_dict()}")
    return datasets, clusters_test


def build_cpsc_datasets(data_dir: str, seed: int, limit: Optional[int] = None):
    """CPSC2018 (CPSC Database + CPSC-Extra) four-way split (preregistered protocol §2: 4-class reduced subspace, patient-level stratified 70/10/20).

    - SUBSPACE_CPSC = {NORM, CD, STTC, MI} (4 classes); HYP (n=11) is dropped and counted via filter_subspace.
    - WARNING: the ORDER of SUBSPACE_CPSC is the integer label encoding -- do not change it alone.
    - patient_wise_split(0.7, 0.1, 0.2) -> train/cal/test (stratified by patient majority label).
    - Val carve: within train, sample an additional 1/7 of patients (-> overall ~60/10/10/20, patient-level).
    - Each record = one patient (patient_id = record name); no strat_fold.
    - assert_no_leakage hard-asserts the four splits; clusters_test wired as in ptbxl/chapman
    """
    from src.data.splits import patient_wise_split, assert_no_leakage
    from src.data.mapping import SUBSPACE_CPSC, filter_subspace

    data_dir = Path(data_dir)
    meta_csv = data_dir / 'metadata_single_label.csv'
    if not meta_csv.exists():
        raise FileNotFoundError(
            f"{meta_csv} not found; run scripts/preprocess_cpsc.py first to generate it")
    meta = pd.read_csv(meta_csv)
    if 'patient_id' not in meta.columns:
        raise KeyError("metadata missing patient_id column (run preprocess_cpsc.py)")

    rep = filter_subspace(meta['label'].tolist(), SUBSPACE_CPSC)
    if rep['n_dropped'] > 0:
        print(f"[cpsc] subspace reduction: kept {rep['n_kept']} records "
              f"(subspace {rep['allowed']}), dropped {rep['n_dropped']} records "
              f"(distribution {rep['dropped_counts']})")
    kept_indices = rep['kept_indices']
    meta_f = meta.iloc[kept_indices].reset_index(drop=True)

    label_map = {c: i for i, c in enumerate(SUBSPACE_CPSC)}
    unknown = sorted(set(meta_f['label']) - set(label_map))
    if unknown:
        raise KeyError(f"labels outside the reduced subspace: {unknown}")

    patients = meta_f['patient_id'].unique().tolist()
    pat_label = meta_f.groupby('patient_id')['label'].agg(
        lambda s: s.mode().iat[0]).to_dict()
    t3 = patient_wise_split(patients, pat_label,
                            ratios=(0.7, 0.1, 0.2), seed=seed)
    train_patients = sorted(set(t3['train']))
    cal_patients = sorted(set(t3['cal']))
    test_patients = sorted(set(t3['test']))

    sub = {p: pat_label[p] for p in train_patients}
    val_patients = _carve_val_patients(sub, 1 / 7, seed + 100)
    train_patients = sorted(set(train_patients) - val_patients)

    assert_no_leakage({
        'train': train_patients, 'val': sorted(val_patients),
        'cal': cal_patients, 'test': test_patients,
    })

    pos = {name: _pos_of_patients(meta_f, ps) for name, ps in
           {'train': train_patients, 'val': val_patients,
            'cal': cal_patients, 'test': test_patients}.items()}
    if limit is not None:
        pos = {k: v[:max(limit // 4, 20)] for k, v in pos.items()}

    clusters_test = meta_f.loc[pos['test'], 'patient_id'].to_numpy().astype(str)

    pos_orig = {k: np.array([kept_indices[i] for i in v], dtype=int)
                for k, v in pos.items()}
    datasets = _build_npz_datasets(meta, meta_csv, pos_orig, label_map)

    print(f"[cpsc] patient-level 4-way split: train({len(train_patients)}p/{len(pos['train'])}r) "
          f"val({len(val_patients)}p/{len(pos['val'])}r) "
          f"cal({len(cal_patients)}p/{len(pos['cal'])}r) "
          f"test({len(test_patients)}p/{len(pos['test'])}r)")
    print(f"[cpsc] label distribution (test): "
          f"{pd.Series(meta_f.loc[pos['test'], 'label']).value_counts().to_dict()}")
    return datasets, clusters_test


def main():
    parser = argparse.ArgumentParser(description='Train ECG Classifier')
    parser.add_argument('--dataset', type=str, default='synthetic',
                        choices=['synthetic', 'ptbxl', 'chapman', 'cpsc'])
    parser.add_argument('--data_dir', type=str, default='./data')
    parser.add_argument('--epochs', type=int, default=50)
    parser.add_argument('--batch_size', type=int, default=16)
    parser.add_argument('--lr', type=float, default=1e-3)
    parser.add_argument('--d_model', type=int, default=64,  # 512 channels cause OOM
                        help='Hidden dimension')
    parser.add_argument('--n_layers', type=int, default=2)
    parser.add_argument('--arch', type=str, default='mamba',
                        choices=['mamba', 'resnet1d', 'inceptiontime'],
                        help='Backbone: inceptiontime | resnet1d (the preregistered 60-cell '
                             'transfer grid); mamba is exploratory-only and NOT part of the '
                             '60-cell grid (see README "Reproducing the results")')
    parser.add_argument('--num_classes', type=int, default=None,
                        help='Class count. Auto-derived from --dataset for real datasets '
                             '(ptbxl/chapman=5, cpsc=4); defaults to 5 for --dataset synthetic. '
                             'An explicit mismatch raises.')
    parser.add_argument('--seq_length', type=int, default=1000)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--save_dir', type=str, default='checkpoints')
    parser.add_argument('--limit', type=int, default=None,
                        help='[debug] truncate each ptbxl split to the first limit/4 records (smoke test)')
    parser.add_argument('--two-layer', action='store_true',
                        help='Enable two-layer joint bootstrap (preregistered protocol §7:117; propagate temperature-fit-set uncertainty into the CI. Recommended for real-data runs)')
    args = parser.parse_args()

    # ---- num_classes resolution (fix 2026-10-11: the old default 5 silently built a 5-head
    # model for cpsc (4 classes), which eval_transfer --load-model then refused; a ghost head
    # you only discover at the end of the chain). ----
    DATASET_NUM_CLASSES = {'ptbxl': 5, 'chapman': 5, 'cpsc': 4}
    if args.dataset == 'synthetic':
        if args.num_classes is None:
            args.num_classes = 5
    else:
        expected = DATASET_NUM_CLASSES[args.dataset]
        if args.num_classes is not None and args.num_classes != expected:
            raise ValueError(
                f"--num_classes={args.num_classes} != class count of dataset "
                f"'{args.dataset}' ({expected}). Pass --num_classes {expected} "
                f"(or omit it) -- a mismatched head cannot be evaluated by eval_transfer.")
        args.num_classes = expected

    if args.arch == 'mamba':
        print("[WARN] --arch mamba is NOT part of the preregistered 60-cell grid "
              "{inceptiontime, resnet1d}; pass --arch explicitly for grid reproduction "
              "(README: 'Reproducing the results').")

    set_seed(args.seed)
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"Using device: {device}, seed={args.seed}")

    # ============ Four-way split: train / val / cal / test ============
    if args.dataset == 'synthetic':
        datasets = {
            'train': SyntheticECGDataset(800, 12, args.seq_length, args.num_classes, 'train', seed=args.seed),
            'val':   SyntheticECGDataset(200, 12, args.seq_length, args.num_classes, 'val',   seed=args.seed + 1),
            'cal':   SyntheticECGDataset(200, 12, args.seq_length, args.num_classes, 'cal',   seed=args.seed + 2),
            'test':  SyntheticECGDataset(200, 12, args.seq_length, args.num_classes, 'test',  seed=args.seed + 3),
        }
        clusters_test = None  # Synthetic data has no patient structure (registered in preregistered protocol §11).
    elif args.dataset == 'ptbxl':
        datasets, clusters_test = build_ptbxl_datasets(
            args.data_dir, args.seed, limit=args.limit)
    elif args.dataset == 'chapman':
        datasets, clusters_test = build_chapman_datasets(
            args.data_dir, args.seed, limit=args.limit)
    elif args.dataset == 'cpsc':
        datasets, clusters_test = build_cpsc_datasets(
            args.data_dir, args.seed, limit=args.limit)
    else:
        raise NotImplementedError(f"Dataset {args.dataset} not implemented yet")

    loaders = {
        'train': create_dataloader(datasets['train'], args.batch_size, shuffle=True, drop_last=True),
        'val':   create_dataloader(datasets['val'], args.batch_size, shuffle=False),
        'cal':   create_dataloader(datasets['cal'], args.batch_size, shuffle=False),
        'test':  create_dataloader(datasets['test'], args.batch_size, shuffle=False),
    }

    # T frozen at 1 during training; temperature applied only as posterior TS
    model = ECGClassifier(
        in_channels=12,
        d_model=args.d_model,
        n_layers=args.n_layers,
        num_classes=args.num_classes,
        dropout=0.1,
        learnable_temp=False,
        backbone_type=args.arch,
    ).to(device)

    print(f"Model arch={args.arch}: d_model={args.d_model}, n_layers={args.n_layers}, "
          f"params={sum(p.numel() for p in model.parameters()):,}")

    # Save dir includes seed and arch so runs do not overwrite each other.
    run_dir = Path(args.save_dir) / args.dataset / args.arch / f"seed{args.seed}"
    run_dir.mkdir(parents=True, exist_ok=True)

    config = {
        'epochs': args.epochs,
        'lr': args.lr,
        'lr_min': 1e-6,
        'weight_decay': 1e-4,
        'patience': 10,
        'save_dir': str(run_dir),
    }

    model = train_model(model, loaders['train'], loaders['val'], config, device)

    # ============ Final protocol: temperature fit on cal, metrics reported only on test ============
    print(f"\n{'='*60}\nFinal Evaluation (temperature fitted on cal, reported on test)\n{'='*60}")

    cal_eval = evaluate(model, loaders['cal'], device, compute_calibration=False)
    test_eval = evaluate(model, loaders['test'], device, compute_calibration=True)

    probs_raw = test_eval['probs']        # (N, C)
    labels = test_eval['labels']          # (N,)
    max_probs_raw = probs_raw.max(axis=1)
    correct_mask = (probs_raw.argmax(axis=1) == labels).astype(float)

    # fit_temperature uses the 2D one-hot branch and only cal's own labels
    # (mixing test labels with cal probabilities would both leak and mismatch).
    one_hot_cal = np.eye(args.num_classes)[cal_eval['labels']]
    T = fit_temperature(cal_eval['probs'], one_hot_cal)
    print(f"Fitted temperature (on cal, cal labels): {T:.4f}")

    # Apply temperature at 2D-matrix level (global TS preserves argmax, hence AUROC unchanged).
    probs_cal = apply_temperature(probs_raw, T)
    max_probs_cal = probs_cal.max(axis=1)

    raw_metrics = compute_all_metrics(max_probs_raw, correct_mask, n_bins=N_BINS, n_bootstrap=1000)  # N1-r2 fix: explicit n_bins
    cal_m = compute_all_metrics(max_probs_cal, correct_mask, n_bins=N_BINS, n_bootstrap=1000)  # N1-r2 fix: explicit n_bins

    # Primary endpoint: paired cluster bootstrap of ΔECE via benefit_inference (paired CI).
    # n_bootstrap=10000 (preregistered protocol §7:116, B=10,000).
    # BCa by default (delete-group jackknife acceleration); real data (ptbxl) passes
    # patient-level clusters=clusters_test -> leave-one-cluster-out.
    rng = np.random.default_rng(args.seed)
    benefit = benefit_inference(
        max_probs_raw, max_probs_cal, correct_mask,
        metric=smooth_ece,  # Binning-free primary estimator
        n_bootstrap=10000,
        rng=rng,
        clusters=clusters_test,  # Synthetic: None -> record-level delete-group; ptbxl: patient ids
    )
    print(f"\n[primary endpoint] SmoothECE raw={benefit['raw']:.4f} -> cal={benefit['cal']:.4f}")
    print(f"[primary endpoint] ΔECE={benefit['benefit']:.4f} "
          f"[95% CI: {benefit['benefit_ci'][0]:.4f}, {benefit['benefit_ci'][1]:.4f}] "
          f"(paired bootstrap, {benefit['method']})")
    print(f"[secondary] ratio R={benefit['ratio']:.2f} [{benefit['ratio_ci'][0]:.2f}, {benefit['ratio_ci'][1]:.2f}]")

    # Two-layer joint bootstrap (preregistered protocol §7:117; enabled via --two-layer).
    if getattr(args, 'two_layer', False):
        two = two_layer_benefit_inference(
            probs_raw, labels_test=correct_mask,
            fit_probs=cal_eval['probs'],
            fit_labels=np.eye(args.num_classes)[cal_eval['labels']],
            fit_fn=fit_temperature,
            apply_fn=apply_temperature,
            metric=smooth_ece,
            b_val=200, b_test=2000,
            rng=np.random.default_rng(args.seed + 1),
        )
        print(f"[two-layer bootstrap] T̂={two['t_hat']:.4f} (sd={two['t_std']:.4f}) "
              f"ΔECE={two['benefit']:.4f} "
              f"[95% CI: {two['benefit_ci'][0]:.4f}, {two['benefit_ci'][1]:.4f}] "
              f"(T uncertainty + resampling, B_val={two['b_val']}x B_test={two['b_test']})")

    print(f"\nTest (raw):  acc={test_eval['acc']:.2f}%  ECE={raw_metrics['ece']:.4f} "
          f"[{raw_metrics['ece_ci_95'][0]:.4f}, {raw_metrics['ece_ci_95'][1]:.4f}]  "
          f"Brier(raw)={raw_metrics['brier_raw']:.4f}")
    print(f"Test (TS):   ECE={cal_m['ece']:.4f} "
          f"[{cal_m['ece_ci_95'][0]:.4f}, {cal_m['ece_ci_95'][1]:.4f}]  "
          f"Brier(TS)={cal_m['brier_raw']:.4f}")

    # Sanity check: global TS must not change argmax (AUROC unchanged).
    assert np.array_equal(probs_raw.argmax(axis=1), probs_cal.argmax(axis=1)), \
        "Global temperature scaling must not change argmax -- pipeline bug"

    # Plot reliability diagram.
    try:
        fig = plot_reliability_diagram(
            max_probs_cal, correct_mask,
            title=f"Reliability Diagram (T={T:.3f})",
            save_path=str(run_dir / 'reliability_diagram.png'),
        )
        import matplotlib.pyplot as plt
        plt.close(fig)  # Close figure to release memory.
        print(f"\nReliability diagram saved to {run_dir}/reliability_diagram.png")
    except Exception as e:
        import traceback
        print(f"Warning: Could not plot reliability diagram: {e}")
        traceback.print_exc()

    print("\nTraining complete!")


if __name__ == '__main__':
    main()
