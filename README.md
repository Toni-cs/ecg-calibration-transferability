# 校准迁移性研究｜W1–W14 实验归档（合成层实验 + T2 训练端规格）

> **本目录是 artifact 分支 / Release 资产，不是 `main`。**
> `main` 属于原仓库 `Toni-cs/ecg-calibration-transferability` 的 60 格边界验证稿，本归档**不修改、不覆盖、不代表**它。

> **本分支为分层发布**：包含 W1–W12 全部实验产物（代码、冻结预注册、逐种子数值、结果、图、日志、实验报告）与 T2 训练端规格。**投稿策略 / 期刊定位 / 内部路线图、上传操作记录、以及与散装目录内容重复的 11 个单轮 zip 已移除。** 归档未发表、未经同行评议、不构成期刊分区承诺，引用或二次发布前请先联系作者。

---

## ⚠️ 先读这五条（比任何结果都重要）

1. **本归档全部是内部合成层实验，未发表、未同行评议、不是 SOTA。**
2. **没有用 GPU、没有用真实患者波形。** 沙盒实测：无 GPU 设备、无 `torch`、无 `mamba_ssm`/`wfdb`/`h5py`、无任何真实波形或权重文件；运行时锁的是 NumPy / SciPy / Matplotlib + 单线程 BLAS。
3. **「600 个 Mamba 种子」是对角 selective SSM 的 NumPy 近似 + 合成 toy 波形**，不是官方 CUDA kernel；原仓库的 Mamba 是纯 PyTorch `mambapy==1.2.0`，无需 CUDA 构建；W2 用解析高斯 logits；60,000 个种子是逐场景抽样，不是 60,000 次前向。
4. **`CACHE_SCHEMA.json` 是契约，不是数据。** 归档内不含真实患者波形、逐记录 logits、`patient_id`、官方模型权重或任何 PhysioNet 受限数据。
5. **所有结论只能叫「协议级 / 合成层」**，不得外推成真实 ECG 结论，不得作为临床或产品依据。

原仓库的 60 格实验基于真实波形、`scripts/train.py` 与 release 里 62 个训练权重；**训练硬件未在仓库中声明**（README L34 写的是 `CUDA optional; CPU suffices for evaluation-only reproduction`）（PTB-XL 21,522 / Chapman–Shaoxing 混合 20,243 / CPSC2018 10,285，InceptionTime + ResNet-1D × 5 种子）。本归档做的是**把校准层从表示学习里切出来，在冻结 logits 上单独压力测试**——正因如此才能跑几十万个独立场景，代价是降了「真实性」这一维。

---

## 做了什么（一句话）

围绕「源域拟合的温度缩放能不能搬到目标语料」，跑了 **W1–W11-B 十一轮内部实验**：换过 estimand、换过骨干、换过估计器、加过定理、加过 60,000 个场景、最后把验收粒度做到 360 条独立断言。**主线结论是负面的多于正面的**，而且每一轮的事前假设被否证都完整留档。

| 量 | 值 |
|---|---|
| 独立种子 / 场景 | 60,000（W7）+ 20,000（W10）+ 10,600（W9）+ 600（W3）+ 600（W5/W6）等 |
| 架构对照 | 对角 SSM（Mamba 近似）+ CNN-1D，两类同号 |
| 定理 | T1–T4 四条（精确分解、非渐近界、误设噪声、Jensen gap） |
| W11 理论验收 | **4/6**（A3 斜率、A5 严格不等式未过；T2 界 93.4% 平凡、保守约 100×） |
| W11-B 百级验收 | **354/360**，6 条 FAIL 全留（TH054/TH064/TH099/PF041/PF048/PF049） |
| 可复现包 | preflight **7/7**、verify **12/12** |
| 原始产物完整性 | **244 个数值产物 SHA256 前后逐位一致**（B5 严格 S1/S2） |

---

## GPU 口径：三层别混

| 层 | 做什么 | GPU | 状态 |
|---|---|---|---|
| (a) 训练 backbone | 原仓库 `train.py` + 62 个权重（架构 `{inceptiontime, resnet1d}`） | **硬件未声明**（CUDA optional、CPU 可评估复现） | ✅ 训练脚本与权重已存在；`mamba` 是 `--arch` 默认值但**不进 60 格** |
| (b) **冻结前向提 logits** | W12：公开语料过一次冻结权重，产出 `logits_cache` | **要一次**（或 CPU/ONNX 慢跑） | ⬜ **唯一未做的一步** |
| (c) 校准层全部实验 | 温度、群结构、证书、bootstrap、证伪、360 条断言 | **不用** | ✅ 本归档全部内容 |

