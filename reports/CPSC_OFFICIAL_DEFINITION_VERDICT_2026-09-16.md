# CPSC 官方 superclass 定义核对 —— 最终裁决

**日期**：2026-09-16
**触发**：用户指令「去核对 CPSC 官方 superclass 定义」
**结论等级**：**P0（含 2 项新发现，比原编码顺序问题更严重）**

---

## 0. TL;DR

| # | 结论 |
|---|---|
| 1 | **CPSC 官方没有 superclass 定义。** CPSC2018 官方 = 9 个疾病类；CPSC2019 官方 = QRS/心率**检测**（无疾病分类标签）。superclass（NORM/MI/STTC/CD/HYP）是 **PTB-XL** 的体系。 |
| 2 | 规范顺序 = PTB-XL/文献惯例 `NORM, MI, STTC, CD, HYP`（= 仓库 `SUPERCLASSES`）。故 4 类子空间应为 **`("NORM","MI","STTC","CD")` —— 新值在规范上正确**，旧值 `("NORM","CD","STTC","MI")` 非规范。 |
| 3 | **但 09-08 的模型与评估是用旧编码自洽训练/运行的。** 09-09 只改代码不重训模型 → 09-10 重生成的 npz 标签与模型语义失配，**40 个含 CPSC 的 cell 全部 MI/CD 错位**，准确率被人为压低 **9.6pp**。 |
| 4 | **论文的 +0.0159 是正确的**，不需要改数字。60/60 main cell 逐位复现（max\|Δ\|=1.11e-16）。 |
| 5 | **三口径之谜彻底闭合**：`delta_obs` (+0.1068) **不是另一个估计量**，而是同一批 probs 配错标签编码的产物 —— 纯伪信号。 |
| 6 | **新发现 P0-A**：论文称语料为 "CPSC2018+2019"，**实际是 CPSC2018（公开）+ CPSC-Extra（未使用）**，语料里**根本没有 CPSC2019**。 |
| 7 | **新发现 P0-B**：论文 4 类子空间里的 **MI 类（CPSC 测试集 14.7%）完全来自 CPSC-Extra 的 SNOMED 标注**（72 码），**不出自 CPSC2018 官方 9 类**（官方 9 类里 MI=0）。 |
| 8 | **新发现 P1**：33 条 CPSC2018 记录（`A6845`–`A6877`）在解压时**静默丢失**（zip 6877 → 提取 6844）。 |

---

## 1. 官方定义核对（外部证据）

### 1.1 CPSC2018 官方 = 9 类，无 superclass

官方页面 `2018.icbeb.org/Challenge.html` 原文（经两处独立转载核对）：

> The 12-lead ECGs used in CPSC 2018 include **one normal type and eight abnormal types**:
> Normal, AF（心房颤动）, I-AVB（一度房室阻滞）, LBBB（左束支阻滞）,
> RBBB（右束支阻滞）, PAC（房性早搏）, PVC（室性早搏）, STD（ST 段压低）, STE（ST 段抬高）

**官方分类体系中没有 MI / STTC / CD / HYP，也没有任何 superclass 分组。**

### 1.2 CPSC2019 官方 = QRS / 心率检测，非分类

- 官方奖项页（`icbeb2020.pastconf.com/CPSC2019Awards`）：按 **QRSacc / HRacc** 评分。
- 多个参赛仓库标题即为 "CPSC-2019 **QRS Detection and HR Estimation**"。

→ **CPSC2019 数据集没有疾病诊断标签**（无 `#Dx`）。

### 1.3 superclass 体系的真实出处 = PTB-XL

NORM / MI / STTC / CD / HYP 来自 PTB-XL 的 `scp_statements.csv` → `diagnostic_class` 字段
（Wagner et al., *Sci Data* 7:148, 2020）。仓库 `SUPERCLASSES` 与文献惯例完全一致。

> **因此"核对 CPSC 官方 superclass 定义"这一命题本身不成立。**
> 真正需要核对的是：(a) PTB-XL 官方 superclass 顺序 → 已确认与新值一致；
> (b) 本仓库自定的 `CPSC_TO_SUPERCLASS` 映射表 → 见 §2.3，**它是死代码**。

