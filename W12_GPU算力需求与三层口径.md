# W12｜GPU 算力需求与三层口径（先把话说准）

**日期**：2026-11-06
**触发**：用户指出「原项目本来是用 GPU 训练的」，并问「是不是需要补 GPU」
**结论先给**：**不需要买一张常驻 GPU，也不需要重训模型；只需要一次性借几小时 GPU（或一块消费卡）做冻结权重的推断前向。** 更省的办法是：先用原仓库那 3 个公开语料 + 它自己 release 里的 checkpoint 跑一次最小前向，几十万条之前就能把真实波形这一环补上。

---

## 1. 三种「用 GPU」必须分开，之前混在一起了

你贴的那张表是原仓库的真实数据层：PTB-XL 21,522 / Chapman–Shaoxing 混合 20,243 / CPSC2018 10,285，统一成 5 个超类，InceptionTime + ResNet-1D × 5 种子 = 60 格。**那是真波形、真训练；但训练所用硬件未在仓库声明**（README L34：`CUDA optional; CPU suffices for evaluation-only reproduction`）。

| 层 | 做什么 | 要不要 GPU | 状态 |
|---|---|---|---|
| **(a) 表示学习 / 训练** | 原仓库 `train.py` 训练 InceptionTime / ResNet-1D（`--arch` 默认 `mamba` 但不进 60 格） | **硬件未声明**（CUDA optional、CPU 可评估复现） | ✅ 训练脚本 + release 里 62 个权重已存在 |
| **(b) 冻结前向 / 提 logits** | W12：拿公开语料过一次冻结权重，产出 `logits_cache` | **要一次**（或用 CPU/ONNX 慢跑） | ⬜ **唯一没做的一步** |
| **(c) 校准层 / 全部 W1–W12 实验** | 温度、群结构、证书、bootstrap、证伪、360 条断言 | **完全不用**，NumPy 就够 | ✅ 已完成，且正因如此才能跑几十万个场景 |

**「零 GPU 重跑」指的是 (c)，不是整个项目。** 之前这句话容易被读成「全项目不需要 GPU」，是表述不严。

### 沙盒实测（不靠推断）

| 项 | 结果 |
|---|---|
| `nvidia-smi` | 不存在 / 无 GPU 设备 |
| `torch` | 未安装 |
| `mamba_ssm` / `causal_conv1d` / `wfdb` / `h5py` | 全部 absent |
| 真实波形 / 权重 / logits 缓存文件 | **0 个** |
| `environment.lock` | NumPy / SciPy / Matplotlib + 单线程 BLAS |

所以 W3 的「600 个 Mamba 种子」是**对角 selective SSM 的 NumPy 近似 + 合成 toy 波形**，W2 是解析高斯 logits，W7 的 60,000 是**逐场景抽样**而非 60,000 次前向。**W1–W12 全部只能叫「合成层 / 协议级内部实验」，不能外推成真实 ECG 结论，更不能写成 SOTA。** 这是用规模换真实性，不是等价替代。

---

## 2. 到底要多少算力

### 有现成的开放权重，不用自己训

**ECGFounder**（NEJM AI 2025）预训练 checkpoint 在 Hugging Face `PKUDigitalHealth/ECGFounder`，**MIT 许可**，代码在 GitHub 。官方明确要求：用权重做验证/微调必须严格照 `dataset.py` 的预处理（滤波、z-score 归一化等），否则复现不出论文结果 。ECG-FM 等也有 MIT 开放权重 。**用开放权重 ≠ 需要 DUA**：DUA 管的是受限原始波形，不是公开模型参数。

### 量级估算

有第三方在 **NVIDIA A100、batch=64** 上测过 12 导联冻结前向：ECGFounder 吞吐 **2423.7 samples/s**、峰值显存约 202 MB 。按此粗算：

| 规模 | 纯前向 | 现实端到端（含解码/重采样/滤波/I/O） |
|---|---|---|
| **52,050 条**（原仓库 3 个公开语料） | ≈ **21 秒** | **不到 1 小时** |
| **≈60 万条**（W12-open 公开侧） | ≈ **4.1 分钟** | **约 2–8 GPU·小时** |
| 135 万条（再加 MIMIC，受限侧） | ≈ 9 分钟 | 约 5–15 GPU·小时 |

> 这些是**粗估**，纯前向数字来自公开 benchmark ，端到端区间是工程判断，**必须以你机器上的实测为准**。真正的瓶颈几乎从来不是矩阵乘，而是 WFDB/HDF5 解码、400↔500 Hz 重采样、带通/陷波、z-score、以及把 60 万条写进缓存的 I/O。

