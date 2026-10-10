# E1b LOCO 验证脚本反方攻击报告

> **反方挑刺代理-E1b 交付**。本报告对正方设计的 `scripts/run_e1b_loco_validation.py`（863 行）进行最严厉的逐行攻击审查，覆盖 LOCO 跨语料库泛化验证的逻辑漏洞、隐含假设、边界失效、统计方法不当、代码 bug。
> **攻击日期**：2026-09-09
> **攻击对象**：`scripts/run_e1b_loco_validation.py`（revision 6709813f, 863 行）
> **参照方案**：`docs/Q2_UPGRADE_PROPOSAL_R5.md` §3.2 E1b（lines 173-188）
> **依赖审查**：`src/utils/calibration.py`、`src/utils/calibration_methods.py`、`scripts/eval_transfer.py`、`src/data/mapping.py`
> **攻击代理**：反方挑刺代理-E1b（GLM-5.2）
> **攻击维度**：反例构造 / 逻辑断链 / 隐含假设 / 边界失效 / 自相矛盾 / 量级错误 / 语义偏移（7 维度全覆盖）

---

## 0. 攻击审查概述

### 严重性汇总表

| 编号 | 严重性 | 攻击维度 | 位置 | 攻击摘要 | 可修补性 |
|------|--------|---------|------|---------|---------|
| F1 | **致命** | 量级错误/语义偏移 | L583-584 | NCV 的 CI 用 ΔECE 的 CI 冒充，是 fabrication 而非 approximation | 需实现 reliability bootstrap |
| F2 | **致命** | 语义偏移/自相矛盾 | L64-66 vs L570-576 | DCR docstring 说"Brier reliability"，代码算 per-sample raw Brier (p-y)²，两者不同量 | 需统一定义 |
| F3 | **致命** | 边界失效/量级错误 | L573-576 | per-sample Brier 退化为置信度阈值检查，threshold=0.05 对应 conf>0.776 或 conf<0.224，非 reliability 语义 | 需重新定义 DCR |
| F4 | **致命** | 逻辑断链/语义偏移 | R5 L178 vs script | R5 协议描述"Youden 阈值迁移"，脚本实现"概率集成+TS校准+Brier reliability"，完全不同的实验 | 需对齐协议或修改脚本 |
| F5 | **致命** | 隐含假设/反例构造 | L459+L461-462 | ensemble 混合 5类checkpoint(投影到4类) 和 4类checkpoint，训练目标不同，概率空间不可比 | 需只用同 num_classes 的 ckpt |
| S1 | **严重** | 隐含假设 | L36 | "ensemble ≥ max(members)" 对校准指标不成立（deep ensemble 经验更好但非下界保证） | 需删除该声称或加条件 |
| S2 | **严重** | 隐含假设 | L35 | "真LOCO ≥ ensemble" 上界未证明，联合训练可因分布冲突劣于 ensemble | 需降级为"经验观察" |
| S3 | **严重** | 边界失效 | L141-145+L178-186 | 3折全部退化为4类（cpsc总在），HYP类从未被LOCO验证，5类空间泛化能力未知 | 需补充5类fold或显式声明 |
| S4 | **严重** | 隐含假设/语义偏移 | L277-284 | 5→4 概率对齐丢弃 HYP 列后重归一化，对 HYP-like 样本引入系统性过自信偏差 | 需用4类重训或加偏差分析 |
| S5 | **严重** | 逻辑断链 | L461-462 | 合并 cal 拟合 TS 时，两源域类先验不同，单参数 TS 欠拟合双峰分布 | 需分源拟合或加权合并 |
| S6 | **严重** | 隐含假设 | L560-564 | benefit_inference 第三参数传 cal_correct（校准后正确性），非 test_labels；bootstrap 重采样 correctness 而非标签 | 需文档化或改用 labels |
| S7 | **严重** | 量级错误 | 全局 | n=3 折无跨折聚合/无统计检验/无异质性检验，每折独立报告，"3折CV"名不副实 | 需加跨折聚合或改称"3 case study" |
| S8 | **严重** | 隐含假设 | L404+L220-231 | 不同 pair 的 checkpoint 架构(d_model/n_layers)可能不同，ensemble 混合不同架构模型无理论依据 | 需验证架构一致 |
| S9 | **严重** | 自相矛盾 | L48 vs L141-145 | docstring 提"5类折(PTB↔Chapman)"，但实际3折全为4类，不存在5类折 | 需修正 docstring |
| S10 | **严重** | 边界失效 | L208-217 | num_classes 从 state_dict 正则推断，架构变更时静默回退到 LOCO 折的 num_classes（可能错误） | 需 checkpoint 显式存 num_classes |
| M1 | **轻微** | 代码质量 | L765-773 | CSV 前8行是注释+空行，pandas.read_csv 需 skiprows，非标准格式 | 需移除注释或用 JSON |
| M2 | **轻微** | 语义偏移 | L467+L597-600 | ood_acc 是校准前准确率（argmax 不变仅对 TS 成立），Platt/Vector 改变 argmax 后未报告 | 需加 ood_acc_cal |
| M3 | **轻微** | 代码质量 | L149 | SAFE_DELTA_ECE = -0.01 定义后从未使用，死代码 | 需删除或使用 |
| M4 | **轻微** | 代码质量 | L810-859 | 汇总只按折打印 mean±std，无跨折总均值，难以看到整体 LOCO 结论 | 需加跨折聚合 |
| M5 | **轻微** | 逻辑断链 | 全局 | E1b 单源 baseline 是 E1a L2 矩阵的子集（同 ckpt 同前向），冗余；仅 ensemble+merged cal 是新内容 | 需引用 E1a 结果 |

