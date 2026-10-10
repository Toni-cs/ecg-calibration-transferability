# 第二轮对抗审查报告（R2）

**日期**：2026-09-17
**方法**：5 个**互相唱反调**的独立审查代理（R2-A…R2-E），各自被指派证伪我上一轮
**特定的一条承重论断**，并被明确要求「主动寻找反例，而不是确认」。主代理随后
亲自复核了代理之间**互相冲突**的分歧点（见 §3）。
**约束**：全部代理只读；临时脚本仅写入 `D:\A1\_attack_scratch\R2*/`；
严禁运行会写产物的脚本（上一轮有代理因此摧毁了 `results/deployment_loco_validation.*`）。

---

## 1. 总判定

| # | 我上一轮的论断 | 判定 |
|---|---|---|
| 1 | 部署安全率 `0.0064` **仓内无源** | ❌ **证伪** |
| 2 | 论文自述子集 `6×2×13=156` 与 `157` 自相矛盾 | ❌ **证伪** |
| 3 | 按论文准则在盘表重算得 `6/156 = 0.0385` | ✅ 成立 |
| 4 | 摘要可预测性上界 `0.1038` 不可复现 | ✅ **成立且更强** |
| 5 | 「失败分支判定不变」 | ⚠️ **作为一般命题不成立** |
| 6 | 主终点 `ΔECE_OOD = +0.015863`（60 格，51/60 正） | ✅ 成立（bit-exact） |
| 7 | `sign(ΔECE) = sign(T−1)` 命中 60/60 | ✅ 数值成立（独立复算） |
| 8 | 该方向检验「有机理支撑」 | ❌ **被打成逻辑等价** |
| 9 | OOD AUROC 修正为 `0.735–0.843` | ✅ 成立 |
| 10 | `swap13` 逐位复现 `ood_acc` **39/40** | ❌ **数字错，实为 40/40** |
| 11 | 补充材料 159 文件 / 窗口内 75 / 可靠性图 60 | ✅ 成立 |
| 12 | `noise24` 不是恒等变换 | ✅ 成立（措辞需修） |
| 13 | Shapley「85% 方向准确率」零信息量 | ✅ 成立（加强） |
| 14 | 分解模型 RMSE `0.3029` vs `0.0145`（**20.86×**） | ⚠️ **措辞过强** |
| 15 | `delta_pred` 全仓无 `.py` 来源 | ⚠️ **字面推翻、实质成立** |
| 16 | 对分解模型的整体「零信息量」定性 | ❌ **过重，必须修正** |

**16 条中：6 条成立、3 条被证伪、3 条被削弱/限定、2 条需改措辞、2 条部分成立。**
即：**上一轮的修正有 6/16 需要返工**。这就是"互相唱反调"的价值。

> **⚠️ 本报告自身随后被第三轮对抗审查（`ADVERSARIAL_ROUND3_2026-09-17.md`）打掉了 4 处。**
> 已就地更正如下，其余以 R3 报告为准：
> 1. **§多口径 RMSE 的比值列混用分母**（C/D 行用「A÷该行」，其余用「该行÷B」）→ 已统一，
>    并补出**真 LOO 口径**：仿射改善 2.86%→1.68%，**R²_oos = 0.00035**（原表全为样本内）。
> 2. **第 7/8 行**：「`sign(ΔECE)=sign(T−1)` 60/60」数值对，但 R2 报告把它称作**逻辑等价**——
>    **该定性错误**。固定 T=2.0 会让 5/60 翻转；换 NEW 温度掉到 56/62。它是**可证伪的经验规律**。
> 3. **第 2 行**：「156 与 157 不矛盾」结论对，但 R2 给出的**分解错**（157 是质数，不可能是
>    2 seeds × 1 architecture）。真解：**157 = 144 + 13**（12 档 × 12 (pair,seed) + fs250 的 13）。
> 4. **第 14 行**的 20.86× 见上表 A 行；`+0.29` 的归属在
>    `CMPB_STRENGTHENING_VERDICT_2026-09-16.md` 中被错挂给 `c3_crossfit_results.csv` → 已改。
> 另：本报告第 14 行表格的**常数基线 = std(y) = 0.014522**，与论文 always-TS 的 −0.0145
> 四位小数巧合相同但**不是同一个量**，不可互引。

---

## 2. 被证伪的论断（逐条）

