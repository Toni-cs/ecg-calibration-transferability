# Chapman 语料混合审计 · 数据层（2026-10-22）

**性质**：只读统计审计（零 GPU、零推理、零数据变更）。本文件是 UPGRADE_PROTOCOL_v3.0 第 2 章类计数实测矩阵的取证依据。
**数据源**：`data/chapman_processed_v2/metadata_single_label.csv`（20,243 行）、`splits/chapman_seed{42..46}.csv`。
**方法**：按 patient_id 的 JS 编号分段（JS≤10247 = Chapman 本体，JS≥10248 = Ningbo 本体），段边界与 ecg-arrhythmia 库的医院来源结构一致。

## 1. 分段构成

| 段 | 记录数 | 占比 |
|---|---|---|
| Chapman 本体（JS00001–JS10247） | 9,847 | 48.64% |
| Ningbo 本体（JS10248–JS36689 段内） | 10,396 | **51.36%** |
| 合计 | 20,243 | 100% |

论文与 README 声称该库为 "Chapman–Shaoxing"（CinC 2021 口径 10,247 条）——实际为一半 Ningbo。

## 2. 段间患病率结构（折叠后单标签口径）

| 超类 | Chapman 段 n（%） | Ningbo 段 n（%） | 合计 n |
|---|---|---|---|
| STTC | 4,692（47.6） | 9,407（90.5） | 14,099 |
| NORM | 4,292（43.6） | 474（4.6） | 4,766 |
| HYP | 444（4.5） | 14（0.1） | 458 |
| CD | 385（3.9） | 427（4.1） | 812 |
| MI | 34（0.4） | 74（0.7） | 108 |

两段是**病种构成完全不同的医院源**（NORM 43.6% vs 4.6%；STTC 47.6% vs 90.5%），不是同分布的随机子集。

## 3. split 结构（seed 42–46 一致）

| split | Chapman 段 | Ningbo 段 | 段比 |
|---|---|---|---|
| train | 5,883 | 6,260 | 51.5% |
| val | 1,010 | 1,015 | 50.1% |
| cal | 997 | 1,028 | 50.8% |
| test | 1,957 | 2,093 | 51.7% |

五个 seed 的 test 集 Ningbo 占比 51.4%–52.5%，train/test 段构成一致。

## 4. 定性判定

1. **非泄漏**：train/test 的段构成一致（51.5% vs 51.7%），无段间泄漏；内部效度未被破坏。
2. **外部效度声明错误**：所有 "chapman→X" 结论的实际语义是 "（Chapman+Ningbo 混合体）→X"。
3. **自变量失真**：混合体患病率（STTC 69.6%、NORM 23.6%）不代表任一真实医院源；一切以混合先验计算的 δ_y / 先验偏移量既非 Chapman 也非 Ningbo 的真实偏移。
4. **稀有类功效**：test 集内 MI=22（Chapman 5 + Ningbo 17）、HYP=92；cal 集内 MI=11、HYP=46——TS/Platt 在 MI 上几乎无拟合材料。
5. **拆分后稀有类**：Chapman 本体 MI=34（<50）；Ningbo 本体 HYP=14（<50）——双层类空间口径的实测触发器。

## 5. 对 60 cell 网格的影响面

涉 Chapman 的方向 4 个（chapman↔ptbxl、chapman↔cpsc 双向）× 2 架构 × 5 seed = **40/60 cell** 需拆分后重跑；受影响结果族 = 全部 16 个下游族的 Chapman 相关子集。
（历史纪元对照：val-leak 重训 20 cell 使 50/60→45/60 且方向结构不变；本审计未做推理层验证，40 cell 拆分重训后的数字以重训产物为准。）

## 6. 后续（推理层三切片审计，另行执行）

用现有 20 个 Chapman 相关 checkpoint 做零梯度三切片推理（混合 test / 纯 Chapman 本体 / 纯 Ningbo 本体），量化"语料混合偏差 = X"——属 exploratory pilot，其读数按 v3.0 §2.7 防火墙条款**不得进入**协议枚举字段与预注册动机节，只进 `reports/mixing_audit/` 留痕。