### 攻击数量统计

- **致命攻击 (F)**：5 个
- **严重攻击 (S)**：10 个
- **轻微攻击 (M)**：5 个
- **总计**：20 个攻击点

### 整体评估

**E1b 脚本存在 5 个致命攻击，其中 F1（NCV CI 伪造）、F4（协议-实现不匹配）、F5（ensemble 混合不可比模型）最为严重。** F1 和 F2/F3 使得两个核心输出指标（NCV、DCR）的数值不可信。F4 意味着脚本产出的结果无法回答 R5 协议提出的问题。F5 意味着 ensemble 近似的核心假设（概率空间对齐）在含 CPSC 的折中不成立。

**即使修复所有致命攻击，10 个严重攻击仍限制结论强度**：最关键的是 S3（3折全退化为4类，HYP 从未被验证）和 S7（n=3 无统计推断，"3折CV"名不副实）。这两个攻击意味着 E1b 的结论范围是"4类子空间中 3 个独立 case study 的描述性观察"，远弱于"3折跨语料库泛化验证"的声称。

**建议**：在修复 F1-F5 之前，E1b 的输出不应被用于任何论文结论。

---

## 1. 致命攻击 (Fatal)

### F1：NCV 的 CI 用 ΔECE 的 CI 冒充——fabrication 而非 approximation

**位置**：L583-584

```python
ncv_point = delta_reliability          # = rel_raw - rel_cal (Brier reliability 差)
ncv_ci = delta_ece_ci                  # CI of smooth_ece 差（不同度量！）
```

**攻击维度**：量级错误 + 语义偏移

**论证**：

NCV 的点估计是 `delta_reliability = rel_raw - rel_cal`，即 **Brier reliability**（Murphy 分解的 reliability 分量，10-bin 分箱后 `(avg_prob - avg_label)²` 的加权和）的改善量。

但 NCV 的 CI 用的是 `delta_ece_ci`，即 **Smooth ECE**（logit 空间核平滑 `|acc_i - p_i|` 的均值）改善量的 BCa CI。

这两个度量的：
1. **定义不同**：Brier reliability 是分箱平方误差；Smooth ECE 是核平滑绝对误差。前者 ∈ [0, 0.25]，后者 ∈ [0, 1]。
2. **尺度不同**：典型 Brier reliability ≈ 0.01-0.05；典型 Smooth ECE ≈ 0.02-0.08。CI 宽度完全不同。
3. **分布不同**：bootstrap 分布形状不同（平方 vs 绝对值，分箱 vs 核平滑）。

**反例**：设 Δreliability = 0.02（点估计），ΔECE 的 95% CI = [0.005, 0.035]。报告 NCV = 0.02 [0.005, 0.035]。但 Δreliability 的真实 CI 可能是 [0.001, 0.06]（更宽，因为 Brier reliability 的 bin 估计方差更大）。下游分析者用 [0.005, 0.035] 做推断，会错误地认为 NCV 显著（CI 不含 0），而真实 CI [0.001, 0.06] 也不含 0 但宽度完全不同，效应量估计被扭曲。

**代码注释的承认**（L581-582）：
```python
# 简化：NCV 点估计 = delta_reliability，CI 用 delta_ece 的 CI 近似
```
注释说"近似"，但**这不是近似，是 fabrication**。近似要求两个量在某种极限下收敛或可证明的界。Brier reliability 和 Smooth ECE 之间没有这样的关系。

**严重性**：致命——NCV 的 CI 被写入 CSV（L643-646）和 JSON，下游分析者可能用此 CI 做推断，得出错误结论。

**修复建议**：实现 Brier reliability 的 cluster bootstrap（在每次重采样上重算 `brier_parts`），或明确在输出中标注 `ncv_ci` 为"不可用"而非填入错误值。

---

### F2：DCR 定义在 docstring 与代码间自相矛盾

**位置**：L64-66（docstring）vs L570-576（实现）

**docstring**（L64-66）：
```
DCR (Deployment Calibration Rate) = 在目标域上，校准后 Brier reliability
    < SAFE_RELIABILITY_THRESHOLD 的样本比例。
```

**实现**（L573-576）：
```python
per_sample_brier_cal = (cal_mp - cal_correct) ** 2    # per-sample raw Brier
dcr_cal = float(np.mean(per_sample_brier_cal < SAFE_RELIABILITY_THRESHOLD))
```

**攻击维度**：语义偏移 + 自相矛盾

**论证**：

1. **"Brier reliability"** 是 Murphy 分解的 reliability 分量（`brier_parts` 返回的第二个值），是**分箱后**的群体级量：`Σ_bin (n_bin/n) * (avg_prob_bin - avg_label_bin)²`。它不是 per-sample 量——单个样本没有"reliability"。

2. 代码计算的是 **per-sample raw Brier**：`(max_prob - correct)²`，这是单样本的 Brier score，不是 reliability 分量。Brier score = Reliability - Resolution + Uncertainty，per-sample raw Brier 混合了这三个分量。

3. **阈值 0.05 的语义被偷换**：docstring 说"Brier reliability < 0.05"（reliability 分量 < 0.05，对应"校准良好"），代码算"per-sample Brier < 0.05"（单样本 Brier score < 0.05，对应"单样本预测误差小"）。这两个判据完全不同。

**反例**：一个完美校准但分辨率低的模型，reliability = 0（所有 bin 的 avg_prob = avg_label），但 per-sample Brier = (p - y)² 仍可能很大（如 p=0.5, y=1 时 Brier=0.25）。按 docstring 定义 DCR=100%（reliability=0 < 0.05），按代码定义 DCR 可能很低（很多样本 Brier > 0.05）。

