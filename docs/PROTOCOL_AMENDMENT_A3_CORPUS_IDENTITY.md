# 预注册修订案 A3 — CPSC 语料身份更正与 MI 来源声明

> **修订案编号**：A3
> **修订日期**：2026-09-16
> **触发轮次**：CPSC 官方 superclass 定义核对（用户指令"去核对 CPSC 官方 superclass 定义"）
> **修订类型**：预注册修订（Preregistration Revision，Nosek et al. 2018 分类）——**措辞/命名层更正 + 新增披露**，非分析计划变更
> **修订前协议哈希**：`docs/EXPERIMENT_PROTOCOL.md` sha256 = `0e8afa923986aba3f5030133c59b8a87b475c3551b819b0137ab9da66eeb9498`（v2.1-A1，2026-09-09T01:33:51Z）
> **状态**：已写入论文；待 OSF 时间戳存档
> **对已发布数值的影响**：**无**（见 A3.5）

---

## A3.1 修订前（as-registered）

协议 §2（`docs/EXPERIMENT_PROTOCOL.md` 第 39 行，及三份同源副本）写作：

> `| CPSC2018+2019 | 源/目标 | 患者级分层 70/10/20；HYP极稀有(n=11,全来自CPSC2019单标签LVH/RVH)→主分析降级{NORM,CD,STTC,MI}4类子空间 …`

即：把所用语料表述为 **CPSC2018 与 CPSC2019 的合并**，并把 HYP 的 11 条记录归因于 **CPSC2019 单标签**。

## A3.2 修订后（as-revised）

> `| CPSC2018（CPSC Database + CPSC-Extra） | 源/目标 | 患者级分层 70/10/20；HYP 极稀有(n=11，全部来自 CPSC-Extra 单标签 LVH/RVH)→主分析降级{NORM,CD,STTC,MI}4类子空间 …`

三点更正：

1. **语料身份**：本研究所用语料是 **CPSC2018**，其构成为
   - **CPSC Database**：6,877 条（公开的 CPSC2018 训练集；本地解压后 6,844 条，见 A3.4）
   - **CPSC-Extra Database**：3,453 条（CPSC2018 中未被挑战赛使用的部分）
   二者均由 PhysioNet/CinC 2020 发布。**语料中不含 CPSC2019。**
2. **CPSC2019 与本研究无关**：CPSC2019 官方任务是 **QRS/心率检测**（评分指标 QRSacc/HRacc），**不提供任何疾病分类标签**，因此不可能进入一个诊断分类迁移研究。
3. **HYP 归因更正**：HYP 的 11 条记录来自 **CPSC-Extra** 的单标签 LVH/RVH，而非 CPSC2019。

## A3.3 新增披露：4 类子空间中的 MI 无 CPSC 官方依据

这是 A3 的**实质性新增内容**（不止是改名）：

- CPSC2018 官方分类体系是 **9 个疾病类别**（Normal, AF, I-AVB, LBBB, RBBB, PAC, PVC, STD, STE），官方原文为 "one normal type and eight abnormal types"，**无 superclass 分组，且不含 MI**。
- 论文采用的 **NORM/MI/STTC/CD/HYP 超类体系是 PTB-XL 的**（Wagner et al., *Sci Data* 7:148, 2020），在本研究中作为**跨库协调（harmonization）选择**使用，**不是 CPSC 定义的概念**。
- 实测（`scripts/verify_cpsc_corpus_identity.py`，只读复算）：

  | 子集 | 记录数 | 不同 SNOMED 码 | 含 MI 码的记录 | MI 码明细 |
  |---|---|---|---|---|
  | CPSC Database | 6,844 | **9** | **0 (0.0%)** | — |
  | CPSC-Extra | 3,453 | **72** | **1,515 (43.9%)** | `164867002`×1168、`164865005`×376、`54329005`×62 |

