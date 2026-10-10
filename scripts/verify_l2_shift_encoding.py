"""判定 results/l2_shift_full_780cells_detail.csv（及其 390 聚合表）的标签编码。

背景
----
`scripts/eval_l2_shift.py` 不读 checkpoint 自存的 `label_map`，而是用**运行时**的
模块级常量 `src.data.mapping.SUBSPACE_CPSC` 重建标签：

    subspace = SUBSPACE_CPSC if num_classes == 4 else None   # L85

而该常量在 2026-09-09~09-16 期间是 NEW 编码 `("NORM","MI","STTC","CD")`
（09-14 提交为 `452b3bf`，09-16 由 `72b2e59` 恢复为 OLD）。L2 两张表的 mtime
是 **2026-09-12 22:05**，落在窗口内；同一窗口内生成的
`results/ablation_ts_components.csv`（09-10）已被三重指纹判定为污染。
故 L2 表**疑似污染**，需经验判定。

判定方法（无需 GPU 重跑）
------------------------
L2 表有 13 档信号扰动。对**非 CPSC 方向**（chapman↔ptbxl），污染不影响数值
（两种编码在那里重合），故可用它标定每一档扰动的"固有偏离"：

    resid(s) = | L2_raw_ece(cell, s) − ablation_OLD_smooth_ece(cell) |   非 CPSC cell

取偏离最小的档 s* 作为**近恒等档**。然后在 CPSC 方向（污染使 raw ECE 抬高
约 0.06~0.11）比较：

    d_clean = | L2_raw_ece(cell, s*) − ablation_OLD_smooth_ece(cell) |
    d_cont  = | L2_raw_ece(cell, s*) − ablation_contaminated_smooth_ece(cell) |

若 d_cont ≈ resid(s*) 而 d_clean 大出一到两个数量级 ⇒ 表是**污染**的。
反之 d_clean ≈ resid(s*) ⇒ 表是干净的。

输出
----
标准输出判定 + results/l2_shift_encoding_verdict.json
"""
from __future__ import annotations
import csv
import io
import json
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent.parent

L2_DETAIL = ROOT / "results/l2_shift_full_780cells_detail.csv"
ABL_OLD = ROOT / "results/ablation_ts_components.OLD_ENCODING.csv"
ABL_CONT = ROOT / "results/ablation_ts_components.csv"
OUT = ROOT / "results/l2_shift_encoding_verdict.json"

CPSC_DIRS = {"chapman->cpsc", "cpsc->chapman", "cpsc->ptbxl", "ptbxl->cpsc"}


def read_csv(p: Path):
    if not p.exists():
        raise SystemExit(f"[致命] 缺少输入 {p} —— 不静默回退。")
    return list(csv.DictReader(io.open(p, encoding="utf-8")))