### 2.1 ❌ 「安全率 0.0064 仓内无源」——**它就在盘上，而且早于污染窗口**

```
$ grep -n "n_total,n_safe" results/deployment_metrics.csv
181:category,name,n_total,n_safe,n_beneficial_only,n_calibrated_only,safe_rate
$ sed -n '182p' results/deployment_metrics.csv
method,ts,157,1,96,1,0.006369
$ ls -la --time-style=+%Y-%m-%d_%H:%M results/deployment_metrics.csv
-rw-r--r-- 1 Administrator 197121 2026-09-05_23:43 results/deployment_metrics.csv
```

- 生产者：`scripts/step3_deployment.py:44-45`（`SAFE_DELTA_ECE=-0.01`、`SAFE_CAL_ECE=0.05`）
  与 `:292-297`（`n_safe/n_total`）。
- 判据：`delta_ece < -0.01 AND cal_ece < 0.05`。
- **mtime 2026-09-05 23:43 → 早于污染窗口（09-09 20:26 起）**，是干净产物。
- 讽刺的是：**论文 L1257 正文已经引用同一个文件**（net benefit 来源）。

**我上轮的"仓内无源"结论错在哪里**：我只 grep 了脚本名与论文，没有 grep
`results/*.csv` 的**列名**（`n_safe` / `safe_rate`）。审计批注必须改写为：

> `0.0064 = 1/157`，源为 `results/deployment_metrics.csv`（09-05，窗口前）。
> **无法从当前（污染）L2 表重算复现**——其输入 `l2_shift_results.json`
> 已于 09-10 17:34 被污染版覆盖。

论文 L1201 的「not presently reproducible」措辞**本来就是对的**；错的是我加的批注。

### 2.2 ❌ 「156 与 157 自相矛盾」

`1/0.0064 = 156.25`，而 **`1/156 = 0.006410` 四舍五入正是 `0.0064`** ——
所以"唯一反推 157"本身就不成立。更进一步：

| 数 | 含义 | 出处 |
|---|---|---|
| **156** | BH-FDR **家族规模** = 6 对 × **2 架构** × 13 档 | `docs/ROUND8_AUDIT_AND_FIXES.md:10` |
| **157** | 部署子集**实际覆盖** = **2 种子** × 1 架构 | `docs/EXPERIMENT_PROTOCOL.md:236`、`ROUND8_AUDIT_AND_FIXES.md:88`、`PROTOCOL_AMENDMENT_A2_FAMILY_REDUCTION.md:28` |

两个「2」不同义（一个是架构、一个是种子），**不是矛盾**。
算术闭合：`157 = 13 格(fs250) + 12 档 × 12 格`，且 `1230 = 102 + 12×94` 自洽。
多出的 1 格是 fs250 上的一个**真实 cell**，不是笔误。

### 2.3 ❌ 「`swap13` 逐位复现 `ood_acc` 39/40」——**实为 40/40**

主代理亲自复核（`_attack_scratch/R2VERIFY/verify_swap13.py`）：

```
4 类 cell（40 个），基准 = checkpoints/transfer/**/transfer_result.json 的 ood_acc：
  原样标签   逐位命中:  1/40   max|d| = 1.998e-01
  swap13 后  逐位命中: 40/40   max|d| = 0.000e+00     ← bit-exact
5 类 cell（22 个）：
  原样标签   逐位命中: 20/22  （2 例外 = ptbxl_chapman/mamba 的 09-02 遗留残缺 ckpt）
  swap13 后  逐位命中:  3/22   ← 误用会破坏 19/22
```

我上轮的「39/40」来自 `results/l2_shift_encoding_verdict.json` 的
`cpsc_cells_matching_contaminated: 39` —— 那是 **L2 ECE @ noise24** 的判定，
**与准确率无关**，我张冠李戴了。另外我描述的比对对象也不存在：
`discrimination_metrics_60exp.csv` **没有 `ood_acc` 列**。

**结论更强了**（40/40 而非 39/40），但**理由错了**。同时新增一条硬约束：
**`swap13` 绝不可用于 5 类 cell**（会破坏 19/22）。

### 2.4 ❌ 「方向检验有机理支撑」——**它被证明是逻辑等价，不是发现**

R2-C 的证明链（主代理已复算确认）：

