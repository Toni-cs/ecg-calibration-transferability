#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""验证分块扫描的数值等价性 + 实测显存/速度收益。

对照（同一权重、同一输入、dropout=0）：
  基准：原版 mambapy Blelloch pscan（未分块）
  分块：``src/models/mamba_chunked.py`` 的分块版

两者应在 fp32 舍入误差内一致（前向 logits 与全部梯度）。

注意：``chunk == L`` 时理论上应逐位相同；``chunk < L`` 时只多出
"块间状态叠加"的舍入，量级 ~1e-7。

用法::

    /c/python/python.exe scripts/validate_chunked_scan.py            # 数值等价性
    /c/python/python.exe scripts/validate_chunked_scan.py --mem      # 显存/速度
"""

from __future__ import annotations

import argparse
import copy
import gc
import sys
import time
from pathlib import Path

import torch

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))

from src.models.ecg_classifier import ECGClassifier  # noqa: E402
from src.models.mamba_chunked import enable_chunked_scan  # noqa: E402


def _build(device, d_model, layers, num_classes=5):
    """注意：dropout=0，否则各变体拿到不同的随机掩码，比较无意义。"""
    torch.manual_seed(0)
    return ECGClassifier(in_channels=12, d_model=d_model, n_layers=layers,
                         num_classes=num_classes, dropout=0.0,
                         backbone_type="mamba").to(device)


def _run(model, x, y, crit):
    model.zero_grad(set_to_none=True)
    logits, _ = model(x)
    crit(logits, y).backward()
    g = torch.cat([p.grad.flatten() for p in model.parameters()
                   if p.grad is not None])
    return logits.detach(), g


def numeric_check(device, chunk=500, seq_len=1000, batch=4, d_model=64,
                  layers=1, seed=0):
    torch.manual_seed(seed)
    base = _build(device, d_model, layers).eval()

    x = torch.randn(batch, 12, seq_len, device=device)
    y = torch.randint(0, 5, (batch,), device=device)
    crit = torch.nn.CrossEntropyLoss()

    ref = copy.deepcopy(base)
    lo, go = _run(ref, x, y, crit)

    m = copy.deepcopy(base)
    n = enable_chunked_scan(m, chunk=chunk, use_checkpoint=True)
    assert n > 0, "没有替换到 MambaBlock"
    l, g = _run(m, x, y, crit)

    d_logit = (l - lo).abs().max().item()
    d_grad = (g - go).abs().max().item()
    rel = d_grad / go.abs().max().item()
    print(f"  L={seq_len} B={batch} chunk={chunk} d_model={d_model} "
          f"layers={layers}（{n} 块）")
    print(f"    logits max|Δ| = {d_logit:.3e}   grad max|Δ| = {d_grad:.3e}   "
          f"相对 = {rel:.3e}   （基准 max|g| = {go.abs().max().item():.3e}）")

    del base, ref, m
    gc.collect()
    torch.cuda.empty_cache()
    return d_logit, d_grad


def mem_check(device, batch_list, seq_len=5000, layers=2, d_model=64,
              num_classes=5, chunk=500, ckpt=True, reps=2):
    for b in batch_list:
        gc.collect()
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats(device)

        model = ECGClassifier(in_channels=12, d_model=d_model, n_layers=layers,
                              num_classes=num_classes, dropout=0.1,
                              backbone_type="mamba").to(device)
        model.train()
        n = enable_chunked_scan(model, chunk=chunk, use_checkpoint=ckpt)
        opt = torch.optim.AdamW(model.parameters(), lr=1e-3)
        crit = torch.nn.CrossEntropyLoss()
        x = torch.randn(b, 12, seq_len, device=device)
        y = torch.randint(0, num_classes, (b,), device=device)

        def step():
            opt.zero_grad(set_to_none=True)
            logits, _ = model(x)
            crit(logits, y).backward()
            opt.step()

        try:
            step()
            torch.cuda.synchronize(device)
            torch.cuda.reset_peak_memory_stats(device)
            t0 = time.perf_counter()
            for _ in range(reps):
                step()
            torch.cuda.synchronize(device)
            dt = (time.perf_counter() - t0) / reps
            peak = torch.cuda.max_memory_allocated(device) / 1e9
            print(f"  B={b:>3}  峰值 {peak:>6.2f} GB   步耗时 {dt:>7.2f} s   "
                  f"s/样本 {dt/b:>6.4f}   （{n} 块, chunk={chunk}, ckpt={ckpt}）")
        except torch.cuda.OutOfMemoryError:
            print(f"  B={b:>3}  OOM")
            torch.cuda.empty_cache()
        del model, opt, x, y
        gc.collect()
        torch.cuda.empty_cache()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mem", action="store_true")
    ap.add_argument("--chunk", type=int, default=500)
    ap.add_argument("--no-ckpt", action="store_true")
    ap.add_argument("--batch", type=int, nargs="+", default=[16, 32])
    ap.add_argument("--layers", type=int, default=2)
    args = ap.parse_args()

    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"device = {dev}")

    print("\n=== 数值等价性（真实 ECGClassifier）===")
    print("  [chunk == L，应为逐位相同]")
    numeric_check(dev, chunk=1000, seq_len=1000)
    print("  [chunk < L]")
    for c in (64, 256, 500):
        numeric_check(dev, chunk=c, seq_len=1000)

    if args.mem:
        print(f"\n=== 显存/速度（L=5000, n_layers={args.layers}, "
              f"chunk={args.chunk}, checkpoint={not args.no_ckpt}）===")
        mem_check(dev, args.batch, layers=args.layers, chunk=args.chunk,
                  ckpt=not args.no_ckpt)


if __name__ == "__main__":
    main()