**严重性**：致命——DCR 的数值与定义不符，论文中报告的 DCR 无法被复现者理解。

**修复建议**：统一 DCR 定义。若用 per-sample Brier，需改 docstring 为"per-sample Brier score < threshold"并重新标定阈值；若用 reliability，需改为 fold 级判据 `1{rel_cal < threshold}`（但失去 per-sample 语义）。

---

### F3：per-sample Brier 退化为置信度阈值检查

**位置**：L573-576

**攻击维度**：边界失效 + 量级错误

**论证**：

对单样本，`cal_mp = max(prob)` ∈ [0,1]，`cal_correct` ∈ {0,1}：

- **正确预测**（cal_correct=1）：`brier = (cal_mp - 1)² = (1 - cal_mp)²`
  - `brier < 0.05` ⟺ `1 - cal_mp < 0.224` ⟺ `cal_mp > 0.776`
  - 语义：**正确且置信度 > 77.6%**

- **错误预测**（cal_correct=0）：`brier = cal_mp²`
  - `brier < 0.05` ⟺ `cal_mp < 0.224`
  - 语义：**错误且置信度 < 22.4%**

因此 DCR = P(正确 ∧ conf>0.776) + P(错误 ∧ conf<0.224)。

这实质上是一个**双阈值置信度门控**，不是 Brier reliability 的任何变体。它与 `step3_deployment.py` 的 SAFE_RELIABILITY_THRESHOLD=0.05 的原始标定语义（fold 级 reliability）完全脱节。

**量级问题**：threshold=0.05 对应 conf 边界 0.224/0.776。若 threshold=0.01（更严格），对应 conf 边界 0.1/0.9。DCR 对 threshold 极敏感，但脚本不报告敏感性。

**反例**：一个模型对所有样本输出 conf=0.5（无信息）。正确率=base_rate。per-sample Brier 恒为 0.25（正确）或 0.25（错误），均 > 0.05。DCR=0%。但该模型的 fold 级 reliability 可能很低（avg_prob=0.5 ≈ avg_label=base_rate），按 docstring 定义 DCR 应接近 100%。

**严重性**：致命——DCR 的实际语义与 docstring 完全不同，且对 threshold 的敏感性未分析。

---

### F4：R5 协议描述"Youden 阈值迁移"，脚本实现"概率集成+TS校准"——实验不匹配

**位置**：R5 L178 vs script L1-90

**R5 协议**（L178）：
```
LOCO 跨语料庫泛化验证：leave-one-corpus-out（LOCO）——
用 2 个语料库的 Youden 阈值在第 3 个上测试（3 折）
```

**脚本实现**：
- 模型层：softmax 概率平均（L459）
- 校准层：合并 cal 拟合 TS/Platt/Vector（L461-462, L539）
- 评估层：Brier reliability、Smooth ECE、DCR、NCV（L545-584）

**攻击维度**：逻辑断链 + 语义偏移

**论证**：

R5 描述的实验是 **Youden 阈值迁移**：在 2 个源域上优化 Youden J 阈值，迁移到第 3 个目标域测试。这是**判别阈值迁移**实验，评估指标应是 Youden J、敏感度、特异度。

脚本实现的是 **概率集成 + 校准迁移**：平均 2 个源域模型的 softmax 概率，合并 cal 拟合校准参数，在目标域评估校准指标。这是**校准迁移**实验，评估指标是 Brier reliability、ECE。

**这两个实验回答完全不同的问题**：
- R5 的问题："源域最优判别阈值在目标域是否仍最优？"
- 脚本的问题："源域校准参数在目标域是否仍有效？"

脚本产出的 `results/deployment_loco_validation.csv` **无法回答 R5 提出的问题**。R5 的"诚实披露条款"（L181-182）提到"Youden J ≈ 0"作为失败标准，但脚本根本不计算 Youden J。

**严重性**：致命——这是 confirmatory 协议（R5 预注册）与实现的不匹配。即使 E1b 标为 exploratory，其产出文件名 `deployment_loco_validation.csv` 被 R5 引用（L179），意味着论文会用此文件支持 R5 的 LOCO 声明，但文件内容与声明不匹配。

**修复建议**：要么修改 R5 协议描述为"校准迁移 LOCO"（与脚本对齐），要么修改脚本实现 Youden 阈值迁移（与 R5 对齐）。两者必须一致。

---

### F5：ensemble 混合 5类checkpoint(投影到4类) 和 4类checkpoint——概率空间不可比

**位置**：L459（ensemble）+ L277-284（5→4 对齐）+ L404（checkpoint 加载）

**攻击维度**：隐含假设 + 反例构造

**论证**：

在 LOCO fold holdout=ptbxl, sources=[chapman, cpsc] 中：

| 源域 | checkpoint | 训练时 num_classes | 训练时 subspace | ckpt_nc |
|------|-----------|-------------------|----------------|---------|
| chapman | M_{chapman→ptbxl} | 5（min(5,5)=5） | None（5类全空间） | 5 |
| cpsc | M_{cpsc→ptbxl} | 4（min(4,5)=4） | SUBSPACE_CPSC | 4 |

ensemble 计算（L459）：
```python
tgt_probs_ensemble = np.mean(tgt_probs_list, axis=0)
# tgt_probs_list[0]: chapman 模型 5类输出 → _align_probs_to_subspace 投影到4类
# tgt_probs_list[1]: cpsc 模型 4类输出（原生4类）
```