---

## 2. 仓库实际数据构成（决定性新发现）

### 2.1 两个子集的真实身份

| 本地目录 | zip 名 | 记录数 | 官方对应 | 依据 |
|---|---|---|---|---|
| `kaggle_cpsc2018/Training_WFDB/A*` | `china-physiological-signal-challenge-in-2018.zip` | zip 6877 → 提取 **6844** | **CPSC Database（CPSC2018 公开数据，官方 6877 条）** | 数量吻合 |
| `kaggle_cpsc2019/Training_2/Q*` | `china-12lead-ecg-challenge-database.zip` | **3453** | **CPSC-Extra Database（CPSC2018 未使用数据，官方 3453 条）** | **数量逐位吻合** |

PhysioNet/CinC 2020 官方页面（`physionet.org/content/challenge-2020/1.0.1/`）原文：

> CPSC Database — **6,877** 条（男 3699；女 3178）
> CPSC-Extra Database — **3,453** 条（男 1843；女 1610）… *the CPSC2018 data that was **not used***

且该 Kaggle 数据集由 **PhysioNet 官方账号**发布，描述为
"The data are from the **China Physiological Signal Challenge in 2018** (CPSC2018)"。

→ **两个文件夹都来自 CPSC2018。语料中不存在 CPSC2019。**

而 `scripts/preprocess_cpsc.py` 把它标为 `("cpsc2019", d19)`，论文写 "CPSC2018+2019" —— **均为事实性错误**。

### 2.2 标签来源与分布（实测）

| 子集 | 唯一 SNOMED 码数 | 单标签分布 |
|---|---|---|
| `Training_WFDB/A*`（6844） | **9** | CD 2409, STTC 3520, NORM 914, **MI 0** |
| `Training_2/Q*`（3453） | **72** | **MI 1515**, STTC 1911, CD 16, HYP 11 |
| **合计（10297 → 映射 10296）** | | CD 2425, STTC 5431, **MI 1515**, NORM 914, HYP 11 |

A* 子集的 9 个码与 CPSC2018 官方 9 类**一一对应**（`59118001` RBBB、`164889003` AF、
`426783006` 窦律、`429622005` STD、`270492004` I-AVB、`164884008` PVC、
`284470004` PAC、`164909002` LBBB、`164931005` STE），**MI = 0**。

Q* 子集（CPSC-Extra）的 MI 全部来自：
`164867002` 陈旧性心梗 ×1168、`164865005` 心梗 ×376、`54329005` 前壁心梗 ×62、
`57054005` 急性心梗、`426434006`。

> ⚠️ **论文 4 类子空间 {NORM, CD, STTC, MI} 中的 MI，其合法性完全依赖 CPSC-Extra 的 SNOMED 标注，而 CPSC 官方 9 类里没有 MI。**
> 若审稿人核对 CPSC 官方定义，这是直接的送分质疑点。

### 2.3 `CPSC_TO_SUPERCLASS` 是死代码

`src/data/mapping.py:336` 定义了一张按 CPSC 官方 9 类名映射的表（`OldMI→MI` 是其唯一 MI 来源）。
全仓 grep：**只被 `__init__.py` 导出与 `tests/test_data.py` 断言引用，没有任何管线调用**。

实际管线（`preprocess_cpsc.py`）走的是 **`SCP_TO_SUPERCLASS`（SNOMED 数值键）**。
→ 论文/文档中"按 CPSC 官方类名映射"的描述与实际实现不符。

---

## 3. 编码顺序的最终裁决（实证）

### 3.1 证据链（全部可复现）

