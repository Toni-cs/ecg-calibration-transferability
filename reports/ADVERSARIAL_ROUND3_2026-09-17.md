# 第三轮对抗审查（R3）—— 五代理互相唱反调

- 日期：2026-09-17
- 对象：**第二轮（R2）新产生的论断**，以及 R2 对 R1 的修正本身
- 仓库：`D:\A1\ecg-lab-v2`，起点提交 `1840a20`
- 方法：5 个**只读**对抗代理（R3-A…R3-E）并行，每个被指派去**证伪**一条承重论断；
  主代理对每一条承重证伪**亲自独立复算**后才采信
- 负载约束：BiMamba 网格在跑（2 个 python 进程），全部代理禁跑写盘脚本

> 上一轮有个攻击者运行 `scripts/run_e1b_loco_validation.py`，把
> `results/deployment_loco_validation.csv/.json` 覆盖掉了。本轮把
> 「**禁止运行任何写 results/ 的脚本**」写成硬约束的第一条。

---

## 1. 裁决总表

| 代理 | 被攻击的论断 | 判定 |
|---|---|---|
| **R3-A** | 安全率 `0.0064 = 1/157` 的分解「157 = 2 seeds × 1 architecture」 | ❌ **FALSIFIED** |
| **R3-B** | `0.1038` 不可复现；多口径 RMSE；「失败分支修正前后未变」 | ❌ **FALSIFIED** |
| **R3-C** | `sign(ΔECE) = sign(T−1)` 是**逻辑等价/同义反复** | ❌ **FALSIFIED** |
| **R3-D** | `ρ=+0.31` 是「误差 vs \|ΔECE\|」的关联；`κ=0` | ❌ **FALSIFIED** |
| **R3-E** | (A) 主终点 `+0.015863`；(B) 论文 L1904 的 `+0.0009/0.010` 有表支撑 | (A) ✅ **SURVIVED** / (B) ❌ **FALSIFIED** |

**5 个代理全部至少打掉一条。** 其中 4 条是**我自己在 R2 里刚写下的东西**。

---

## 2. 主代理的独立复核（不采信代理的一面之词）

### 2.1 复现基线：`smooth_ece` 逐位复现 ✅

脚本 `_attack_scratch/R3VERIFY/verify_r3b.py`。修正一处**我自己的调用口径错误**
（把类别索引当二值标签传入；`smooth_ece` 要的是 `y = (argmax == label)`）：

```
V1: smooth_ece 复现 (n=62)
  raw       max|Δ| = 0.000e+00
  stage1_ts max|Δ| = 0.000e+00
```

⇒ `results/ablation_ts_components.OLD_ENCODING.csv` 与缓存 probs 完全自洽，
主终点管线可信。**这也顺带证实 `delta_obs_orig` 就是该表的 `raw − stage1_ts`。**

### 2.2 R3-C 的反例：**逐值命中** ✅（决定性）

对 62 个 cell 施加**固定** `T = 2.0`（远在拟合温度范围 [0.932, 1.498] 之外）：

```
ΔECE(T=2.0) = se_raw − se_T2 < 0 的 cell 数 = 5/62
  cpsc->chapman/inceptiontime/s42  ΔECE=-0.0314   T_src=1.030
  cpsc->chapman/inceptiontime/s44  ΔECE=-0.0551   T_src=1.076
  cpsc->chapman/resnet1d/s42       ΔECE=-0.0559   T_src=0.993
  cpsc->chapman/resnet1d/s45       ΔECE=-0.0590   T_src=1.098
  ptbxl->chapman/resnet1d/s42      ΔECE=-0.0063   T_src=1.108
```

**这 5 个 cell 与 R3-C 报的一模一样、数值逐位相同。**

⇒ `T > 1` **不能**推出 `ΔECE > 0`。`sign(ΔECE) = sign(T−1)` 在 60/60 成立，
是**拟合温度恰好落在 [0.932, 1.498] 区间**的经验结果，**不是数学恒等**。

**编码敏感性对照**：

| 温度来源 | sign 一致率 |
|---|---|
| OLD 编码温度（正确） | **62/62** |
| NEW 编码温度（错） | **56/62** |

对编码敏感 ⇒ 非定义使然。

### 2.3 R3-E(B)：论文 AUROC 数字**错**，且可修 ✅

