"""诊断：为什么重建脚本产出 +0.1066 而原 JSON 是 +0.0159？

对同一 cell，并排计算多个候选量，找出与 JSON 各字段对应的真实口径。
"""
import csv, json, os, sys
import numpy as np

sys.path.insert(0, '.')
from src.utils.calibration import smooth_ece, ece as binned_ece
from src.utils.calibration_methods import (
    fit_temperature_multiclass, apply_temperature_multiclass)

CACHE = 'checkpoints/e2_probs_cache'
orig = json.load(open('results/strengthening_battle_corrected.json', encoding='utf-8'))
by_cell = {}
for r in orig:
    by_cell['%s_%s_%s_seed%d' % (r['source'], r['target'], r['arch'], r['seed'])] = r

reb = {r['cell']: r for r in
       csv.DictReader(open('results/rebuild_shapley_crossfit.csv', encoding='utf-8'))}


def toplabel(probs, labels):
    return probs.max(axis=1), (probs.argmax(axis=1) == labels).astype(float)


print('%-42s %8s %8s %8s %8s %8s %8s' % (
    'cell', 'orig.orig', 'orig.obs', 'reb.orig', 'sm_raw', 'sm_ts', 'sm_diff'))
print('-' * 100)

diffs = []
for cell in list(reb)[:6]:
    o = by_cell.get(cell)
    if not o:
        continue
    f = cell + '.npz'
    d = np.load(os.path.join(CACHE, f), allow_pickle=True)
    cal_p, cal_y, tgt_p, tgt_y = (d['cal_probs'], d['cal_labels'],
                                  d['test_probs'], d['test_labels'])
    tp = fit_temperature_multiclass(cal_p, cal_y)
    rc, ry = toplabel(tgt_p, tgt_y)
    tc, ty = toplabel(apply_temperature_multiclass(tgt_p, tp), tgt_y)
    sm_raw = smooth_ece(rc, ry)
    sm_ts = smooth_ece(tc, ty)
    print('%-42s %+8.4f %+8.4f %+8.4f %8.4f %8.4f %+8.4f' % (
        cell[:42], o['delta_obs_orig'], o['delta_obs'],
        float(reb[cell]['delta_obs_orig']), sm_raw, sm_ts, sm_raw - sm_ts))

print()
print('=== 全 60 cell：重建值 vs 原字段的相关 ===')


def corr(a, b):
    a = np.asarray(a, float); b = np.asarray(b, float)
    a = a - a.mean(); b = b - b.mean()
    d = (a.std() * b.std())
    return float((a * b).mean() / d) if d > 0 else float('nan')


cells = [c for c in reb if c in by_cell]
x = [float(reb[c]['delta_obs_orig']) for c in cells]
y_o = [by_cell[c]['delta_obs_orig'] for c in cells]
y_b = [by_cell[c]['delta_obs'] for c in cells]
print('corr(rebuild, orig.delta_obs_orig) = %+.4f   mean orig=%.4f rebuild=%.4f'
      % (corr(x, y_o), np.mean(y_o), np.mean(x)))
print('corr(rebuild, orig.delta_obs)      = %+.4f   mean orig=%.4f'
      % (corr(x, y_b), np.mean(y_b)))

print()
print('=== 原 JSON 的 raw_ood_orig / cal_ood_orig 是什么量？ ===')
print('%-42s %10s %10s %10s %10s' % ('cell', 'json_raw', 'json_cal',
                                     'sm_raw', 'sm_ts'))
for cell in cells[:6]:
    o = by_cell[cell]
    f = cell + '.npz'
    d = np.load(os.path.join(CACHE, f), allow_pickle=True)
    cal_p, cal_y, tgt_p, tgt_y = (d['cal_probs'], d['cal_labels'],
                                  d['test_probs'], d['test_labels'])
    tp = fit_temperature_multiclass(cal_p, cal_y)
    rc, ry = toplabel(tgt_p, tgt_y)
    tc, ty = toplabel(apply_temperature_multiclass(tgt_p, tp), tgt_y)
    print('%-42s %10.4f %10.4f %10.4f %10.4f' % (
        cell[:42], o['raw_ood_orig'], o['cal_ood_orig'],
        smooth_ece(rc, ry), smooth_ece(tc, ty)))