**「零 GPU 重跑」只指 (c)。** 补 (b) 不需要买卡：ECGFounder 等有 MIT 开放权重，单卡 A100 上 12 导联冻结前向约 2424 samples/s，≈60 万条纯前向仅几分钟，端到端约 2–8 GPU·小时（粗估）。最省事的起手式是**先用原仓库那 3 个公开语料 + 它自己的 checkpoint** 做一次最小前向，不到一小时就能把合成结论搬到真实波形上。详见 `W12_GPU算力需求与三层口径.md`。

> 沙盒无法代跑 (b)。它只能交付契约、preflight 断言、流水线骨架与验收脚本；真实前向必须落在有 GPU / `torch` / `wfdb` 的外部机器上。

### 一区级升级：T2（本轮新增，只有规格、没有训练结果）

「3 个公开库 + 一次冻结前向」**确实不够一区强度**。`tier1_gpu/` 把研究升级为：

| 维 | W12 | **T2** |
|---|---|---|
| 语料 | 3 个 / 52,050 条 | **13 个 / 主队列 ≈331 万记录、≈248 万独立患者、≥8 国** |
| GPU 端 | 只有冻结前向 | **Stage A 150 次从零训练 + Stage B 108 次基础模型适配 + Stage C CPU 校准层** |
| 架构 | 2 个 1D CNN（60 格正式网格） | **5 个架构族**（复用仓库已有 `mambapy`/`mamba_chunked.py` 路径并正式纳入网格；另含 CNN–SSM–Attention 混合）。**Mamba 不是新增架构**：原仓库 README L103 已声明 `--arch` 默认为 `mamba`，只是不进 60 格 |
| 标签 | 5 超类 | **4 套本体**（5/9/4/66 类）+ 心内科复核 |
| 外验 | 3 类 LOCO | **12 类 LOCO** + 患者/中心簇 bootstrap + 9 指标链 |
| 验收 | 12 门 | **12 条冻结验收门**，含「T2 界非平凡比例 >10%」这一合成层已知弱点检验 |

百万级走的是 **CODE-II**（巴西 2,735,196 条 / 2,093,748 患者，SciLifeLab 学术申请，**非美国数据、不直接受 DOJ DSP 对华阻断**）；MIMIC-IV-ECG / HEEDB 仍排除在承诺之外。

**本轮真实跑的只有规格自检**：13 语料 catalog、种子与 W1–W12 零冲突、preflight 结构断言 **36/36 PASS**、环境断言 **7 条 UNAVAILABLE 如实报**、12 门逻辑自检 8/12（G12 按设计不能自证）、训练骨架 `py_compile` 通过且 150/108/1 份计划全部标 `PLANNED_NOT_EXECUTED`。**真实 GPU 训练 0 次、真实波形 0 条。** 详见 `tier1_gpu/TIER1_GPU_UPGRADE.md` 与 `tier1_gpu/PREREGISTRATION_T2.md`。

---

## 数据准入与合规

- 本归档**不含**任何 credentialed / restricted 数据，因此不涉及 PhysioNet DUA 的「共享访问权」「第三方 LLM 传输」「发表单条记录」等禁止项；开放代码本身也是该类 DUA 的义务。
- 但 W12 的受限侧（MIMIC-IV-ECG）自 **2025-07-08** 起受美国司法部 DOJ Data Security Program 影响，PhysioNet 对中国大陆 IP / 机构隶属用户阻止**部分**受控数据集访问，且无学术豁免。W12 已拆为 **W12-open**（公开语料，≈55–60 万记录 / ≈37.7 万独立患者）+ **W12-restricted**（待官方书面答复，不设截止日）。详见 `W12_数据准入与替代方案.md`。
- 合规部分**不构成法律意见**；DSP 适用性与 covered person 认定须由单位法务与 PhysioNet 书面确认。

---

## 目录结构