`results/discrimination_metrics_60exp.OLD_ENCODING.csv` 原状态：

- `auroc_ts_minus_raw` **124/124 全空**
- **表内只有 `variant=raw` 行** ⇒ 结构上不可能有 TS−raw 差值
- 生成脚本 `recompute_discrimination_old_encoding.py:116` **硬编码 `""`**

我用 `apply_temperature`（多分类 = `p^(1/T)` 逐行归一）从缓存 probs 复原 TS 概率，
真实算出该列：

| 口径 | mean ΔAUROC | max\|Δ\| |
|---|---|---|
| **OLD 标签 + OLD 温度（正确）** | **+0.000355** | **0.001706** |
| OLD 标签 + NEW 温度（对照） | +0.002050 | 0.010477 |
| 论文 R2 注释所写 | +0.000856 | 0.010477 |

⇒ R2 注释里的两个数**不同源**：`0.010477` 只能在**用错温度**时复现，`0.000856` 两个口径都对不上。
**论文正文的 `+0.0009 / 0.010` 必须改成 `+0.0004 / 0.002`。**

### 2.4 R3-A：`157` 的真实分解（整数约束唯一解）✅

`157` 是**质数**，所以「157 = 2 seeds × 1 architecture」算术上不可能。
用 `deployment_metrics.csv` 表 6 自身的边际量做约束：

- 12 个非 fs250 档：各 `12 × 8 − 2 = 94`
- fs250：`13 × 8 − 2 = 102`
- 每方法（非 matrix）= `12×12 + 13 = 157`；matrix = `12×10 + 11 = 131`
- 合计 `12×94 + 102 = 1230 = 7×157 + 131` ✅（三处独立自洽）

⇒ **`157 = 144 + 13`**：两种子快照在 `fs250` 档多出 **1 个 (pair,seed)**，
是残缺网格产物。**论文原解释错误。**

洁净性证据也比 R2 说的更硬：该 CSV **受 git 跟踪**，HEAD blob 与工作区**逐字节相同**，
提交 `dd96647` 时间 `2026-09-08 21:54:58` < 污染窗口起点 ⇒ **不依赖可被 `touch` 的 mtime**。

### 2.5 R3-E(A)：主终点成立 ✅

```
n main = 60
mean delta_obs_orig = +0.015862645     （51/60 正；IT 27/30、R1D 24/30）
独立复现 4/4 cell（含 1 个 5 类）：max|Δ| = 1.11e-16
```

但发现**两条未披露的内部不自洽**：

1. **`T` ≡ T_new，而 `raw_ood_orig`/`cal_ood_orig` 用 T_old** →
   `(T, raw_ood_orig, cal_ood_orig)` **不可联合复现**。实测：
   `max|JSON.T − T_new| = 4.8e-07`，`max|JSON.T − T_old| = 2.97`，
   `corr(T_old, T_new) = 0.300`。按 `JSON.T` 复算 cell 1 得 `+0.0829` 而非 `+0.0139`。
2. `nb_gain` 自洽（max|Δ|=1.11e-16），非缺陷。

---

## 3. 代理提出、但**我复核后判定代理自己也不够准确**的地方

| 代理 | 代理的说法 | 复核结论 |
|---|---|---|
| R3-A | 「第 4 列是 n_safe=1，断言把它读成 1 unsafe」 | ✅ 代理对。**我的**措辞错，已改 |
| R3-B | 「真 LOO 下仿射 0.014519（0.9998×）」 | ⚠️ 比值分母混用。**用留一常数 0.014768 算是 0.983×（改善 1.7%）**；代理的 7.07× 也用了样本内常数做分母 |
| R3-B | 「分解模型不存在独立的失败分支」 | ✅ 成立。唯一注册分支在 §8.5；分解模型只是「strengthen」它 |
| R3-C | 「60/60 的充要条件是 T_src ≤ T*」 | ✅ 与我实测一致（未删失 19/19 > 1，min 1.25） |
| R3-C | 「T\* 是网格产物，非真最优」 | ✅ 成立。网格手挑 9 点、上界 2.0，41/60 被钉在 2.0 |
| R3-D | 「论文引用的是 Spearman(pred, y)，不是 corr(误差,\|ΔECE\|)」 | ✅ **代理对**。论文措辞（L1545-1548「rank correlation with the true ΔECE_OOD」）**本身正确**；错的是我对它的转述。`corr(err,\|y\|)` 实测 Pearson +0.0764（p=0.56）、Spearman +0.2020（p=0.12），**论文没有引用过这个量** |
| R3-D | 「κ=0 只是审计注释里的记号」 | ✅ 成立。仓库的 κ 是 `rebuild_shapley_crossfit.py:195` 的 hack（只返回 0.0 或 −1），**从未进论文正文**；真 Cohen's κ 复算确为 0.0000 |

