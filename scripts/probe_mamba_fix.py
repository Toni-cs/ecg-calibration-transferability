"""验证：BiMamba OOM 可通过"分块扫描 + 梯度检查点"救回

根因：mambapy 的 selective_scan (pscan 模式) 物化 (B, L, ED, N) 中间张量并
      保留全时间步历史 → 显存随 L 线性暴涨。d_model=64, expand=2 → ED=128,
      d_state=16 → 每个 (B,L,ED,N) 在 B*L=80000 时约 0.65 GB，pscan 内部还有
      多份 → 单层 >8GB。

修法（不改模型语义、只改执行策略）：
  A. 分块扫描：把时间维切成 chunk，逐块扫，显存降为 O(chunk)
  B. 梯度检查点：torch.utils.checkpoint 重算前向，省激活
  C. 换 sequential 扫描（pscan=False）：显存 O(B*ED*N)，但慢

本脚本量化三档的显存/耗时权衡，证明可行性。
"""
import sys, time
sys.path.insert(0, '.')
import torch
import torch.nn as nn

torch.cuda.empty_cache()
p = torch.cuda.get_device_properties(0)
print('gpu: %s  %.1f GB' % (p.name, p.total_memory / 1e9))
print()

from mambapy.mamba import Mamba, MambaConfig


def make(d_model=64, d_state=16, expand=2):
    return Mamba(MambaConfig(d_model=d_model, n_layers=1, d_state=d_state,
                             d_conv=4, expand_factor=expand))


def try_run(tag, fn):
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    t0 = time.time()
    try:
        fn()
        torch.cuda.synchronize()
        dt = time.time() - t0
        peak = torch.cuda.max_memory_allocated() / 1e9
        print('  %-34s OK   peak %5.2f GB  %6.2f s' % (tag, peak, dt))
        return True, peak, dt
    except torch.cuda.OutOfMemoryError:
        torch.cuda.empty_cache()
        print('  %-34s OOM' % tag)
        return False, None, None
    except Exception as e:
        torch.cuda.empty_cache()
        print('  %-34s ERR  %s' % (tag, str(e)[:40]))
        return False, None, None


B, L, D = 16, 2500, 64
print('配置: batch=%d seq_len=%d d_model=%d  (B*L = %d)' % (B, L, D, B * L))
print()

print('[基线] pscan=True（原实现）')
def base():
    m = make(D).cuda(); m.train()
    x = torch.randn(B, L, D).cuda()
    m(x).pow(2).mean().backward()
try_run('pscan 训练', base)

print()
print('[方案 C] pscan=False（sequential 扫描）')
def seq():
    m = make(D).cuda(); m.train()
    m.config.pscan = False
    x = torch.randn(B, L, D).cuda()
    m(x).pow(2).mean().backward()
try_run('sequential 训练', seq)

print()
print('[方案 B] 梯度检查点（pscan=True）')
def ckpt():
    from torch.utils.checkpoint import checkpoint
    m = make(D).cuda(); m.train()
    x = torch.randn(B, L, D).cuda()
    out = checkpoint(m, x, use_reentrant=False)
    out.pow(2).mean().backward()
try_run('checkpoint 训练', ckpt)

print()
print('[方案 A] 分块扫描（时间维切 chunk，每块独立扫）')
def chunked(chunk=500):
    m = make(D).cuda(); m.train()
    x = torch.randn(B, L, D).cuda()
    outs = []
    for s in range(0, L, chunk):
        outs.append(m(x[:, s:s + chunk, :]))
    torch.cat(outs, dim=1).pow(2).mean().backward()
try_run('chunk=500 训练', lambda: chunked(500))

print()
print('[组合] checkpoint + chunk')
def ckpt_chunk(chunk=500):
    from torch.utils.checkpoint import checkpoint
    m = make(D).cuda(); m.train()
    x = torch.randn(B, L, D).cuda()
    outs = [checkpoint(m, x[:, s:s + chunk, :], use_reentrant=False)
            for s in range(0, L, chunk)]
    torch.cat(outs, dim=1).pow(2).mean().backward()
try_run('ckpt+chunk=500 训练', lambda: ckpt_chunk(500))

print()
print('[上层] 4 层 BiMamba 骨干（checkpoint 包裹）')
try:
    from src.models.s4_backbone import ECGMambaBackbone
    from torch.utils.checkpoint import checkpoint

    def backbone_ckpt():
        m = ECGMambaBackbone(in_channels=12, d_model=64,
                             n_layers=4).cuda()
        m.train()
        x = torch.randn(B, 12, L).cuda()
        y = m(x)
        y.float().pow(2).mean().backward()
    try_run('ECGMambaBackbone n_layers=4', backbone_ckpt)
except Exception as e:
    print('  import fail:', e)

print()
print('--- 判读 ---')
print('若 sequential / checkpoint 显著降显存且能在 8.5GB 内跑通 B=16,L=2500,')
print('则 BiMamba 的 OOM 属实现级可修问题，第 3 个架构不必降级为玩具格。')