**核心问题**：

1. **chapman 模型**在 5 类空间训练，学习到 HYP 作为独立类别。其 4 类投影（丢弃 HYP 列后重归一化）**不是**一个原生 4 类模型的输出——它从未被训练为"在 4 类子空间中分类"。

2. **cpsc 模型**在 4 类空间训练，从未见过 HYP 类。其输出是原生 4 类概率。

3. **ensemble 平均**这两个概率向量，相当于平均一个"被迫投影的 5 类模型"和一个"原生 4 类模型"。这没有理论依据——Deep Ensemble (Lakshminarayanan 2017) 要求成员在**同一训练目标**下训练，这里两个成员的训练目标不同（5 类 vs 4 类）。

**反例**：设目标域样本 x 真实标签为 MI。
- chapman 5类模型输出：[NORM=0.1, MI=0.3, STTC=0.1, CD=0.1, HYP=0.4]（误判 HYP）
- 投影到4类：[NORM=0.1/0.6, MI=0.3/0.6, STTC=0.1/0.6, CD=0.1/0.6] = [0.17, 0.50, 0.17, 0.17]
- cpsc 4类模型输出：[NORM=0.2, CD=0.2, STTC=0.2, MI=0.4]
- ensemble = mean = [0.185, 0.35, 0.185, 0.285]（MI 仍是 argmax）

但 chapman 模型对 HYP-like 样本的投影会系统性地**分散概率到非 HYP 类**，引入虚假的不确定性。这不是"近似联合训练"，而是"混合不同训练目标的模型"。

**严重性**：致命——ensemble 近似的核心假设 A1（L42-43）在含 CPSC 的折中不成立。3 折中 2 折（holdout=ptbxl, holdout=chapman）涉及 5类+4类混合，仅 fold 3（holdout=cpsc, sources=[ptbxl, chapman]）的 5类+5类混合在投影后也有同样问题。

**修复建议**：要么只用同 num_classes 的 checkpoint 做 ensemble（放弃含 CPSC 的折），要么为每个 LOCO 折重新训练 4 类模型（真 LOCO）。

---

## 2. 严重攻击 (Serious)

### S1：ensemble ≥ max(members) 对校准指标不成立

**位置**：L36

```
下界：ensemble ≥ max(M_S1→T, M_S2→T) 单源 best（集成不劣于成员）
```

**攻击维度**：隐含假设 + 反例构造

**论证**：

"集成不劣于成员"对**预测准确率**在特定条件下成立（如成员独立且无偏），但对**校准指标**（Brier reliability、ECE）**不成立**。

**反例**：两个模型在目标域上的校准：
- 模型 A：完美校准（reliability=0），准确率 80%
- 模型 B：完美校准（reliability=0），准确率 80%
- ensemble = mean(A, B)：可能**过自信**（两个模型对同一样本都输出高置信度，平均后仍高，但若同时错误则 reliability 恶化）

具体地，设样本 x 真实标签 y=1：
- A 输出 p=0.8，B 输出 p=0.8 → ensemble=0.8，reliability 贡献 (0.8-1)²=0.04
- 若 A、B 独立错误：A 输出 p=0.8(y=0), B 输出 p=0.8(y=0) → ensemble=0.8，reliability 贡献 (0.8-0)²=0.64

Deep Ensemble 的校准优势是**经验观察**（Lakshminarayanan 2017 报告 NLL 更低），不是保证的下界。Rahaman et al. (2021) "Uncertainty Quantification in Deep Ensembles" 显示 ensemble 可以恶化校准，尤其当成员相关时。

**严重性**：严重——脚本声称的"保守性"下界不成立，意味着 ensemble 可能比单源更差，"若近似已显示改善，真 LOCO 只会更好"的推理链条断裂。

---

### S2：真 LOCO ≥ ensemble 上界未证明

**位置**：L35

```
上界：真 LOCO 用全部 S1∪S2 数据训练，模型容量充分利用 → 性能 ≥ ensemble
```

**攻击维度**：隐含假设

**论证**：

"在 S1∪S2 上训练的模型 ≥ ensemble(S1, S2)" 对**任意**性能指标都不成立。

**反例**：S1 和 S2 有强分布偏移（如 PTB-XL 德国设备和 CPSC 中国设备）。在 S1∪S2 上训练的单模型需要同时拟合两个不同分布，可能因**负迁移**而性能下降。而 ensemble 的两个成员各自专精一个分布，平均后可能在目标域更鲁棒。

这在**迁移学习**文献中是已知现象：Multi-source training 的效果取决于源域间的相关性，不相关源域的联合训练可能劣于选择性集成（见 Mansour et al. 2009 "Domain Adaptation with Multiple Sources"）。

**严重性**：严重——上界和下界都不成立（S1+S2），脚本 L34-37 的"保守性"论证完全失效，"近似方案的 OOD 性能上限是真 LOCO，下限是单源 best"是错误的。

---

### S3：3折全部退化为4类——HYP 类从未被 LOCO 验证

**位置**：L141-145（LOCO_FOLDS）+ L178-186（num_classes 推断）

**攻击维度**：边界失效

**论证**：

3 个 LOCO 折的 num_classes 推断：

| 折 | holdout | sources | num_classes = min(所有) | subspace |
|----|---------|---------|------------------------|----------|
| 1 | ptbxl(5) | chapman(5), cpsc(4) | min(5,5,4)=**4** | SUBSPACE_CPSC |
| 2 | chapman(5) | ptbxl(5), cpsc(4) | min(5,5,4)=**4** | SUBSPACE_CPSC |
| 3 | cpsc(4) | ptbxl(5), chapman(5) | min(5,5,4)=**4** | SUBSPACE_CPSC |

