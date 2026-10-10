# `e2_probs_cache` 标签编码修复与 2 格重建：审计通知

**日期**：2026-09-18
**触发**：重训 `cpsc_ptbxl/inceptiontime/seed{42,43}` 后，追查哪些产物仍依赖那 2 格
**结论**：缓存有两个**互不相关**的缺陷 —— 2 格缺失、38 格标签错位。两者都已修复并独立验证。
**影响面**：`real_prior_recovery.csv`（已恢复可复现）、`rebuild_shapley_crossfit.*`（原产物确认污染）、`noise_floor_curve.csv`、`bootstrap_diagnostics.csv`、`c3_crossfit_results.csv`、`c4_resnet1d_8method.csv`（均已按干净缓存重生成）。

---

## 1. 缺陷一：缓存缺 2 格

`checkpoints/e2_probs_cache/` 有 60 个 npz，但其中 2 个是 BiMamba 玩具格，**60 格正式网格里缺 2 格**：

| 缺失 | 下落 |
|---|---|
| `cpsc_ptbxl_inceptiontime_seed42.npz` | `checkpoints/_retrain_backup_20260917/`（**重训前**版本，2026-09-10 12:36） |
| `cpsc_ptbxl_inceptiontime_seed43.npz` | 同上 |

时间线：09-17 15:22 `real_prior_recovery.py` 曾用含这 2 格的缓存生成过 60 行产物；09-17 20:22 重训流程把这 2 个 npz **移动**到备份目录，缓存自此只剩 58 格正式网格。

**后果**：任何 glob 该缓存的消费者会**静默地**只用 58 格。`real_prior_recovery.py` 与
`rebuild_shapley_crossfit.py` 都直接 glob，**不经过 `encoding_guard`**，因此护栏拦不住。

## 2. 缺陷二：38 格标签错位（与缺陷一无关，此前未登记）

**判定方法**：用缓存自带的 probs，比较「缓存标签」与「`swap13` 后的标签」哪个与
`transfer_result.json` 自报的 `id_acc` / `ood_acc` 吻合。**无需前向推理**，60 格全覆盖。

**判定结果（60/60 格上 `id` 与 `ood` 判定完全一致）**：

| | 格数 | 胜出方 | 胜出时 mean\|Δacc\| | 落败时 mean\|Δacc\| |
|---|---|---|---|---|
| K=4（含 CPSC 的 4 个 pair） | 40 | `swap13` 38 / `as-is` 2 | 0.0069 | 0.13–0.16（≈随机） |
| K=5（`chapman_ptbxl`, `ptbxl_chapman`） | 20 | `as-is` 17 / 平局 3 | 0.0069 | — |

- 判为 `as-is` 的那 2 个 K=4 格，正是本通知第 3 节重建的 2 格。
- 判为 `swap13` 的 3 个 K=5 格实为 `as-is == swap13` 的**平局**（tie-break 取了后者）。
- 逐格实例（`cpsc_ptbxl/inceptiontime/seed44`）：缓存标签给准确率 **0.5073**（随机），
  `swap13` 给 **0.7527**，`transfer_result.json` 自报 **0.7380**。

**结论**：**缓存里的 38 个 K=4 格标签是错的**（与自身 probs 不同编码），22 个 K=5 格正确。
这正是 `results/_L2_SHIFT_CONTAMINATION_NOTICE.md` 记录的 2026-09-10 批次，但此前**只知道
"缓存无编码戳、被护栏拒绝"，不知道错的到底是哪几格、错成什么样**。

**独立佐证**：`scripts/verify_npz_label_encoding.py`（按 `json.methods.ts.ood.raw` 反查）
给出同一划分（修复前 37 SWAP13 + 21 AS-IS + 2 UNKNOWN；2 个 UNKNOWN 是 BiMamba 孤儿）。

## 3. 修复

### 3.1 重建缺失的 2 格 —— `scripts/rebuild_missing_probs_cache.py --apply`

用**产生缓存的同一条前向管线**（`run_e2_ablation_discrimination.load_probs_for_checkpoint`）
重放这 2 格，写入时带上 `label_encoding` 编码戳。

