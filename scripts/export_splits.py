"""Export patient-level split indices (paper Code/Data availability deliverable).

Purpose: export the data splits actually used by the 60-seed experiments to CSV, so
anyone can exactly reconstruct this study's data splits from the public source database
without trusting a prose description of the split logic.

Output: splits/{dataset}[_sub4]_seed{S}.csv with columns:
  record_id       preprocessed-record id (npy stem, consistent with metadata_single_label.csv)
  patient_id      patient id
  split           train / val / cal / test (data-loader semantics, see below)
  in_train_loader yes/no -- whether the record also enters the training loader
[PTB-XL as-used semantics, post-repair] Since the 2026-10-05 val-leak repair, train.py
build_ptbxl_datasets subtracts the carved val-patient records from the training loader
(np.setdiff1d); the carve is patient-level and assert_no_leakage is re-derived from the
final loader positions. This export therefore flags in_train_loader=yes iff the record
enters the train loader (split == 'train'), and the 21,397 val-patient rows across the
10 ptbxl-family seed files read in_train_loader=no (they read yes in the pre-repair
snapshots). cal (fold9) / test (fold10) have zero patient overlap with folds 1-8
(asserted). For Chapman/CPSC the val patients were always removed from the train set
(in_train_loader=no).

Lockstep contract with the builder: this script's split logic mirrors, line by line,
build_ptbxl_datasets / build_chapman_datasets / build_cpsc_datasets in scripts/train.py.
If the builder's split logic changes, this script must be updated in sync and cross-validated
against the real builder with --validate (run on a machine with preprocessed data).

Usage:
    python scripts/export_splits.py                 # export seeds 42-46, all variants
    python scripts/export_splits.py --validate 42   # cross-validate against the real builder
    python scripts/export_splits.py --seeds 42 43   # specify seeds
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.data.splits import (  # noqa: E402
    patient_wise_split, ptbxl_official_folds,
)
from src.data.mapping import SUBSPACE_CPSC, filter_subspace  # noqa: E402

SEEDS_DEFAULT = [42, 43, 44, 45, 46]
DATA_ROOTS = {
    "ptbxl": "data/ptbxl_processed",
    "chapman": "data/chapman_processed_v2",
    "cpsc": "data/cpsc_processed",
}


def _carve_val_patients(pat_label: dict, frac: float, seed: int) -> set:
    """Line-by-line mirror of train.py _carve_val_patients (lockstep: keep in sync)

    Note: must use rng.permutation then take the first n_val members (identical to the builder);
    do not use rng.choice: the RNG consumption sequence differs and would select different patient members.
    """
    rng = np.random.default_rng(seed)
    val_patients: set = set()
    for lab in sorted(set(pat_label.values())):
        members = sorted(p for p, l in pat_label.items() if l == lab)
        members = list(np.asarray(members, dtype=object)[rng.permutation(len(members))])
        n_val = max(1, int(round(len(members) * frac)))
        val_patients.update(members[:n_val])
    return val_patients


def _split_chapman_like(meta_f: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Chapman/CPSC-style split: patient_wise_split(0.7, 0.1, 0.2) + 1/7 val carve.

    Line-by-line mirror of the split section in train.py build_chapman_datasets / build_cpsc_datasets.
    """
    patients = meta_f["patient_id"].unique().tolist()
    pat_label = meta_f.groupby("patient_id")["label"].agg(
        lambda s: s.mode().iat[0]).to_dict()
    t3 = patient_wise_split(patients, pat_label,
                            ratios=(0.7, 0.1, 0.2), seed=seed)
    train_patients = sorted(set(t3["train"]))
    cal_patients = sorted(set(t3["cal"]))
    test_patients = sorted(set(t3["test"]))
    sub = {p: pat_label[p] for p in train_patients}
    val_patients = _carve_val_patients(sub, 1 / 7, seed + 100)
    train_patients = sorted(set(train_patients) - val_patients)

    def _s(pid):
        if pid in val_patients:
            return "val"
        if pid in train_patients:
            return "train"
        if pid in cal_patients:
            return "cal"
        return "test"

    out = pd.DataFrame({
        "record_id": meta_f["id"].astype(str),
        "patient_id": meta_f["patient_id"].astype(str),
    })
    out["split"] = out["patient_id"].map(_s)
      # Chapman/CPSC: val already removed from the train set -> in_train_loader = (split=='train')
    out["in_train_loader"] = np.where(out["split"] == "train", "yes", "no")
    return out.sort_values("record_id").reset_index(drop=True)