**所有 3 折都是 4 类**，因为 cpsc（4类）总是出现在 sources 或 holdout 中。SUBSPACE_CPSC = (NORM, CD, STTC, MI)，**HYP 类在所有折中被丢弃**。

这意味着：
1. LOCO 验证**只覆盖 4 类子空间**，5 类全空间的泛化能力**从未被验证**。
2. HYP 类的跨语料库迁移效果**完全未知**——而 HYP（肥厚型心肌病）在 PTB-XL 和 Chapman 中是重要类别。
3. R5 L178 声称"3个语料库的 LOCO 验证"，但实际只验证了 3 个语料库的 **4 类子空间**。

**严重性**：严重——论文若报告"LOCO 跨语料库泛化验证"，读者会理解为全空间验证，但实际只是 4 类子空间。HYP 类的迁移性能是空白。

**修复建议**：补充一个 5 类 fold（holdout=ptbxl, sources=[chapman]——但这是单源不是 LOCO），或显式声明"LOCO 仅在 4 类子空间 (NORM,CD,STTC,MI) 上验证，HYP 类的跨语料库泛化未评估"。

---

### S4：5→4 概率对齐引入系统性过自信偏差

**位置**：L277-284

```python
keep_idx = [SUPERCLASSES.index(c) for c in subspace]  # [0,3,2,1] for SUBSPACE_CPSC
aligned = probs[:, keep_idx]                            # 丢弃 HYP 列
aligned = aligned / aligned.sum(axis=1, keepdims=True) # 重归一化
```

**攻击维度**：隐含假设 + 语义偏移

**论证**：

5 类模型输出 `[p_NORM, p_MI, p_STTC, p_CD, p_HYP]`，丢弃 HYP 后重归一化：
`[p_NORM, p_MI, p_STTC, p_CD] / (1 - p_HYP)`

**偏差来源**：

1. **对 HYP-like 样本**（p_HYP 高）：重归一化后剩余类概率被大幅放大，模型被迫在 4 类中做出高置信度预测，但这些预测是**虚假的**——模型本意是"HYP"，不是"剩余类中的某一个"。

2. **对 NORM-like 样本**（p_HYP 低）：重归一化几乎无影响，行为正常。

3. **系统性**：偏差只出现在 HYP 高概率样本上，这些样本在 PTB-XL/Chapman 中占一定比例（HYP 是 5 类之一）。偏差方向是**过自信**（概率被放大），会**恶化校准**（reliability 增加）。

**反例**：5 类模型对 HYP 样本输出 `[0.1, 0.1, 0.1, 0.1, 0.6]`。投影到 4 类：`[0.25, 0.25, 0.25, 0.25]`（均匀分布）。这看起来"不确定"，但实际是模型在说"是 HYP"——投影后的均匀分布**不是**真正的 4 类不确定性，而是"我不知道在这 4 类中选哪个"的伪不确定性。这会扭曲 Brier reliability 和 ECE 的计算。

**严重性**：严重——5→4 投影引入的偏差会系统性影响含 5 类 checkpoint 的折（3 折中的 2 折），使校准指标的改善量被低估或高估（取决于 HYP 样本比例）。

---

### S5：合并 cal 拟合 TS 时两源域类先验不同——单参数 TS 欠拟合

**位置**：L461-462

```python
merged_cal_probs = np.concatenate(src_cal_probs_list, axis=0)
merged_cal_labels = np.concatenate(src_cal_labels_list, axis=0)
```

**攻击维度**：隐含假设

**论证**：

在 fold holdout=ptbxl, sources=[chapman, cpsc] 中：
- chapman cal：美国数据，类先验 π_chapman = [p_NORM, p_CD, p_STTC, p_MI]（美国人群分布）
- cpsc cal：中国数据，类先验 π_cpsc = [p_NORM, p_CD, p_STTC, p_MI]（中国人群分布）

合并后拟合单一 TS 参数 T_unified。但：
1. 两源的**模型预测分布**不同（chapman 模型和 cpsc 模型在不同数据上训练）
2. 两源的**真实标签分布**不同（π_chapman ≠ π_cpsc）
3. 合并后的 cal 集是**双峰分布**（两个源域的混合）

单参数 TS 无法拟合双峰分布——它只能全局缩放温度。若 chapman 模型过自信（需 T>1）而 cpsc 模型欠自信（需 T<1），合并拟合的 T_unified 是两者的折中，**对两个源域都不是最优**。

**与真 LOCO 的差异**：真 LOCO 在 S1∪S2 上训练一个模型，该模型的 cal split 上的预测分布是**单峰**的（同一模型在混合数据上的输出）。合并两个独立模型的 cal 预测是**双峰**的。TS 在单峰 vs 双峰上的拟合效果完全不同。

**严重性**：严重——脚本 docstring A2（L44-46）承认此风险并建议"也报告 vector/platt 作敏感性"，但 vector/platt 同样是全局方法，无法处理双峰。需要**分源拟合**或**加权合并**（按源域先验加权）。

---

### S6：benefit_inference 传 cal_correct 而非 test_labels——bootstrap 语义

**位置**：L560-564

```python
ben = benefit_inference(
    raw_mp, cal_mp, cal_correct,      # 第三参数是 cal_correct，不是 test_labels
    metric=metric_fn, ...
)
```

**攻击维度**：隐含假设

**论证**：

`benefit_inference` 的签名（calibration.py L417-427）第三参数是 `labels`。这里传的是 `cal_correct = (cal_probs.argmax(1) == test_labels).astype(float)`——**校准后预测的正确性**，不是真实标签。

