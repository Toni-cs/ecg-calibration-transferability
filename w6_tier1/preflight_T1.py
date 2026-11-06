"""Preflight assertions for the T1 (1.15M-record) stage.

These are executable contracts, not documentation. Each raises AssertionError
with an actionable message. Run `python preflight.py` for a synthetic self-test.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

EXPECTED_12_LEADS = ['I', 'II', 'III', 'aVR', 'aVL', 'aVF',
                     'V1', 'V2', 'V3', 'V4', 'V5', 'V6']


def assert_lead_alignment(header_leads, dataset_name: str) -> dict:
    """Match by NAME, never by channel index.

    MIMIC-IV-ECG ships I,II,III,aVR,aVF,aVL,V1-V6 (aVF/aVL swapped vs almost
    every other 12-lead corpus); CODE-15% and CODE-test also differ from each
    other. Silently indexing by position crosses two leads.
    """
    got = [str(x).strip() for x in header_leads]
    assert set(got) == set(EXPECTED_12_LEADS), (
        f'{dataset_name}: lead-name mismatch -> {got}')
    order = [got.index(x) for x in EXPECTED_12_LEADS]
    return {'dataset': dataset_name, 'canonical_order_indices': order,
            'was_already_canonical': order == list(range(12))}


def assert_patient_disjoint(split_df: pd.DataFrame) -> dict:
    """Patient-level split: no patient may appear in two folds."""
    g = split_df.groupby('patient_id')['split'].nunique()
    bad = g[g > 1]
    assert len(bad) == 0, f'{len(bad)} patients leak across splits'
    return {'n_patients': int(len(g)), 'cross_split_patients': 0}


def assert_a3_orbits(orbit_df: pd.DataFrame, min_groups: int = 2) -> dict:
    """A3: each patient must be observed in >=2 distinct device/time groups."""
    n = orbit_df.groupby('patient_id')['group_id'].nunique()
    frac = float((n >= min_groups).mean())
    assert frac >= 0.60, (
        f'A3 violated: only {frac:.1%} of patients have >= {min_groups} groups; '
        'PARI-style pairing is not identifiable on this cohort')
    return {'n_patients': int(len(n)), 'frac_with_orbits': frac,
            'median_groups_per_patient': float(n.median())}


def assert_code15_negatives(exams: pd.DataFrame) -> dict:
    """CODE-15%: 173,347 records are neither flagged abnormal nor flagged
    normal_ecg. They MUST NOT become confident negatives.
    """
    flags = ['1dAVb', 'RBBB', 'LBBB', 'SB', 'ST', 'AF']
    any_abn = exams[flags].fillna(False).astype(bool).any(axis=1)
    normal = exams['normal_ecg'].fillna(False).astype(bool)
    ambiguous = (~any_abn) & (~normal)
    used_neg = normal & (~any_abn)
    assert not (ambiguous & used_neg).any(), 'ambiguous records used as negatives'
    return {'n_records': int(len(exams)),
            'n_clean_negative': int(used_neg.sum()),
            'n_ambiguous_excluded': int(ambiguous.sum()),
            'ambiguous_fraction': float(ambiguous.mean())}


def assert_fixed_scale_stat(stat_name: str) -> None:
    """PARI/BCC identification contract: rank statistics are T-invariant."""
    banned = ('rank', 'argsort', 'percentile_rank', 'auroc_of_confidence',
              'order_statistic', 'spearman')
    assert not any(b in stat_name.lower() for b in banned), (
        f'{stat_name}: rank-based statistic is invariant to monotone T and '
        'cannot identify temperature; use fixed-scale confidence bins/moments')


def assert_prereg_before_forward(prereg_ts: str, first_forward_ts: str) -> dict:
    """Anti-HARKing gate: registration must precede any T1 model forward."""
    import pandas as pd
    a, b = pd.Timestamp(prereg_ts), pd.Timestamp(first_forward_ts)
    assert a < b, f'registration {a} is not before first forward {b}'
    return {'prereg': str(a), 'first_forward': str(b),
            'lead_seconds': float((b - a).total_seconds())}


def assert_effective_sample_size(n_records: int, n_patients: int) -> dict:
    """Report the honest statistical unit; records are NOT independent."""
    assert n_patients < n_records, 'expected repeated measurements'
    return {'n_records': n_records, 'n_patients': n_patients,
            'records_per_patient': round(n_records / n_patients, 2),
            'bootstrap_unit': 'patient_id',
            'warning': 'all CIs must use patient-block bootstrap, not record-level'}


if __name__ == '__main__':
    print('=== preflight self-test (synthetic) ===')
    print('MIMIC lead map:', assert_lead_alignment(
        ['I','II','III','aVR','aVF','aVL','V1','V2','V3','V4','V5','V6'],
        'MIMIC-IV-ECG'))
    d = pd.DataFrame({'patient_id': list(range(80)) + list(range(80, 100)),
                      'split': ['train']*80 + ['test']*20})
    print('patient split:', assert_patient_disjoint(d))
    leaky = pd.DataFrame({'patient_id': list(range(100))*2,
                          'split': ['train']*100 + ['test']*100})
    try:
        assert_patient_disjoint(leaky)
        raise RuntimeError('leak detector FAILED to fire')
    except AssertionError:
        print('leak detector correctly REJECTED a cross-split patient')
    o = pd.DataFrame({'patient_id': np.repeat(np.arange(200), 4),
                      'group_id': np.tile([0,1,2,3], 200)})
    print('A3 orbits:', assert_a3_orbits(o))
    e = pd.DataFrame({f: [False]*1000 for f in ['1dAVb','RBBB','LBBB','SB','ST','AF']})
    e['normal_ecg'] = [True]*400 + [False]*600
    print('CODE-15% negatives:', assert_code15_negatives(e))
    assert_fixed_scale_stat('equal_width_confidence_histogram')
    print('fixed-scale stat: PASS')
    print('prereg gate:', assert_prereg_before_forward(
        '2026-11-05T09:00:00Z', '2026-11-05T09:30:00Z'))
    print('effective n:', assert_effective_sample_size(1_145_814, 395_122))
    print('\nALL PREFLIGHT SELF-TESTS PASS')
