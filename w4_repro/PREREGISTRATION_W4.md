# 预注册｜W4 复现成功论文协议并补洞（冻结）

**版本**：v1.0（终局）
**冻结时间**：2026-11-06（Asia/Shanghai）
**性质**：确认性。**本文件冻结后才执行主跑。**
**保留**：W1（PARI 否证）、W2 v1.0（H1=False）、W2 v1.1（F-B FAIL / 删图）、W3（600 Mamba 种子，H1=False 差 6 个种子）全部结果照实公开，不得删除。

---

## 1. 复现对象（"成功的论文"）

**Frontiers in Cardiovascular Medicine, 2026**：*Label-efficient cross-population transfer learning for electrocardiographic risk stratification: evaluation across German, Chinese and US cohorts*，doi `10.3389/fcvm.2026.1928354`，PMC13601223。**已同行评议**。

它是调研到的 15 篇候选里**校准评估链最完整**的一篇：

| 项 | 论文做法 |
|---|---|
| 数据 | PTB-XL 7,371（源）→ Chapman-Ningbo 4,574（主目标）+ MIT-BIH 576 段 / **48 条记录**（零样本压力） |
| 标签 | 13 个 SNOMED-CT 超类，7 类组成复合诊断评分 |
| 特征 | 38 维物理单位可解释特征，源训练分区单独标准化 |
| 模型 | 紧凑多任务骨干 30,400 参数 |
| 切分 | **患者级**分离；源训练 / 目标 **专用 calibration split** / **未触碰 test** |
| 校准 | noisy-OR 融合 7 类概率 → **isotonic 在专用 split 拟合** |
| 统计 | bootstrap CI、Holm 校正、亚组交互、DCA |
| 报告 | Chapman-Ningbo 复合终点 **AUROC 0.791、Brier 0.055、ECE 0.018**；其中 **97% 阳性为 LVH** |

**次选架构基线**：ECG-RAMBA（arXiv:2512.23347，Bi-Mamba + MiniRocket + HRV，零样本 CPSC-2021 PR-AUC 0.708）。已核实：**无官方代码**，仅有社区实现 `BrianNguyen29/ECG-RAMBA`（4 stars，MIT，需 CUDA `mamba-ssm` + ≥10GB VRAM）。本沙盒不具备，故**不声称跑通其前向**；仅作为架构对照的文献锚点。

---

## 2. 诚实边界（必须写进论文）

- 本轮**不复现真实波形、真实权重、38 维物理特征**。沙盒无 PhysioNet DUA 数据、无官方权重、无 CUDA `mamba-ssm`。
- 我们复现的是**评估协议的结构**：患者级 disjoint calibration/test、noisy-OR 复合终点、isotonic 重校准、极端类别失衡（97% 阳性集中一类）、48 条记录的 stress set、bootstrap。
- logits 由 W3 的**对角 selective SSM（Mamba 对角近似）**前向产生，合成 7 类多标签 toy 波形。
- 因此本轮结论是**协议级 / 方法论级**，**不是**对该论文数值结果的复现，也不外推为真实 ECG 结论。真实数据前向仍须 T1 preflight + DUA。

---

## 3. 四个待补的洞（事前固定，精确到论文环节）

| ID | 具体漏洞 | 量化方式 |
|---|---|---|
| **H1** | 论文只报**复合终点** ECE 0.018；13 类压成 1 个 noisy-OR 分数后，**classwise 误校准被平均掉** | 同一 test 上 `classwise macro ECE − composite ECE` |
| **H2** | 论文**没有「不重校准」对照**，无法回答"isotonic 是否在部分亚组有害" | 对照 source-only，按 group × 人口代理亚组算 `ΔBrier > 0` 的**校准危害率** |
| **H3** | MIT-BIH 压力集仅 **48 条记录**，CI 宽到无法支撑零样本结论 | 48 vs 800 条记录的 bootstrap CI 宽度比 |
| **H4** | 论文无**何时不该重校准**的门控；设备/时间漂移只由不同语料隐式表达，未按可观测群定义 | 无标签门控（源域参考直方图距离）→ 三态 `ISOTONIC / FALLBACK`，事前冻结阈值 |