def main():
    l2 = read_csv(L2_DETAIL)
    old = {}
    for r in read_csv(ABL_OLD):
        if r["stage"] == "raw" and "mamba" not in r["arch"]:
            old[(f'{r["source"]}->{r["target"]}', r["arch"], str(r["seed"]))] = float(r["smooth_ece"])
    cont = {}
    for r in read_csv(ABL_CONT):
        if r["stage"] == "raw" and "mamba" not in r["arch"]:
            cont[(f'{r["source"]}->{r["target"]}', r["arch"], str(r["seed"]))] = float(r["smooth_ece"])

    keys = {(r["direction"], r["arch"], str(r["seed"])) for r in l2}
    keys = {k for k in keys if k in old and k in cont}
    shifts = sorted({r["shift"] for r in l2})
    print(f"L2 cell 数 = {len(keys)}   shift 档 = {len(shifts)}")

    def val(cell, shift):
        for r in l2:
            if (r["direction"], r["arch"], str(r["seed"])) == cell and r["shift"] == shift:
                return float(r["raw_ece"])
        return None

    noncpsc = [k for k in keys if k[0] not in CPSC_DIRS]
    cpsc = [k for k in keys if k[0] in CPSC_DIRS]
    print(f"非 CPSC cell = {len(noncpsc)}（用于标定）   CPSC cell = {len(cpsc)}（用于判定）")

    # 1) 用非 CPSC cell 标定各档扰动的固有偏离
    print("\n" + "=" * 74)
    print("1) 各档扰动在非 CPSC cell 上的固有偏离（越小越接近恒等）")
    print("=" * 74)
    resid = {}
    for s in shifts:
        d = [abs(val(k, s) - old[k]) for k in noncpsc if val(k, s) is not None]
        resid[s] = float(np.median(d))
    for s, v in sorted(resid.items(), key=lambda x: x[1]):
        print(f"  {s:<9} median|Δ| = {v:.4f}")
    s_star = min(resid, key=resid.get)
    r_star = resid[s_star]
    print(f"\n  -> 近恒等档 s* = {s_star}（median 固有偏离 {r_star:.4f}）")

    # 2) 在 s* 上判定 CPSC cell 的编码
    print("\n" + "=" * 74)
    print(f"2) CPSC cell 在 {s_star} 档上与两种口径的吻合度")
    print("=" * 74)
    d_clean = np.array([abs(val(k, s_star) - old[k]) for k in cpsc])
    d_cont = np.array([abs(val(k, s_star) - cont[k]) for k in cpsc])
    print(f"  |L2 − OLD(clean)|      : median {np.median(d_clean):.4f}   "
          f"mean {d_clean.mean():.4f}   max {d_clean.max():.4f}")
    print(f"  |L2 − 污染口径|        : median {np.median(d_cont):.4f}   "
          f"mean {d_cont.mean():.4f}   max {d_cont.max():.4f}")
    print(f"  非 CPSC 固有偏离基准    : {r_star:.4f}")
    ratio = np.median(d_clean) / max(np.median(d_cont), 1e-9)
    print(f"\n  median 比值（clean / 污染）= {ratio:.1f}×")

    # 逐 cell 明细
    print(f"\n  {'cell':<38} {'L2':>8} {'OLD':>8} {'污染':>8} {'→':>4}")
    for k, dc, dn in sorted(zip(cpsc, d_clean, d_cont), key=lambda x: -x[1])[:12]:
        v = val(k, s_star)
        tag = "污染" if dn < dc else "clean"
        print(f"  {k[0]+'/'+k[1]+'/'+k[2]:<38} {v:>8.4f} {old[k]:>8.4f} {cont[k]:>8.4f} {tag:>4}")

    n_match_cont = int((d_cont < d_clean).sum())
    verdict = ("CONTAMINATED" if np.median(d_cont) < np.median(d_clean) / 5 else "INCONCLUSIVE")
    print("\n" + "=" * 74)
    print(f"判定：L2 表 = {verdict}")
    print(f"  逐 cell：与污染口径更近的 {n_match_cont}/{len(cpsc)}")
    print(f"  非 CPSC 对照（应两种口径相同）："
          f"median|Δ| vs OLD {np.median([abs(val(k,s_star)-old[k]) for k in noncpsc]):.4f}")
    print("=" * 74)

    OUT.write_text(json.dumps({
        "verdict": verdict,
        "near_identity_shift": s_star,
        "non_cpsc_residual_median": r_star,
        "cpsc_d_clean_median": float(np.median(d_clean)),
        "cpsc_d_contaminated_median": float(np.median(d_cont)),
        "cpsc_cells_matching_contaminated": n_match_cont,
        "cpsc_cells_total": len(cpsc),
        "generated_at_mtime": "2026-09-12 22:05 (inside the 09-09..09-16 encoding window)",
        "note": ("eval_l2_shift.py reads the runtime SUBSPACE_CPSC, not the checkpoint's "
                 "stored label_map; the tuple was NEW during the window."),
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n判定已写入 {OUT}")


if __name__ == "__main__":
    main()
