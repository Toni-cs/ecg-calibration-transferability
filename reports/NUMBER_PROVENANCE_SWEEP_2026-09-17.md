# 数字溯源清扫报告

**日期**：2026-09-17
**触发**：本轮已连续发现 6 次由**标签编码错配**导致的数值修正，每次都改动了论文的标题性结论。与其等审稿人发现第 7 次，不如自己系统扫一遍。
**方法**：把论文正文（去注释）中每一个数值声明对回它的源文件，并**验证源文件本身的编码**——而不是只验证"论文抄对了源文件"。

---

## 0. 一句话结论

论文**引用的文件名是干净的**，但**其中两个被引文件本身是污染的**，另有一个关键数字**在仓库内根本没有来源**。三处都已在正文加注，待 L2 网格重跑后统一修复。

---

## 1. 清扫方法

三步，可机械执行：

1. **建立引用图**：从正文（剔除 `%` 注释行与行内注释）抽出所有 `results/` `checkpoints/` `scripts/` `docs/` 路径，还原 `\_` 转义。
2. **标注污染窗口**：根因是 2026-09-09~09-16 期间 `SUBSPACE_CPSC` 为 NEW 编码而模型未重训。以**文件 mtime** 落在窗口内为一级嫌疑。
3. **经验判定**：mtime 只是线索。对每个嫌疑产物，用**不依赖 GPU 的判别法**独立判定（见 §3）。

> ⚠️ 教训：第 1 步的 grep 必须先去注释。首轮用 `grep -o "results/..."` 直接扫全文件，把审计注释里的文件名也算成了"正文引用"，得出"论文引用了 3 个污染文件"的**假警报**。正确做法见 `_sweep_numbers.txt` 的生成方式。

---

## 2. 污染窗口地图（按 mtime）

窗口 = **2026-09-09 ~ 2026-09-16**（NEW 编码生效期；NEW 值 09-14 提交为 `452b3bf`，09-16 由 `72b2e59` 恢复为 OLD）。同一窗口内 09-10 生成的 `ablation_ts_components.csv` 已被三重指纹判定为污染，证明工作区在 09-10 已是 NEW。

| 文件 | mtime | 窗口 | 状态 |
|---|---|---|---|
| `results/deployment_metrics.csv` | 09-05 | 前 | ✅ 干净 |
| `results/predictability_3arch.csv` | **09-05** | 前 | ⚠️ **数字干净，输入已被覆盖 → 不可复现**（§4） |
| `results/c3_crossfit_results.csv` | 09-06 | 前 | ✅ 干净 |
| `results/robustness_validation_5seeds.csv` | 09-08 | 前 | ✅ 干净（主终点源，+0.015863 与 OLD 逐位一致） |
| `results/deployment_holdout_recompute.csv` | 09-08 | 前 | ✅ 干净 |
| `results/c1_brier_reliability.csv` | **09-10** | **内** | ⚠️ 未判定，待查 |
| `results/discrimination_metrics_60exp.csv` | **09-10** | **内** | ⚠️ 未判定，待查 |
| `results/strengthening_battle_corrected.json` | 09-10 | 内 | ❌ 已知（`T`、`delta_obs`） |
| `checkpoints/.../l2_shift_results.json`（60 个） | **09-10~09-13** | **内** | ❌ **本轮新判定**（§3.2） |
| `results/l2_shift_full_390cells.csv` | **09-12** | **内** | ❌ **本轮新判定**（§3.1） |
| `results/l2_shift_full_780cells_detail.csv` | **09-12** | **内** | ❌ **本轮新判定**（§3.1） |
| `results/ablation_ts_components.OLD_ENCODING.csv` | 09-17 | 后 | ✅ 修正表 |
| `results/real_prior_recovery.csv` | 09-17 | 后 | ✅ 干净 |

**论文实际引用的文件**（去注释后）：`l2_shift_full_390cells.csv`（×2）、
`discrimination_metrics_60exp.csv`（×2）、`deployment_holdout_recompute.csv`、
`deployment_metrics.csv`、`ablation_ts_components.OLD_ENCODING.csv`、
`checkpoints/e2_probs_cache/*.npz`。

