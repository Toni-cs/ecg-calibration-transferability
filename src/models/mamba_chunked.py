#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""分块 select 扫描：把 mambapy 的 O(B·L·ED·N) 显存降到 O(B·chunk·ED·N)。

=====================================================================
为什么需要
=====================================================================
``mambapy.MambaBlock.selective_scan`` 会物化三个 ``(B, L, ED, N)`` 张量
（``deltaA`` / ``deltaB`` / ``BX``），pscan 内部还会再持有若干份。
本仓配置 d_model=64 → ED=128、d_state=16 → N=16、L=5000（``data/*/data/*.npy``
为 ``(12, 5000)``），故 B=16 时单个张量即 655 MB，实测峰值 **19.7 GB**
（RTX 5060 Laptop 仅 8.55 GB → 靠 WDDM 换页到系统内存，18 s/步）。

=====================================================================
只分块 SSM，不分块卷积 —— 这是关键
=====================================================================
``MambaBlock.forward`` 里真正吃显存的是 ``selective_scan``。它前面的
``conv1d`` 与 ``x_proj`` 都是 ``O(B·L·ED)``（B=16/L=5000 时仅 41 MB / 7.7 MB），
可以整条序列算完再交给分块的 SSM。

因此**不需要处理卷积跨块边界**（那正是"补左侧 3 token halo"问题的来源）——
本模块完全不碰 ``conv1d``。分块只发生在递推内部，数值上等价。

=====================================================================
递推的分块形式（数学上精确）
=====================================================================
逐时刻递推为 ``h_t = ΔA_t ⊙ h_{t-1} + BX_t``，``y_t = h_t·C_t + D·x_t``。
设块内 ``h_loc`` 为 pscan 在 ``h_{-1}=0`` 下的结果，``cumA_t = Π_{s≤t} ΔA_s``，
则真实状态为

    h_t = h_loc_t + cumA_t ⊙ h_in

（线性叠加，精确）。块尾状态即下一块的 ``h_in``。

``cumA`` 用 log 空间累加避免连乘误差：``ΔA = exp(logΔA)``，而 ``logΔA = Δ·A``
本来就已算出，故 ``cumA = exp(cumsum(Δ·A))``。因 ``A<0``、``Δ>0``，
``cumsum`` 恒 ≤ 0，**不会上溢**；下溢到 0 恰好等于"初始状态影响已消失"，
是正确结果。

=====================================================================
梯度检查点
=====================================================================
若不加检查点，反向传播仍会保留每个块的中间量，显存不降。故每个块用
``torch.utils.checkpoint`` 包一层：反向时逐块重算，任一时刻只持有一个块。

=====================================================================
已否决的替代方案：cumsum 比值形式（勿重走）
=====================================================================
块内用 ``h_t = exp(c_t)·Σ_{s≤t} BX_s·exp(−c_s)``（``c = cumsum(logΔA)``）
可以完全不调 pscan，只需 4 个累积算子。但**实测否决**，两条理由：

1. **数值不安全。** 该式需要把 ``exp(±range)`` 落进 fp32，``range`` 是块内
   总衰减 ``Σ|logΔA|``，**随块长线性增长**。实测（``scripts/measure_deltaA_range.py``，
   真实 ECGClassifier）块内 cumsum 极差：

   ====== ========== ========== ==========
   块长    中位        最大        fp32 判定
   ====== ========== ========== ==========
   32      2.76       51.94      安全
   64      5.61      103.93      溢出
   128    11.32      207.80      溢出
   500    44.50      809.16      溢出
   ====== ========== ========== ==========

   上溢阈值 ``ln(3.4e38)=88.7``。故块长必须 ≤48，且训练中 Δ 增长即失效
   （``scripts/validate_chunked_scan.py`` 里 chunk≥64 直接 NaN）。

2. **而且更慢。** 块长被压到 48 意味着 L=5000 要 105 次外层 Python 迭代，
   启动开销盖过收益。实测 B=16/L=5000（含反向，4 个 block）：

   ==================== ========== ==========
   配置                  峰值       步耗时
   ==================== ========== ==========
   pscan, chunk=500      5.24 GB    1.38 s
   cumsum, chunk=48      4.99 GB    2.00 s
   cumsum, chunk=32      4.97 GB    2.87 s
   ==================== ========== ==========

   即 pscan 版本在显存与速度上同时占优，故保留 pscan。

**另一个反直觉的结论：分块本身不是加速手段。** 实测 chunk=250/500/1000 的
步耗时都是 1.39 s —— 因为 Blelloch pscan 的 up-sweep 张量逐级减半，
总访存量与块长基本无关，瓶颈是 ``(B,L,ED,N)`` 的内存带宽（约 940 GB/s 实测，
已接近该卡峰值），不是 Python 循环次数。所以**不要指望靠调 chunk 提速**；
分块的唯一价值是把 19.7 GB 压到 5.2 GB。
"""

from __future__ import annotations

from typing import Optional

import torch
from torch.utils.checkpoint import checkpoint as _ckpt

from mambapy.pscan import pscan


def _chunk_scan_step(xs, ds, Bs, Cs, h_in, A, D):
    """单块递推。xs/ds: (B,c,ED)；Bs/Cs: (B,c,N)；h_in: (B,ED,N)；A: (ED,N)；D: (ED,)"""
    log_dA = ds.unsqueeze(-1) * A                       # (B,c,ED,N)  恒 ≤ 0
    dA = torch.exp(log_dA)
    dB = ds.unsqueeze(-1) * Bs.unsqueeze(2)             # (B,c,ED,N)
    BX = dB * xs.unsqueeze(-1)                          # (B,c,ED,N)

    h_loc = pscan(dA, BX)                               # h_{-1} = 0
    cumA = torch.exp(torch.cumsum(log_dA, dim=1))       # (B,c,ED,N) ∈ (0,1]
    h_c = h_loc + cumA * h_in.unsqueeze(1)              # 叠加传入状态

    y = (h_c @ Cs.unsqueeze(-1)).squeeze(3) + D * xs    # (B,c,ED)
    return y, h_c[:, -1]


def selective_scan_chunked(x, delta, A, B, C, D,
                           chunk: int = 500, use_checkpoint: bool = True):
    """与 ``MambaBlock.selective_scan`` 同签名、同返回值，但按时间分块。

    x/delta: (B,L,ED)   A: (ED,N)   B/C: (B,L,N)   D: (ED,)   -> y: (B,L,ED)
    """
    Bb, L, ED = x.shape
    N = A.shape[1]
    h = torch.zeros(Bb, ED, N, device=x.device, dtype=x.dtype)
    ys = []
    for s in range(0, L, chunk):
        e = min(s + chunk, L)
        args = (x[:, s:e], delta[:, s:e], B[:, s:e], C[:, s:e], h, A, D)
        if use_checkpoint:
            y, h = _ckpt(_chunk_scan_step, *args, use_reentrant=False)
        else:
            y, h = _chunk_scan_step(*args)
        ys.append(y)
    return torch.cat(ys, dim=1)


def enable_chunked_scan(model: torch.nn.Module, chunk: int = 500,
                        use_checkpoint: bool = True, verbose: bool = False) -> int:
    """把 model 内所有 mambapy ``MambaBlock`` 的 ``selective_scan`` 换成分块版。

    返回被替换的块数（0 表示这个模型没有 Mamba 块，例如 inceptiontime/resnet1d）。
    """
    n = 0
    for m in model.modules():
        if type(m).__name__ == "MambaBlock" and hasattr(m, "selective_scan"):
            cfg = getattr(m, "config", None)
            if cfg is not None and getattr(cfg, "pscan", True) is False:
                continue                      # 顺序扫描路径，无需分块
            if getattr(m, "_chunked_scan", False):
                continue

            def make(mod, c=chunk, uc=use_checkpoint):
                def patched(x, delta, A, B, C, D):
                    return selective_scan_chunked(x, delta, A, B, C, D,
                                                  chunk=c, use_checkpoint=uc)
                return patched

            m.selective_scan = make(m)
            m._chunked_scan = True
            n += 1
    if verbose and n:
        print(f"[chunked-scan] 已替换 {n} 个 MambaBlock（chunk={chunk}, "
              f"checkpoint={use_checkpoint}）")
    return n