`smooth_ece(probs, labels)` 的语义是：在 `probs`（置信度）上计算校准误差，`labels` 是"该置信度是否对应正确预测"（binary correctness）。这是 **top-label calibration** 的标准做法（与 eval_transfer.py L263 一致）。

但 bootstrap 重采样时，重采样的是 `(raw_mp, cal_mp, cal_correct)` 三元组。这意味着：
- 重采样后 `raw_mp[idx]` 和 `cal_mp[idx]` 是同一批样本的 raw/cal 置信度
- `cal_correct[idx]` 是同一批样本的**校准后正确性**

**问题**：`cal_correct` 依赖于 `cal_probs`（校准后预测），而 `cal_probs` 依赖于校准参数（TS 的 T）。bootstrap 重采样 `cal_correct` 时，T 是固定的（点估计），不随重采样变化。这忽略了**T 的拟合不确定性**——T 在 cal split 上拟合，其不确定性应传入 ΔECE 的 CI。

`two_layer_benefit_inference`（calibration.py L780-860）正是为解决此问题而设计（两层 bootstrap：val 重采样→重拟合 T→test 重采样→ΔECE），但 E1b 脚本**未使用** `two_layer_benefit_inference`，只用了单层 `benefit_inference`。

**严重性**：严重——CI 低估了 T 拟合不确定性，CI 偏窄。eval_transfer.py 有同样问题（协议注记 L799-800 "嵌套B=10000×重拟合在O(n²) metric下不可行，此为诚实近似并已登记"），但 E1b 脚本未引用此注记。

---

### S7：n=3 折无跨折聚合/无统计检验——"3折CV"名不副实

**位置**：L810-859（汇总）+ 全局

**攻击维度**：量级错误

**论证**：

脚本产出 3 折 × 5 seeds × 3 methods × 3 scenarios × 13 metrics = 1755 行记录。汇总（L810-859）按 **(holdout, method, scenario)** 聚合，即每折每方法每场景报告 5 seeds 的 mean±std。

**缺失的统计推断**：
1. **无跨折聚合**：没有报告 3 折的总均值、总 std、或随机效应模型。
2. **无跨折统计检验**：没有检验 3 折的 LOCO 改善是否一致（异质性检验，如 Cochran's Q）。
3. **无 LOCO vs 单源的配对检验**：每折每 seed 有 LOCO 和单源结果，但未做配对 t 检验或 Wilcoxon 检验。
4. **无 FDR 校正**：3 折 × 3 方法 × 3 场景 = 27 个比较，无多重比较校正。

R5 L182 诚实披露"n=3 无法达到 p<0.05"，但脚本的结构暗示"3折CV"——读者可能误解为有统计推断的交叉验证。实际上这只是 **3 个独立的 case study**，每个 case study 内部有 5 seeds 的描述统计。

**严重性**：严重——"3折 Leave-One-Corpus-Out"的命名暗示交叉验证，但无 CV 的统计推断。应改称"3 个独立 case study"或补充跨折聚合。

---

### S8：不同 pair 的 checkpoint 架构可能不同——ensemble 无理论依据

**位置**：L404（checkpoint 路径）+ L220-231（架构推断）

**攻击维度**：隐含假设

**论证**：

`_load_model_from_ckpt` 从 state_dict 推断 d_model 和 n_layers（L220-231）。不同 pair 的 checkpoint 可能有不同架构：
- M_{chapman→ptbxl}：d_model=64, n_layers=2（假设）
- M_{cpsc→ptbxl}：d_model=64, n_layers=2（假设）

脚本假设架构一致（L49: "假设 6 个 pair 的 inceptiontime checkpoint 都存在"），但**不验证**。若某 pair 用了不同 d_model（如 d_model=128），ensemble 会平均不同容量模型的 softmax 输出。

**理论问题**：Deep Ensemble 要求成员是**同架构**独立训练的模型。不同架构模型的 softmax 平均没有 PAC-Bayes 保证（L30 引用的 Reuning 2020 要求同架构）。

**严重性**：严重——若架构不一致，ensemble 的理论依据失效。脚本应在加载后验证所有成员的 d_model/n_layers 一致。

---

### S9：docstring 提"5类折(PTB↔Chapman)"但实际不存在——自相矛盾

**位置**：L48 vs L141-145

**docstring**（L48）：
```
5类折 (PTB↔Chapman) 与 4类折 (含CPSC) 不可直接比较。
```

**实际**：如 S3 所述，3 折全部是 4 类（因 cpsc 总在场）。不存在 5 类折。

**攻击维度**：自相矛盾

**论证**：

docstring 暗示有"5类折"和"4类折"两种类型，但实际上只有 4 类折。这会误导读者认为部分折在 5 类全空间验证、部分在 4 类子空间验证，而实际全部在 4 类子空间。

**严重性**：严重——docstring 与实际行为矛盾，影响对实验范围的理解。

---

### S10：num_classes 从 state_dict 正则推断——架构变更时静默回退

**位置**：L208-217

```python
classifier_weights = []
for k in sd:
    m = re.match(r"classifier\.(\d+)\.weight", k)
    if m and sd[k].ndim == 2:
        classifier_weights.append((int(m.group(1)), int(sd[k].shape[0])))
if classifier_weights:
    ckpt_nc = classifier_weights[-1][1]
else:
    ckpt_nc = num_classes  # 回退到 LOCO 折的 num_classes
```

**攻击维度**：边界失效

**论证**：

