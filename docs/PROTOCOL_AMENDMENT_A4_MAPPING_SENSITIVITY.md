# 预注册修订案 A4 — 映射敏感性分析判据的可行化（§10 / G 端点）

> **修订案编号**：A4
> **修订日期**：2026-10-11
> **触发轮次**：2026-10-10/11 对抗审查交叉裁决（发现自己从未立案的 §10 承诺 + 其判据引用了未交付端点）
> **修订类型**：预注册修订（Preregistration Revision）——**判据操作化变更**（endpoint for the gate），分析承诺本身不变
> **修订前协议哈希**：`docs/EXPERIMENT_PROTOCOL.md` sha256 = `0e8afa923986aba3f5030133c59b8a87b475c3551b819b0137ab9da66eeb9498`（不变，本修订不改协议正文）
> **状态**：已写入论文；待 OSF 时间戳存档（与 A3 同批）
> **对已发布数值的影响**：**无**（见 A4.5）
> **执行状态**：**变体实验电池尚未执行**（见 A4.4——这是本修订的诚实边界）

---

## A4.1 修订前（as-registered）与不可执行性判决

协议 §10 交付物清单（`docs/EXPERIMENT_PROTOCOL.md` 第 193 行）承诺：

> **映射敏感性分析（操作化）**：对每个歧义映射决策生成替代变体，重跑 1 个代表迁移对全管线；
> 稳健性判据 = **G 跨对排序 Kendall τ ≥ 0.8** 且主检验结论不变，否则在讨论中降级对应 claim。

2026-10-11 审查发现该承诺存在两层问题：

1. **从未执行、从未立案**：全仓（results/、docs/、reports/、git 历史）不存在任何
   映射变体产物（无 variant 表、无 Kendall τ 输出），论文正文 0 处提及该分析，
   §11.5 偏离登记（15 项）中亦无立案记录。
2. **判据引用的端点不可执行**：判据定义在 **G = ECE_S1 − ECE_oracle**（协议 §5 的
   次要端点）上，而论文自身 Limitation (xviii) 已承认：
   *"the secondary endpoint G … is not delivered: fit_oracle/apply_oracle are
   implemented but were never executed on real data, so G is undefined."*
   **按原文执行 §10 需要先交付 G**（全方法池 × 全网格的 oracle 家族），
   使敏感性分析的执行成本叠加在未偿付的 G 交付之上。

## A4.2 修订后（as-revised）：判据重新落地到已交付端点

将 §10 的稳健性判据从 **G 端点** 重新操作化为 **已交付主终点 ΔECE_OOD**：
对每个歧义映射决策的变体 v，重跑受影响的网格子集后，判据为：

| 编号 | 判据（A4 版） | 说明 |
|---|---|---|
| A4-G1 | **跨对排序保持**：variant v 与 as-delivered 基线的 **6 语料对级别 ΔECE_OOD 均值排序 Kendall τ ≥ 0.8** | 对级均值 = 2 架构 × 5 seeds 的对内均值（与注册聚合引擎同源） |
| A4-G2 | **主检验结论不变**：协议家族的 BH-12 与 Bonferroni-12 显著层数与方向（当前基线 7/12 与 6/12）不变 | 同一引擎（stratum mean, SE=s/√5, 单侧 z） |
| A4-G3（失败分支，原条款保留） | τ < 0.8 或主检验结论改变 → **在 Discussion 中降级对应 claim** | 与注册原文的失败分支逐字等价 |

受影响范围声明：CPSC 标签映射的歧义决策只影响 **CPSC 涉及的 4 个迁移方向**
（ptbxl_cpsc / chapman_cpsc / cpsc_ptbxl / cpsc_chapman，2 架构 × 5 seeds = 40 格）；
ptbxl_chapman / chapman_ptbxl 两方向（20 格）的标签与结构不含 CPSC 映射，
**不因变体重跑而改变**，其已交付值直接用于 τ 计算的排序锚点。

## A4.3 变体清单（"每个歧义映射决策"的操作化）

