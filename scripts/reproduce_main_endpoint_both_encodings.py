"""最终复现：从 e2_probs_cache/*.npz 出发，分别按两套标签编码重算主终点 ΔECE。

目的：
  (1) 按 OLD 编码（idx1=CD,idx3=MI）→ 能否逐 cell 复现 transfer_result.json 的 deltaECE
      以及 60-cell 均值 +0.0159（论文头条数）。
  (2) 按 NEW 编码（npz 现状）→ 得到的是被破坏后的数字（预期 ~+0.1066，即 delta_obs 口径）。

若 (1) 成立：说明论文 +0.0159 是 OLD 编码下的自洽结果，本身无误；
            npz（09-10）因只改标签不改模型而失配 → 这才是 delta_obs=+0.1068 的真正来源。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.utils.calibration import (  # noqa: E402
    apply_temperature, fit_temperature, smooth_ece,
)

CACHE = ROOT / "checkpoints" / "e2_probs_cache"
TRANSFER = ROOT / "checkpoints" / "transfer"
TOL = 1e-9


def swap13(labels: np.ndarray) -> np.ndarray:
    out = labels.copy()
    out[labels == 1] = 3
    out[labels == 3] = 1
    return out


def onehot(y: np.ndarray, k: int) -> np.ndarray:
    m = np.zeros((len(y), k), dtype=float)
    m[np.arange(len(y)), y] = 1.0
    return m


def parse_name(stem: str):
    parts = stem.split("_")
    return parts[0], parts[1], "_".join(parts[2:-1]), parts[-1]


def delta_ece(cal_p, cal_y, test_p, test_y):
    k = test_p.shape[1]
    T = fit_temperature(cal_p, onehot(cal_y, k))
    ts_p = apply_temperature(test_p, T)
    raw = smooth_ece(test_p.max(1), (test_p.argmax(1) == test_y).astype(float))
    cal = smooth_ece(ts_p.max(1), (ts_p.argmax(1) == test_y).astype(float))
    return raw - cal, T, raw, cal


def main() -> None:
    rows = []
    for npz_path in sorted(CACHE.glob("*.npz")):
        src, tgt, arch, seed = parse_name(npz_path.stem)
        if arch == "mamba":
            continue
        d = np.load(npz_path)
        tp = d["test_probs"].astype(float)
        ty_new = d["test_labels"].astype(int)
        cp = d["cal_probs"].astype(float)
        cy_new = d["cal_labels"].astype(int)

        tr_path = TRANSFER / f"{src}_{tgt}" / arch / seed / "transfer_result.json"
        tr = json.loads(tr_path.read_text(encoding="utf-8")) if tr_path.exists() else None
        tr_d = tr["methods"]["ts"]["ood"]["deltaECE"] if tr else float("nan")
        tr_raw = tr["methods"]["ts"]["ood"]["raw"] if tr else float("nan")

        is_cpsc = "cpsc" in (src, tgt)
        if is_cpsc:
            ty_old, cy_old = swap13(ty_new), swap13(cy_new)
        else:
            ty_old, cy_old = ty_new, cy_new  # 非 CPSC：两套一致

        d_old, T_old, raw_old, cal_old = delta_ece(cp, cy_old, tp, ty_old)
        d_new, T_new, raw_new, cal_new = delta_ece(cp, cy_new, tp, ty_new)

        rows.append({
            "pair": f"{src}->{tgt}", "arch": arch, "seed": seed, "cpsc": is_cpsc,
            "tr_d": tr_d, "tr_raw": tr_raw,
            "d_old": d_old, "T_old": T_old, "raw_old": raw_old,
            "d_new": d_new, "T_new": T_new, "raw_new": raw_new,
        })

    cpsc_rows = [r for r in rows if r["cpsc"]]
    nonc_rows = [r for r in rows if not r["cpsc"]]

    print("=" * 100)
    print(f"cell 数：总 {len(rows)}  含CPSC {len(cpsc_rows)}  不含CPSC {len(nonc_rows)}")
    print("=" * 100)

    print(f"\n{'pair':24s} {'arch':13s} {'seed':7s} {'transfer':>12s} {'OLD复现':>12s} {'NEW':>12s} {'Δold-tr':>10s} {'T_old':>7s}")
    for r in cpsc_rows:
        print(f"{r['pair']:24s} {r['arch']:13s} {r['seed']:7s} "
              f"{r['tr_d']:12.8f} {r['d_old']:12.8f} {r['d_new']:12.8f} "
              f"{r['d_old']-r['tr_d']:+10.2e} {r['T_old']:7.4f}")

    print("\n" + "-" * 100)
    print("[非 CPSC 对照]（两套编码应完全一致）")
    for r in nonc_rows[:4]:
        print(f"{r['pair']:24s} {r['arch']:13s} {r['seed']:7s} "
              f"{r['tr_d']:12.8f} {r['d_old']:12.8f} {r['d_new']:12.8f}")

    # 汇总
    import statistics as st
    print("\n" + "=" * 100)
    print("汇总")
    print("=" * 100)
    tr_all = [r["tr_d"] for r in rows]
    old_all = [r["d_old"] for r in rows]
    new_all = [r["d_new"] for r in rows]

    def s(name, v):
        print(f"  {name:34s} n={len(v):3d}  mean={np.mean(v):+.6f}  median={np.median(v):+.6f}  "
              f"pos={sum(1 for x in v if x>0):3d}/{len(v)}")

    print("\n[60 main cells]")
    s("transfer_result.json (论文口径)", tr_all)
    s("npz + OLD 编码", old_all)
    s("npz + NEW 编码", new_all)

    print("\n[40 含 CPSC cells]")
    s("transfer_result.json", [r["tr_d"] for r in cpsc_rows])
    s("npz + OLD 编码", [r["d_old"] for r in cpsc_rows])
    s("npz + NEW 编码", [r["d_new"] for r in cpsc_rows])

    print("\n[20 非 CPSC cells]")
    s("transfer_result.json", [r["tr_d"] for r in nonc_rows])
    s("npz + OLD 编码", [r["d_old"] for r in nonc_rows])
    s("npz + NEW 编码", [r["d_new"] for r in nonc_rows])

    maxdiff = max(abs(r["d_old"] - r["tr_d"]) for r in rows)
    print(f"\n最大 |ΔECE_old − ΔECE_transfer| = {maxdiff:.3e}")
    if maxdiff < 1e-6:
        print("  => 逐 cell 复现成功：论文 +0.0159 是 OLD 编码下的自洽结果。")
    else:
        print("  => 未完全复现，需进一步排查。")

    # T 相关性（解释 delta_obs 的 T 膨胀）
    Ts = np.array([r["T_old"] for r in cpsc_rows])
    dn = np.array([r["d_new"] for r in cpsc_rows])
    do = np.array([r["d_old"] for r in cpsc_rows])
    print(f"\n[40 含 CPSC] corr(T, ΔECE_old) = {np.corrcoef(Ts, do)[0,1]:+.4f}")
    print(f"[40 含 CPSC] corr(T, ΔECE_new) = {np.corrcoef(Ts, dn)[0,1]:+.4f}")


if __name__ == "__main__":
    main()