⇒ 两个 `l2_shift` 引用指向**污染文件**；`discrimination_metrics_60exp.csv` 是**待查项**。

---

## 3. 新判定：L2 移位族全部污染

### 3.1 判定方法（不依赖日期推断）

L2 有 13 档信号扰动。其中 **`noise24`** 在**非 CPSC** 方向（chapman↔ptbxl，两种编码在那里重合）上几乎不改变数值 → 可作为**近恒等档**来标定"该档固有偏离"。再用它判别 CPSC 方向属于哪种口径：

```
d_clean = | L2(cell, noise24) − 干净口径 |
d_cont  = | L2(cell, noise24) − 污染口径 |
```

脚本：`scripts/verify_l2_shift_encoding.py`（写出 `results/l2_shift_encoding_verdict.json`）。

### 3.2 结果

**① 聚合/明细表**（用 `raw_ece` 对 `smooth_ece`）

| 量 | 值 |
|---|---|
| 非 CPSC 20 格固有偏离（median） | **0.0007** |
| CPSC 40 格 \|L2 − 干净\| median | **0.0987** |
| CPSC 40 格 \|L2 − 污染\| median | **0.0012** |
| 比值 | **79×** |
| 逐 cell 与污染口径更近 | **39/40** |

**② 每 cell 的 `l2_shift_results.json`**（用 `delta_ece` 对主终点）

⚠️ 该文件的 `delta_ece` 是**相反符号约定**（`post − raw`），比较前需取负 —— 首轮漏了这一步，得到"0/40 指向污染"的**错误结论**。

| 量 | 值 |
|---|---|
| 非 CPSC 20 格固有偏离（median） | **0.0002** |
| CPSC 40 格 \|L2 − 干净\| median | **0.1693** |
| CPSC 40 格 \|L2 − 污染\| median | **0.0027** |
| 比值 | **62×** |
| 逐 cell 与污染口径更近 | **39/40** |

个例：`cpsc_ptbxl/resnet1d/44` 在 `noise24` 档 `L2 = −0.2898`，
污染口径 `−0.2900`（Δ=0.0002），干净口径 `+0.0049`（Δ=0.2947）。

**两个独立产物族、两种独立方法、同一结论。**

### 3.3 根因（与 ablation 那次不同）

`scripts/eval_l2_shift.py` L85 用**运行时**模块常量重建标签：

```python
subspace = SUBSPACE_CPSC if num_classes == 4 else None
```

它**没有**读 `checkpoints/transfer/**/transfer_result.json` 里自存的 `label_map`
（那 40 个含 CPSC 的 cell 全部是 `{"CD":1,"MI":3,"NORM":0,"STTC":2}` = OLD）。
`SUBSPACE_CPSC` 的时间线（git 证据）：

| 提交 | 日期 | 取值 |
|---|---|---|
| `df9c914` | 08-30 | `("NORM","CD","STTC")` |
| `dd96647` | 09-08 | `("NORM","CD","STTC","MI")` ← OLD |
| `452b3bf` | 09-14 | `("NORM","MI","STTC","CD")` ← **NEW** |
| `72b2e59` | 09-16 | `("NORM","CD","STTC","MI")` ← 恢复 OLD |

⇒ **probs 来自 OLD checkpoint，标签用 NEW 常量重建**，MI↔CD 互换。

---

## 4. 论文摘要的数字在仓库内已不可复现

`scripts/step2_predictability.py` 读的正是 `l2_shift_results.json`。
但 `results/predictability_3arch.csv` 的 mtime 是 **09-05（窗口前）**，
即由**污染前**的输入生成。论文引用的合并 LOO R² = −0.096、CI 上界 **0.104**
与该文件逐位一致（5 处引用，含摘要）。

然而那些**输入已被污染版覆盖**。实测重跑：

| 口径 | TS LOO R² | 95% CI | 上界 < 0.5？ |
|---|---|---|---|
| 论文 / 09-05 历史文件（干净输入，**输入已丢失**） | **−0.0958** | [−0.7199, **+0.1038**] | 是 |
| 重跑于当前污染输入 | **+0.0321** | [−0.7206, **+0.2919**] | 是 |