```
README.md                          本文件
LICENSE                            MIT
PUBLIC_MANIFEST.sha256             公开层逐文件 SHA256
FULL_MANIFEST.sha256               本分支逐文件 SHA256（sha256sum -c 可直接校验）
W12_GPU算力需求与三层口径.md         GPU 三层、算力估算、四条路径
W12_数据准入与替代方案.md           DUA 流程、DSP 阻断、公开侧替代组合
成功论文架构漏洞与补洞报告.md        文献查新与 W4 协议级补洞
仓库快照复核与口径更正.md            Mamba / Zenodo / GPU 三处口径更正的依据（保留作诚信留痕）
upload_artifacts.py                上传工具（dry-run 默认，凭据只从环境变量读）
（UPLOAD_DRYRUN.log 仅本地留存，不随分支上传）

tier1_gpu/          T2 一区级 GPU 训练端升级：规格、冻结预注册 T2、13 语料配置、
                    网格规划器、preflight、12 门验收器、训练骨架模板、自检结果与总览图
                    （全部为规格级；真实 GPU 训练 0 次）

pari_experiment/     W1  PARI 合成识别与证伪（负面 → 删除）
gsgt_experiment/     W2  群结构化 GST、图正则被否证
mamba_experiment/    W3  对角 SSM + 600 独立种子
w4_repro/            W4  成功论文漏洞确认、门控失败
w5_srgst/            W5  GS-GST，600 全新种子跨过 90% 线
w6_tier1/            W6  命题 1 + CERT-GATE，危害率 9.67%→1.33%
w7_60k/              W7  60,000 场景、143 个不可变分片
w8_dualgate/         W8  硬门设计失效诊断
w9_lbst/             W9  命题 2（异方差 BLUP / Jensen）
w10_continuous/      W10 连续端点 + 20,000 种子，合格集为空
w11_theory/          W11 四条定理、576 格理论验收、可复现包、W11-B 360 条断言
```

每轮目录都含：冻结预注册、内核代码、逐种子/逐场景原始数值（`.npz` 分片或 JSON）、结果 JSON、图、日志、实验报告。**没有挑子集、没有删失败种子。**

---

## 完整审计史（一个不删）

| 轮 | 结论 |
|---|---|
| W1 | PARI 与 pooled 逐位相同、A1 无效 → 删除 |
| W2 | bootstrap 单位错配（v1.0 永久保留）；图正则有害、F-B 符号翻转 → 删图 |
| W3 | 600 Mamba：ΔECE −0.0248、CI 全负，但 534/600 差 6 个种子过线；H1=False 不改阈值 |
| W4 | 危害率 0.184、48 条记录 CI 宽 3.62× 确认；H4 门控失败、F4 漂移解释否证 |
| W5 | GS-GST 543/600 跨线；H1 高标准未达，照实留 |
| W6 | 命题 1 + CERT-GATE 9.67%→1.33%；H4/H5/H6 三项未过 |
| W7 | 60,000 场景 6/9；P3 按构造为 0、P4 estimand 不同、P5 尾部 100% 判 GST |
| W8 | 硬门失效：`n_min` 退化、门恒开 → 换路 |
| W9 | 命题 2（144/144）；9/12；事后「二值伪影」假设被自己的数据否证 |
| W10 | 连续端点 + 20,000 种子；6/12、合格集为空；LOCO 结构互斥机理查清 |
| W11 | T1–T4；理论 4/6；T2 界 93.4% 平凡；可复现包 12/12 |
| W11-B | 360 条独立断言，354/360，6 FAIL 全留；B5 证明 244 个原始产物逐位未变；**无新结论** |

**检查项变多 ≠ 更严谨，更 ≠ 更接近一区。** W11-B 只是验收粒度扩展。

---

## 复现