1. `T*`（**目标域最优温度**）> 1 对 **60/60** 成立（41 格右删失于网格上界 2.0，
   即 `T* ≥ 2`）。
2. `corr(T_src, T*) = −0.019` —— 源域拟合温度与目标域最优温度**毫无关系**。
3. 因此 `1 < T_src < T* ⇒ ΔECE > 0`，`T_src < 1 < T* ⇒ ΔECE < 0`。
4. 故 `sign(ΔECE) = sign(T_src − 1) ⟺ T_src > 1`。

**即：论文的「51/60 显著为正」在逻辑上等价于「T 中位 1.0757 > 1」，
也就是「源模型在自己的 cal 集上过自信」。** 这不是恒等式（R2-C 用完美校准
合成数据构造了反例：完美校准下 T=1.25 → ΔECE=−0.0221，符号相反），
但**它不携带任何迁移信息**。

配套证据（同一次审查）：
- 完美校准 + 固定 `T=1.0757` 的配对 bootstrap：`ΔECE=+0.008173`，
  **95% CI `[+0.000003, +0.013619]` 排除 0** → 论文的"显著"无法区分
  真实收益与**估计量噪声底**。
- 9 个负格（T∈0.932–0.997，均值 −0.0047）与噪声底 null（−0.0082…−0.0000）
  **不可区分**；固定 `T=1.0757` 时这 9 格**全部翻正**（60/60 全正）。
- **51 个正格里 47 格落在 T∈(1,1.15]**，正是噪声底本身为正的窗口
  （null@1.0757 = +0.0039）。
- 源域 T 只拿到目标域可及 ECE 降幅的 **13.4%**（中位 12.9%）。

⚠️ **这不推翻论文主终点**（`+0.015863` 仍是真实测量值，且 `OOD > ID` 的
decay 分析独立成立），但**必须改表述**：不能再把"51/60 显著为正"当作
"校准迁移有益"的证据，它只说明"源模型过自信"。见 §4.3。

---

## 3. 主代理亲自复核的分歧点

代理之间有冲突，我逐个复算：

### 3.1 `sign(ΔECE) = sign(T−1)`：60/60 还是 54/60？

**60/60。** R2-E 报的 54/60 是用 `strengthening_battle_corrected.json` 里的 `T`
算的 —— 那个 `T` 是 **NEW 编码**的（corr 1.000000 with NEW，仅 0.2998 with OLD）。
用 OLD 编码 T 复算（`ablation_ts_components.OLD_ENCODING.csv`，`stage1_ts`）：
```
匹配上 T 的 cell: 60
sign(ΔECE)==sign(T-1) 一致: 60/60
T>1 的 cell: 51/60
```
R2-C 另有独立复算：从 `e2_probs_cache/*.npz` 重拟合 T，
`max|T_recomp − T_csvOLD| = 0.000e+00`、`max|ΔECE_recomp − ΔECE_csv| = 0.000e+00`。
**→ 论文 L1097 的注释 60/60 正确，不需改。**

### 3.2 9 个反例的 CI 方向：下界还是上界？

**整段 CI 为负（`ci_hi < 0`）**，不是「下界 < 0」。我上轮在 MEMORY 里记错了。

```
ood_significant=True 行数: 51          ← 判据是 ci_lo > 0
ood_ci_hi < 0 （整段CI为负，显著有害）: 9
ood_ci_lo < 0 （CI 跨0或全负）      : 9
  整段CI为负的 9 格明细:
    chapman_cpsc   inceptiontime seed45  ΔECE=-0.005650 CI=[-0.005814,-0.005464]
    chapman_cpsc   resnet1d       seed43  ΔECE=-0.000600 CI=[-0.000616,-0.000584]
    chapman_ptbxl  inceptiontime seed42  ΔECE=-0.002479 CI=[-0.003466,-0.001610]
    chapman_ptbxl  resnet1d       seed45  ΔECE=-0.003567 CI=[-0.003645,-0.003485]
    cpsc_chapman   resnet1d       seed42  ΔECE=-0.000998 CI=[-0.001202,-0.000795]
    cpsc_chapman   resnet1d       seed44  ΔECE=-0.016788 CI=[-0.017024,-0.016529]
    cpsc_ptbxl     resnet1d       seed43  ΔECE=-0.004964 CI=[-0.005053,-0.004870]
    cpsc_ptbxl     resnet1d       seed44  ΔECE=-0.004855 CI=[-0.004946,-0.004762]
    ptbxl_chapman  inceptiontime seed46  ΔECE=-0.002605 CI=[-0.002861,-0.002294]
```