### CPU 也能走，只是慢

有 ONNX 版 ECGFounder，输入 `(batch, 12, 5000)`、500 Hz，**Raspberry Pi 4 上 115 ms/条**；x86 桌面会快不少 。按 Pi 的量级 60 万条约 19 小时纯推断，x86 大概数小时到十几小时。**所以 GPU 不是硬性必需，是「把几小时压到几十分钟」的加速器。**

---

## 3. 四条路，怎么选

| 方案 | 做法 | 适合 | 代价 |
|---|---|---|---|
| **① 学校/课题组集群借几小时**（推荐） | 一次性前向，产出 `logits_cache` 后立刻归还 | 有现成 A100 / 4090 / A800 | 几乎为零 |
| **② 云上租几小时** | 按小时租单卡，跑完销毁实例 | 没有集群 | 几十到百余元量级 |
| **③ CPU + ONNX 慢跑** | 不装 CUDA，分批跑 | 完全没 GPU | 数小时～十几小时，且要装 `onnxruntime` |
| **④ 暂不做 (b)** | 停在合成层，明确下调结论与期刊定位 | 只想先发表协议级结果 | 一区第 6 维永远缺位 |

**不建议买卡。** 这是一锤子买卖：权重冻结、只前向一次，之后所有校准实验回到 CPU 的 logits 上零 GPU 重跑 —— 这正是 W6/W7/W9 已经证明可行、也是能跑几十万场景的前提。

仓库已有的 Mamba 是 **`mambapy==1.2.0` 纯 PyTorch 实现，无需 CUDA 构建**；`mamba-ssm` / `causal-conv1d` 在 `requirements.txt` 里只是 Linux 可选注释。若将来切换到官方 CUDA kernel 才需要 CUDA GPU，那是增强项而非 W12 前置。

---

## 4. 最省事的起手式：先复用你贴的那张表

你给的图里三个语料（PTB-XL、Chapman–Shaoxing 混合、CPSC2018）**本来就是 PhysioNet 公开数据，不涉 DUA、不涉 2025 年 DOJ DSP 限制**。而原仓库的 60 格 checkpoint 就在它自己的 GitHub release 资产里。

于是最小闭环是：

1. 下这 3 个公开语料（52,050 条）+ 原仓库 release 的 InceptionTime / ResNet-1D checkpoint
2. 在外部 GPU 上冻结前向，产出**第一份真实 logits 缓存**
3. `preflight.py` 七项断言过一遍（导联按名对齐、患者级 disjoint split、CODE-15% 歧义标签等）
4. 把 W6 的 CERT-GATE、W9 命题 2、W11 四条定理**原封不动**搬到真实 logits 上重跑

这一步几十分钟到一小时就能出结果，**而且直接回答了「合成层结论在真实波形上还成不成立」**——比一口气铺 60 万条更划算。之后再扩到 CODE-15% / IKEM / SPH / CODE-II-open 的 ≈60 万条。

### 我能不能代跑

**不能。** 沙盒无 GPU、无 `torch`/`wfdb`/`h5py`、无真实波形文件。我能交付的是：`CACHE_SCHEMA.json` 契约、`preflight.py` 七项断言、前向流水线骨架、12 门验收脚本、逐文件哈希 manifest。真实前向必须落在**你那边的 GPU 机器**上。上一版写「W12-open 今天就能启动、其余我可自动执行」不准确，已在 `直到一区执行计划.md` 更正为「需外部 GPU 环境」。

---

## 5. 一句话回答

**不用补一张常驻 GPU，也不用重训；借一次单卡几小时做冻结前向就够了，甚至 CPU/ONNX 也能磨出来。** 真正缺的不是算力所有权，是「把 W1–W12 从合成 logits 搬到真实 logits」那一次前向——而它最好就从你贴的那 3 个公开语料 + 原仓库 checkpoint 开始，成本不到一小时。

---

## 6. 诚实边界

- 前向吞吐与显存来自公开 A100 benchmark ，端到端小时数为工程粗估，非实测
- ECGFounder 权重 MIT 开放，但**必须按其 `dataset.py` 预处理**才能对齐论文口径 
- 使用开放模型权重不涉及 PhysioNet credentialed DUA；受限原始波形（MIMIC-IV-ECG、HEEDB）仍受 DUA 与 DOJ DSP 约束，见 `W12_数据准入与替代方案.md`
- 本文件不构成法律意见；DSP 适用性由单位法务与 PhysioNet 书面确认
- 引用请在正文中按 `[citation:N]` 对应检索文档核验，归档 README 不重复列 DOI