- **结论方向不变**：两种口径都触发预注册失败分支。
- 但引用的 `0.104` **不可复现**；当前输入给 `0.292`。
- **处置**：`predictability_3arch.csv` 恢复为 09-05 历史版（论文数字的存档）；
  污染重跑版并存为 `predictability_3arch.CONTAMINATED_INPUTS.csv`。

---

## 5. 安全率 0.0064：仓库内无来源

论文 3 处引用（L1201 / L1901 / L1993）"TS safety rate 0.0064"，承载
"TS 不是普遍安全"这一结论。溯源结果：

| 检查 | 结果 |
|---|---|
| 全 `results/` 搜字符串 `0.0064` | 只命中其它列的同名数字子串，**无一是安全率** |
| 含 `safety` 列的文件 | 只有两张 L2 表，取值域 `{0,1}`（780 行中 679 行 = 1，即 **87% 安全**） |
| 反推分母 | `1/157 = 0.0063694 ≈ 0.0064` ⇒ 该数是 **1/157** |
| 论文自述子集 | 6 对 × 2 seed × 13 档 = **156**，**157 多 1，内部不一致** |
| 按论文判据在当前明细表复算 | inceptiontime×seeds42,43 得 **6/156 = 0.0385**；全 780 行 **31/780 = 0.0397** |

⇒ 该数字来自**污染前**的一次运行，产物不在仓库内；当前口径给出约 **6 倍**之值。
方向性结论（安全判据罕被满足）两种口径都成立，但**确切率必须重算**。
已在正文明确标注不可复现。

---

## 6. 已执行的修复

| 动作 | 产物 |
|---|---|
| 新增 L2 污染通告 | `results/_L2_SHIFT_CONTAMINATION_NOTICE.md` |
| 新增 L2 编码判定脚本 | `scripts/verify_l2_shift_encoding.py` → `results/l2_shift_encoding_verdict.json` |
| 恢复历史（干净输入）CSV | `results/predictability_3arch.csv`（09-05 版） |
| 并存污染重跑版 | `results/predictability_3arch.CONTAMINATED_INPUTS.csv` |
| 论文 L2 引用处加溯源注记 | `paper/main_bspc.tex`（覆盖度说明段） |
| 论文安全率加不可复现声明 | `paper/main_bspc.tex`（§deployment） |
| 两段 AUDIT 注释（含复现路径与判定数字） | `paper/main_bspc.tex` |

编译 64 页，0 undefined refs。

---

## 7. 待办（按优先级）

1. **修 `eval_l2_shift.py` 的口径缺陷**：优先读 checkpoint 自存的 `label_map`，
   并加断言（运行时编码必须等于 `label_map`，否则 raise）。**这是根因，不修则下次改
   `SUBSPACE_CPSC` 会再次静默污染。** 同理应审 `run_e2_ablation_discrimination.py`
   与 `step2_predictability.py` 的取数路径。
2. **重跑 L2 网格**（60 cell × 13 档 × 8 方法，需 GPU，约数小时）。跑完后
   `l2_shift_results.json`、两张 `l2_shift_full_*`、`predictability_3arch.csv`
   一并重生，并重算论文所有引用它们的数字（含摘要的 0.104、安全率 0.0064）。
3. **判定两个待查项**：`results/c1_brier_reliability.csv`、
   `results/discrimination_metrics_60exp.csv`（均 09-10，窗口内）。
4. **给每个被引数字建立"来源 + 编码"登记**，纳入投稿前检查单。
5. 复核 `results/deployment_loco_validation.csv`（**09-11**，窗口内，1.08 MB，
   本轮未判定）。

---

# 第二轮（同日续）：根因扩散面、补充材料包、判别力

第一轮把根因定位到 `eval_l2_shift.py` 一处。第二轮发现**这不是一处，是十处**，
并顺带查清了两个待查项、补充材料包的整包状态、以及一个**论文数值被低估**的问题。

## 8. 根因是「同一句代码在 7 个脚本里重复 10 次」

全仓扫描 `subspace = SUBSPACE_CPSC if num_classes == 4 else None`：

