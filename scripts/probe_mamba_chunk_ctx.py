"""验证：带 overlap 的分块扫描能否做到数学恒等

发现：朴素分块的偏差来自 depthwise conv1d（d_conv=4）跨越块边界。
因果卷积只需左侧 d_conv-1 个 token 作为上下文。若每块向左多取 (d_conv-1)
个 token 做"上下文"，再丢弃这些 token 的输出，即可与全序列**严格恒等**。

注意：Mamba 的 SSM 状态 h 也会跨块累积，需要同时传递状态。
本脚本分两步验证：
  步1：仅补 conv 上下文（不传 SSM 状态）→ 看残余偏差
  步2：补上下文 + 传 SSM 状态 → 期望恒等
"""
import sys
sys.path.insert(0, '.')
import torch
import torch.nn.functional as F

torch.manual_seed(0)
from mambapy.mamba import Mamba, MambaConfig

D, S, EXP, CONV = 64, 16, 2, 4
m = Mamba(MambaConfig(d_model=D, n_layers=1, d_state=S, d_conv=CONV,
                      expand_factor=EXP)).cuda().eval()
ED = D * EXP

B, L = 2, 1500
x = torch.randn(B, L, D).cuda()

with torch.no_grad():
    ref = m(x)

print('d_conv=%d → 因果卷积需要左侧 %d 个 token 作上下文' % (CONV, CONV - 1))
print('%-10s %-10s %-14s %-14s' % ('策略', 'chunk', 'max|Δ|', 'mean|Δ|'))

# ---- 策略 1：朴素分块 ----
def naive(chunk):
    return torch.cat([m(x[:, s:s + chunk, :])
                      for s in range(0, L, chunk)], dim=1)


# ---- 策略 2：左侧补 conv 上下文（丢弃输出）----
def with_ctx(chunk):
    pad = CONV - 1
    outs = []
    for s in range(0, L, chunk):
        lo = max(0, s - pad)
        seg = x[:, lo:s + chunk, :]
        o = m(seg)
        outs.append(o[:, s - lo:, :])
    return torch.cat(outs, dim=1)


for chunk in [1000, 500, 250, 100]:
    with torch.no_grad():
        a = naive(chunk)
        b = with_ctx(chunk)
    da = (a - ref).abs()
    db = (b - ref).abs()
    print('%-10s %-10d %-14.3e %-14.3e' % ('朴素', chunk, da.max().item(), da.mean().item()))
    print('%-10s %-10d %-14.3e %-14.3e' % ('补上下文', chunk, db.max().item(), db.mean().item()))

print()
print('--- 逐层定位：偏差来自 conv 还是 SSM 状态 ---')
# 手动重放 MambaBlock 内部，分离两段
blk = m.layers[0]
mixer = blk.mixer
with torch.no_grad():
    xz = mixer.in_proj(x)
    xx, zz = xz.chunk(2, dim=-1)
    # conv 段
    xc = xx.transpose(1, 2)
    conv_full = mixer.conv1d(xc)[:, :, :L]
    # 分块做 conv
    cparts = []
    for s in range(0, L, 500):
        seg = xc[:, :, max(0, s - 3):s + 500]
        cparts.append(mixer.conv1d(seg)[:, :, :min(500, L - s)])
    conv_chunk = torch.cat(cparts, dim=2)
    dc = (conv_chunk - conv_full).abs()
    print('  conv 分块(补上下文)  max|Δ| %.3e  mean|Δ| %.3e' % (dc.max().item(), dc.mean().item()))

    # SSM 段：用 conv 后的同一输入，比较整体 vs 分块（不传状态）
    xin = F.silu(conv_full).transpose(1, 2)
    zin = F.silu(zz)
    y_full = mixer.ssm(xin, zin)
    yparts = []
    for s in range(0, L, 500):
        yparts.append(mixer.ssm(xin[:, s:s + 500, :], zin[:, s:s + 500, :]))
    y_chunk = torch.cat(yparts, dim=1)
    dy = (y_chunk - y_full).abs()
    print('  SSM 分块(不传状态)   max|Δ| %.3e  mean|Δ| %.3e' % (dy.max().item(), dy.mean().item()))
    print()
    print('  判读: conv 段若恒等 → 上下文修复有效')
    print('        SSM 段若不恒等 → 必须显式传递状态 h (B, ED, N)')