| 变体 | 歧义点 | 替代处理 | 影响类别 |
|---|---|---|---|
| **V1** | STE 在 CPSC-Extra SNOMED 体系中的归类（as-delivered：STE→STTC，经由 PTB-XL 超类体系） | STE→MI（按 STE 的临床语义归入 MI 类） | cpsc/PTB-XL 映射表 1 行 |
| **V2** | 多标签记录的单标签坍缩（as-delivered：`PRIORITY = [MI, STTC, CD, HYP, NORM]` 取首个命中） | 两种替代：(a) 变更优先级序（如 CD 先于 MI）；(b) 剔除多超类记录而非坍缩 | `scripts/preprocess_cpsc.py` 1 行 + 元数据重算 |
| **V3（已排除，理由声明）** | 语料范围（CPSC-Database-only，剔除 CPSC-Extra） | 排除理由：MI 类将整体消失（CPSC Database MI=0，见 A3.3），4 类子空间退化为 3 类，破坏全部迁移对两侧类别数对称的预注册结构（协议 §2） | — |

排除 V3 的声明记录在此，防止执行期临时增删变体的选择性空间。变体电池执行
后，每个变体独立提交 A4-V1/A4-V2 结果报告（含 τ 值与主检验读数），该报告
附 OSF addendum 镜像。

## A4.4 执行状态：尚未执行（本修订的核心诚实声明）

截至本修订签署（2026-10-11）：

- **没有任何变体已被预处理或训练**；A4 交付的是**判据的先行定义**，不是结果。
- 执行成本估算（作者已确认 GPU 资源：单卡 RTX 5060 Laptop 8GB，
  2026-10-07 修复波实测 20 格 ≈ 1 人日）：V1+V2 两变体 × 40 格 ≈ **2–5 GPU 日**，
  计划执行窗口由作者排期；执行完成前，论文中的跨库 claim 保持其现有披露强度。
- **预先定义防 HARKing**：判据（A4-G1/A4-G2/G3）在任何变体结果存在之前定义并
  存档，与 A1.1.4 的论证规范一致；后续无论结果落在哪个分支，本文件为唯一判据原件。

## A4.5 对已发布数值的影响：无

| 问题 | 结论 |
|------|------|
| 已交付表格变了吗？ | **没有。** A4 不触碰任何 results/、splits/、checkpoint。 |
| 主终点要重算吗？ | **不用。** A4 变更的是"变体电池通过与否的尺子"，不是尺子丈量过的数字。 |
| 协议 §10 的分析承诺变了吗？ | **没有。** 承诺（跑映射敏感性、失败则降级 claim）保留；仅判据端点由 G 更换为 ΔECE_OOD，理由 = G 在真实数据上未定义（Limitation xviii 自认）。 |
| 论文正文同步 | Preregistration 章节新增 A4 小节；preregistration record 列表从 "A1–A3" 更新为 "A1–A4"；cover letter 的修订案计数同步。 |

## A4.6 透明性声明

- 与 A3 同规范：`docs/EXPERIMENT_PROTOCOL.md` 及三份快照**保持字节不变**，
  本修订单独存档；协议 SHA-256 清单不受影响。
- "判据端点换轨"的动机链完整可查：审计发现（2026-10-10/11）→ G 未交付
  （论文自认）→ 在任何变体结果存在之前换轨并声明。本修订**不**存在"改到显著"
  的动机；其失败分支照旧保留降级 claim 的义务。
- 依据：Nosek et al. 2018（preregistration revision 分类）；本协议 A1.1.4
  （anti-HARKing 先例）；Limitation (xviii)（G 未交付的自认，论文 §Limitations）。

---

## 附录 A4-A：受影响的文件清单

| 文件 | 改动 |
|---|---|
| `docs/PROTOCOL_AMENDMENT_A4_MAPPING_SENSITIVITY.md` | **本文件**（双树同步） |
| `paper/main_cmpb.tex` §Amendments | 新增 A4 小节（A3 小节之后） |
| `paper/main_cmpb.tex` §Preregistration record | 修订案清单 "A1, A2, A3" 更新为含 A4 |
| `paper/cover_letter.tex` | "Three pre-registration amendments" → 四案口径并补一句 A4 |
| `README.md`（发布仓）§Preregistration record | amendments 状态行同步（A3、A4 均随仓、未入 deposit 的披露口径不变） |
| `docs/CORRECTIONS_LEDGER_2026-10-11.md` | A17 行（本修订 + 同步验证） |

**保持字节不变的预注册快照（不改）**：`docs/EXPERIMENT_PROTOCOL.md`、
`paper/osf_upload/01/02` 两份协议副本、
`paper/submission/supplementary/S1_protocol/EXPERIMENT_PROTOCOL.md`。