| # | 检验 | 结果 | 脚本 |
|---|---|---|---|
| E1 | npz 类别索引分布 vs CPSC 真实类分布 | index1=14.7%=MI、index3=23.6%=CD → **npz 用新编码** | 内联 |
| E2 | npz 标签 1↔3 交换后重算 raw vs `transfer_result.raw` | **39/40 吻合**（<1e-9）；20/20 非 CPSC 不需交换 | `verify_cpsc_encoding_final.py` |
| E3 | 两套编码下的 accuracy | **0.5265（旧）vs 0.4308（新）**，39/40 旧胜 | `verify_source_encoding.py` |
| E4 | 逐类召回（`chapman→cpsc seed42`） | 模型从不预测类 3；预测的 163 次全落类 1 → 类 1 召回 **0.301（旧）/ 0.013（新）** | 同上 |
| E5 | npz+旧编码 复现 `transfer_result.deltaECE` | **60/60 逐位吻合，max\|Δ\| = 1.11e-16** | `reproduce_main_endpoint_both_encodings.py` |
| E6 | `JSON.T` vs `T_new`（新编码拟合温度） | **corr = 1.000000，max\|Δ\| = 0.000e+00** | `match_json_fields.py` |
| E7 | `JSON.delta_obs` vs npz+新编码 | **corr = 0.998819** | 同上 |
| E8 | `JSON.delta_obs_orig` vs npz+旧编码 | **60/60 偏差 0.000000**（仅 2 个 mamba 玩具 cell 不符） | `diagnose_json_orig_fields.py` |
| E9 | `ckpt_nc != num_classes` 行为 | `eval_transfer.py:124` 直接 `raise` → **不存在"5 类源截断成 4 类"的路径** | 源码 |

**E9 推翻了此前 P0 审计中 F2 缺陷的立论前提**：`docs/p0_final_verdict.md` 称 F2 危害来自
"5 类源 → 4 类目标截断只做数值截断不做语义重映射"，但代码里这条路径会直接报错，
且 4 类迁移的**源数据集也是用 `SUBSPACE_CPSC` 构建的**（`eval_transfer.py:101-102`），
源/目标编码天然一致。

### 3.2 裁决

- **规范层面：新值 `("NORM","MI","STTC","CD")` 正确**（与 `SUPERCLASSES[:4]` 一致）。
- **运行层面：旧值才是 09-08 实际使用的编码**，且源/目标自洽 → 数字有效。
- **09-09 的改动是一次"规范上正确、运行上有害"的改动**：只改代码不重训模型，
  导致 40 个含 CPSC 的 cell 标签与模型语义失配。

---

## 4. 三口径之谜彻底闭合

`results/strengthening_battle_corrected.json`（62 条，60 main + 2 mamba）三个 ΔECE 字段的真实身份：

| 字段 | 60-main 均值 | **真实含义** | 可用性 |
|---|---|---|---|
| `delta_obs_orig` | **+0.015863** | 同一批 probs + **旧编码**标签 = 论文主终点 | ✅ **有效**（= `robustness_validation_5seeds.csv` = `transfer_result.json`，三者逐位相同） |
| `delta_obs` | **+0.106843** | 同一批 probs + **新编码**标签 → **纯标签错位伪信号** | ❌ **无效** |
| `delta_pred` | **+0.301460** | 分解模型 Shapley 预测值（与标签无关） | ⚠️ provenance 仍缺 |

**内部矛盾**：该 JSON 的 `T` 字段 ≡ `T_new`（新编码拟合，E6 逐位相同），
但 `raw_ood_orig`/`cal_ood_orig`/`delta_obs_orig` 用的是**旧编码温度**（E8）。
→ **该 JSON 是混合编码产物，`T` 与 `*_orig` 字段互不自洽。**

### 4.1 对既有诊断的更正

| 旧结论 | 更正 |
|---|---|
| `delta_obs` 的 T 膨胀是 "SmoothECE 噪声底伪信号" | **根因是标签编码错位**，不是（或不只是）噪声底。T 膨胀是错位计算的副产物。 |
| "只有 21/60 npz cell 与 transfer 同源，39/60 来自另一次丢失的 run" | **错误**。60/60 都是同一次 run 的 probs；表观不符纯粹来自标签编码。 |
| `rebuild_shapley_crossfit.py` 产出的是 `delta_obs` 口径 | 仍成立 —— 该脚本读 npz 标签，因此复现的是**被污染的口径**。 |

---

## 5. 对论文（`paper/main_bspc.tex`）的逐项影响