| 脚本 | 行 | 是否复用既有 checkpoint | 判定 |
|---|---|---|---|
| `eval_transfer.py` | 102 | 是（`--load-model` 分支） | ❌ 缺陷（**万恶之源**，40 个含 CPSC 的 cell 都经此产出） |
| `run_e1a_l2_shift_full.py` | 335 | 是 | ❌ 缺陷（两张 `l2_shift_full_*` 的生产者） |
| `run_e1b_loco_validation.py` | 191 | 是 | ❌ 缺陷 |
| `run_e2_ablation_discrimination.py` | 394 | 是 | ❌ 缺陷 |
| `run_e3_brier_dcr_ncv.py` | 528 | 是 | ❌ 缺陷 |
| `run_e4_temperature_analysis.py` | 267 | 是 | ❌ 缺陷（3 份温度 CSV 的生产者） |
| `run_e5_inception_lite.py` | 396 | 否（全新训练） | ✅ 无风险（自洽） |
| `run_e5_inception_lite.py` | 536 | 是 | ❌ 缺陷 |
| `run_e5_inception_lite.py` | 635 | 是（源模型来自 536） | ❌ 缺陷 |
| `run_e6_reliability_diagrams.py` | 538 | 是 | ❌ 缺陷（70 张可靠性图的生产者） |

**结论**：这不是"某个脚本写错了"，而是**同一个口径缺陷被复制了 10 份**。
只要 `SUBSPACE_CPSC` 改动而模型未重训，任何一处被调用都会静默产出污染值 ——
这正是"六个数字各自独立出错"的机制。

### 8.1 修复方式：抽成唯一实现

新增 `src/utils/encoding_guard.py`（唯一实现），10 处全部改为调用它：

* `checkpoint_subspace(run_dir, num_classes, runtime_subspace)`
  —— 以 checkpoint 自存的 `transfer_result.json:subspace` 为**唯一权威**，
  与运行时不一致即 `raise`；`num_classes != 4` 直接返回 `None`。
* `assert_cache_encoding(...)` —— 缓存必须带 `label_encoding` 戳，无戳即拒绝。
* `assert_encoding_record(...)` —— 下游消费者校验 JSON 记录的编码戳。
* `encoding_stamp(num_classes, subspace)` —— 规范化编码戳字符串。

`step2_predictability.py` 作为**下游消费者**，现在要求 `l2_shift_results.json`
带编码戳，否则 `raise`。

### 8.2 护栏实测

| 测试 | 结果 |
|---|---|
| 全部 63 个 checkpoint 目录过 `checkpoint_subspace` | **62 PASS / 1 RAISE**（唯一 RAISE = 正在跑的 `chapman_cpsc/mamba/seed42`，无 `transfer_result.json` ⇒ 正确地拒绝） |
| `run_e1a --dry-run` | **60/60 `[pending]`**（修复前会因形式检查通过而全部 `[complete]`，静默复用污染 JSON） |
| `step2_predictability.py` 直接运行 | `raise`（拒绝 09-10~09-12 那批无戳 JSON） |
| 无戳缓存 / 戳不符缓存 / 无戳 JSON 记录 | 三种均正确 `raise`；`allow_unstamped=True` 可显式放行 |
| 真实缓存 `chapman_cpsc_resnet1d_seed42.npz` | 正确 `raise` |

**关键设计**：`is_checkpoint_complete()` 新增判据 0（编码戳匹配），
所以**断点续传不再复用污染文件** —— 这是让护栏真正生效的一环，
否则形式检查（13 档齐全、字段完整）会放过全部污染 JSON。

## 9. 第一轮两个待查项的裁决

### 9.1 `discrimination_metrics_60exp.csv`（09-10 12:45）→ ❌ 污染

输入是 `checkpoints/e2_probs_cache/*.npz`，**全部 62 份 mtime = 09-10 12:30~12:40**
（窗口内），probs=OLD / labels=NEW。逐位实证：

```
chapman_cpsc / inceptiontime / seed42 / split=cal / variant=raw
  缓存原样（NEW 标签）AUROC = 0.641959   ← 与 CSV 所载 0.641959 逐位相同（差 0.000000）
  swap13（OLD 标签）  AUROC = 0.861000   ← 正确值，高 0.219
```

