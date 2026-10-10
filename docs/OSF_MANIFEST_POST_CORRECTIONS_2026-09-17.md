# OSF 归档清单：清单后更正记录（2026-09-17 修订版）

> **清单**：`docs/osf_archive_manifest.json`（时间戳 `2026-09-16T02:44:47Z`，14 个文件）
> **本记录日期**：2026-09-17
> **取代**：`docs/OSF_MANIFEST_POST_CORRECTIONS_2026-09-16.md`（当时只观察到 2 个漂移文件；
> 当晚后续提交使漂移数升至 6，故重发完整版）
> **性质**：清单是"某一时刻的快照"。**本记录不修改该快照**，只登记快照之后发生的变化，
> 使读者能把"清单里记的是什么"与"仓库现在是什么"对上。
> **复现**：`python scripts/audit_manifest_drift.py`（只读）

---

## 1. 汇总

| 类别 | 数量 |
|---|---|
| 哈希未变 | **8 / 14** |
| 哈希已变 | **6 / 14** |
| 清单中已不存在 | **0 / 14** |

**关键：`docs/EXPERIMENT_PROTOCOL.md` 哈希未变**，即预注册协议快照本身**完整未被触碰**
（sha256 `0e8afa923986aba3f5030133c59b8a87b475c3551b819b0137ab9da66eeb9498`，52,641 字节，
与其副本字节相同）。本项目的做法是：**协议永远不改，改动一律另立修订案**（A1 / A2 / A3）。

未变的 8 个文件：`docs/EXPERIMENT_PROTOCOL.md`、`scripts/step3_deployment.py`、
`src/data/l2_shifts.py`、`src/models/baselines.py`、`src/models/ecg_classifier.py`、
`src/utils/calibration.py`、`src/utils/calibration_methods.py`、`src/utils/prior_shift.py`。

> 注意：`src/utils/calibration.py` 未变是**重要正面证据**——`smooth_ece` 的实现
> （含带宽与 $n^{-0.2}$ 归一）自清单时刻起从未被改动，因此论文中所有 ECE 数值的
> 度量定义是稳定的；后来发现的问题全部在**标签编码**层，不在度量层。

## 2. 已变文件（6 个）

| 文件 | 旧 sha256 | 新 sha256 | 大小 |
|---|---|---|---|
| `src/data/mapping.py` | `649bde9e4e13ffd31ab77b9cad8b21d372e495a2fa0cda52d8658b50686b2db2` | `df56ae645fb503bb74dae5cc7d92df3909e2a85207dcbe292c87e95d230b92db` | 30,018 → 32,857 |
| `scripts/eval_transfer.py` | `06860d8b9abd1e1684e8940847f64f1fbdfbdbf4a229bc8fe951a91a8c49522c` | `24178dd2da1aa3777708c254c78bd1966bf56f9456c9179cd57628e284236fd1` | 19,312 → 21,157 |
| `scripts/eval_l2_shift.py` | `369d8d959d72895e910b788d0515a105710ea04d1eacd39aa3cd1d06767d4759` | `603e48d1cf553ff8e15f047a160a031b3431dd04668f7dc7d413dbaf593b8779` | 10,585 → 12,236 |
| `scripts/step2_predictability.py` | `ace6a52c32bc50e15bcc5e975c2b587e5e147d35ca18e169b9f7be84e591dec6` | `62a811ec02c4cda752d6b77bfdb913b7d8370a45b5b033e2bddbe782ceded572` | 11,431 → 12,526 |
| `scripts/summarize_l2_shifts.py` | `ff8d537a169e575f59e8bb68281c7f1248358de4f647f88cb8415e8340c713b8` | `ec25bc0b434cc06c48f636b2f6d66cb3ce8807f3d3ecd8b2c7018aff346da578` | 5,235 → 9,177 |
| `paper/main_bspc.tex` | `ae24f68ee1721551a38d59f78ed511aea68a3f13fc7d5aaaf8d573af3bcf9937` | `f6b528dd997a34d610f668b82e35cb38e710e5f71468574275147f10358e8547` | 111,108 → 146,172 |

### 2.1 `src/data/mapping.py` —— 修复（编码回退）

清单钉住的是 **2026-09-09 的损坏版本**：该版本把 `SUBSPACE_CPSC` 改成
`("NORM","MI","STTC","CD")` 却**未重训模型**。2026-09-16 已**回退**至模型实际训练顺序
`("NORM","CD","STTC","MI")`，并加长注释说明"顺序即编码"、补 `CPSC_TO_SUPERCLASS`
的死代码标注与语料身份说明（提交 `72b2e59`）。

**回退不改变任何已发布数值**：回退后 60 格主终点逐位复现
（mean `+0.015863`，max|Δ| = `1.110e-16`）。清单里那一版是错的，当前这一版才对。

### 2.2 `scripts/eval_transfer.py` / `eval_l2_shift.py` / `step2_predictability.py` —— 加编码守卫

