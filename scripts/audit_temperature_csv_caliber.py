"""判定 results/temperature_distribution_analysis.csv 的 T_global 属于哪套编码。

方法：对每个 cell，从 e2_probs_cache/*.npz 分别按 OLD / NEW 编码重算 T，
与 CSV 的 T_global 逐位比对。

只读。
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.utils.calibration import fit_temperature  # noqa: E402

CACHE = ROOT / "checkpoints" / "e2_probs_cache"
CSV = ROOT / "results" / "temperature_distribution_analysis.csv"


def swap13(y):
    o = y.copy()
    o[y == 1] = 3
    o[y == 3] = 1
    return o


def onehot(y, k):
    m = np.zeros((len(y), k))
    m[np.arange(len(y)), y] = 1.0
    return m


def main() -> None:
    rows = list(csv.DictReader(open(CSV, encoding="utf-8")))
    print(f"CSV 记录数: {len(rows)}")

    res = []
    for r in rows:
        stem = f"{r['source']}_{r['target']}_{r['arch']}_seed{r['seed']}"
        f = CACHE / f"{stem}.npz"
        if not f.exists():
            continue
        d = np.load(f)
        cp = d["cal_probs"].astype(float)
        cy = d["cal_labels"].astype(int)
        is_cpsc = "cpsc" in (r["source"], r["target"])
        T_new = float(fit_temperature(cp, onehot(cy, cp.shape[1])))
        T_old = float(fit_temperature(cp, onehot(swap13(cy) if is_cpsc else cy,
                                                cp.shape[1])))
        csv_T = float(r["T_global"])
        res.append({"stem": stem, "cpsc": is_cpsc, "csv_T": csv_T,
                    "T_old": T_old, "T_new": T_new,
                    "d_old": abs(csv_T - T_old), "d_new": abs(csv_T - T_new)})

    print(f"匹配到 npz 的 cell: {len(res)}")

    cpsc = [r for r in res if r["cpsc"]]
    nonc = [r for r in res if not r["cpsc"]]
    print(f"  含 CPSC: {len(cpsc)}   非 CPSC: {len(nonc)}")

    # 关键判据：只在含 CPSC 的 cell 上做（非 CPSC 两套编码相同，无判别力）
    m_old = sum(1 for r in cpsc if r["d_old"] < 1e-6)
    m_new = sum(1 for r in cpsc if r["d_new"] < 1e-6)
    print()
    print("=== 含 CPSC 的 cell（有判别力）===")
    print(f"  逐位命中 OLD 编码: {m_old}/{len(cpsc)}")
    print(f"  逐位命中 NEW 编码: {m_new}/{len(cpsc)}")
    if cpsc:
        print(f"  max|CSV_T - T_old| = {max(r['d_old'] for r in cpsc):.6f}")
        print(f"  max|CSV_T - T_new| = {max(r['d_new'] for r in cpsc):.6f}")

    if nonc:
        print()
        print("=== 非 CPSC 的 cell（对照，两套编码应一致）===")
        print(f"  逐位命中: {sum(1 for r in nonc if r['d_old'] < 1e-6)}/{len(nonc)}"
              f"   max|CSV_T - T| = {max(min(r['d_old'], r['d_new']) for r in nonc):.6f}")

    vals = [r["csv_T"] for r in res]
    print()
    print("=== CSV T_global 统计 ===")
    print(f"  n={len(vals)} median={np.median(vals):.4f} mean={np.mean(vals):.4f} "
          f"min={min(vals):.4f} max={max(vals):.4f} "
          f"T>=2: {100*sum(1 for v in vals if v>=2)/len(vals):.1f}%")

    # 与论文口径（60 主格）对比
    main60 = [r for r in res if r["stem"].split("_")[2] in ("inceptiontime", "resnet1d")]
    if main60:
        v = [r["csv_T"] for r in main60]
        vo = [r["T_old"] for r in main60]
        vn = [r["T_new"] for r in main60]
        print()
        print("=== 60 主格口径对比 ===")
        print(f"  CSV T_global      median={np.median(v):.4f} "
              f"T>=2: {100*sum(1 for x in v if x>=2)/len(v):.1f}%")
        print(f"  T_OLD(正确口径)    median={np.median(vo):.4f} "
              f"T>=2: {100*sum(1 for x in vo if x>=2)/len(vo):.1f}%")
        print(f"  T_NEW(污染口径)    median={np.median(vn):.4f} "
              f"T>=2: {100*sum(1 for x in vn if x>=2)/len(vn):.1f}%")

    verdict = ("NEW(污染)" if m_new > m_old else
               ("OLD(正确)" if m_old > m_new else "AMBIGUOUS"))
    print()
    print(f"==> 判定：temperature_distribution_analysis.csv 的 T_global = {verdict}")


if __name__ == "__main__":
    main()