逐方向 OOD AUROC 均值：**0.629–0.792 → 0.735–0.843**
（chapman→cpsc 0.674→0.755；cpsc→chapman 0.631→0.825；cpsc→ptbxl 0.642→0.804；
ptbxl→cpsc 0.629→0.843；两个 5 类方向逐位不变）。

**论文暴露**：L1840 "AUROC ranges from 0.629 (CPSC→Chapman) to 0.795"、
L1974 "OOD AUROC means range 0.629--0.792" —— 后者**精确复现污染表**。
原句的方向归属亦有误（0.629 实为 PTB-XL→CPSC）。

**已修**：生成修正表 `results/discrimination_metrics_60exp.OLD_ENCODING.csv`
（`scripts/recompute_discrimination_old_encoding.py`，124 行 = 62 cache × {cal,test}，
仅 `variant=raw`；40 个 4 类 cache 重编码、22 个 5 类 cache 逐位不变），
论文 L1840/L1974 已改为 0.735–0.843 并改引修正表。

**注**：`mean ΔAUROC_TS−raw ≈ −0.001` 的声明**仍然有效**（温度缩放是逐样本单调变换，
与标签编码无关）；"AUROC 对标签置换不变"这一直觉**是错的**（逐类 OvR 依赖列—类对应）。

### 9.2 `c1_brier_reliability.csv` / `c1_dcr_ncv*.csv`（09-10 12:29）→ ❌ 冒烟 + 窗口内

两个独立缺陷：

1. **规模**：输入 `checkpoints/transfer/**/e3_probs.npz`，**全部 60 份 mtime = 09-10 12:24**
   （窗口内），且每个 split **只有 n=20 条**（`cal/id/ood` 全为 20）。
   生产者 `--limit` 默认 `None`，该批显然用了很小的 `--limit`（≤83）。
   `c1_brier_reliability.csv` 亦自报 `n_id=n_ood=20`。
2. **编码**：同 9.1 的错位模式（运行时 NEW 标签配 OLD checkpoint）。

**论文暴露**（逐位来自 `c1_dcr_ncv_summary.csv`）：

| 数值 | 次数 |
|---|---|
| OOD NCV `+0.008125` | 3 |
| ID NCV `−0.006292` | 1 |
| DCR OOD `+0.016667` | 1 |

**另发现一处标错名**：论文 L1909 把 C1 称作 "Brier reliability main claim"，
但 §intro 对 C1 的定义是 "Primary OOD benefit"（终点 `ΔECE_OOD`，51/60 正），
而 `c1_brier_reliability.csv` 自身给出的是 **44/60 为正**。
审稿人对照补充材料时会发现 51/60 ≠ 44/60。**已改为按 C1 的真实定义表述。**

通告：`results/_C1_DCR_NCV_SMOKE_NOTICE.md`。

## 10. 新发现：补充材料包整包落在窗口内

`paper/submission/supplementary/`（打包 **09-13 20:06**）共 159 个文件，
**80 个 mtime 落在窗口内**：

* **16 张 S2 结果表** —— 其中 6 个已确认污染（`ablation_ts_components.csv`、
  两张 `l2_shift_full_*`、温度族 3 件）、3 个本轮确认（`discrimination_metrics_60exp.csv`、
  `c1_brier_reliability*`、`c1_dcr_ncv*`）、1 个待裁决
  （`deployment_loco_validation.csv`，09-11，n_target=2120 **全量**但由带缺陷脚本产出）、
  2 个冒烟/空占位（`deployment_loco_validation_smoke.csv` n=20、
  `c3_inceptiontime_lite_30exp.csv` **0 数据行**）。
* **70 张 S4 可靠性图 PDF**（09-12）—— 生产者 `run_e6_reliability_diagrams.py`
  带同一缺陷 ⇒ 4 类方向的曲线画在错位标签上。

**`SHA256SUMS.txt`（09-13）把这些污染值钉进了哈希清单。**

**好消息**：`S3_per_experiment/**/transfer_result.json` 共 60 份
**mtime 全部 = 09-08**（窗口前），其自存的 `subspace` 是窗口前的权威编码记录，
也是本轮全部裁决的立论基础。`EXPERIMENT_PROTOCOL.md` 虽 mtime 09-09，
但**哈希与 manifest 钉住的 `0e8afa92…` 逐位一致**（内容未变）。