---

## 4. 落地修复（全部已验证）

| # | 修复 | 证据 |
|---|---|---|
| 1 | `recompute_discrimination_old_encoding.py` 扩写：**同时输出 `variant=ts` 行**并真实填充差值列 | 248 行（124 raw + 124 ts）；**raw 行逐字段零差异**；差值列 **0 空值** |
| 2 | 论文 L1904：`+0.0009/0.010` → **`+0.0004/0.002`** | 编译 66 页 / 0 undefined |
| 3 | 论文 §(ii) 重写：删掉逻辑上无效的「A fixed-direction artefact cannot produce a sign that flips with T」，改为**可证伪的经验规律**并披露 T=2.0 反例 | 同上 |
| 4 | 论文 157 段重写：`157 = 144 + 13`，并披露 **1/157 对四法相同**（非 TS 独有） | 同上 |
| 5 | `ADVERSARIAL_ROUND2` 的 RMSE 比值列**统一分母** + 补 **LOO 口径** | 仿射改善 2.86%→**1.68%**，**R²_oos = 0.00035** |
| 6 | `CMPB_STRENGTHENING_VERDICT` 的 `+0.29` 归属：`c3_crossfit_results.csv` → **`strengthening_battle_corrected.json`** | mean +0.2856 / median +0.2913 |
| 7 | `strengthening_battle_corrected.json` **增量补 `T_old`**（不动 `T`，避免破坏消费者） | 62/62 补全；主终点仍 +0.015862645；已备份 `.bak_before_T_old` |
| 8 | 本轮报告 | 本文件 |

---

## 5. 残余不确定（诚实列出）

1. **`157` 的逐 cell 清单已不可重建**：磁盘上的 `l2_shift_results.json` 现为 5 种子全量
   （`ts` 有 **390** 个 (pair,seed,shift)），09-05 快照被 09-10 覆盖。
   上面的 `144+13` 是**边际量约束下的唯一整数解**，不是逐行核对。
2. **`T*` 的上界 2.0 是人为网格**，`T* > 1` 在 60/60 成立但 41/60 右删失；
   未删失的 19 个 cell 全部 > 1（min 1.25）——删失**没有**制造这个结论，但幅度不可信。
3. **`ρ=+0.31` 是 Spearman**，Pearson 只有 +0.2371（p=0.068，不显著）。论文只报 Spearman，
   应显式注明统计量名。
4. **`0.1038` 仍不可从当前输入重算**（编码护栏会让 `load_l2_data()` 直接 raise）；
   它本身在仓内（`predictability_3arch.csv` 与补充材料副本 md5 相同）。措辞应为
   「**不可从当前输入重算**」，而非「仓内无此数」。
5. **分解模型的样本外解释力 ≈ 0**（仿射 R²_oos = 0.00035）——这是本文真实短板，
   已写进报告，**不可**用「仿射能救」来软化。

---

## 6. 本轮驱动的待办

- ⏳ `docs/osf_archive_manifest.json` 的 `post_manifest_corrections` 需**再增 3 条**
  （本轮改了 `strengthening_battle_corrected.json`、`discrimination_metrics_60exp.OLD_ENCODING.csv`、
  `ablation_ts_components.OLD_ENCODING.csv` 未变但被新脚本读）。
- ⏳ 补充材料 S2 里的 `discrimination_metrics_60exp.OLD_ENCODING.csv` 副本需**同步刷新**
  （现在还是 124 行版）。
- ⏳ 论文 §(ii) 引用的「56/62」需在正文脚注给出复现脚本路径。
- ⏳ 重跑 E2 / L2 网格后，`157` 与 `390` 的口径要统一表述（当前 157 只能从 CSV 读）。
- ⏳ 沿用 R2 未完成项：push 两仓库、期刊名切 CMPB、`auprc_ts_minus_raw` 已在本次填好。