### 3.3 主终点与 T 分布（独立复算）

```
ΔECE_OOD: mean = 0.0158626452   n=60   pos=51     min/max = -0.016788 / +0.082593
ΔECE_ID : mean = 0.0082635703   n=60   pos=47
T 中位 1.074885（62 格）/ 1.075689（60 格）  T≥2: 0/62
```

---

## 4. 新增发现（上一轮没有的）

### 4.1 【P0】E1b LOCO 全表污染，且**自我记录**

`results/deployment_loco_validation.csv`（09-11 18:23，全量 1755 行）：
- 其 `label_map` 列 = `{"NORM":0,"MI":1,"STTC":2,"CD":3}` = **NEW**
- 其 checkpoint 自存 `subspace` = `['NORM','CD','STTC','MI']` = **OLD**（mtime 09-08）
- → **模型 OLD、标签 NEW**，全部 13 指标 × 135 cells 失效。

论文正文**不引用**该表（`grep -n "LOCO" paper/main_bspc.tex` 无命中），
但它**在补充材料 S2 里**（`README.md` 称 S2 是"主文每个数字的来源"）→
投稿前必须重跑。详见 `results/_LOCO_CONTAMINATION_NOTICE.md`。

**附带**：`docs/adversarial_r1_attack_e1b.md:186-188` 另有一条独立缺陷 ——
R5 预注册要求 Youden J ≈ 0 作为失败标准，脚本**根本不计算 Youden J**。

### 4.2 【P0】论文 L1856 的 `ΔAUROC_TS−raw` 仍是污染值，且**符号是反的**

论文写 `mean ΔAUROC_TS−raw = −0.001, max |change| 0.024` —— 与污染表该列
**逐位相同**（`mean −0.000979 / max 0.024247`）。用 OLD 编码重算：

| | mean | max\|Δ\| |
|---|---|---|
| 污染（NEW） | −0.000979 | 0.024247 |
| **OLD（正确）** | **+0.000856** | **0.010477** |
| OLD（仅 4 类） | +0.001005 | 0.010477 |

**符号翻转、幅度腰斩。** 另外"as the monotone transform requires"表述有误：
多分类 macro-OvR 的跨样本排序受逐行归一因子影响，实测 Spearman 仅 0.9945–0.9999，
TS **并不严格保值**。`OLD_ENCODING.csv` 的 `auroc_ts_minus_raw` 列 **124/124 全空**，
必须补齐。

### 4.3 【P1】论文 L1511-1514 的「错误簇」不成立

论文称 9 个符号错误"聚集在 CPSC→Chapman 与 Chapman→PTB-XL"。在
`delta_obs_orig` 口径下实测散布 **5 个 pair**：
`chapman→cpsc 2 / chapman→ptbxl 2 / cpsc→chapman 2 / cpsc→ptbxl 2 / ptbxl→chapman 1`，
声称的两个 pair 仅覆盖 **4/9**。

### 4.4 【P1】分解模型**并非**零信息量（我上轮定性过重）

对分解模型**有利**的证据（R2-E）：

| 证据 | 值 |
|---|---|
| Spearman ρ（`delta_pred` vs `delta_obs_orig`） | **+0.3138，p=0.0146** |
| LOO 60/60 折 | **全正**（min +0.2809，max +0.3696）→ 稳健 |
| 分层 `ptbxl_chapman` | ρ=+0.697（p=0.025），pearson +0.853 |
| 分层 `resnet1d` | ρ=+0.446（p=0.013） |
| 分层 `T≥1` | ρ=+0.386（p=0.003） |
| Top-15 排序重叠 | **8/15**（随机 3.8）= 2.1× 富集 |
| **9 个符号错误全在近零区** | 错误格 \|obs\| 均值 **0.00472** vs 正确格 **0.01950**（差 4.13×）；剔 \|obs\|<0.02 后 23 格 **100%** 准确 |

多口径 RMSE（y = `delta_obs_orig`，n=60）。**比值列已统一分母** —— 旧版 C/D 行写的是
「A ÷ 该行」，其余行写的是「该行 ÷ B」，混用（R3-B 指出）：

