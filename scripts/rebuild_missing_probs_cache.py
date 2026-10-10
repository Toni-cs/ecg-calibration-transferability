"""重建 e2_probs_cache 中缺失的 2 格 npz（用重训后的 checkpoint）

背景
----
cpsc_ptbxl/inceptiontime/seed{42,43} 于 2026-09-17 重训，以消除「两格共用同一个
CPSC->Chapman 源模型」的独立性缺陷。但它们的 e2_probs_cache 条目从未重生成：
缓存里只有 60 格中的 58 格（另含 2 个 BiMamba 玩具运行）。

后果：任何 glob 该缓存的消费者（real_prior_recovery.py、rebuild_shapley_crossfit.py）
会**静默地**只用 58 格。已发表的产物（results/real_prior_recovery.csv，60 行）
是在缓存尚有 60 格时生成的，因此当前不可复现。

本脚本做什么
------------
用产生缓存的**同一条**前向管线
（run_e2_ablation_discrimination.load_probs_for_checkpoint）重放这 2 格，
并按当前护栏要求的格式写入 npz（含 CACHE_STAMP_KEY 编码戳）。

自我校验（关键）
----------------
同时重放一个**未被重训**的格 cpsc_ptbxl/inceptiontime/seed44，与已存在的 npz
逐元素比对。若一致 → 管线忠实 → 新写入的 2 格可信；若不一致 → 拒绝写入。

用法：
    python scripts/rebuild_missing_probs_cache.py
    python scripts/rebuild_missing_probs_cache.py --apply   # 实际写入
默认 dry-run（只校验、不写）。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

# 注意：run_e2_ablation_discrimination 会连带 import torch。--fix-labels 是纯
# numpy 操作，不应被 torch 绑架，故这些导入放在需要它们的函数内部（惰性导入）。
CACHE_DIR = _PROJECT_ROOT / "checkpoints" / "e2_probs_cache"
CACHE_STAMP_KEY = "label_encoding"

# 待重建：重训过的 2 格。元组为 (pair, arch, seed)，pair = f"{source}_{target}"
TARGETS = [("cpsc_ptbxl", "inceptiontime", 42),
           ("cpsc_ptbxl", "inceptiontime", 43)]
# 自校验：两个未被重训的格 —— 一个 K=4（含 CPSC，缓存标签被污染），一个 K=5
CONTROLS = [("cpsc_ptbxl", "inceptiontime", 44),
            ("ptbxl_chapman", "resnet1d", 42)]


def split_pair(pair: str):
    """'cpsc_ptbxl' -> ('cpsc', 'ptbxl')"""
    src, tgt = pair.split("_", 1)
    return src, tgt


def swap13(y: np.ndarray) -> np.ndarray:
    """CD(1) <-> MI(3) 置换 —— 2026-09-10 缓存污染的确切形式。"""
    o = y.copy()
    o[y == 1] = 3
    o[y == 3] = 1
    return o


class Args:
    """load_probs_for_checkpoint 需要的参数集，取正式网格的默认值。"""
    limit = None
    batch_size = 16
    num_workers = 0
    d_model = 64
    n_layers = 2
    use_cache = False          # 强制重算，不走缓存
    allow_unstamped_cache = False


def stamp_for(source: str, target: str, arch: str, seed: int):
    """复刻 E2 的编码戳推导：以 checkpoint 自存 subspace 为准。"""
    from run_e2_ablation_discrimination import CKPT_ROOT, DATASET_NUM_CLASSES
    from src.data.mapping import SUBSPACE_CPSC
    from src.utils.encoding_guard import checkpoint_subspace, encoding_stamp

    run_dir = CKPT_ROOT / f"{source}_{target}" / arch / f"seed{seed}"
    num_classes = min(DATASET_NUM_CLASSES[source], DATASET_NUM_CLASSES[target])
    runtime_subspace = SUBSPACE_CPSC if num_classes == 4 else None
    subspace = checkpoint_subspace(run_dir, num_classes, runtime_subspace)
    return num_classes, subspace, encoding_stamp(num_classes, subspace)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="实际写入 2 个新 npz；默认只做自校验（dry-run）")
    ap.add_argument("--fix-labels", action="store_true",
                    help="就地修复 09-10 污染批次的 K=4 缓存标签（1<->3 置换）")
    ap.add_argument("--dry-run-fix", action="store_true",
                    help="与 --fix-labels 同用时只报告、不写入")
    args_cli = ap.parse_args()

    if args_cli.fix_labels:
        return fix_labels(dry_run=args_cli.dry_run_fix)

    import torch

    from run_e2_ablation_discrimination import load_probs_for_checkpoint

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"device = {device}")
    print(f"缓存目录 = {CACHE_DIR}\n")

    # ---------------- 自校验：重放未变动的格并与已有 npz 比对 ----------------
    # 判据分两层：
    #   probs  必须**逐位一致** —— 证明前向管线与生成缓存时完全相同
    #   labels 必须相等，或恰为 CD<->MI(1<->3) 置换 —— 后者是已登记的
    #          2026-09-10 污染的确切形式（当前管线产出的是与 checkpoint 一致的
    #          正确编码；已用 transfer_result.json 的 id_acc 裁决：K=4 格上
    #          正确标签给 0.73~0.85，污染标签只有 0.45~0.51，等同随机）
    ok = True
    for pair, arch, seed in CONTROLS:
        src, tgt = split_pair(pair)
        cache_file = CACHE_DIR / f"{pair}_{arch}_seed{seed}.npz"
        print(f"[自校验] 重放 {pair}_{arch}_seed{seed} 并与已有 npz 比对")
        if not cache_file.exists():
            print(f"  ERROR: 对照 npz 不存在：{cache_file}")
            return 2

        ref = np.load(cache_file, allow_pickle=True)
        got = load_probs_for_checkpoint(src, tgt, arch, seed, Args(), device)
        if got is None:
            print("  ERROR: 对照格前向失败（checkpoint 缺失或加载失败）")
            return 2

        for key in ("cal_probs", "test_probs"):
            a, b = np.asarray(ref[key]), np.asarray(got[key])
            if a.shape != b.shape:
                print(f"  MISMATCH {key}: shape {a.shape} vs {b.shape}")
                ok = False
                continue
            d = float(np.abs(a.astype(float) - b.astype(float)).max()) if a.size else 0.0
            ident = np.array_equal(a, b)
            print(f"  {key:<12} shape={a.shape}  max|Δ|={d:.3e}  "
                  f"{'逐位一致' if ident else '**不一致**'}")
            if not ident:
                ok = False

        for key in ("cal_labels", "test_labels"):
            a, b = np.asarray(ref[key]), np.asarray(got[key])
            if np.array_equal(a, b):
                tag = "一致（缓存未污染）"
            elif np.array_equal(swap13(a), b):
                tag = "缓存 = swap13(管线)（已登记的 1<->3 污染）"
            else:
                tag = "**未知差异**"
                ok = False
            print(f"  {key:<12} shape={a.shape}  {tag}")
        print()

    if not ok:
        print("自校验失败 —— 前向管线与生成缓存时不同，拒绝写入任何新格。")
        print("（请先查明差异来源，不要用不可复现的缓存覆盖产物。）")
        return 1
    print("自校验通过：probs 逐位可复现；labels 差异（若有）恰为已登记的 1<->3 污染。\n")

    # ---------------- 重建 2 格 ----------------
    results = {}
    for pair, arch, seed in TARGETS:
        src, tgt = split_pair(pair)
        name = f"{pair}_{arch}_seed{seed}"
        out = CACHE_DIR / f"{name}.npz"
        nc, sub, enc = stamp_for(src, tgt, arch, seed)
        print(f"[重建] {name}")
        print(f"  num_classes={nc}  subspace={sub}  stamp={enc}")
        print(f"  目标文件存在={out.exists()}"
              f"{'（将被覆盖）' if out.exists() else ''}")
        got = load_probs_for_checkpoint(src, tgt, arch, seed, Args(), device)
        if got is None:
            print("  ERROR: 前向失败，跳过")
            return 2
        print(f"  cal={got['cal_probs'].shape}  test={got['test_probs'].shape}"
              f"  num_classes={got['num_classes']}")

        if args_cli.apply:
            np.savez_compressed(
                out,
                cal_probs=got["cal_probs"], cal_labels=got["cal_labels"],
                test_probs=got["test_probs"], test_labels=got["test_labels"],
                num_classes=got["num_classes"],
                **{CACHE_STAMP_KEY: enc},
            )
            print(f"  已写入 {out}")
        else:
            print("  (dry-run，未写入)")
        results[name] = got
        print()

    # ---------------- 汇总 ----------------
    print("=" * 68)
    if args_cli.apply:
        print("已重建 2 格。下一步：")
        print("  python scripts/real_prior_recovery.py")
        print("  python scripts/rebuild_shapley_crossfit.py")
    else:
        print("dry-run 完成。加 --apply 实际写入。")
    print("=" * 68)
    return 0


def fix_labels(dry_run: bool) -> int:
    """就地修复 09-10 缓存污染：把 K=4 格的标签做 1<->3 置换。

    只改标签，probs 一字不动（已证明 probs 与 checkpoint 逐位一致）。
    判据：npz 无编码戳 且 num_classes==4 → 该格来自 09-10 的污染批次。
    修复后可用 scripts/verify_npz_label_encoding.py 反向验证：
    全部格子应判为 AS-IS。
    """
    files = sorted(CACHE_DIR.glob("*.npz"))
    n_fixed = n_skip_stamped = n_skip_k5 = n_noop = 0
    fixed_names = []
    for f in files:
        d = np.load(f, allow_pickle=True)
        if CACHE_STAMP_KEY in d.files:
            n_skip_stamped += 1
            continue
        K = int(d["num_classes"])
        if K != 4:
            n_skip_k5 += 1
            continue
        cl, tl = np.asarray(d["cal_labels"]), np.asarray(d["test_labels"])
        ncl, ntl = swap13(cl), swap13(tl)
        if np.array_equal(cl, ncl) and np.array_equal(tl, ntl):
            n_noop += 1          # 标签里根本没有 1 或 3，置换是恒等
            continue
        if dry_run:
            print(f"  [dry] {f.name}: cal {int((cl!=ncl).sum())}/{len(cl)} "
                  f"test {int((tl!=ntl).sum())}/{len(tl)} 个标签将被置换")
        else:
            np.savez_compressed(
                f,
                cal_probs=d["cal_probs"], cal_labels=ncl,
                test_probs=d["test_probs"], test_labels=ntl,
                num_classes=K,
            )
        n_fixed += 1
        fixed_names.append(f.name)
    print(f"K=4 且无戳的缓存：修复 {n_fixed} 个"
          f"（另有 {n_noop} 个置换为恒等、{n_skip_k5} 个 K=5 无需处理、"
          f"{n_skip_stamped} 个已带戳跳过）")
    if dry_run:
        print("dry-run，未写入。加 --fix-labels 且不带 --dry-run-fix 以实际写入。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