- 即：**4 类子空间中的 MI 全部来自 CPSC-Extra 的 SNOMED 标注**，CPSC Database 侧 MI = 0。MI 占映射后全语料 1,515/10,296 = **14.71%**（预处理摘要：`data/cpsc_processed/preprocess_summary.json`，`total_records=10297`、`mapped_single_label=10296`）。
- **由此产生的口径分支**：若严格按官方 9 类名口径（`CPSC_TO_SUPERCLASS` 表），4 类子空间应退化为 **{NORM, CD, STTC}（3 类）**。本研究保留 MI，理由是它是在 CPSC 一侧保留"心梗"这一临床类别、并使所有迁移对两侧类别数对称的唯一方式。
- **该口径选择已在论文 Data 章节显式声明**（`paper/main_bspc.tex` §Data，2026-09-16 修订）。

## A3.4 附带发现：33 条 CPSC2018 记录在解压时静默丢失

- 归档 `china-physiological-signal-challenge-in-2018.zip` 内 **6,877** 条 `.hea`；本地 `Training_WFDB/` 实际 **6,844** 条。
- 丢失编号连续：**A6845–A6877（33 条）**。CPSC-Extra 侧完整（zip 3,453 = 磁盘 3,453）。
- 定性：**provenance limitation**，非分析选择。已在论文 Data 章节披露，并列为待补事项（可无损恢复：重解压该 zip）。

## A3.5 对已发布数值的影响：无

| 问题 | 结论 |
|---|---|
| 记录集变了吗？ | **没有。** 数据管线从未读取"CPSC2019"这个字符串；它只读 SNOMED 标签与波形。 |
| 60 格主分析要重跑吗？ | **不要。** 主终点 ΔECE_OOD = +0.0159 不受命名影响。 |
| 协议 §2 的分析计划变了吗？ | **没有。** 子空间集合仍是 {NORM, CD, STTC, MI}，患者级 70/10/20 不变，HYP 剔除策略不变。 |
| 变更性质 | **措辞/归因更正 + 新增披露**，不是 HARKing，也不是分析变更。 |

## A3.6 实现层更正（非协议变更，但须记录）

2026-09-09 提交 `452b3bf` 曾把 `src/data/mapping.py` 的
`SUBSPACE_CPSC` 由 `("NORM","CD","STTC","MI")` 改为 `("NORM","MI","STTC","CD")`
（注释自称 "F2 修复"），**但未重训任何模型**。

由于该元组**顺序即整数标签编码**（`label_map = {c: i for i, c in enumerate(SUBSPACE_CPSC)}`），
09-10 之后重新生成的 npz 标签与 09-08 训练的 checkpoint 语义失配，
使全部含 CPSC 的 40 个 cell 的 **MI 与 CD 两类标签互换**，
并污染了中间产物 `results/strengthening_battle_corrected.json` 的
`delta_obs` 与 `T` 字段（详见 `reports/CPSC_OFFICIAL_DEFINITION_VERDICT_2026-09-16.md`）。

- **2026-09-16 已回退**该行至 `("NORM","CD","STTC","MI")`（即模型实际训练顺序），
  并加入回归测试 `tests/test_data.py::TestMapping::test_subspace_cpsc_order_is_pinned` 钉死顺序。
- **论文主终点未受影响**：`delta_obs_orig` 字段（= 同 probs + 旧标签）逐格复现
  `checkpoints/transfer/**/transfer_result.json`，60/60 一致，max\|Δ\| = 1.11e-16。
  被污染的是 `delta_obs`（新标签口径）与 `T`，二者**不是**论文终点。
- 该更正**不改变协议 §2**（协议只规定子空间为一个集合），属实现层缺陷修复。

## A3.7 修订前后对照表

