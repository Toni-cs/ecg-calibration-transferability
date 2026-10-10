"""侦查：BiMamba 的 OOM 到底是显存不足还是实现问题

测法：拆解 ECGMambaBackbone 各段显存占用，并测不同 seq_len 下的峰值。
若瓶颈在 mambapy 的内部扫描物化（而非模型本身），可用梯度检查点/分块救回来。
"""
import sys, os
sys.path.insert(0, '.')
import torch
import torch.nn as nn

print('torch', torch.__version__)
print('cuda:', torch.cuda.is_available())
if torch.cuda.is_available():
    p = torch.cuda.get_device_properties(0)
    print('gpu: %s  %.1f GB  sm_%d%d' % (p.name, p.total_memory / 1e9,
                                          p.major, p.minor))
print()

try:
    from src.models.s4_backbone import ECGMambaBackbone
    print('[ok] import ECGMambaBackbone')
except Exception as e:
    print('[FAIL] import:', type(e).__name__, e)
    sys.exit(1)


def probe(seq_len, batch, d_model=64, n_layers=4, train=True):
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    try:
        m = ECGMambaBackbone(in_channels=12, d_model=d_model,
                             n_layers=n_layers).cuda()
        x = torch.randn(batch, 12, seq_len).cuda()
        if train:
            m.train()
            y = m(x)
            loss = y.float().pow(2).mean()
            loss.backward()
        else:
            m.eval()
            with torch.no_grad():
                y = m(x)
        peak = torch.cuda.max_memory_allocated() / 1e9
        del m, x, y
        torch.cuda.empty_cache()
        return True, peak
    except torch.cuda.OutOfMemoryError as e:
        torch.cuda.empty_cache()
        return False, str(e)[:80]
    except RuntimeError as e:
        torch.cuda.empty_cache()
        return False, '%s: %s' % (type(e).__name__, str(e)[:70])


print('%-10s %-8s %-6s %-6s %s' % ('seq_len', 'batch', 'layers', 'train', 'peak/result'))
for seq_len, batch in [(1000, 16), (1000, 32), (1000, 64),
                       (2500, 16), (2500, 32),
                       (5000, 8), (5000, 16)]:
    ok, info = probe(seq_len, batch)
    print('%-10d %-8d %-6d %-6s %s' % (
        seq_len, batch, 4, 'yes',
        ('%.2f GB' % info) if ok else ('OOM/' + info)))

print()
print('--- 分段测：n_layers=1 单块 ---')
for seq_len, batch in [(2500, 32), (5000, 16), (5000, 32)]:
    ok, info = probe(seq_len, batch, n_layers=1)
    print('%-10d %-8d %-6d %-6s %s' % (
        seq_len, batch, 1, 'yes',
        ('%.2f GB' % info) if ok else ('OOM/' + info)))

print()
print('--- 只前向不反向（分离激活 vs 权重）---')
for seq_len, batch in [(2500, 32), (5000, 16)]:
    ok, info = probe(seq_len, batch, train=False)
    print('%-10d %-8d %-6d %-6s %s' % (
        seq_len, batch, 4, 'no',
        ('%.2f GB' % info) if ok else ('OOM/' + info)))
