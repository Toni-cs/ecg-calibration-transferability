#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""串行跑满 BiMamba 的 30 格迁移网格（6 pair x 5 seeds）。

为什么需要它
============
BiMamba 已实现（``src/models/s4_backbone.py`` 的 ``ECGMambaBackbone``，
即 ``--arch mamba``），但从未真正跑过：``checkpoints/transfer/*/mamba/``
下只有 2 个 60 样本的 toy 格（``n_id=60, n_ood=60``，无 ``label_map``），
而 inceptiontime/resnet1d 各 30 格（``n_id=2172, n_ood=4050``）。

BiMamba 的 OOM 已修复（``src/models/mamba_chunked.py``，分块扫描），
B=16/L=5000 从 19.7 GB 降到 5.2 GB。单步 1.39 s，整网格约 6 天。

设计要点
========
- **可断点续跑**：每格跑完检查 ``transfer_result.json`` 是否含 ``label_map``
  且方法数完整，已完成的直接跳过。中途中断重跑不会重复劳动。
- **串行**：显存只够一个进程（8.55 GB），并行会 OOM。
- **协议对齐**：命令行与 ``launch_resnet1d_seed444546.py`` 完全一致
  （8 种校准方法、epochs=50、bootstrap=10000、percentile BCI），
  只多一个 ``--mamba-chunk``。
- **口径对齐**：当前 ``src/data/mapping.py`` 的 ``SUBSPACE_CPSC`` 为
  OLD 编码 ``(NORM, CD, STTC, MI)``，与已归档的 60 格 ``label_map``
  一致，故新格与主网格同口径。

用法::

    /c/python/python.exe scripts/run_mamba_grid.py                # 跑全部 30 格
    /c/python/python.exe scripts/run_mamba_grid.py --dry-run      # 只列出计划
    /c/python/python.exe scripts/run_mamba_grid.py --seeds 42     # 只跑 seed 42
    /c/python/python.exe scripts/run_mamba_grid.py --pairs ptbxl_cpsc
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DATA = {
    "chapman": "data/chapman_processed_v2",
    "cpsc": "data/cpsc_processed",
    "ptbxl": "data/ptbxl_processed",
}

PAIRS = [
    ("chapman", "cpsc"),
    ("chapman", "ptbxl"),
    ("cpsc", "chapman"),
    ("cpsc", "ptbxl"),
    ("ptbxl", "chapman"),
    ("ptbxl", "cpsc"),
]

SEEDS = [42, 43, 44, 45, 46]

# 与 launch_resnet1d_seed444546.py 完全一致（仅多 --mamba-chunk）
METHODS = ["ts", "platt", "isotonic", "vector", "matrix", "dirichlet",
           "em_prior", "bbse_prior"]

REQUIRED_METHODS = set(METHODS)


def cell_dir(src: str, tgt: str, seed: int, save_dir: Path) -> Path:
    return save_dir / f"{src}_{tgt}" / "mamba" / f"seed{seed}"


def is_done(src: str, tgt: str, seed: int, save_dir: Path) -> bool:
    """完成的判据：transfer_result.json 存在，含 label_map，
    且 methods 覆盖全部 8 种（防止半途中断留下残缺产物）。"""
    f = cell_dir(src, tgt, seed, save_dir) / "transfer_result.json"
    if not f.exists():
        return False
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return False
    if not d.get("label_map"):
        return False
    return REQUIRED_METHODS.issubset(set(d.get("methods", {}).keys()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", default=SEEDS)
    ap.add_argument("--pairs", nargs="+", default=None,
                    help="如 ptbxl_cpsc；默认全部 6 对")
    ap.add_argument("--arch", default="mamba")
    ap.add_argument("--mamba-chunk", type=int, default=500)
    ap.add_argument("--epochs", type=int, default=50)
    ap.add_argument("--bootstrap", type=int, default=10000)
    ap.add_argument("--n-jobs", type=int, default=8)
    ap.add_argument("--num-workers", type=int, default=0)
    ap.add_argument("--save-dir", default="checkpoints/transfer")
    ap.add_argument("--log-dir", default="logs/mamba_grid")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="重跑已完成的格")
    args = ap.parse_args()

    save_dir = (ROOT / args.save_dir).resolve()
    log_dir = (ROOT / args.log_dir).resolve()
    log_dir.mkdir(parents=True, exist_ok=True)

    pairs = PAIRS
    if args.pairs:
        want = set(args.pairs)
        pairs = [(s, t) for s, t in PAIRS if f"{s}_{t}" in want]
        missing = want - {f"{s}_{t}" for s, t in pairs}
        if missing:
            print(f"[ERR] 未知 pair: {sorted(missing)}")
            return 1

    jobs = []
    # seed 优先（而非 pair 优先）：这样每跑完一个 seed 就得到 6 个完整的
    # 可比较格，中途停下也有可用结果，而不是"某对 5 个 seed + 其余 5 对空缺"。
    for seed in args.seeds:
        for src, tgt in pairs:
            done = is_done(src, tgt, seed, save_dir)
            jobs.append((src, tgt, seed, done))

    todo = [j for j in jobs if args.force or not j[3]]
    print(f"网格：{len(pairs)} pair x {len(args.seeds)} seed = {len(jobs)} 格")
    print(f"已完成 {len(jobs)-len(todo)} 格，待跑 {len(todo)} 格")
    if not todo:
        print("全部已完成，无需运行。")
        return 0

    print(f"\n{'#':>3} {'cell':<26} {'状态':<10}")
    for i, (src, tgt, seed, done) in enumerate(jobs, 1):
        print(f"{i:>3} {src}->{tgt}/seed{seed:<4} {'已完成' if done and not args.force else '待跑'}")

    if args.dry_run:
        print("\n--dry-run：未实际运行。")
        return 0

    common = [
        sys.executable, "scripts/eval_transfer.py",
        "--arch", args.arch,
        "--mamba-chunk", str(args.mamba_chunk),
        "--methods", *METHODS,
        "--epochs", str(args.epochs),
        "--gpu-inference",
        "--bootstrap", str(args.bootstrap),
        "--bci-method", "percentile",
        "--n-jobs", str(args.n_jobs),
        "--num-workers", str(args.num_workers),
        "--save-dir", args.save_dir,
    ]

    # 子进程输出不缓冲，否则单格日志要等整格跑完才落盘，无法监控进度
    child_env = dict(os.environ, PYTHONUNBUFFERED="1")

    progress = log_dir / "_progress.txt"

    def write_progress(lines):
        progress.write_text("\n".join(lines) + "\n", encoding="utf-8")

    t_start = time.time()
    times = []
    failures = []
    log_lines = []
    for i, (src, tgt, seed, _done) in enumerate(todo, 1):
        name = f"{src}_{tgt}_{args.arch}_seed{seed}"
        log_path = log_dir / f"{name}.log"
        cmd = common + [
            "--source", src, "--source-dir", DATA[src],
            "--target", tgt, "--target-dir", DATA[tgt],
            "--seeds", str(seed),
        ]
        print(f"\n[{i}/{len(todo)}] {name}  -> {log_path.name}", flush=True)
        t0 = time.time()
        with open(log_path, "w", encoding="utf-8") as fh:
            proc = subprocess.Popen(cmd, stdout=fh, stderr=subprocess.STDOUT,
                                    cwd=str(ROOT), env=child_env)
            rc = proc.wait()
        dt = time.time() - t0
        times.append(dt)
        ok = rc == 0 and is_done(src, tgt, seed, save_dir)
        status = "OK" if ok else f"FAIL(rc={rc})"
        if not ok:
            failures.append(name)
        done_n = len(times)
        avg = sum(times) / done_n
        eta = avg * (len(todo) - done_n)
        line = (f"[{i}/{len(todo)}] {name:<34} {status:<12} "
                f"用时 {dt/3600:5.2f} h  累计 {(time.time()-t_start)/3600:6.2f} h  "
                f"剩余预计 {eta/3600:5.1f} h")
        print(line, flush=True)
        log_lines.append(line)
        write_progress(
            [f"网格：{len(pairs)} pair x {len(args.seeds)} seed = {len(jobs)} 格",
             f"待跑 {len(todo)} 格，已完成 {done_n} 格，失败 {len(failures)} 格",
             f"平均每格 {avg/3600:.2f} h，预计剩余 {eta/3600:.1f} h",
             ""] + log_lines)

    print(f"\n=== 完成 ===  总用时 {(time.time()-t_start)/3600:.2f} h")
    if failures:
        print(f"失败 {len(failures)} 格：{failures}")
        print("重跑本脚本即可自动续跑失败的格。")
        return 1
    print("全部 30 格完成。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
