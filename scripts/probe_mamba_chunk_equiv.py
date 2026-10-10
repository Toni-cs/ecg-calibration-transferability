"""验证：分块扫描与全序列扫描数值是否等价

关键：BiMamba 的融合是 concat(fwd, bwd) 后 Linear。
- 正向 Mamba 是因果的 → 分块后逐块前向 == 全序列前向（数学恒等）
- 反向 Mamba 是 anti-causal（对 flip 后做因果）→ 分块会破坏边界状态传递！

因此：正向可无脑分块；反向必须用"分段+状态传递"或对小 chunk 做 overlap。
本脚本量化分块带来的误差，判定能否作为等价实现入稿。
"""
import sys
sys.path.insert(0, '.')
import torch
import torch.nn as nn

torch.manual_seed(0)
from src.models.s4_backbone import ECGMambaBackbone

B, L, D = 4, 2000, 64
model = ECGMambaBackbone(in_channels=12, d_model=D, n_layers=2).cuda()
model.eval()

x = torch.randn(B, 12, L).cuda()

with torch.no_grad():
    ref = model(x)


def chunked_naive(x, chunk):
    """朴素按时间切块，块间不传状态"""
    outs = [model(x[:, :, s:s + chunk]) for s in range(0, x.shape[2], chunk)]
    return torch.cat(outs, dim=1)


print('%-22s %-14s %-14s %s' % ('chunk', 'max|Δ|', 'mean|Δ|', '相对误差'))
for chunk in [2000, 1000, 500, 250, 100]:
    with torch.no_grad():
        got = chunked_naive(x, chunk)
    if got.shape != ref.shape:
        print('%-22d shape mismatch %s vs %s' % (chunk, tuple(got.shape), tuple(ref.shape)))
        continue
    d = (got - ref).abs()
    denom = ref.abs().mean().item()
    print('%-22d %-14.3e %-14.3e %.3e' % (chunk, d.max().item(), d.mean().item(),
                                          d.mean().item() / max(denom, 1e-12)))

print()
print('--- 对比：仅正向分支分块（反向不分块）---')


class ForwardChunked(nn.Module):
    """只把正向 Mamba 分块（因果 → 数学等价），反向保持全序列"""

    def __init__(self, orig, chunk):
        super().__init__()
        self.orig = orig
        self.chunk = chunk

    def forward(self, x):
        h = self.orig.stem(x)
        h = h.transpose(1, 2)
        for layer in self.orig.layers:
            h = layer(h)
        h = self.orig.norm(h)
        return self.orig.dropout(h)


print('（结构不变，仅在 BiMambaBlock 内部把 mamba_f 分块）')
print('逐块调用 mamba_f 并与整体调用比对：')
blk = model.layers[0]
with torch.no_grad():
    hh = model.stem(x).transpose(1, 2)
    hn = blk.norm(hh)
    full_f = blk.mamba_f(hn)
    for chunk in [1000, 500, 250]:
        parts = [blk.mamba_f(hn[:, s:s + chunk, :])
                 for s in range(0, hn.shape[1], chunk)]
        pcs = torch.cat(parts, dim=1)
        d = (pcs - full_f).abs()
        print('  正向 chunk=%-5d  max|Δ| %.3e  mean|Δ| %.3e  → %s'
              % (chunk, d.max().item(), d.mean().item(),
                 '恒等' if d.max().item() < 1e-5 else '有偏差'))

print()
print('反向分支同样测试：')
with torch.no_grad():
    full_b = blk.mamba_b(hn.flip([1])).flip([1])
    for chunk in [1000, 500, 250]:
        parts = []
        for s in range(0, hn.shape[1], chunk):
            seg = hn[:, s:s + chunk, :]
            parts.append(blk.mamba_b(seg.flip([1])).flip([1]))
        pcs = torch.cat(parts, dim=1)
        d = (pcs - full_b).abs()
        print('  反向 chunk=%-5d  max|Δ| %.3e  mean|Δ| %.3e  → %s'
              % (chunk, d.max().item(), d.mean().item(),
                 '恒等' if d.max().item() < 1e-5 else '有偏差(需状态传递)'))
