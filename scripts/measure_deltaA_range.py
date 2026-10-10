#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""测量 SSM 衰减项 log(ΔA) 的真实动态范围。

决定"能否用 cumsum 比值形式替代 Blelloch pscan"的关键量：
若块内 log(ΔA) 的极差 (max-min) 远小于 ln(fp32_max)≈88，则比值形式安全。

同时测量 Δ 的分布，以及训练若干步后 Δ 是否漂移。

用法::

    /c/python/python.exe scripts/measure_deltaA_range.py
    /c/python/python.exe scripts/measure_deltaA_range.py --train-steps 50
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import torch
import torch.nn.functional as F

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))

from mambapy.mamba import Mamba, MambaConfig  # noqa: E402
from src.models.ecg_classifier import ECGClassifier  # noqa: E402


def stats(t: torch.Tensor, name: str):
    f = t.detach().float().flatten()
    if f.numel() > 1_000_000:                       # quantile 有元素数上限
        idx = torch.randperm(f.numel(), device=f.device)[:1_000_000]
        f = f[idx]
    q = torch.quantile(f, torch.tensor([0.0, 0.01, 0.5, 0.99, 1.0], device=f.device))
    print(f"  {name:<22} min={q[0]:>10.4f}  p1={q[1]:>9.4f}  med={q[2]:>8.4f}  "
          f"p99={q[3]:>8.4f}  max={q[4]:>10.4f}")


def probe(model, x, tag, chunk_lens=(32, 64, 128, 256, 500)):
    """取第一个 MambaBlock，算 log_dA 的分布与各块长下的极差。

    输入约定：backbone 收 (B, 12, L)，内部 stem + transpose 后才是
    MambaBlock 的 (B, L, d_model)，这里复现该前缀。
    """
    blocks = [m for m in model.modules() if type(m).__name__ == "MambaBlock"]
    blk = blocks[0]
    ED = blk.config.d_inner

    with torch.no_grad():
        h = model.backbone.stem(x).transpose(1, 2)   # (B, L, d_model)
        h = model.backbone.layers[0].norm(h)         # BiMambaBlock 的预归一化
        x = h
        L = x.shape[1]
        xz = blk.in_proj(x)
        xb, _z = xz.chunk(2, dim=-1)
        xc = xb.transpose(1, 2)
        xc = blk.conv1d(xc)[:, :, :L].transpose(1, 2)
        xs = F.silu(xc)

        deltaBC = blk.x_proj(xs)
        dr = blk.config.dt_rank
        dlt = deltaBC[..., :dr]
        Bm = deltaBC[..., dr:dr + blk.config.d_state]
        delta = (blk.dt_proj.weight @ dlt.transpose(1, 2)).transpose(1, 2)
        delta = F.softplus(delta + blk.dt_proj.bias)          # (B,L,ED)
        A = -torch.exp(blk.A_log.float())                     # (ED,N)
        log_dA = delta.unsqueeze(-1) * A                      # (B,L,ED,N) <= 0

    print(f"\n=== {tag} ===")
    stats(delta, "delta (Δ)")
    stats(A, "A")
    stats(log_dA, "log(ΔA)")
    print(f"  全局极差 (max-min) = "
          f"{(log_dA.max() - log_dA.min()).item():.2f}   "
          f"(fp32 安全上限 ln(3.4e38) ≈ 88.7)")

    print(f"  {'块长':>6} {'cumsum极差 中位':>16} {'cumsum极差 最大':>16} "
          f"{'p99.99':>10} {'判定':>10}")
    for C in chunk_lens:
        n = L // C
        if n == 0:
            continue
        t = log_dA[:, :n * C].reshape(log_dA.shape[0], n, C, ED, log_dA.shape[-1])
        # 关键量：块内 cumsum(log_dA) 的极差 = 该块的总衰减，
        # 它决定比值形式里 exp(±range) 是否上溢（fp32 上限 88.7）
        cs = torch.cumsum(t, dim=2)
        rng = (cs.amax(dim=2) - cs.amin(dim=2))          # (B,n,ED,N)
        med = rng.median().item()
        mx = rng.max().item()
        p9999 = torch.quantile(rng.flatten().float()[:1_000_000], 0.9999).item()
        verdict = "安全" if mx < 80 else ("临界" if mx < 88 else "会溢出")
        print(f"  {C:>6} {med:>16.2f} {mx:>16.2f} {p9999:>10.2f} {verdict:>10}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--seq-len", type=int, default=5000)
    ap.add_argument("--train-steps", type=int, default=0,
                    help="先做若干 Adam 步，观察 Δ 是否漂移")
    ap.add_argument("--d-model", type=int, default=64)
    ap.add_argument("--layers", type=int, default=2)
    args = ap.parse_args()

    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    torch.manual_seed(0)

    model = ECGClassifier(in_channels=12, d_model=args.d_model,
                          n_layers=args.layers, num_classes=5, dropout=0.1,
                          backbone_type="mamba").to(dev)
    model.train()
    x = torch.randn(args.batch, 12, args.seq_len, device=dev)

    probe(model, x, "初始化后")

    if args.train_steps:
        opt = torch.optim.Adam(model.parameters(), lr=1e-3)
        y = torch.randint(0, 5, (args.batch,), device=dev)
        crit = torch.nn.CrossEntropyLoss()
        for i in range(args.train_steps):
            opt.zero_grad(set_to_none=True)
            logits, _ = model(x)
            crit(logits, y).backward()
            opt.step()
            if (i + 1) % 25 == 0:
                print(f"  ...已训练 {i+1} 步, loss={crit(logits, y).item():.4f}")
        probe(model, x, f"训练 {args.train_steps} 步后")


if __name__ == "__main__":
    main()