通告：`results/_SUPPLEMENTARY_WINDOW_NOTICE.md`。

## 11. 新发现：`osf_archive_manifest.json` 漂移 5 处

manifest 钉住 14 个文件，**5 个已漂移**（4 个是本轮/上轮有意修改，1 个是 09-16 的编码回退）：

| 文件 | pinned | now |
|---|---|---|
| `paper/main_bspc.tex` | `ae24f68ee172` | `6ea10b785d24` |
| `scripts/eval_transfer.py` | `06860d8b9abd` | `24178dd2da1a` |
| `scripts/eval_l2_shift.py` | `369d8d959d72` | `603e48d1cf55` |
| `scripts/step2_predictability.py` | `ace6a52c32bc` | `62a811ec02c4` |
| `src/data/mapping.py` | `649bde9e4e13` | `df56ae645fb5` |

仍应**加 `post_manifest_corrections` 字段记录"清单后改动"**，而非静默重生成。

## 12. 第二轮已执行的修复

| 动作 | 产物 |
|---|---|
| 新增共享编码护栏 | `src/utils/encoding_guard.py` |
| 10 处缺陷点全部接入护栏 | `eval_transfer.py` / `eval_l2_shift.py` / `run_e1a_l2_shift_full.py` / `run_e1b_loco_validation.py` / `run_e2_ablation_discrimination.py` / `run_e3_brier_dcr_ncv.py` / `run_e4_temperature_analysis.py` / `run_e5_inception_lite.py`(×2) / `run_e6_reliability_diagrams.py` |
| 断点续传加编码戳判据 | `run_e1a_l2_shift_full.py::is_checkpoint_complete`（判据 0） |
| 写 JSON 时落编码戳 | `eval_transfer.py`、`eval_l2_shift.py`、`run_e1a_l2_shift_full.py` |
| 缓存读写两侧加戳 | `run_e2_ablation_discrimination.py`（+ `--allow-unstamped-cache`）、`run_e3_brier_dcr_ncv.py` |
| 下游消费者要求戳 | `step2_predictability.py` |
| 判别表 OLD 编码修正版 | `results/discrimination_metrics_60exp.OLD_ENCODING.csv` + `scripts/recompute_discrimination_old_encoding.py` |
| 论文 AUROC 范围修正 | `paper/main_bspc.tex` L1840、L1974（0.629–0.792 → 0.735–0.843） |
| 论文 C1 标错名修正 | `paper/main_bspc.tex` L1909 |
| 三份新通告 | `_DISCRIMINATION_CONTAMINATION_NOTICE.md`、`_C1_DCR_NCV_SMOKE_NOTICE.md`、`_SUPPLEMENTARY_WINDOW_NOTICE.md` |

编译 **65 页，0 undefined refs**。

## 13. 第二轮后的待办（按优先级）

1. **重跑 L2 网格**（60 cell × 13 档 × 8 方法，需 GPU）→ 重生
   `l2_shift_results.json`、两张 `l2_shift_full_*`、`predictability_3arch.csv`，
   并重算论文所有引用处（含摘要 `0.104`、安全率 `0.0064`）。
   *护栏上线后重跑是安全的：旧 JSON 无戳，`is_checkpoint_complete` 会判为不完整。*
2. **重跑 E3（全量 n）** → 替换 OOD/ID NCV 与 DCR 三个数值。
3. **重跑 E2/ablation** → 用 `--no-cache` 清掉 09-10 那批无戳缓存，
   重生 `ablation_ts_components.csv` 与 `discrimination_metrics_60exp.csv` 全 variant。
4. **裁决 `deployment_loco_validation.csv`**（09-11，全量，带缺陷脚本）。
5. **重跑 E4 温度族 + E6 可靠性图**（各 3 件 / 70 张）。
6. **重新组装补充材料包并重签 `SHA256SUMS.txt`**；移除
   `c3_inceptiontime_lite_30exp.csv`（空）与 `deployment_loco_validation_smoke.csv`（n=20）。
7. **`osf_archive_manifest.json` 加 `post_manifest_corrections`**（现有 5 处漂移）。
8. 投稿前检查单：**每个被引数字登记"来源文件 + 编码戳 + 规模(n)"三项**。

