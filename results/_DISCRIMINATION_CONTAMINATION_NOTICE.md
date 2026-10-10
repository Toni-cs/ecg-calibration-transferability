# 污染通告：`discrimination_metrics_60exp.csv`

**状态**：❌ **污染（判别力被系统性低估）**
**新增日期**：2026-09-17
**受影响产物**：`results/discrimination_metrics_60exp.csv`（mtime **2026-09-10 12:45**）
**已提供修正版**：`results/discrimination_metrics_60exp.OLD_ENCODING.csv`
**论文引用处**：L1840（AUROC 范围）、L1974（OOD AUROC 均值范围）— 已修正

---

## 1. 一句话结论

该表的 AUROC/AUPRC/F1/PPV/NPV/MCC **全部**由「OLD 编码的 probs + NEW 编码的 labels」
算出（MI↔CD 错位），判别力被系统性低估。逐方向 OOD AUROC 均值由
**0.629–0.792** 修正为 **0.735–0.843**。

---

## 2. 输入与时间线

| 环节 | 文件 | mtime | 编码 |
|---|---|---|---|
| probs 来源 | `checkpoints/transfer/**/best_model.pt` | 2026-09-08 | **OLD** |
| probs/labels 缓存 | `checkpoints/e2_probs_cache/*.npz`（**全部 62 份**） | 2026-09-10 12:30–12:40 | probs=OLD，**labels=NEW** |
| 本表 | `results/discrimination_metrics_60exp.csv` | 2026-09-10 12:45 | 按 NEW 标签计算 |

缓存生成者 `run_e2_ablation_discrimination.py::load_probs_for_checkpoint` 原先用
**运行时** `SUBSPACE_CPSC` 重建标签（当日 = NEW），而 checkpoint 是 09-08 的 OLD 编码，
且**未重训模型** ⇒ 标签与 probs 语义错位（MI↔CD 互换，占 38.3% 样本）。

---

## 3. 实证裁决（不依赖日期推断）

对 `chapman_cpsc / inceptiontime / seed42 / split=cal / variant=raw`，
从缓存重算 AUROC（`roc_auc_score(..., multi_class="ovr", average="macro")`）：

| 标签口径 | AUROC | 与 CSV 所载 0.641959 之差 |
|---|---|---|
| 缓存原样（**NEW**） | **0.641959** | **0.000000** ← 逐位相同 |
| `swap13`（**OLD**） | **0.861000** | 0.219041 |

⇒ 该 CSV 确实是用错位标签算的；且修正量是 0.219，**不是四舍五入级别**。

逐方向 OOD AUROC 均值（5 种子 × 2 架构；`ptbxl_chapman` 含 2 个 mamba 格）：

| 方向 | K | CSV（污染） | OLD（正确） | 差 |
|---|---|---|---|---|
| chapman→cpsc | 4 | 0.6743 | 0.7554 | +0.0812 |
| cpsc→chapman | 4 | 0.6312 | 0.8251 | +0.1939 |
| cpsc→ptbxl | 4 | 0.6419 | 0.8044 | +0.1625 |
| ptbxl→cpsc | 4 | 0.6290 | 0.8425 | +0.2135 |
| chapman→ptbxl | 5 | 0.7353 | 0.7353 | 0（不涉及 CPSC） |
| ptbxl→chapman | 5 | 0.7922 | 0.7922 | 0（不涉及 CPSC） |
| **6 方向范围** | | **0.629–0.792** | **0.735–0.843** | |

论文 L1974 引的 "0.629--0.792" **精确复现污染表**，故必须修正。

---

## 4. 修正版与其边界

`results/discrimination_metrics_60exp.OLD_ENCODING.csv`
（由 `scripts/recompute_discrimination_old_encoding.py` 生成）：

* 124 行 = 62 个 cache × {cal, test}，仅 `variant=raw`。
* 40 个 4 类 cache 用 `swap13` 重编码；22 个 5 类 cache **原样**（逐位不变，
  已验证与原件 0 处不一致）⇒ 修正是外科式的。
* **不包含** `ts` / `binned` / `threshold` 三个 variant —— 它们依赖标定方法，
  属全量重跑范围。论文引用的 AUROC 范围与 ΔAUROC 只涉及 `raw`，故修正版足够。

---

## 5. 论文已做修正

| 位置 | 原 | 现 |
|---|---|---|
| L1840 | `mean OOD AUROC ranges from 0.629 (CPSC→Chapman) to 0.795 (PTB-XL→Chapman)` | `from 0.735 (Chapman→PTB-XL) to 0.843 (PTB-XL→CPSC)` |
| L1840 | 引 `discrimination_metrics_60exp.csv` | 引 `...OLD_ENCODING.csv` |
| L1974 | `OOD AUROC means range 0.629--0.792` | `0.735--0.843` |
| L1974 | 引 `discrimination_metrics_60exp.csv` | 引 `...OLD_ENCODING.csv` |

原句的方向归属亦有误：0.629 实为 **PTB-XL→CPSC**，非 CPSC→Chapman。

**注**：AUROC 对标签置换不敏感这一点**不成立** —— 逐类 OvR AUROC 依赖「哪一列对应
哪一类」，故标签错位会改变数值（本例 0.642 → 0.861）。与之相对，
`mean ΔAUROC_TS−raw ≈ −0.001` 的声明**仍然有效**：温度缩放是逐样本单调变换，
不改变类内排序，故 ΔAUROC ≈ 0 与标签编码无关。

---

## 6. 根因修复

* 新增 `src/utils/encoding_guard.py`：`checkpoint_subspace()` 以 checkpoint 自存的
  `transfer_result.json:subspace` 为唯一权威编码，与运行时常量不符即 `raise`；
  `assert_cache_encoding()` 要求缓存携带 `label_encoding` 戳，无戳即拒绝。
* `run_e2_ablation_discrimination.py` 已接入上述护栏，并在写缓存时写入编码戳；
  新增 `--allow-unstamped-cache` 显式逃生舱（默认拒绝 09-10 那批无戳缓存）。
* 该缺陷是**同一句代码在 7 个脚本里重复 10 次**的结果，已全部改为调用共享护栏
  （`eval_transfer.py`、`run_e1a_l2_shift_full.py`、`run_e1b_loco_validation.py`、
  `run_e2_ablation_discrimination.py`、`run_e3_brier_dcr_ncv.py`、
  `run_e4_temperature_analysis.py`、`run_e5_inception_lite.py`×3、
  `run_e6_reliability_diagrams.py`、`eval_l2_shift.py`）。
* `step2_predictability.py` 作为下游消费者，现在要求 `l2_shift_results.json`
  携带编码戳，否则 `raise`。
