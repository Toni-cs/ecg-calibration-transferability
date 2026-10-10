"""判定源模型的输出索引语义：OLD(idx1=CD,idx3=MI) 还是 NEW(idx1=MI,idx3=CD)。

方法：对含 CPSC 的 40 个 cell，分别按两套目标标签编码计算 accuracy。
若源模型与某套编码一致，该套下 accuracy 应显著更高（MI/CD 判别通常远高于随机）。
同时打印类 1/3 的召回率，看模型是否真的在区分这两类。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "checkpoints" / "e2_probs_cache"
TRANSFER = ROOT / "checkpoints" / "transfer"


def swap13(labels: np.ndarray) -> np.ndarray:
    out = labels.copy()
    out[labels == 1] = 3
    out[labels == 3] = 1
    return out


def parse_name(stem: str):
    parts = stem.split("_")
    return parts[0], parts[1], "_".join(parts[2:-1]), parts[-1]


def main() -> None:
    rows = []
    for npz_path in sorted(CACHE.glob("*.npz")):
        src, tgt, arch, seed = parse_name(npz_path.stem)
        if arch == "mamba":
            continue
        if "cpsc" not in (src, tgt):
            continue
        d = np.load(npz_path)
        probs = d["test_probs"]
        labels = d["test_labels"].astype(int)
        pred = probs.argmax(axis=1)
        lab_sw = swap13(labels)

        acc_A = float((pred == labels).mean())   # npz 新编码
        acc_B = float((pred == lab_sw).mean())   # 旧编码

        # 类 1 / 类 3 召回（在各自编码下）
        def recall(lab, k):
            m = lab == k
            return float((pred[m] == k).mean()) if m.sum() else float("nan")

        rows.append((src, tgt, arch, seed, acc_A, acc_B,
                     recall(labels, 1), recall(lab_sw, 1),
                     recall(labels, 3), recall(lab_sw, 3),
                     int((pred == 1).sum()), int((pred == 3).sum())))

    print("=" * 118)
    print("含 CPSC 的 cell：两套编码下的 accuracy")
    print("  acc_A = 与 npz(新编码 idx1=MI,idx3=CD) 对齐")
    print("  acc_B = 与旧编码 (idx1=CD,idx3=MI) 对齐")
    print("=" * 118)
    hdr = (f"{'direction':22s} {'arch':13s} {'seed':7s} {'acc_A':>8s} {'acc_B':>8s} "
           f"{'B-A':>8s} {'rec1@A':>7s} {'rec1@B':>7s} {'rec3@A':>7s} {'rec3@B':>7s} {'np1':>5s} {'np3':>5s}")
    print(hdr)
    for r in rows:
        src, tgt, arch, seed, a, b, r1a, r1b, r3a, r3b, n1, n3 = r
        print(f"{src+'->'+tgt:22s} {arch:13s} {seed:7s} {a:8.4f} {b:8.4f} "
              f"{b-a:+8.4f} {r1a:7.3f} {r1b:7.3f} {r3a:7.3f} {r3b:7.3f} {n1:5d} {n3:5d}")

    wins_B = sum(1 for r in rows if r[5] > r[4] + 1e-12)
    wins_A = sum(1 for r in rows if r[4] > r[5] + 1e-12)
    ties = len(rows) - wins_B - wins_A
    print("-" * 118)
    print(f"acc_B > acc_A : {wins_B}/{len(rows)}    acc_A > acc_B : {wins_A}/{len(rows)}    并列 : {ties}")
    print(f"平均 acc_A = {np.mean([r[4] for r in rows]):.4f}   平均 acc_B = {np.mean([r[5] for r in rows]):.4f}")

    # 按方向细分
    print("\n按方向：")
    by_dir = {}
    for r in rows:
        by_dir.setdefault(f"{r[0]}->{r[1]}", []).append(r)
    for k in sorted(by_dir):
        g = by_dir[k]
        dA = np.mean([r[4] for r in g])
        dB = np.mean([r[5] for r in g])
        print(f"  {k:22s} acc_A={dA:.4f}  acc_B={dB:.4f}  Δ(B-A)={dB-dA:+.4f}  "
              f"B胜{sum(1 for r in g if r[5]>r[4]+1e-12)}/{len(g)}")


if __name__ == "__main__":
    main()