```bash
# 1) 校验归档完整性
sha256sum -c FULL_MANIFEST.sha256   # 或 PUBLIC_MANIFEST.sha256（内容一致）

# 1b) T2 规格自检（CPU，纯 stdlib / NumPy；不触发任何 GPU 训练）
cd tier1_gpu
python -u grid_planner.py            # 13 语料 / 150+108 网格 / 种子不相交 / 预算敏感性
python -u preflight_gpu.py --smoke   # 36 结构断言 + 7 环境断言（如实 UNAVAILABLE）
python -u acceptance_gates.py        # 12 门逻辑自检（非科学结论）
python -u train_gpu.py --stage A --plan-only --out results/plan
python -u make_t2_figure.py
cd ..

# 2) W11 原始验收（7/7 与 12/12）
cd w11_theory/repro
python -u preflight.py
python -u verify_release_results.py

# 3) W11-B 三组各 120 条独立断言
cd ../..
python -u scale/theory_assertions.py       # TH001-TH120
python -u repro/preflight_120.py           # PF001-PF120
python -u repro/verify_120.py              # VG001-VG120

# 4) 严格 S1/S2 哈希 + B1-B6 总控（会真实重跑上面三个脚本）
python -u scale/run_w11b.py
python -u scale/make_w11b_figure.py
```

完整一键命令见 `w11_theory/repro/REPRODUCE.md`。环境锁在 `w11_theory/repro/environment.lock`；所有随机种子与分片区间在 `SEED_MANIFEST.json`；61+ 个文件的哈希在 `WEIGHT_HASHES.sha256`。

> `run_w11b.py` 在重跑三组脚本**之前**算一次 244 个原始数值产物的 SHA256 快照 S1，**之后**再算 S2，`S1 == S2` 才通过 B5。三组脚本对原始产物只读。

---

## 距「一区」还差什么（不粉饰）

七维里 **1–4（理论、部署证书、患者级统计、9 指标链）已达一区级**，5 的机理查清；仍缺：

| 维 | 状态 | 卡在哪 |
|---|---|---|
| 6 真实多中心队列 + 真训练端 | ⚠️ **规格齐备、执行为零** | **外部 GPU 机器**；CODE-II 需 PI 提交学术申请；MIMIC/HEEDB 受 DOJ DSP 限制 |
| 7 临床 + 生统 + 第三方独立复跑 | ❌ | 心内科执业医师、生物统计审阅、非作者组复跑者、单位认定分区名单 |

**T2 已把第 5、6 维的规格补齐**（13 语料 / 331 万记录 / 150+108 次训练 / 12 类 LOCO / 12 条冻结门），但**所有真实 GPU 训练仍未执行**——沙盒内已无可自动推进的实验。再换第五个收缩式、再加种子、再换架构、再加检查项、再写一份规格，边际收益为零。真实队列上命题若失效，按停止条件如实发表负面结果，**不撤稿、不换指标、不回退合成结论**。

---

## 未随本分支公开的部分

以下为**投稿策略 / 期刊定位 / 内部路线图与上传操作记录**，保留在本地私有归档，不随分支发布：

`升二区执行计划.md`、`创新点与工作量补强方案.md`、`百万级数据与原创方法方案.md`、`一区构想与实施蓝图.md`、`直到一区执行计划.md`、`上传前核查与归档清单.md`、`成功论文架构漏洞与补洞报告.md`

**另移除 11 个单轮 zip**（`pari_experiment_w1.zip` 等）：它们与同名散装目录内容完全重复，删除后分支体积从 40.99 MiB 降到约 10 MiB，且不丢失任何原始数值。

> 查新时已发现 2026-10-15 同题预印本，未发表路线图公开后不可撤回。**代码、预注册、逐种子数值、实验报告、图、日志与 T2 规格全部保留，一个不删。**

本地另保留 `W1_W12_全量产物_上传候选.zip` 作为离线快照（含完整 `UPLOAD_MANIFEST.sha256`）。

---

## 许可与引用

本归档中的原创代码与文档采用 **MIT**（见 `LICENSE`）。原仓库 `Toni-cs/ecg-calibration-transferability` 的许可、预注册、更正账本与 checkpoints **以该仓库自身文件为准**，本归档不复制、不改写、不替它背书。

引用本归档时请同时注明：① 这是未发表的合成层内部实验；② 不含真实患者数据；③ 未完成冻结权重前向。相关工作的正式引用请以各数据集/模型官方页面为准，本文档不代列 DOI。

---

## 联系与状态

- 状态：**内部归档，未投稿，未同行评议**
- 分区判断：以作者单位认定的最新名单为准，本归档不作任何分区承诺
- 上传工具：`upload_artifacts.py`（`--dry-run` 默认；凭据仅从 `GITHUB_TOKEN` 环境变量临时读取，不写入任何文件、不回显）