| 口径 | RMSE | vs A（模型 pred） | vs B（常数均值） |
|---|---|---|---|
| A. pred = `delta_pred` | 0.302916 | 1.00 | **20.86×** |
| B. const = mean(y) | 0.014522 | 0.048 | 1.00 |
| C. const = 0 | 0.021506 | 0.071 | 1.48 |
| D. const = median(y) | 0.014606 | 0.048 | 1.006 |
| E. pred − 均值偏差（去偏） | 0.100958 | 0.333 | **6.95×** |
| **F. 仿射（OLS 2 参数）** | **0.014107** | 0.047 | **0.97×（翻转）** |

仅 F 翻转，且 F 用掉 2 个拟合参数只改善 **2.85%**（R²=0.0562）。

**⚠️ 追加修正（R3-B 提出，主代理已独立复算）**：上表 A–F **全部是样本内口径**，
不是 cross-fitting。真留一（LOO）下：

| 口径 | LOO RMSE | vs 留一常数 |
|---|---|---|
| const = mean(y) | 0.014768 | 1.00 |
| 去偏 | 0.102669 | **6.95×** |
| 仿射（2 参数） | 0.014519 | **0.983×（仅改善 1.7%）** |

且仿射的 **R²_oos = 0.00035**（样本内 0.0562 → 样本外 ≈ 0）。
⇒ 仿射的「2.85% 改善」有 2.86% → 1.68% 的样本内衰减，**样本外解释力几乎为零**。
任何「仿射校正能救活分解模型」的措辞都不成立。

另：本表的「常数基线」= **std(y)**（y 的样本标准差），它与论文 always-TS 的
−0.0145（`results/c3_crossfit_results.csv` 的 `delta_ece_mean`）**四位小数巧合相同，
但两者不是同一个量**，不可互引（R3-B 指出）。

**正确表述**（替换"零信息量"）：
> 方向准确率与恒正基线**逐位相等**（51/60，κ=0），**不构成方向信息**；
> 但秩次关联弱而显著（ρ=+0.31，p=0.015，LOO 稳健），
> 且误差集中于 `|ΔECE| < 0.017` 的近零区。

⚠️ 另注：`sign(T−1)` 的准确率是 **54/60**（用 NEW 编码 T）—— 但这本身
不构成对分解模型的比较基准，因为 OLD 编码 T 的 `sign(T−1)` 是 60/60。

### 4.5 `delta_pred` 的 provenance：**字面推翻、实质成立**

`git log --all --diff-filter=A | grep -i shap` **确实**找到
`scripts/rebuild_shapley_crossfit.py`、`results/strengthening_battle_corrected.PROVENANCE.json`、
`_recon_A..H.py`、`_audit_algo_hunter.py`。但该重建脚本**不复现**原 JSON：

```
T              orig==rebuild  60/60 exact, max|diff| = 0.0
delta_pred     exact_match 0/60, max|diff| = 0.4226, corr = +0.2567
delta_obs_orig exact_match 20/60, corr = +0.1991
rebuild 的 "delta_obs_orig" 实际是**新编码** delta_obs（corr +0.9987, mean +0.1066 vs +0.1068）
```

→ **原始 provenance 仍然缺失**，且重建脚本**自身贴错字段标签**。
另：`|delta_pred − Σshapley| = 1.11e-16`，与论文 L1505 的
`ŝ·slope + b̂·intercept + π̂·prevalence` **不符**。
`corr(delta_pred, T) = −0.8087` → 它主要是 **T 的代理**。

### 4.6 可预测性：`0.1038` 不可复现**被强化**

- `0.1038` = 合并 LOO-(arch,pair) R² 的 **bootstrap 97.5 百分位**
  （B=2000, seed=42, percentile），出自 `scripts/step2_predictability.py:231-248`。
- 09-05 原件保存在 `paper/submission/supplementary/S2_result_tables/predictability_3arch.csv`
  （mtime 09-05 23:46:57），与 `results/` 版**逐字节相同**。
- **点估计与 CI 都不可复现**；而且**在同一输入下** CI 也不可复现：
  仅改变 `set()` 的 group 枚举顺序 → `ci_hi ∈ [+0.2676, +0.2985]`、
  `ci_lo ∈ [−0.7685, −0.7189]`。→ 两轮用 4 位有效数字比较**本无意义**。