1. **正则 `r"classifier\.(\d+)\.weight"`** 假设分类头命名为 `classifier.{N}.weight`。若模型架构变更（如改名为 `head.weight` 或 `fc.weight`），正则不匹配，静默回退到 `num_classes`（LOCO 折的 4 类）。

2. **回退是错误的**：若 checkpoint 实际是 5 类模型，回退到 4 类会导致 `load_state_dict` 失败（维度不匹配），但错误信息是"num_classes 不匹配"而非"正则推断失败"，误导调试。

3. **无警告**：回退时不打印警告，用户不知道推断失败。

**反例**：inceptiontime 模型的分类头若命名为 `model.head.weight` 而非 `classifier.0.weight`，正则不匹配，所有 checkpoint 静默回退到 4 类。若 checkpoint 实际是 5 类，`load_state_dict` 报错"shape mismatch"，用户困惑。

**严重性**：严重——静默回退可能导致所有 checkpoint 加载失败或（更糟）加载错误架构的模型。

---

## 3. 轻微攻击 (Minor)

### M1：CSV 前8行是注释——非标准格式

**位置**：L765-773

```python
w.writerow(["# E1b: LOCO 跨语料库泛化验证"])
w.writerow(["# 设计: ..."])
# ... 7 行注释 + 1 行空行
w.writerow(columns)  # 列名在第 9 行
```

**攻击**：`pandas.read_csv()` 默认会尝试解析注释行为数据行，报错或产生垃圾行。需 `skiprows=8` 或 `comment='#'`。JSON 输出（L791-807）是替代方案，但 CSV 是主要输出（R5 L179 引用 `.csv`）。

**修复**：移除注释行，或改用 `#` 前缀的 metadata 字段在 JSON 中。

---

### M2：ood_acc 是校准前准确率——Platt/Vector 改变 argmax

**位置**：L467 + L597-600

```python
ood_acc_ensemble = float((tgt_probs_ensemble.argmax(1) == tgt_labels).mean())
# ... 后续未计算校准后 acc
```

**攻击**：TS 不改变 argmax（温度缩放保序），但 Platt（per-class sigmoid）和 Vector scaling（per-class scale+bias）**会改变 argmax**。脚本只报告校准前 ood_acc，未报告校准后 ood_acc。对于 Platt/Vector，校准可能改善或恶化准确率，这是有信息量的指标。

**修复**：增加 `ood_acc_cal = (cal_probs.argmax(1) == test_labels).mean()` 并输出。

---

### M3：SAFE_DELTA_ECE 定义后从未使用——死代码

**位置**：L149

```python
SAFE_DELTA_ECE = -0.01  # NCV: ΔECE < -0.01 → 校准有益 > 1%
```

**攻击**：全文搜索 `SAFE_DELTA_ECE` 仅出现在定义处，从未在逻辑中使用。DCR 用了 `SAFE_RELIABILITY_THRESHOLD`（L575-576），但 NCV 的阈值 `SAFE_DELTA_ECE` 未被用于任何判据。

**修复**：删除，或实现 NCV 的二值判据 `ncv_beneficial = (ncv_point > abs(SAFE_DELTA_ECE))`。

---

### M4：汇总无跨折总均值——难以看到整体 LOCO 结论

**位置**：L810-859

**攻击**：`_print_summary` 按 `(holdout, method, scenario)` 聚合，每折独立打印。没有"3折平均 LOCO 改善 = X±Y"的总汇总。读者需手动从 3 行中算平均。

**修复**：增加跨折聚合行，如 `ALL holdouts: loco_ensemble delta_rel = mean±std (n=15)`。

---

### M5：E1b 单源 baseline 与 E1a L2 矩阵冗余

**位置**：L495-511（单源 baseline）

**攻击**：E1b 的 `single_source_S1` / `single_source_S2` 场景使用与 E1a 相同的 checkpoint（M_{S_i→holdout}）、相同的前向（源 cal 拟合 → 目标 test 评估）、相同的指标（Brier reliability、ECE）。这是 E1a L2 矩阵的子集（6 对中的 3 对，3 方法中的子集）。

E1b 的**唯一新内容**是 `loco_ensemble` 场景（ensemble + merged cal fit）。单源 baseline 可直接引用 E1a 结果，无需重算。

**修复**：从 E1a 的 `results/l2_shift_full_390cells.csv` 读取单源 baseline，只计算 ensemble 场景。

---

## 4. 攻击维度覆盖性声明

| 攻击维度 | 覆盖情况 | 对应攻击 |
|---------|---------|---------|
| 反例构造 | ✓ | F1(NCV CI 反例), F3(无信息模型 DCR), F5(HYP-like 样本投影), S1(ensemble 恶化校准反例), S2(负迁移反例), S4(HYP 投影偏差反例) |
| 逻辑断链 | ✓ | F4(协议→实现断链), F5(训练目标→ensemble 断链), S5(合并 cal→TS 断链), M5(E1a→E1b 冗余断链) |
| 隐含假设 | ✓ | F5(同训练目标假设), S1(ensemble 下界假设), S2(真LOCO 上界假设), S5(单峰 cal 假设), S6(T 固定假设), S8(同架构假设) |
| 边界失效 | ✓ | F3(per-sample Brier 退化), S3(全4类退化), S4(HYP 丢弃), S10(正则回退) |
| 自相矛盾 | ✓ | F2(DCR docstring vs 代码), S9(5类折 vs 全4类) |
| 量级错误 | ✓ | F1(Brier vs ECE 尺度), F3(threshold→conf 边界), S7(n=3 无统计推断) |
| 语义偏移 | ✓ | F1(reliability→ECE CI), F2(reliability→raw Brier), F4(Youden→校准), F5(5类→4类投影), S4(HYP→均匀分布), M2(校准前 acc) |