| 位置 | 内容 | 判定 |
|---|---|---|
| 主终点 +0.0159 / 51-60 / t=6.434 | 数字 | ✅ **正确，无需修改** |
| L342-343 `$\{$NORM, CD, STTC, MI$\}$` | 类表顺序 | ⚠️ 与数字自洽但非规范；审稿人可能质疑为何与 5 类的 NORM/MI/STTC/CD/HYP 顺序不一致 |
| L315 / §data "CPSC2018+2019" | 语料描述 | ❌ **事实错误**（应为 CPSC2018 + CPSC-Extra） |
| 4 类子空间含 MI | 类合法性 | ❌ **MI 无官方依据**（CPSC 官方 9 类无 MI） |
| HYP n=11 降级理由 | 依据 | ✅ 成立（HYP 确实 n=11） |
| 按类名的分项指标 | — | ✅ **论文没有**（已 grep 确认无 per-class breakdown）→ 无类名错标风险 |

---

## 6. 行动清单

### P0（投稿前必须）

| # | 行动 | 成本 |
|---|---|---|
| P0-1 | **修正语料描述**：论文与 `preprocess_cpsc.py` 中的 "CPSC2019" 改为 "CPSC-Extra（CPSC2018 未使用数据）"；"CPSC2018+2019" → "CPSC2018 (CPSC Database + CPSC-Extra)" | 低 |
| P0-2 | **决定 MI 类去留**：① 若坚持官方口径 → 4 类子空间降为 {NORM, CD, STTC}（3 类），全部重算；② 若保留 MI → 需在数据章节显式声明"MI 来自 CPSC-Extra 的 SNOMED 标注，非 CPSC2018 官方 9 类"，并给出映射依据 | 中 |
| P0-3 | **标记污染产物**：`checkpoints/e2_probs_cache/*.npz`（09-10 标签）与 `results/strengthening_battle_corrected.json` 的 `delta_obs`/`T` 字段不可再被下游消费 | 低 |

### P1

| # | 行动 | 成本 |
|---|---|---|
| P1-1 | **统一编码**：(A) 回滚 `SUBSPACE_CPSC` 为旧顺序 + 加显式注释（零成本，数字不变）；或 (B) 用新顺序**重训全部 4 类模型**并重跑 40 个 cell（规范，推荐用于 CMPB） | A 低 / B 高 |
| P1-2 | **补回 33 条丢失记录**（`A6845`–`A6877`）并重跑 CPSC 侧预处理 | 低 |
| P1-3 | 重生成 npz 缓存（若选 P1-1(B)） | 中 |

### P2

| # | 行动 | 成本 |
|---|---|---|
| P2-1 | 删除或接入 `CPSC_TO_SUPERCLASS`（当前为死代码，且会误导读者以为管线走官方类名） | 低 |
| P2-2 | 修正 `docs/p0_final_verdict.md` / `p0_counter_p0_6_7.md` 中 F2 缺陷的立论前提（5→4 截断路径不存在） | 低 |
| P2-3 | `scripts/verify_main_from_transfer.py` 排除 `cpsc_cpsc` 冒烟 cell | 低 |

---

## 7. 复现脚本

| 脚本 | 作用 |
|---|---|
| `scripts/verify_cpsc_encoding_final.py` | 标签 1↔3 交换 vs `transfer_result.raw`（E2） |
| `scripts/verify_source_encoding.py` | 两套编码下的 accuracy / 逐类召回（E3、E4） |
| `scripts/reproduce_main_endpoint_both_encodings.py` | 双编码逐 cell 复现 ΔECE（E5） |
| `scripts/match_json_fields.py` | JSON 字段来源匹配（E6、E7） |
| `scripts/diagnose_json_orig_fields.py` | `delta_obs_orig` 逐条比对 + 内部一致性（E8） |

复现环境：`/c/python/python.exe`（managed Python 的 numpy 损坏），`-X faulthandler`。

---

## 8. 一句话总结

> CPSC 官方根本没有 superclass 定义，新顺序在规范上是对的、旧顺序才是论文实际用的；
> 但真正的问题不在顺序 —— 而在于**论文把 CPSC2018 的未使用半区（CPSC-Extra）误称为 CPSC2019**，
> 并且**论文 4 类子空间里的 MI 类整个来自这半区的 SNOMED 标注，而 CPSC 官方 9 类里没有 MI**。
> 主终点 +0.0159 本身是正确且可逐位复现的。
