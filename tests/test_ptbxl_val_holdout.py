"""PTB-XL early-stopping val must stay held out: builder/export lockstep regression test.

Background (fix 2026-10-05, lab tree; ported here 2026-10-11, see
docs/PTBXL_VAL_LEAK_RETRAIN_PLAN.md in the lab tree):
Before the fix, build_ptbxl_datasets' pos['train'] took the FULL folds-1-8 train_pos,
so val-patient records entered both the train and val loaders (early stopping was
monitoring the training set -> model selection silently invalid) -- while
assert_no_leakage consumed the already-reduced train_patients, i.e. the asserted object
and the dataset object were mismatched and the assertion always passed. This file pins
the four post-fix invariants against regression:

  1. val records stay out of the training loader (train & val == empty)
  2. train | val == folds 1-8 (exactly the carved-out records are dropped -- no over/under deletion)
  3. the four splits are pairwise disjoint at record AND patient level, and the asserted
     object is derived from the loader positions (same origin as the datasets)
  4. scripts/export_splits.py's in_train_loader mirrors the builder line by line
     (this is what `--validate <seed>` does on real data; here with synthetic data, fast)

Run: python -m pytest tests/test_ptbxl_val_holdout.py -v
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "scripts"))

from src.data.mapping import SUPERCLASSES  # noqa: E402

from train import build_ptbxl_datasets  # noqa: E402
import export_splits  # noqa: E402

SEEDS = [42, 45]
N_FOLDS = 10
N_PATIENTS_PER_FOLD = 8
N_RECORDS_PER_PATIENT = 2


@pytest.fixture()
def ptbxl_meta_dir(tmp_path):
    """Synthetic PTB-XL-shaped metadata: patient-level strat_fold 1..10 + official five superclasses."""
    data_dir = tmp_path / "ptbxl"
    data_dir.mkdir()
    rng = np.random.default_rng(7)
    rows = []
    for fold in range(1, N_FOLDS + 1):
        for i in range(N_PATIENTS_PER_FOLD):
            pid = fold * 1000 + i  # same shape as real PTB-XL: integer patient_id
            label = SUPERCLASSES[i % len(SUPERCLASSES)]
            for r in range(N_RECORDS_PER_PATIENT):
                rid = f"r{fold:02d}{i:02d}_{r}"
                rows.append({
                    "id": rid,
                    "label": label,
                    "npy_path": f"{rid}.npy",
                    "patient_id": pid,
                    "strat_fold": fold,
                    "fs": 100,
                    "original_len": 100,
                })
    meta = pd.DataFrame(rows)
    # Shuffle row order so the split logic demonstrably depends on patient/fold, not row order
    meta = meta.sample(frac=1.0, random_state=0).reset_index(drop=True)
    meta.to_csv(data_dir / "metadata_single_label.csv", index=False)
    # ECGNPZDataset defaults to data_dir = metadata_csv.parent / "data"
    npy_dir = data_dir / "data"
    npy_dir.mkdir()
    for rid in meta["id"]:
        np.save(npy_dir / f"{rid}.npy",
                rng.normal(size=(12, 100)).astype(np.float32))
    return data_dir, meta


def _folds18_records(meta: pd.DataFrame) -> set:
    return set(meta.loc[meta["strat_fold"].between(1, 8), "id"].astype(str))


class TestPTBXLValHoldout:
    @pytest.mark.parametrize("seed", SEEDS)
    def test_val_records_not_in_train_loader(self, ptbxl_meta_dir, seed):
        """The fix proper: val records must genuinely leave the training loader."""
        data_dir, _ = ptbxl_meta_dir
        ds, _ = build_ptbxl_datasets(str(data_dir), seed)
        train = set(ds["train"].record_ids)
        val = set(ds["val"].record_ids)
        assert val, "val carve must not be empty (otherwise this test is meaningless)"
        assert not (train & val), (
            f"train&val is non-empty ({len(train & val)} records): val records returned to "
            "the training loader -- early stopping would monitor the training set again")
        assert train | val == _folds18_records(pd.read_csv(
            data_dir / "metadata_single_label.csv")), (
            "train|val must equal exactly folds 1-8 (over- or under-deletion breaks the protocol)")

    @pytest.mark.parametrize("seed", SEEDS)
    def test_all_four_splits_disjoint_record_and_patient(
            self, ptbxl_meta_dir, seed):
        """Pairwise disjointness at record and patient level; the assertion is derived from the loader positions."""
        data_dir, meta = ptbxl_meta_dir
        ds, clusters_test = build_ptbxl_datasets(str(data_dir), seed)
        rec = {k: set(v.record_ids) for k, v in ds.items()}
        for a in rec:
            for b in rec:
                if a >= b:
                    continue
                assert not (rec[a] & rec[b]), f"{a}&{b} record-level leakage"

        pat_of = dict(zip(meta["id"].astype(str),
                          meta["patient_id"].astype(int)))
        pats = {k: {pat_of[r] for r in v} for k, v in rec.items()}
        for a in pats:
            for b in pats:
                if a >= b:
                    continue
                assert not (pats[a] & pats[b]), f"{a}&{b} patient-level leakage"

        # clusters_test must align record-by-record with the test dataset (prerequisite of the
        # patient-level cluster bootstrap in the primary endpoint)
        assert list(clusters_test) == [
            pat_of[r] for r in ds["test"].record_ids]

    @pytest.mark.parametrize("seed", SEEDS)
    def test_export_lockstep_matches_builder(self, ptbxl_meta_dir, seed):
        """export_splits' in_train_loader must mirror the builder (lockstep)."""
        data_dir, meta = ptbxl_meta_dir
        ds, _ = build_ptbxl_datasets(str(data_dir), seed)
        out = export_splits._split_ptbxl(meta.copy(), seed, None)

        csv_train = set(out.loc[out["in_train_loader"] == "yes", "record_id"])
        assert csv_train == set(ds["train"].record_ids), (
            "export differs from the builder's training loader (lockstep broken)")

        val_rows = out.loc[out["split"] == "val"]
        assert len(val_rows) > 0
        assert set(val_rows["in_train_loader"]) == {"no"}, (
            "export val rows must read in_train_loader=no (in sync with the builder)")

        for name in ("val", "cal", "test"):
            csv_ids = set(out.loc[out["split"] == name, "record_id"])
            assert csv_ids == set(ds[name].record_ids), f"{name} split mismatch"

        assert len(out) == len(meta)