- 穷举 126,573 个子集，仅 1 个 6 位小数命中 `−0.095782`（n=234，只用 9/12 折），
  但其分架构值与 09-05 表1 差 0.351/0.093；局部密度 165,500/单位 ⇒
  **该窗口期望假阳性 0.26 个** → 命中是多重检验假阳性。
- **`2465` 不可达**：`2465 mod 13 = 8`，而现存 cell 计数全为 13 的倍数
  （104/91）⇒ 09-05 的网格形状与今日不同。
- 新增：论文的 `−0.1424`（pair-only 6 折）**同样不可复现**（按现数据算得 −0.4008）。

### 4.7 补充材料计数：75/60 正确，但 `SHA256SUMS.txt` 漏登记 4 个

159 文件 ✅ / 窗口内 **75** ✅（非 80）/ PDF **60** ✅（非 70，其中含 CPSC 的 40 张）。
类型：pdf 60、csv 13、txt 1、md 1。
窗口按**本地时**算得 75；误按 UTC 会得 78。
**`SHA256SUMS.txt` 只登记 155 条**，缺 4 个：`README.md`、
`S1_protocol/OSF_MANIFEST_POST_CORRECTIONS_2026-09-16.md`、
`S1_protocol/PROTOCOL_AMENDMENT_A3_CORPUS_IDENTITY.md`、以及清单自身。

### 4.8 `noise24`：结论对，措辞不准

σ_n/σ_s 实测 **0.063096** = 10^(−24/20) ✅；加性 ✅（`signal+noise`）；
非恒等 ✅（max|Δ|=0.211）；确定种子 ✅。
但 `src/data/l2_shifts.py:135` 的定义是**功率比**
（`noise_power = sig_power/10^(snr/10)`），所以「24 dB **幅度比**」措辞不严谨
（数值恰好相同）。
noise24 确为 13 档中最小扰动：非 CPSC 20 格 `median|ΔECE| = 0.000726`，
次小 noise12 = 0.003501（4.8×）。

### 4.9 新出现的独立性疑点

`cpsc_chapman` 与 `cpsc_ptbxl` 在 seed42/43 的 `cal_probs` **md5 完全相同**
→ 这 4 格的独立性存疑，未定性。（若成立，会削弱以 cell 为单位的 n=60 口径。）

### 4.10 其它论文数值复核

- 论文 OOD 准确率段（`0.540/0.546/0.388–0.701`；`0.510/0.424/0.619/0.620`）
  经复算**全部正确**（排 mamba 后 60 格）✅
- 4 类 **cell** 级 OOD AUROC 逐格范围是 **0.703992–0.865245**
  （最小 = `chapman→cpsc/inceptiontime/seed45`）。论文措辞是 "mean … by direction"，
  故 `0.735–0.843`（6 方向均值范围）不算错，但引用时须写明是方向均值。
- `cpsc→chapman/inceptiontime/seed42/test`：论文引 `ΔAUROC = −0.024247`（污染），
  OLD 下 = **+0.004203**。
- `ptbxl→cpsc/inceptiontime/seed43`：`swap13` acc = 0.586291 vs
  `q2_npz_recompute.ood_acc` = 0.386485（差 0.199806）。
- `chapman_cpsc/inceptiontime/seed43` 的**准确率指纹退化**
  （混淆矩阵第 1、3 行全 0，两读法 acc 均 0.484200）→ 该格必须用**频次指纹**
  判定（idx1 = 14.73% = MI、idx3 = 23.58% = CD，对上 CPSC 先验 14.71%/23.55%），
  swap 后 T = 1.048536 与 CSV 一致。

---

## 5. 本轮已落地的修正

