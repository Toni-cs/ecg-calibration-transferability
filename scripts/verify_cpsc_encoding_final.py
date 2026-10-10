"""CPSC 编码漂移最终裁决实验。

问题：SUBSPACE_CPSC 于 2026-09-09 由 ("NORM","CD","STTC","MI") 改为
("NORM","MI","STTC","CD")。transfer_result.json 产于 09-08（旧编码），
e2_probs_cache/*.npz 产于 09-10（新编码）。二者是否只是标签 1/3 交换？

实验：对每个 cell，
    raw_A = smooth_ece(conf, correct(probs, labels))            # 不交换
    raw_B = smooth_ece(conf, correct(probs, swap13(labels)))    # 交换 1<->3
与 transfer_result.json 的 methods.ts.ood.raw 比对。

若 CPSC 相关 cell 全部 raw_B == raw（且 chapman<->ptbxl 全部 raw_A == raw），
则：probs 同一批，唯一差异就是标签编码 1/3 交换 → 单一成因确证。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.utils.calibration import smooth_ece  # noqa: E402

CACHE = ROOT / "checkpoints" / "e2_probs_cache"
TRANSFER = ROOT / "checkpoints" / "transfer"
TOL = 1e-9


def swap13(labels: np.ndarray) -> np.ndarray:
    out = labels.copy()
    out[labels == 1] = 3
    out[labels == 3] = 1
    return out


def parse_name(stem: str):
    parts = stem.split("_")
    src, tgt = parts[0], parts[1]
    seed = parts[-1]
    arch = "_".join(parts[2:-1])
    return src, tgt, arch, seed


def main() -> None:
    rows = []
    for npz_path in sorted(CACHE.glob("*.npz")):
        src, tgt, arch, seed = parse_name(npz_path.stem)
        if arch == "mamba":  # toy cells, excluded from 60 main
            continue
        tr_path = TRANSFER / f"{src}_{tgt}" / arch / seed / "transfer_result.json"
        if not tr_path.exists():
            rows.append((src, tgt, arch, seed, None, None, None, "NO_TRANSFER"))
            continue

        d = np.load(npz_path)
        probs = d["test_probs"]
        labels = d["test_labels"].astype(int)
        conf = probs.max(axis=1)
        pred = probs.argmax(axis=1)

        raw_A = smooth_ece(conf, (pred == labels).astype(float))
        lab_sw = swap13(labels)
        raw_B = smooth_ece(conf, (pred == lab_sw).astype(float))

        tr = json.loads(tr_path.read_text(encoding="utf-8"))
        raw_tr = tr["methods"]["ts"]["ood"]["raw"]

        a_ok = abs(raw_A - raw_tr) < TOL
        b_ok = abs(raw_B - raw_tr) < TOL
        tag = "A" if a_ok else ("B" if b_ok else "NONE")
        rows.append((src, tgt, arch, seed, raw_tr, raw_A, raw_B, tag))

    cpsc_cells = [r for r in rows if "cpsc" in (r[0], r[1]) and r[7] != "NO_TRANSFER"]
    non_cpsc = [r for r in rows if "cpsc" not in (r[0], r[1]) and r[7] != "NO_TRANSFER"]

    print("=" * 78)
    print(f"总 cell 数（排除 mamba toy）：{len(rows)}")
    print(f"  含 CPSC：{len(cpsc_cells)}   不含 CPSC：{len(non_cpsc)}")
    print("=" * 78)

    print("\n[不含 CPSC 的 cell]（对照：应为 A，即不交换即匹配）")
    from collections import Counter
    print("  ", dict(Counter(r[7] for r in non_cpsc)))

    print("\n[含 CPSC 的 cell]（假设：应为 B，即交换后匹配）")
    print("  ", dict(Counter(r[7] for r in cpsc_cells)))

    print("\n按方向细分（含 CPSC）：")
    by_dir = {}
    for r in cpsc_cells:
        by_dir.setdefault(f"{r[0]}->{r[1]}", []).append(r[7])
    for k in sorted(by_dir):
        print(f"  {k:24s} {dict(Counter(by_dir[k]))}")

    print("\n" + "=" * 78)
    print("逐 cell 明细（含 CPSC，仅列 raw 数值）")
    print(f"{'direction':22s} {'arch':14s} {'seed':8s} {'A(不交换)':>13s} {'B(交换)':>13s} {'transfer':>13s} {'判定':>6s}")
    for r in cpsc_cells:
        src, tgt, arch, seed, raw_tr, raw_A, raw_B, tag = r
        print(f"{src+'->'+tgt:22s} {arch:14s} {seed:8s} {raw_A:13.8f} {raw_B:13.8f} {raw_tr:13.8f} {tag:>6s}")

    n_B = sum(1 for r in cpsc_cells if r[7] == "B")
    n_A = sum(1 for r in cpsc_cells if r[7] == "A")
    print("\n" + "=" * 78)
    print(f"结论：含 CPSC 的 {len(cpsc_cells)} 个 cell 中，交换后匹配 {n_B} 个，不交换匹配 {n_A} 个")
    if n_B == len(cpsc_cells) and n_A == 0:
        print("  => 单一成因确证：probs 同一批，transfer_result 用旧编码，npz 用新编码。")
    elif n_A == len(cpsc_cells):
        print("  => 交换无影响（该方向标签不含 1/3 类，或 probs 不同批）。")
    else:
        print("  => 混合结果，需进一步拆解。")


if __name__ == "__main__":
    main()