**已被别人占住、本轮不重复声称**：
- 《Calibration Transfer Gap》(Research Square 2026-10-15) 已做「少量标签下无条件重拟合有害」+ 收缩/CV/信息准则门控（非 ECG）
- BUDDY (ICLR 2026) 已做 group-conditional temperature（LLM）
- HG-CRC (arXiv:2607.24562) 已做分层 group-conditional conformal risk control + abstention
- Calibrated Selective Classification (S-MMCE) 已做「拒绝自身不确定性不可靠的样本」
- MD-TS (NeurIPS **2022**，ImageNet-C，非 ECG) 已做逐域温度 + embedding→T
- ECL (ICML 2026 接收，非 ECG) 已做协变量漂移下期望一致性条件

**本轮 novelty 精确边界**：首次在 **ECG 无标签、按可观测部署群、患者级 disjoint split** 下，以**校准危害率**为终点检验「何时回退到不校准」，并把该门控接在冻结 SSM logits 上。**不声称**首次提出校准门控、首次分域温度、首次 conformal abstention。

---

## 4. 种子集（冻结，互不重叠）

| 用途 | 种子 | n |
|---|---|---|
| **Pilot（定门控阈值）** | 5000–5049 | 50 |
| **主跑（确认性）** | 5100–5399 | **300** |
| **证伪** | 5400–5459 | 60 |

W1/W2/W3 用过的 0–29 / 1000–1029 / 2000–2029 / 3000–3599 / 3600–3659 / 3700–3799 **全部不复用**。

**门控阈值只在 pilot 上用标签确定一次**（Youden J），主跑 300 种子**完全不参与阈值选择**。这是报告第 7 节明确要求的「不能同一批数据选阈值又评价性能」。

---

## 5. DGP 与协议（冻结）

- K=7 类，标签 `y ~ Bernoulli(p_i)` **采样**（非 argmax）；target 令第 0 类高发模拟 **97% 阳性为 LVH**
- 群漂移：G=4 个可观测部署群，真实 `log T_g = log 2.4 ± spread(0.9) + N(0,0.08)`；源域 T=1
- 每记录 = 1 名患者（合成层显式声明；真实阶段改 patient-block）；source n=1200 / target n=800 / stress n=48
- 患者级 disjoint：target 30% calibration / 70% test，**零重叠**
- logits 由 Mamba 对角 SSM 前向 + 冻结 multiridge readout 产生，按源域 logits 标准差缩放后乘 T_g（防 sigmoid 饱和）
- 复合分数 `1 − ∏(1−p_k)`；复合标签 `any(y_k=1)`
- isotonic (PAVA) 在 calibration split 拟合，test 上评估
- ECE = 10-bin equal-width；Brier、AUROC、calibration slope 同步报

---

## 6. 主终点与阈值（冻结）

| ID | 主终点 | 通过条件 |
|---|---|---|
| **H1** | `gap = classwise macro ECE − composite ECE` | `mean gap ≥ 0.020`，且 ≥90% 种子 gap>0 |
| **H2** | 无条件 isotonic 的**校准危害率**（`ΔBrier>0` 的亚组比例） | `mean ≥ 0.10`（即 ≥10% 亚组被重校准伤害） |
| **H3** | 48 条 vs 800 条 stress 的 bootstrap CI 宽度 | 宽度比 `≥ 2.0` |
| **H4** | 无标签门控相对无条件 isotonic | 危害率**下降 ≥50%**，且 false-gate rate `< 0.25`，且整体 ΔBrier 不恶化（跨种子 bootstrap CI 上界 < 0） |

**统计单位**：主判据一律**跨种子 paired bootstrap B=10,000**（单位 = 种子）；不用单种子记录级 CI（W2 v1.0 的教训）。

### F0 有效性门槛（先于一切结果）
1. 每种子 target calibration 与 test 的 patient id 交集为 0
2. 每种子 composite 标签阳性率 ∈ (0.05, 0.95)（保证 isotonic 非平凡）
3. `ece_binary` / isotonic / AUROC 的自检用例通过
4. 任一不满足 → 全部作废，重新冻结注册

---

## 7. 证伪检验（5400–5459，事前固定）

| ID | 操作 | 预期 |
|---|---|---|
| F1 | 打乱亚组标签 | 门控 AUC → 0.5（`|AUC−0.5| < 0.10`） |
| F2 | 主指标换成 classwise macro ECE | H1 的 gap 消失（`|gap| < 0.005`） |
| F3 | stress 增至 800 条 | CI 显著收窄（证明 48 条不足） |
| F4 | `spread=0`（群同质） | 危害率 → 0（证明危害来自漂移而非 isotonic 本身） |

任一不符 → 删除对应因果解释。