def _split_ptbxl(meta: pd.DataFrame, seed: int,
                 subspace: tuple | None) -> pd.DataFrame:
    """PTB-XL split: official folds 1-8/9/10 + 12.5% patient-level val carve within folds 1-8.

    Line-by-line mirror of the split section in train.py build_ptbxl_datasets (lockstep).
    Post-repair semantics (2026-10-05 fix, ported 2026-10-11): the train loader =
    folds-1-8 records minus the carved val-patient records.
    """
    split_meta = meta
    if subspace is not None:
        rep = filter_subspace(meta["label"].tolist(), subspace)
        split_meta = meta.iloc[rep["kept_indices"]].reset_index(drop=True)

    folds_df = split_meta[["patient_id"]].assign(fold=split_meta["strat_fold"])
    splits = ptbxl_official_folds(folds_df)
    train_pos = np.sort(np.asarray(splits["train"]["records"], dtype=int))
    meta18 = split_meta.loc[train_pos]
    pat_label = meta18.groupby("patient_id")["label"].agg(
        lambda s: s.mode().iat[0]).to_dict()
    val_patients = _carve_val_patients(pat_label, 0.125, seed + 100)
    # Unify as a str set: meta patient_id may be int64, _s() compares by str
    val_patients = {str(p) for p in val_patients}
    cal_patients = sorted(set(np.asarray(splits["cal"]["patients"], dtype=object).tolist()))
    test_patients = sorted(set(np.asarray(splits["test"]["patients"], dtype=object).tolist()))

    def _s(row):
        pid = str(row["patient_id"])
        fold = int(row["fold"])
        if pid in val_patients:
            return "val"
        if fold == 9:
            return "cal"
        if fold == 10:
            return "test"
        return "train"

    out = pd.DataFrame({
        "record_id": split_meta["id"].astype(str),
        "patient_id": split_meta["patient_id"].astype(str),
        "fold": split_meta["strat_fold"].astype(int),
    })
    out["split"] = out.apply(_s, axis=1)
    # Fixed semantics 2026-10-05 (ported 2026-10-11): the train loader = folds-1-8 records
    # minus the val-patient records (split=='train' iff fold<=8 AND pid NOT a carved val
    # patient), mirroring train.py build_ptbxl_datasets np.setdiff1d (lockstep).
    out["in_train_loader"] = np.where(out["split"] == "train", "yes", "no")
    return out.drop(columns=["fold"]).sort_values("record_id").reset_index(drop=True)


def export_all(seeds: list[int], out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    jobs = [
        ("ptbxl_seed{seed}.csv", "ptbxl", None),
        ("ptbxl_sub4_seed{seed}.csv", "ptbxl", SUBSPACE_CPSC),
        ("chapman_seed{seed}.csv", "chapman", None),
        ("chapman_sub4_seed{seed}.csv", "chapman", SUBSPACE_CPSC),
        ("cpsc_seed{seed}.csv", "cpsc", None),    # cpsc builder fixes the subspace internally
    ]
    for seed in seeds:
        for name_tpl, ds, subspace in jobs:
            meta = pd.read_csv(Path(DATA_ROOTS[ds]) / "metadata_single_label.csv")
            if ds == "ptbxl":
                df = _split_ptbxl(meta, seed, subspace)
            elif ds == "chapman":
                meta_f = meta
                if subspace is not None:
                    rep = filter_subspace(meta["label"].tolist(), subspace)
                    meta_f = meta.iloc[rep["kept_indices"]].reset_index(drop=True)
                df = _split_chapman_like(meta_f, seed)
            else:  # cpsc: builder fixes SUBSPACE_CPSC internally
                rep = filter_subspace(meta["label"].tolist(), SUBSPACE_CPSC)
                meta_f = meta.iloc[rep["kept_indices"]].reset_index(drop=True)
                df = _split_chapman_like(meta_f, seed)
            path = out_dir / name_tpl.format(seed=seed)
            df.to_csv(path, index=False)
            written.append(path)
            print(f"[export] {path.name}: {len(df)} records "
                  f"({df['split'].value_counts().to_dict()})")
    return written


def validate_against_builders(seed: int) -> bool:
    """Cross-validate against the real builders on a machine with preprocessed data (strongest guarantee)."""
    from train import (  # noqa: E402  deferred import (torch is heavy)
        build_ptbxl_datasets, build_chapman_datasets, build_cpsc_datasets,
    )
    ok = True
    checks = [
        ("ptbxl", dict(subspace=None), "ptbxl"),
        ("ptbxl", dict(subspace=SUBSPACE_CPSC), "ptbxl_sub4"),
        ("chapman", dict(subspace=None), "chapman"),
        ("chapman", dict(subspace=SUBSPACE_CPSC), "chapman_sub4"),
        ("cpsc", {}, "cpsc"),
    ]
    for ds, kwargs, name in checks:
        builder = {"ptbxl": build_ptbxl_datasets,
                   "chapman": build_chapman_datasets,
                   "cpsc": build_cpsc_datasets}[ds]
        datasets, _ = builder(DATA_ROOTS[ds], seed, limit=None, **kwargs)
        csv = pd.read_csv(Path("splits") / f"{name}_seed{seed}.csv")
        for split_name in ("train", "val", "cal", "test"):
            ids_builder = set(map(str, datasets[split_name].record_ids))
            if split_name == "train":
                ids_csv = set(csv.loc[csv["in_train_loader"] == "yes", "record_id"])
            else:
                ids_csv = set(csv.loc[csv["split"] == split_name, "record_id"])
            match = ids_builder == ids_csv
            ok &= match
            print(f"  [{name}/{split_name}] builder={len(ids_builder)} "
                  f"csv={len(ids_csv)} {'MATCH' if match else 'MISMATCH'}")
    return ok


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--seeds", type=int, nargs="+", default=SEEDS_DEFAULT)
    ap.add_argument("--out-dir", type=Path, default=Path("splits"))
    ap.add_argument("--validate", type=int, default=None, metavar="SEED",
                    help="Cross-validate against the real builder for the given seed (requires local preprocessed data)")
    args = ap.parse_args()
    if args.validate is not None:
        ok = validate_against_builders(args.validate)
        sys.exit(0 if ok else 1)
    export_all(args.seeds, args.out_dir)


if __name__ == "__main__":
    main()
