# OSF 归档清单：清单后更正记录

> ⚠️ **已被取代（2026-09-17）**：本记录写作时只观察到 **2** 个漂移文件；当晚后续提交
> 使漂移数升至 **6**（新增 `scripts/eval_transfer.py`、`scripts/eval_l2_shift.py`、
> `scripts/step2_predictability.py`、`scripts/summarize_l2_shifts.py`）。
> **完整版请见 `docs/OSF_MANIFEST_POST_CORRECTIONS_2026-09-17.md`。**
> 本文件保留为"当时知道什么"的历史记录，不作修改。

> **清单**：`docs/osf_archive_manifest.json`（时间戳 `2026-09-16T02:44:47Z`，14 个文件）
> **本记录日期**：2026-09-16
> **性质**：清单是"某一时刻的快照"。**本记录不修改该快照**，只登记快照之后发生的变化，
> 使读者能把"清单里记的是什么"与"仓库现在是什么"对上。
> **复现**：`python scripts/audit_manifest_drift.py`（只读）

---

## 1. 汇总

| 类别 | 数量 |
|---|---|
| 哈希未变 | **12 / 14** |
| 哈希已变 | **2 / 14** |
| 清单中已不存在 | **0 / 14** |

**关键：`docs/EXPERIMENT_PROTOCOL.md` 哈希未变**，即预注册协议快照本身**完整未被触碰**
（sha256 `0e8afa923986aba3f5030133c59b8a87b475c3551b819b0137ab9da66eeb9498`，52,641 字节，
与其三份副本字节相同）。本项目的做法是：**协议永远不改，改动一律另立修订案**（A1 / A2 / A3）。

## 2. 已变文件（2 个）

### 2.1 `src/data/mapping.py`

| | |
|---|---|
| 旧 sha256 | `649bde9e4e13ffd31ab77b9cad8b21d372e495a2fa0cda52d8658b50686b2db2` |
| 新 sha256 | `df56ae645fb503bb74dae5cc7d92df3909e2a85207dcbe292c87e95d230b92db` |
| 大小 | 30,018 → 32,857 字节 |

**原因**：清单钉住的是 **2026-09-09 的损坏版本**——该版本把
`SUBSPACE_CPSC` 改成了 `("NORM","MI","STTC","CD")` 却未重训模型。
2026-09-16 已**回退**至模型实际训练顺序 `("NORM","CD","STTC","MI")`，
并加长注释说明"顺序即编码"、补 `CPSC_TO_SUPERCLASS` 的死代码标注与语料身份说明。

**重要**：回退**不改变任何已发布数值**。回退后 60 格主终点仍逐位复现
（mean `+0.015863`，max\|Δ\| = `1.110e-16`）。换言之，清单里的那一版是错的，
当前这一版才对；这是**修复**，不是变更分析。

### 2.2 `paper/main_bspc.tex`

| | |
|---|---|
| 旧 sha256 | `ae24f68ee1721551a38d59f78ed511aea68a3f13fc7d5aaaf8d573af3bcf9937` |
| 新 sha256 | `2f91a65bcfe0e138d67fdc6649e0aef4ff38eae844f97324fb8e116a427961f8` |
| 大小 | 111,108 → 114,965 字节 |

**原因**（三组改动，均见修订案 A3 与提交历史）：

1. **语料身份更正**：`CPSC2018+2019` → `CPSC2018`（CPSC Database + CPSC-Extra），
   涉及摘要、数据集列表、类别词汇表段落、数据可用性共 4 处；§Data 补记录数、
   MI 来源披露、superclass 归属声明。
2. **补 CPSC 引用**：此前论文**完全没有 CPSC 参考文献**，新增
   `liu2018cpsc`、`physionet2020cpsc`。
3. **新增 §"Pre-registration amendment A3"**，并在参考文献中加入 A3 条目。
4. 目标期刊由 BSPC 改为 CMPB（`\journal{}` 与相关注释）。

页数 58 → 59（pdflatex 两遍，0 undefined references）。

## 3. 清单未收录、但属分析关键路径的新增文件

清单是 14 个文件的**子集**（它记录的是协议 + 核心脚本），以下文件在清单之后新增，
建议在下次归档时一并纳入：

| 文件 | 作用 |
|---|---|
| `docs/PROTOCOL_AMENDMENT_A3_CORPUS_IDENTITY.md` | 语料身份更正 + MI 来源披露 |
| `docs/PROTOCOL_AMENDMENT_A2_FAMILY_REDUCTION.md` | confirmatory 家族 156 → 12 |
| `reports/CPSC_OFFICIAL_DEFINITION_VERDICT_2026-09-16.md` | 编码裁决完整证据链 |
| `tests/test_data.py` | 含钉死 `SUBSPACE_CPSC` 顺序的回归测试 |
| `scripts/reproduce_main_endpoint_both_encodings.py` | 主终点双编码复现 |
| `scripts/verify_main_from_transfer.py` | 60 格复算 + label_map 编码核验 |
| `scripts/verify_cpsc_corpus_identity.py` | 语料身份只读核验 |
| `scripts/audit_temperature_csv_caliber.py` | 温度 CSV 口径判定 |
| `scripts/emit_contamination_provenance.py` | 污染边车生成 |
| `results/strengthening_battle_corrected.PROVENANCE.json` | JSON 字段级口径判定 |
| `checkpoints/e2_probs_cache/_CONTAMINATION_NOTICE.md` | npz 标签污染通知 |

## 4. 清单自身的一处过期字段

`docs/osf_archive_manifest.json` 的 `"target_venue": "BSPC (中科院二区)"` 已过期：
目标期刊 2026-09-16 改为 **CMPB**（Computer Methods and Programs in Biomedicine）。

**处理方式：不修改。** 清单记录的是"2026-09-16T02:44Z 那一刻我们相信什么"，
这是历史事实，保留才有审计价值。本记录即为对该字段的更正说明。

## 5. 结论

- 预注册协议快照**零改动**，完整性未受影响。
- 2 个漂移文件中，`mapping.py` 是**修复**（把损坏版改回训练实际使用的编码，数值不变）；
  `main_bspc.tex` 是**措辞更正 + 新增披露 + 补引用 + 换期刊**。
- 无任何文件丢失，无任何已发布数值改变（60 格主终点逐位复现，max\|Δ\| = 1.110e-16）。