---

## 8. 失败条款（终局，不存在 v1.1）

| 触发 | 处置 |
|---|---|
| H1–H4 任一未通过 | 对应洞不成立，如实报告；不换指标、不挑子群、不补种子、不改阈值 |
| F0 失败 | 全部作废，重新冻结 |
| F1–F4 任一不符 | 删除因果解释 |
| 门控阈值在 pilot 上 AUC < 0.60 | 门控不成立，H4 直接判 False |
| 真实 T1 未复现 | 如实发表负面结果，不撤稿 |

**不再修订预注册**。W2 已有两轮条款修正、W3 已终局，本轮为最终轮。

---

## 9. 与已公开内部结果的关系

W3 的 600 个 Mamba 种子显示 **11% 部署场景 GST 有害**，且「失真强度」与增益相关仅 **+0.267**（简单门控不成立）。W4 的 H4 是**换一类无标签统计量**（源域参考直方图距离 / Ψ 曲线深度）在**论文协议**里重新检验门控；若仍失败，则按条款如实判定「门控未解决」，不得包装。

**W1–W4 全部为内部实验，未公开数据/代码/预注册/第三方复现，不得写成已发表算法或 SOTA。**

---

## 附录 E1｜实现勘误（发生在任何确认性种子执行之前）

**时间戳**：2026-11-06，**早于** pilot 5000–5049 / 主跑 5100–5399 / 证伪 5400–5459 的首次执行。
**仅使用 debug 种子 6000–6007 做冒烟测试**，该集合不属于任何确认性种子集，其结果**不进入报告**。

冒烟测试暴露三处使实验无效的实现缺陷，按 F0 有效性门槛修正：

| # | 缺陷 | 修正 |
|---|---|---|
| E1-a | 源域与目标域标签语义不一致 → 冻结 readout 迁移后 **AUROC ≈ 0.48、classwise ECE ≈ 0.42**，模型无判别力 | 源域与目标域使用**同一标签语义**（均 `lvhdominant=True`）；保留 97% 阳性集中于第 0 类，但**不等于** 97% 记录阳性 |
| E1-b | 单方向温度漂移下全局 isotonic 对所有群都有益 → 危害率恒为 0，无法检验 H2 | 改为**混合方向漂移**（两族 T>1 over-confident、两族 T<1 under-confident）+ **长尾群规模** `p=[0.45,0.30,0.18,0.07]`，对应真实 cart_id 长尾；`spread=0` 时 T≡1 保证 F4 成立 |
| E1-c | 随机初始化 SSM 特征上的冻结 ridge 无法解码稀疏多标签，判别力仍不足 | logits 改为 **真实条件概率 `logit(p_i)` + Mamba/18 维物理特征投影扰动**（SSM 前向仍参与，呼应 ECG-RAMBA 的 MiniRocket+HRV+Bi-Mamba 融合与被复现论文的 38 维物理特征）。W3 已用 600 个真 Mamba 前向种子覆盖表征层，W4 聚焦**评估协议** |

**F0 新增两条有效性检查**（事前追加）：
1. 目标域复合终点 **AUROC ≥ 0.55**（否则判别力无效，全部作废）
2. isotonic 是单调但阶梯化的变换，会产生大量 ties 并人为压低 AUROC；因此 **AUROC 用校准前连续分数报告**（理论上 isotonic 不改变排序），并在结果中注明

另修正 `f0_selftest` 中一处笔误：10-bin 下 `[0.1,0.2,0.8,0.9]` vs `[0,0,1,1]` 的 ECE 应为 **0.15**，不是 0。

**不变项**：主终点 H1–H4 及阈值、pilot/main/证伪种子集、门控统计量（源域参考直方图 L2 距离）、Youden 阈值只由 pilot 决定、四个证伪检验、失败条款、不存在 v1.1 —— 全部与 v1.0 正文逐字一致。本勘误只修**实现有效性**，不修判定规则。

**已知口径限制（不修改，按失败条款如实判定）**：H1 的 `gap = classwise macro ECE − composite ECE` 比较的是「未校准的逐类概率」与「isotonic 校准后的复合分数」，口径不完全对等。若 H1 未通过，按 §8 如实报告，**不换指标、不重构 gap**；论文「根本未报告 classwise 指标」这一事实作为讨论中的方法论观察，不作为救援性终点。

---

**签署**：作者 ______ ／ 统计合作者 ______ ／ 临床合作者 ______