提交 `269184d`（"Encoding guard: the defect was replicated 10x, not once"）。
三处都加了 `label_map` / 标签顺序的断言：若复用检查点的 `label_map` 与当前
`SUBSPACE_*` 顺序不一致，或复用检查点的 `num_classes` 与目标不匹配，直接抛错而不是
静默产出错位结果。**这是防止 2.1 类缺陷重演的机制，不是分析口径的变更。**

### 2.3 `scripts/summarize_l2_shifts.py` —— R2 审计后重写守卫

提交 `1840a20`（"R2 adversarial audit: 6 of my own claims falsified; guard reworked"）。
原守卫对"检查点是否完整"的判定过松，会跳过实际缺失的档位；重写后按
`__seed_strategy__` 版本 + 全档位存在性双重校验。

### 2.4 `paper/main_bspc.tex` —— 措辞更正 + 新增披露 + 补引用 + 换期刊

三组改动（提交 `72b2e59`、`ad99988`，及 2026-09-17 本次编辑）：

1. **语料身份更正**：`CPSC2018+2019` → `CPSC2018`（CPSC Database + CPSC-Extra），
   涉及摘要、数据集列表、类别词汇表段落、数据可用性共 4 处；§Data 补记录数、
   MI 来源披露、superclass 归属声明。
2. **补 CPSC 引用**：此前论文**完全没有 CPSC 参考文献**，新增
   `liu2018cpsc`、`physionet2020cpsc`。
3. **新增 §"Pre-registration amendment A3"**，并在参考文献中加入 A3 条目。
4. 目标期刊由 BSPC 改为 CMPB（`\journal{}`、cover letter、补充材料 README）。
5. 2026-09-17：正文"both amendments (A1, A2)" → "all three amendments (A1, A2, A3)"；
   cover letter 同步补 A3 披露。

> **哈希是移动目标**：稿件在投稿前会持续修订，上表 `main_bspc.tex` 的新哈希是
> **本记录日期**的值。**投稿时刻的最终哈希**应记入投稿清单，而不是本文件。

## 3. 清单未收录、但属分析关键路径的新增文件

清单是 14 个文件的**子集**（记录的是协议 + 核心脚本）。以下文件在清单之后新增：

| 文件 | 作用 |
|---|---|
| `docs/PROTOCOL_AMENDMENT_A3_CORPUS_IDENTITY.md` | 语料身份更正 + MI 来源披露 |
| `docs/PROTOCOL_AMENDMENT_A2_FAMILY_REDUCTION.md` | confirmatory 家族 156 → 12 |
| `reports/CPSC_OFFICIAL_DEFINITION_VERDICT_2026-09-16.md` | 编码裁决完整证据链 |
| `tests/test_data.py` | 含钉死 `SUBSPACE_CPSC` 顺序的回归测试 |
| `scripts/reproduce_main_endpoint_both_encodings.py` | 主终点双编码复现 |
| `scripts/verify_main_from_transfer.py` | 60 格复算 + `label_map` 编码核验 |
| `scripts/verify_cpsc_corpus_identity.py` | 语料身份只读核验 |
| `scripts/audit_temperature_csv_caliber.py` | 温度 CSV 口径判定 |
| `scripts/emit_contamination_provenance.py` | 污染边车生成 |
| `results/strengthening_battle_corrected.PROVENANCE.json` | JSON 字段级口径判定 |
| `checkpoints/e2_probs_cache/_CONTAMINATION_NOTICE.md` | npz 标签污染通知 |

## 4. 清单自身的一处过期字段

`docs/osf_archive_manifest.json` 的 `"target_venue": "BSPC (中科院二区)"` 已过期：
目标期刊 2026-09-16 改为 **CMPB**（Computer Methods and Programs in Biomedicine）。

**处理方式：不修改该字段。** 清单记录的是"2026-09-16T02:44Z 那一刻我们相信什么"，
这是历史事实，保留才有审计价值。更正写在 `_post_manifest_corrections` 字段与本文件中。

## 5. 结论

- 预注册协议快照**零改动**，完整性未受影响。
- 6 个漂移文件中，`mapping.py` 是**修复**（把损坏版改回训练实际使用的编码，数值不变）；
  三个脚本加的是**防重演的守卫**；`summarize_l2_shifts.py` 是守卫重写；
  `main_bspc.tex` 是**措辞更正 + 新增披露 + 补引用 + 换期刊**。
- **无任何文件丢失，无任何已发布数值因这些改动而改变**（60 格主终点逐位复现，
  max|Δ| = 1.110e-16）。
- 唯一会真正改变数值的动作是**独立于清单的检查点重训**（见
  `reports/CHECKPOINT_INDEPENDENCE_AUDIT_2026-09-17.md`），其影响范围已单独界定为
  `cpsc_ptbxl/inceptiontime/seed{42,43}` 两格。