| 项 | 修订前 | 修订后 |
|---|---|---|
| 语料名称 | CPSC2018+2019 | CPSC2018（CPSC Database + CPSC-Extra） |
| CPSC2019 是否入语料 | 隐含"是" | **明确"否"**（2019 是 QRS 检测任务，无诊断标签） |
| HYP n=11 归因 | CPSC2019 单标签 | CPSC-Extra 单标签 |
| 记录数披露 | 未披露 | 6,844 + 3,453（并披露丢失 33 条） |
| MI 来源 | 未说明 | **显式声明**：全部来自 CPSC-Extra SNOMED，CPSC Database 侧 MI=0 |
| superclass 归属 | 未说明 | 显式声明为 **PTB-XL 的**体系，非 CPSC 官方 |
| 官方口径下的子空间 | 未讨论 | 显式讨论：严格官方口径应为 3 类 {NORM,CD,STTC} |
| 分析计划 / 主终点 | — | **不变** |

## A3.8 透明性声明

- 本次更正由**外部规范核对**（CPSC 官方挑战赛页面、PhysioNet/CinC 2020 语料页）触发，
  **非由结果方向驱动**；更正前后主终点数值完全相同，不存在"改到显著"的动机。
- 更正涉及的**原始表述快照保持字节不变**（`docs/EXPERIMENT_PROTOCOL.md` 及其三份副本），
  本修订案单独存档，符合 Nosek et al. 2018 的"修订前/后双档"要求。
- 依据：CPSC2018 官方挑战赛页面（9 类，无 superclass）；CPSC2019 官方挑战赛页面（QRS/HR 检测）；
  PhysioNet/CinC 2020 语料页（CPSC Database 6,877 条 + CPSC-Extra 3,453 条）；
  Wagner et al. 2020（PTB-XL superclass 体系来源）。
- 复现脚本：`scripts/verify_cpsc_corpus_identity.py`（只读）。
- 完整裁决：`reports/CPSC_OFFICIAL_DEFINITION_VERDICT_2026-09-16.md`。

---

## 附录 A3-A：受影响的文件清单

**已更正的交付物（面向审稿人）**

| 文件 | 改动 |
|---|---|
| `paper/main_bspc.tex` §Data | 语料身份重写 + 记录数 + MI 来源 + superclass 归属声明 |
| `paper/main_bspc.tex` §Abstract | `CPSC2018+2019` → `CPSC2018` |
| `paper/main_bspc.tex` §Class vocabulary | `CPSC2018+2019` → `CPSC2018` |
| `paper/main_bspc.tex` §Data availability | 同上 + 补 CPSC 引用 |
| `paper/main_bspc.tex` 参考文献 | **新增** `liu2018cpsc`、`physionet2020cpsc`（此前**完全没有** CPSC 引用） |
| `paper/cover_letter.tex` | `CPSC2018+2019` → `CPSC2018` |

**保持字节不变的预注册快照（不改）**

| 文件 | 原因 |
|---|---|
| `docs/EXPERIMENT_PROTOCOL.md` | sha256 已入 OSF 清单，改动会破坏预注册完整性 |
| `paper/osf_upload/01_PROTOCOL_EN.md` | OSF 上传副本 |
| `paper/osf_upload/02_PROTOCOL_ZH_original.md` | OSF 上传副本 |
| `paper/submission/supplementary/S1_protocol/EXPERIMENT_PROTOCOL.md` | 投稿补充材料副本 |

**代码层更正**

| 文件 | 改动 |
|---|---|
| `src/data/mapping.py` | `SUBSPACE_CPSC` 回退至训练顺序；`CPSC_TO_SUPERCLASS` 标注为**死代码**并补语料身份/ MI 来源说明 |
| `scripts/preprocess_cpsc.py` | 头部语料身份说明；记录数更正；`--cpsc2019-root` 语义澄清 |
| `tests/test_data.py` | **新增** `test_subspace_cpsc_order_is_pinned` |
| `scripts/verify_cpsc_corpus_identity.py` | **新增**（只读核验脚本） |
| `ecg-release` 同名文件 | 同步（英文版） |