**自我校验**（脚本内置，通过才允许写）：重放 2 个**未被重训**的对照格，
- `cpsc_ptbxl/inceptiontime/seed44`（K=4）
- `ptbxl_chapman/resnet1d/seed42`（K=5）

判据分两层：
- `cal_probs` / `test_probs` **必须逐位一致** → 前向管线与生成缓存时完全相同 ✅
  （实测 max\|Δ\| = 0.000e+00，两种对照均如此）
- `cal_labels` / `test_labels` 必须相等，**或恰为 CD↔MI（1↔3）置换** → 后者即已登记的污染形式 ✅

### 3.2 修复 38 格错位标签 —— `scripts/rebuild_missing_probs_cache.py --fix-labels`

就地做 1↔3 置换，**probs 一字不动**（已证明 probs 与 checkpoint 逐位一致）。
判据：无编码戳 且 `num_classes==4`。实际修复 **38 个**，跳过 22 个 K=5、2 个已带戳。

**反向验证**：修复后 `verify_npz_label_encoding.py` 给出 **60/60 AS-IS**（+2 个 BiMamba UNKNOWN）。

## 4. 修复的影响：哪些数字变了，哪些没变

### 4.1 标签修复对 `real_prior_recovery` **零影响**（可证）

BBSE 的 π̂ 随标签同步置换（混淆矩阵列置换 ⇒ 解置换），而 MAE 是逐类绝对差之和，
对**同时**置换不变。实测（修复前后逐格）：

| 列 | max\|Δ\| | 相对 |
|---|---|---|
| `err_baseline` | 2.78e-17 | 1.7e-16 |
| `err_bbse` | 5.55e-17 | 2.7e-16 |
| `cond_bbse` | 7.68e-10 | 2.4e-14 |
| **`err_em`** | **3.40e-01** | **真实变化** |

**`err_em` 不是置换不变的** —— `fit_em` 是带收敛容差的迭代算法，置换会改变迭代路径
（且它本来就有"1000 次迭代未收敛"的告警）。**论文只引用 BBSE，不受影响。**

### 4.2 2 格重建对 `real_prior_recovery` 的影响：恰 6 个字段

重建前（含重训前的旧 2 格）→ 重建后：60 行中**恰好 6 个字段**变化，全在那 2 格
（`err_bbse`、`err_em`、`cond_bbse` 各 2），**其余 58 行逐位不变**。`err_baseline` 不变
（只依赖标签分布，而数据划分未变）。

**最终可复现数值**（论文原文：0.1132 / 0.1916 / 40.9% / 56/60）：

| 量 | 值 |
|---|---|
| 格子总数 | 60 |
| 源先验基线 MAE | **0.1916** |
| BBSE MAE | **0.1127** |
| 相对降低 | **41.2%** |
| BBSE 优于基线 | **56/60** |
| BBSE 优于 EM | 38/60 |
| cond > 1e4 | 1/60 |

### 4.3 `rebuild_shapley_crossfit.*`：原产物**确认是污染版**

09-16 15:13 的产物 `delta_obs_orig` 均值 = **+0.1066**、T 中位数 **2.49**、T≥2 占 66.7%
—— 这些都是**污染（新编码）口径**的特征值，而论文主终点是 **+0.0154**、T 中位数 **1.08**、
T≥2 占 **0%**。**该产物不可引用。**

在干净缓存上重跑后：

- `delta_obs_orig` 均值 = **+0.015414**，50/60 为正 ——
  与主表 `results/robustness_validation_5seeds.csv` **逐格吻合 60/60，max\|Δ\| = 4.66e-07**
  （即主表 6 位小数的舍入界）。**这是一条完全独立的代码路径复现主终点**（npz + SmoothECE
  vs `eval_transfer.py` 的度量），是本通知最强的一致性证据。
- `corr(delta_obs_orig, T)` = +0.9759（R² = 0.9524），与已知的旧编码口径（+0.9753 / 0.9512）一致。

**但 `delta_pred` 不可用 —— 脚本口径退化（新发现）**：

脚本调用 `decompose_benefit(..., slope=1.0, intercept=0.0)`。`inject_transform` 在
(1.0, 0.0) 下是**恒等变换**，所以