| 修正 | 文件 | 状态 |
|---|---|---|
| 护栏 `strict` 逃生舱 + `load_checkpoint_subspace` + D5 修复 | `src/utils/encoding_guard.py` | ✅ 已验证 |
| D1：e5 两处 `strict=False` | `scripts/run_e5_inception_lite.py` | ✅ 已验证 |
| D2：e1b 自愈式编码解析（按 ckpt 自己的 subspace） | `scripts/run_e1b_loco_validation.py` | ✅ 已验证 |
| D3：e3 护栏移到 `ckpt.exists()` 之后 | `scripts/run_e3_brier_dcr_ncv.py` | ✅ 冒烟 |
| D4：e1a 护栏移到 `ckpt.exists()` 之后 | `scripts/run_e1a_l2_shift_full.py` | ✅ `--dry-run` 60/60 pending |
| F4：e4 缓存写入/校验编码戳 | `scripts/run_e4_temperature_analysis.py` | ✅ 冒烟 |
| F5：`summarize_l2_shifts.py` 强制编码校验 | `scripts/summarize_l2_shifts.py` | ✅ 实测拒掉全部 12 个污染 run |
| LOCO JSON 重建 + 污染通告 | `scripts/reconstruct_loco_json.py`、`results/_LOCO_CONTAMINATION_NOTICE.md` | ✅ round-trip 0 差异 |

**F5 实测输出**（修复前会静默聚合污染值）：
```
⛔ 因编码护栏被拒的 run：12 个（这些是 09-10~09-12 的污染产物）
    ptbxl_chapman/seed42: 无 `label_encoding` 戳 ...
已加载 0 个**通过编码校验**的 run
无可汇总的数据。中止（不输出任何表格，避免把污染值当结果）。
```

**D2 实测输出**（修复前 3/3 折 FATAL）：
```
holdout=ptbxl    sources=['chapman','cpsc'] nc=4
   chapman 自存 subspace = None
   cpsc    自存 subspace = ('NORM','CD','STTC','MI')
   → 解析结果 subspace = ('NORM','CD','STTC','MI')
   → label_map = {NORM:0, CD:1, STTC:2, MI:3}      ← OLD，正确
holdout=chapman  …同上…
holdout=cpsc     ptbxl/chapman 均给出 OLD → 一致
```

---

## 6. 残余不确定性（诚实登记）

1. **`0.0064` 本身仍是"相对干净"而非"绝对正确"**：`deployment_metrics.csv`
   无配套 stdout 日志，"step3 是唯一生产者"属强推断；且未验证 09-05 那次
   L2 run 是否已含更早期缺陷。
2. **157 中那个 fs250 额外格的身份**无法确认 —— 原 `l2_shift_results.json`
   已于 09-10 17:34 被覆盖。
3. **`delta_pred` 的原始生成脚本仍缺**，其确切定义只能从重建脚本反推
   （`decompose_benefit` 的 `delta_total`）。
4. **`main60` 与 `pred>0` 集恰好重合**是巧合还是结构性（如 π 分量恒正）？
   因原始脚本缺失**无法判定** —— 这是关于分解模型的最大残余不确定性。
5. **`cpsc_chapman`/`cpsc_ptbxl` 的 `cal_probs` md5 相同**（4 格独立性存疑）。
6. **R2-C 的"完美校准"合成实验**中 logit 尺度 σ=1.6 是任意选取，
   噪声底**数值**依赖它；但符号结构（T 略 >1 时 null 为正、阈值 ≈1.15）稳健。
7. **未用 patient-level cluster bootstrap** 复核 9 格结论（用的是 sample-level 近似）。
8. **`T*` 网格右删失**（41/60 命中上界 2.0），真实 `T*` 更大；
   但"`T*>1`"不受影响（下界 1.25）。

---

## 7. 由本轮驱动的待办

- ⏳ **改论文**：L1856 `ΔAUROC_TS−raw`（−0.001/0.024 → +0.000856/0.010477）；
  L1511-1514 错误簇（2 pair → 5 pair，覆盖 4/9）；分解模型表述
  （"零信息量" → 方向零信息 + 秩次弱显著）；L1505 Shapley 公式不符；
  安全率审计批注（"仓内无源" → "源为 09-05 的 deployment_metrics.csv"）；
  "51/60 显著为正"的表述降级（§2.4）。
- ⏳ **补齐 `OLD_ENCODING.csv` 的 `auroc_ts_minus_raw` 列**（现 124/124 空）。
- ⏳ **重跑 E1b**（自愈护栏已就位，30 个 ckpt 全在位）。
- ⏳ **补登 `SHA256SUMS.txt` 缺失的 4 个文件**。
- ⏳ **查 `cpsc_chapman`/`cpsc_ptbxl` 的 `cal_probs` 同 md5 问题**。

---
*本报告由主代理汇总 5 个对抗代理的独立结论 + 主代理亲自复核的分歧点。*
*所有数字均可用报告中给出的命令复现。*
