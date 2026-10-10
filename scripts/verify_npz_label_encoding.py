"""逐格判定 `checkpoints/e2_probs_cache/*.npz` 的标签编码。

## 为什么需要

2026-09-09 的提交 `452b3bf` 把 `src/data/mapping.py` 的 `SUBSPACE_CPSC` 改成
`("NORM","MI","STTC","CD")`，但**没有重训任何模型**。于是 09-10 重新生成的 npz
标签与 09-08 训练的 checkpoint 语义错位（MI↔CD 互换）。09-16 已回退常量，
但 npz 未重新生成。

现在的问题不是"是否污染"（已知），而是**逐个文件到底处于哪套编码** ——
因为 `real_prior_recovery.py` 与 `rebuild_shapley_crossfit.py` 都直接读它，
且在加载时不做任何归一化。

## 判定法（直接、可证伪）

`transfer_result.json` 里存了该格在**模型自身编码**下的 OOD raw ECE
（`methods.ts.ood.raw`，口径 `smooth_ece_0.45*(n/2000)^-0.2`）。

所以：用 npz 的 `test_probs` 配 (a) 原标签、(b) swap13(原标签) 各算一次 raw ECE，
**哪一个与 json 对上，该文件就是哪套编码**。

- 对上 (a) → 文件与模型编码一致（干净）
- 对上 (b) → 文件是错位编码（需 swap13 归一化）
- 两个都不对 → 另有问题，必须人工查

用法:
    python scripts/verify_npz_label_encoding.py
只读，不写任何文件。
"""
from __future__ import annotations

import glob
import json
import os
import sys

import numpy as np

CACHE = "checkpoints/e2_probs_cache"
TRANSFER = "checkpoints/transfer"
TOL = 1e-9


def _smooth_ece(probs: np.ndarray, labels: np.ndarray) -> float:
    """`src/utils/calibration.smooth_ece` 的自足副本。

    此处刻意不 import 该模块：`src.utils.__init__` 会连带 import torch，
    而本脚本只需要这一个纯 numpy 函数（且判定必须能在无 GPU 环境下跑）。
    公式与实现逐行对齐：logit 空间高斯核，带宽 h=0.45*(n/2000)**-0.2，
    在每个数据点处算核加权准确率，与预测概率之差取绝对值后平均。
    """
    probs = np.asarray(probs, dtype=float)
    labels = np.asarray(labels, dtype=float)
    n = len(probs)
    bandwidth = 0.45 * (n / 2000.0) ** (-0.2)
    p_clip = np.clip(probs, 1e-6, 1 - 1e-6)
    logit_p = np.log(p_clip / (1 - p_clip))
    abs_err = np.empty(n)
    chunk = max(1, int(2e7 // max(n, 1)))
    for s in range(0, n, chunk):
        e = min(s + chunk, n)
        z = (logit_p[s:e, None] - logit_p[None, :]) / bandwidth
        w = np.exp(-0.5 * z ** 2)
        acc_i = (w * labels[None, :]).sum(axis=1) / np.maximum(
            w.sum(axis=1), 1e-12)
        abs_err[s:e] = np.abs(acc_i - probs[s:e])
    return float(abs_err.mean())


def swap13(y: np.ndarray) -> np.ndarray:
    """交换标签 1 与 3（CPSC 的 MI↔CD 在旧/新编码间正好互换）。"""
    out = y.copy()
    out[y == 1] = 3
    out[y == 3] = 1
    return out


def raw_ece(probs: np.ndarray, labels: np.ndarray) -> float:
    """按论文口径：top-label 边际 ECE，带宽 h=0.45*(n/2000)^-0.2。"""
    top = probs.argmax(axis=1)
    conf = probs[np.arange(len(probs)), top]
    return _smooth_ece(conf, (top == labels).astype(float))


def main() -> int:
    rows = []
    missing = []
    for npz in sorted(glob.glob(f"{CACHE}/*.npz")):
        base = os.path.basename(npz)[:-4]
        parts = base.rsplit("_", 2)
        if len(parts) != 3:
            continue
        pair, arch, seed = parts[0], parts[1], parts[2]
        seed = seed.replace("seed", "")
        jpath = os.path.join(TRANSFER, pair, arch, f"seed{seed}",
                             "transfer_result.json")
        if not os.path.exists(jpath):
            missing.append(base)
            continue
        d = json.load(open(jpath, encoding="utf-8"))
        try:
            ref = float(d["methods"]["ts"]["ood"]["raw"])
        except Exception:
            missing.append(base)
            continue

        z = np.load(npz)
        tp, tl = z["test_probs"], z["test_labels"]
        a = raw_ece(tp, tl)
        b = raw_ece(tp, swap13(tl))
        da, db = abs(a - ref), abs(b - ref)
        # 平局（swap 不改变 ECE，说明该格标签在 1<->3 下对称）时判为 AS-IS：
        # 与模型编码一致优先，不引入无谓的交换。
        if da <= TOL:
            verdict = "AS-IS"
        elif db <= TOL:
            verdict = "SWAP13"
        else:
            verdict = "UNKNOWN"
        rows.append((base, ref, a, b, da, db, verdict))

    print("=" * 96)
    print("npz 标签编码逐格判定（基准 = transfer_result.json 的 ts.ood.raw）")
    print("=" * 96)
    print(f"{'cell':<44}{'json raw':>10}{'as-is':>10}{'swap13':>10}  {'判定':<8}")
    for base, ref, a, b, da, db, v in rows:
        flag = "" if v != "UNKNOWN" else "   <<< 需人工查"
        print(f"{base:<44}{ref:>10.6f}{a:>10.6f}{b:>10.6f}  {v:<8}{flag}")

    from collections import Counter
    c = Counter(v for *_, v in rows)
    print()
    print(f"合计 {len(rows)} 个 npz：", dict(c))
    if missing:
        print(f"缺 json 或字段的 npz（{len(missing)}）: {missing}")
    print()
    print("解读：AS-IS = 该文件标签与模型编码一致（干净）；"
          "SWAP13 = 错位编码，加载时必须 swap13 归一化。")
    return 0 if c.get("UNKNOWN", 0) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