```
shap_s  = 0.000000（全部 60 格）
shap_b  = 0.000000（全部 60 格）
shap_pi = +0.184788  == delta_pred
```

即 `delta_pred` 退化成「仅先验项」，**不是三分量分解**。已加守卫：退化结果默认
**拒绝落盘**（需显式 `--allow-degenerate-injection`）。

**因此本通知不改动论文 §real_shapley 的 +0.29 / +0.31 / 20.86×。** 这三个数字
在三种可构造的配置下都复现不出来：

| 配置 | `delta_pred` | 误差 | RMSE 倍数 | Spearman ρ |
|---|---|---|---|---|
| 干净缓存（本脚本） | +0.1848 | +0.1694 | 13.08× | **−0.2184** |
| 污染缓存（swap13） | +0.1208 | +0.0111 | 1.35× | — |
| 09-16 产物 | +0.1494 | — | — | — |
| **论文 / `strengthening_battle_corrected.json`** | **+0.3015** | **+0.2856** | **20.86×** | **+0.31** |

论文的 ρ = **+0.31** 与本次实测的 **−0.2184**（LOO 全程为负，−0.256…−0.185）**符号相反**；
审计报告自己测得的 `corr(delta_pred, delta_obs_orig) = −0.61` 也是负的。
→ §real_shapley 的重写清单新增一条**最高优先级**项：`delta_pred` 的 `(slope, intercept)`
取值必须先在真实数据上定下口径，再重算全部引用数字。

### 4.4 其余产物（均按干净缓存重生成）

| 产物 | 生成脚本 | 与旧版差异 | 论文引用 |
|---|---|---|---|
| `noise_floor_curve.csv` | `noise_floor_signed.py`（读 npz） | 按 60 格重算 | 仅注释提及 |
| `bootstrap_diagnostics.csv` | `p2_optional_fixes.py`（读主表） | 新文件与主表 **480/480 一致**；旧文件（09-06）有 16 行偏离（= 2 格 × 8 方法，max\|Δ\|=0.233） | 未引用 |
| `c3_crossfit_results.csv` | `p2_optional_fixes.py` | 重生成 | 未引用 |
| `c4_resnet1d_8method.csv` | `p2_optional_fixes.py`（读 `transfer_result.json`） | 重生成，现与权威源一致 | 未引用 |

旧版本一律以 `results/_<name>.PRE_RETRAIN.csv` 保留（只增不删）。

## 5. 复现命令

```bash
PY="C:/python/python.exe"          # 托管 python 无 torch，凡涉 src.* 必须用此解释器

# 1) 自校验（dry-run，不写盘）
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 $PY scripts/rebuild_missing_probs_cache.py

# 2) 重建 2 格（带编码戳）
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 $PY scripts/rebuild_missing_probs_cache.py --apply

# 3) 修复 38 格错位标签（纯 numpy，无需 torch）
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python scripts/rebuild_missing_probs_cache.py --fix-labels

# 4) 反向验证：应为 60/60 AS-IS
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 $PY scripts/verify_npz_label_encoding.py

# 5) 重生成下游产物
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 $PY scripts/real_prior_recovery.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 $PY scripts/noise_floor_signed.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 $PY scripts/p2_optional_fixes.py
```

## 6. 尚未闭合

1. **`rebuild_shapley_crossfit.py` 的 `(slope, intercept)` 口径** —— 决定 §real_shapley 的
   全部数字，是重写清单的阻塞项。
2. **`strengthening_battle_corrected.json` 的 `delta_pred` 仍无来源** —— 全仓无 `.py` 产出它。
3. **BiMamba 2 个孤儿 npz**（`ptbxl_chapman_mamba_seed42/43`）留在缓存里，两个消费者都显式
   过滤，但它们仍是"额外文件"，未来消费者可能忘记过滤。
4. **`real_prior_recovery.py` / `rebuild_shapley_crossfit.py` 不经过 `encoding_guard`** ——
   两者直接 glob npz。建议给它们加一条"必须 60 格、必须带戳或已登记修复"的断言。
