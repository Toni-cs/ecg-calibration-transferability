# OSF Addendum — 2026-10-12

** deposit**：Project **53h64**（Registration **Wjz3y**，frozen 2026-09-14，不可修改）
**性质**：Addendum（补充存档），不改写任何已冻结内容；本文件为 A3/A4 的 OSF 镜像与冻结数字的演化披露。

---

## 1. 本 addendum 补入的文件（F2 闭环）

自本次上传起，本 deposit 包含：

| 文件 | 说明 |
|---|---|
| `PROTOCOL_AMENDMENT_A3_CORPUS_IDENTITY.md`（2026-09-16） | 语料身份更正：注册文本所称 "CPSC2018+2019" 实为 **CPSC2018 only**（CPSC Database 6,877 + CPSC-Extra 3,453，均经 PhysioNet/CinC 2020 分发；无 CPSC2019）；并新增披露：CPSC2018 官方 9 类体系无 superclass、无 MI，4 类子空间的 MI 全部来自 CPSC-Extra 的 SNOMED 标注。 |
| `PROTOCOL_AMENDMENT_A4_MAPPING_SENSITIVITY.md`（2026-10-11） | §10 映射敏感性判据的可行化：注册判据定义在次要端点 G 上，而 G 未在真实数据上交付（论文 Limitations xviii 自认）——判据重新操作化为已交付的 ΔECE_OOD（6 操纵对排序 Kendall τ≥0.8 + 确认性计数不变 BH-12=7/12、Bonferroni-12=6/12；失败分支=注册原文的 claim 降级义务，逐字保留）。变体 V1/V2 在任何变体结果存在**之前**列举（anti-HARKing），V3 排除并记录理由。**截至本 addendum，变体电池尚未执行**（估算 2–5 GPU 日，执行状态诚实记录）。 |
| `CORRECTIONS_LEDGER_2026-10-11.md` | 2026-10-10/11 对抗审查后的修复台账 A1–A17（含逐条机械验证证据），并声明更早审查轮次（Round-9 等）中被三代重跑取代的数字不得再引用。 |

论文中的对应声明（§Preregistration record）自本次上传起成立：
"The protocol, the amendments (A1, A2, A3, A4), and a per-file archival-status
report are publicly archived at https://doi.org/10.17605/OSF.IO/53H64."

## 2. 冻结注册数字的演化披露（F3 闭环）

注册快照（Wjz3y）记录的主终点读数 **51/60**（2026-09-08 数据纪元）为冻结值，
**OSF 注册不可修改**。其后的两次修复重训**如实**改变了该读数：

| 日期 | 事件 | 结果 |
|---|---|---|
| 2026-09-08 | 主网格交付（注册冻结前） | 51/60 |
| 2026-09-17 | 检查点独立性修复：cpsc_ptbxl/InceptionTime seed42/43 重训 | 50/60 |
| 2026-10-07 | **PTB-XL 早停 val 泄漏修复**：20 个 PTB-XL 源 cell 重训（split 语义修复，21,397 行 val→不进训练加载器）；全部 16 个下游结果族重算 | **45/60**，ΔECE_OOD +0.0154 → **+0.0093**（[+0.0055, +0.0132]），ID 均值 +0.0082 → +0.0034；预注册的 ID 边界失败分支照旧触发（30/60） |

**原则**：注册是"冻结那一刻"的记录，不是"最新结论"的记录；演化以带日期、带
台账（`CORRECTIONS_LEDGER_2026-10-11.md`）的 addendum 呈现，**不回改注册本体**。
所有交付表（`results/robustness_validation_5seeds.csv` 等）与论文正文均为
45/60 口径，且可由发布仓 `scripts/verify_release_results.py`（12/12 PASS）
与逐格 `transfer_result.json` 交叉验证。

## 3. 相关材料链接更正（F1 闭环）

注册元数据与项目页中曾引用的
`https://github.com/gt17641001169-design/ecg-calibration-transportability`
为失效地址。更正为：

> **https://github.com/Toni-cs/ecg-calibration-transportability**

（同一仓库；发布 main 分支含完整修复链与 `v1.0.0`/`historical/full-work-20260917`
tag；后修复权重资产将于 v1.1.0 release 挂载。）

## 4. 语言与引用

本文为 English-first addendum；中文摘要在各节标题下保留与正文对齐的中文陈述。
引用本 addendum 时引用 project DOI: https://doi.org/10.17605/OSF.IO/53H64
（registration Wjz3y 仅作为 2026-09-14 时刻的冻结快照引用）。

---

<!-- 中文对照摘要 -->
**这个 supplement 是什么**：2026-10-10/11 对抗审查发现的预注册体系三处缺口
（A3/A4 未入 deposit、OSF 页面死链、冻结数字与终值的三代演化未披露）的
闭环文件。三份 md 附件入 deposit；注册本体不动；演化以 addendum 披露。