**全部 7 个攻击维度均已尝试，每个维度至少找到 2 个有效攻击点。**

---

## 5. 与 E1a 的关系审查

### 冗余分析

E1a（L2 移位矩阵）覆盖 6 个方向对 × 8 方法 × 5 seeds = 240 格。E1b 的单源 baseline 覆盖 3 折 × 2 源 × 3 方法 × 5 seeds = 90 格，是 E1a 的子集（相同 checkpoint、相同前向、相同指标，方法子集）。

**冗余程度**：E1b 的 90 格单源 baseline 中，约 90 格与 E1a 重叠（若 E1a 已跑相同 checkpoint）。仅 `loco_ensemble` 场景（3 折 × 3 方法 × 5 seeds = 45 格）是 E1b 独有。

### 矛盾分析

E1a 和 E1b 在单源 baseline 上应**数值一致**（相同 checkpoint、相同前向）。但：
1. E1a 用 `eval_transfer.py` 的 `run_pair`，E1b 用 `run_loco_fold` 的 `_eval_scenario`。
2. E1a 的 `num_classes = min(source, target)`，E1b 的 `num_classes = min(所有源, 目标)`。在 LOCO 折中，E1b 的 num_classes 可能更小（因多了一个源的约束）。
3. **潜在矛盾**：E1a 的 chapman→ptbxl 是 5 类（min(5,5)=5），E1b 的 holdout=ptbxl 折中 chapman 单源 baseline 是 4 类（min(5,4,5)=4）。**同一 checkpoint 在 E1a 和 E1b 中用不同 num_classes 评估**，结果不可比。

**严重性**：严重（升级为 S11）——E1a 和 E1b 的单源 baseline 数值不一致，论文中若同时引用两者，读者会困惑。

---

## 6. 整体裁决

### 致命问题的影响

5 个致命攻击中：
- **F1（NCV CI 伪造）**：NCV 的 CI 不可信，任何基于 NCV CI 的推断无效。
- **F2+F3（DCR 定义矛盾+退化）**：DCR 的数值与定义不符，且退化为置信度阈值检查，与部署安全语义脱节。
- **F4（协议-实现不匹配）**：脚本不回答 R5 提出的问题（Youden 阈值迁移），产出无法支持 R5 的 LOCO 声明。
- **F5（ensemble 混合不可比模型）**：ensemble 近似的核心假设在含 CPSC 的折中不成立，3 折中 2 折受影响。

### 严重问题的限制

10 个严重攻击中，最限制结论强度的是：
- **S3（全4类退化）**：LOCO 只验证 4 类子空间，HYP 类泛化未知。
- **S7（n=3 无统计推断）**：3 个独立 case study，非交叉验证。
- **S1+S2（上下界不成立）**：ensemble 近似的保守性论证失效。

### 修复优先级

1. **P0（必须修复才能产出可信结果）**：F1, F2, F3, F4, F5
2. **P1（修复后才能用于论文）**：S1, S2, S3, S4, S5, S7, S9, S11（E1a-E1b 矛盾）
3. **P2（建议修复）**：S6, S8, S10, M1-M5

### 最终结论

**E1b 脚本在当前状态下不应被用于任何论文结论。** 5 个致命攻击使得两个核心指标（NCV、DCR）的数值不可信，且实验不匹配 R5 协议。即使修复致命攻击，10 个严重攻击将结论限制为"4类子空间中 3 个独立 case study 的描述性观察"，远弱于"3折跨语料库泛化验证"的声称。

**与 E1a 攻击的比较**：E1a 的攻击主要在统计方法（BCa、cluster bootstrap）层面；E1b 的攻击更根本——在实验设计层面（ensemble 近似不成立、协议不匹配、指标定义错误）。E1b 的问题比 E1a 更严重，因为 E1b 是 exploratory 实验，设计自由度更高，但也因此缺乏 confirmatory 实验的预注册约束，更容易出现设计缺陷。

---

## 附录：逐行审查日志（关键行）

| 行号 | 审查结论 |
|------|---------|
| L64-66 | DCR docstring 定义（与 L570-576 矛盾，见 F2） |
| L141-145 | LOCO_FOLDS 定义（3折全4类，见 S3） |
| L149 | SAFE_DELTA_ECE 死代码（见 M3） |
| L178-186 | R5 协议描述 Youden 阈值（与脚本实现不匹配，见 F4） |
| L208-217 | num_classes 正则推断（静默回退风险，见 S10） |
| L220-231 | d_model/n_layers 推断（不验证一致性，见 S8） |
| L277-284 | 5→4 概率对齐（HYP 丢弃偏差，见 S4） |
| L404 | checkpoint 路径（5类+4类混合，见 F5） |
| L459 | ensemble 概率平均（混合不可比模型，见 F5） |
| L461-462 | 合并 cal 拟合 TS（双峰分布次拟合，见 S5） |
| L467 | ood_acc 校准前（Platt/Vector 改变 argmax，见 M2） |
| L560-564 | benefit_inference 传 cal_correct（T 固定假设，见 S6） |
| L570-576 | DCR per-sample Brier 实现（与 docstring 矛盾，见 F2/F3） |
| L583-584 | NCV CI 用 ΔECE CI（fabrication，见 F1） |
| L765-773 | CSV 注释行（非标准格式，见 M1） |
| L810-859 | 汇总无跨折聚合（见 S7/M4） |

**审查完成。20 个攻击点已全部记录，7 个攻击维度已全部覆盖。**
