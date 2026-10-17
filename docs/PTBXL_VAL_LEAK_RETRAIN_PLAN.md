# PTB-XL 早停验证集未留出：重训方案与影响评估

**日期**：2026-10-05　**状态**：待拍板（未执行任何重训）
**性质**：本文档只做方案与影响评估，不含任何已运行的结果。

> **执行记录（2026-10-05，随执行追加）**：见文末 §8。P0-a 已完成（4 项验证全过），
> P0-b PILOT 已启动，试点格由 seed{42,43} 改为 seed{44,45}，原因见 §8.2（seed42/43
> 是 d_model=32 的异质格，不代表受影响 20 格中的 18 个 d64 格）。

---

## 1. 问题定义

### 1.1 根因（代码级）

`scripts/train.py` 的 `build_ptbxl_datasets`：

| 行 | 代码 | 后果 |
|---|---|---|
| `:369` | `train_pos = np.sort(np.asarray(splits['train']['records'], dtype=int))` | folds 1–8 **全量**记录位置 |
| `:373` | `val_patients = _carve_val_patients(pat_label, 0.125, seed + 100)` | 从 folds 1–8 内抽 12.5% 患者作 val |
| `:374` | `train_patients = sorted(set(pat_label) - val_patients)` | ← **已减掉 val** |
| `:381` | `assert_no_leakage({'train': train_patients, 'val': sorted(val_patients), ...})` | 断言用的是**减过的**变量 |
| `:388` | `pos = {'train': np.sort(train_pos), 'val': _pos_of(val_patients), ...}` | 数据集用的是**没减的** `train_pos` |

即：**断言校验的变量与构建数据集的变量不是同一个**。`assert_no_leakage` 必然通过，但
`val` 的全部记录仍在训练加载器里。`:325` docstring 声称的"硬性断言 train/val/cal/test
患者两两不交"因此是虚假保证。

### 1.2 独立佐证

`scripts/export_splits.py:10-16` 是与 builder 逐行镜像的导出脚本，其 docstring 明写：

> 【重要·PTB-XL as-used 语义】train.py 的 build_ptbxl_datasets 中，carve 出的
> val 患者记录仍保留在训练加载器（folds 1-8 全量训练，val 仅作早停监控）——
> 这是 60 个实验的实际运行口径……Chapman/CPSC 的 val 患者已从训练集正确剔除
> （in_train_loader=no）。

实测 `splits/*.csv`：10 个 PTB-XL 文件的 val 行 **`in_train_loader=yes` 全中**
（2141/2141 … 2173/2173）；Chapman / CPSC 全部为 **0**。

### 1.3 协议符合性——需要精确表述，不能夸大

协议 `docs/EXPERIMENT_PROTOCOL.md`：

- **§2:37**：PTB-XL 划分 = "folds 1-8训练 / fold 9校准 / fold 10内部测试"。
  协议层面**根本没有 val 这一split**——val carve 是实现层为早停额外加的。
- **§2:42** 硬性断言对象 = "**train/cal/test** 患者ID交集为空"。

因此：

| 断言 | 是否违反 |
|---|---|
| 协议 §2:42 train / cal / test 三者不交 | ✅ **未违反**。fold9(cal)、fold10(test) 与 folds1–8 严格不交，主终点**评估数据是干净的** |
| `train.py:325` 自称的 train/**val**/cal/test 四者不交 | ❌ **违反**（且断言因变量错配而未能发现） |
| §4:82 早停准则 = val NLL | ❌ 实际用 val ECE —— **已登记**为偏离（A2 ⑦，`docs/EXPERIMENT_PROTOCOL.md:236`） |
| **早停用的 val 是模型见过的数据** | ❌ **未登记**，属新发现的偏离 |
| 跨库一致性 | ❌ PTB-XL 的 val 在训练器内、Chapman/CPSC 的在训练器外（`export_splits.py:101-102`），**早停口径三库不一致且未披露** |

**一句话定性**：这不是"测试集泄漏"，而是"**模型选择失效**"——早停无法观测到过拟合
（训练集上的 ECE 随训练持续下降），实际保留的 checkpoint 比设计预期更晚、更过拟合。
方向不确定，**必须实测**，不能靠推理给结论。

---

## 2. 影响面

### 2.1 直接受影响的 cell：20 / 60

只有 **PTB-XL 作源域**的模型是用 `build_ptbxl_datasets` 训出来的：

| pair | PTB-XL 角色 | 模型是否受污染 | 主网格 cells |
|---|---|---|---|
| `ptbxl_chapman` | **源** | ✅ 是 | 10（2 arch × 5 seeds） |
| `ptbxl_cpsc` | **源** | ✅ 是 | 10 |
| `cpsc_ptbxl` | 目标 | ❌ 否（模型训于 CPSC） | 10 |
| `chapman_ptbxl` | 目标 | ❌ 否（模型训于 Chapman） | 10 |
| `cpsc_chapman` | 无关 | ❌ 否 | 10 |
| `chapman_cpsc` | 无关 | ❌ 否 | 10 |

另有 `ptbxl_chapman/{mamba}/seed{42,43}` 2 个 toy checkpoint（论文已声明排除在主终点外）。

**已核实：同源两个 pair 不共用权重**——对 3 组同源 pair × 2 arch × 2 seeds 逐一算
SHA-256，`best_model.pt` **全部不同**。所以重训是**按 pair 独立**的 20 次，不是 10 次
（这与 2026-09-17 修复的 `cpsc_ptbxl` 复用 `cpsc_chapman` 权重属同一类独立性要求）。

### 2.2 必须连带重算的产物

`results/` 中含 `ptbxl_chapman` / `ptbxl_cpsc` 行的数据族（排除通告与审计 md）：

| 族 | 文件 |
|---|---|
| 主表（权威） | `robustness_validation_5seeds.csv`、`robustness_report.md` |
| bootstrap | `bootstrap_diagnostics.csv` |
| E3 | `c1_brier_reliability.csv`、`c1_dcr_ncv_multiclass.csv` |
| 方法边界 | `c4_resnet1d_8method.csv` |
| 温度族 | `binned_temperature_exploratory.csv`、`temperature_distribution_analysis.csv`、`temperature_shift_sensitivity.csv` |
| 反例 | `counterexample_discrimination.csv/.json`、`counterexample_analysis.md` |
| 噪声底 / 先验 | `noise_floor_curve.csv`、`real_prior_recovery.csv` |
| Shapley | `rebuild_shapley_crossfit.csv/.json`、`rebuild_shapley_slopeT.csv/.json` |
| S2 | `s2_dose_response.csv` |

> 注：`discrimination_metrics_60exp.csv`、`c3_crossfit_results.csv`、`l2_shift_full_*`、
> `predictability_3arch.csv`、`decomposition_*` 未被上述串匹配命中，可能因 pair 命名
> 形式不同（如 `ptbxl->chapman`）。**执行前须以 pair 字段重新枚举一遍，本文清单是下界。**

连带：`checkpoints/transfer/ptbxl_{chapman,cpsc}/{arch}/seed*/` 下的
`transfer_result.json`、`e3_probs.npz`、`e6_probs.npz`、`l2_shift_results.json`；
补充材料 `S3_per_experiment/` 对应 20 个 JSON；6 方向可靠性图；`paper/main_bspc.tex` 中
全部 60 格聚合数字。

**先例可循**：09-17 那次重训留了 `_*.PRE_RETRAIN.csv` 备份（`bootstrap_diagnostics`、
`c4_resnet1d_8method`、`noise_floor_curve`、`rebuild_shapley_crossfit`），本次照同一模式。

### 2.3 重跑后必须重算的头条数字

| 指标 | 当前值 | 是否会动 |
|---|---|---|
| 主终点 mean | `+0.015414` | ✅ 会（20/60 cells 变） |
| 主终点正例 | `50/60 = 83.3%` | ✅ 会，**可能跨过 51/60 或 49/60** |
| 架构拆分 | IT `26/30`、RN `24/30` | ✅ 会 |
| 剔 6 退化格 | `44/60 = 73.3%` | ✅ 会 |
| ID 边界（CI 含 0） | `23/60 = 38.3%`（BCa）／`29/60 = 48.3%`（percentile） | ✅ 会，**两个口径都可能改变 A1.4.2 分支是否触发** |
| ID 均值 / OOD÷ID | `+0.008217` ／ `1.88×` | ✅ 会 |
| 聚类稳健区间 | `+0.0154 [0.0106, 0.0202]`，SD `0.0076` | ✅ 会 |
| NCV OOD/ID、DCR、E3 族 | `+0.000293` / `−0.000042` / `+0.000618` | ✅ 会（E3 输入即这些 checkpoint） |

> 也就是说：**一旦重训，本轮已完成的正文 NCV 数字对账（P0-②）会作废，必须在重训之后
> 重做一遍**。同理，发布仓 `ecg-release/results/` 与补充材料 `SHA256SUMS.txt` 都会失效，
> 必须放在整条链的最后重建。

---

## 3. 修复方案

### 3.1 代码改动（最小集）

`scripts/train.py`，在 `:373` 算出 `val_patients` 之后、`:388` 组装 `pos` 之前插入
减法（**必须在 `:370` `meta18 = split_meta.loc[train_pos]` 之后**，否则 val carve 本身会变）：

```python
val_pos = _pos_of(val_patients)
train_pos = np.setdiff1d(train_pos, val_pos)   # val 真正离开训练加载器
```

`:374` 的 `train_patients` 保留（它现在与 `pos['train']` 语义一致，`:381` 的断言从
"形式上通过"变成"真的在测数据集"）。

**必须同步**（`export_splits.py:18-20` 的 lockstep 约定）：
`_split_ptbxl` 中 `in_train_loader` 对 val 行改为 `no`，docstring `:10-16` 的
"as-used 语义"整段改写。改完跑 `python scripts/export_splits.py --validate 42`
与真实 builder 交叉验证。

### 3.2 验证（重训前必须先过）

1. `splits/ptbxl_*` 10 个文件的 val 行 `in_train_loader` 全部变 `no`；
2. `train.py` 打印的 `[ptbxl] 患者级四分割` 中 `train` 记录数下降约 12.5%（folds1–8 内）；
3. `assert_no_leakage` 改为直接吃 `pos` 推出的患者集，确保断言对象 = 数据集对象；
4. 单测：构造一个小 meta，断言 `set(pos['train']) & set(pos['val']) == ∅`。

---

## 4. 成本估算

协议 §3.5 预算表（`docs/EXPERIMENT_PROTOCOL.md:59-69`）给出的单价：

| 项 | 协议估计 | 折算 |
|---|---|---|
| 基础训练 45 runs | 3–5 GPU 日 | **≈ 1.6–2.7 h/run** |
| 本次 20 runs | — | **≈ 33–55 GPU·h ≈ 1.4–2.3 GPU 日** |
| S1 主网格 eval-only（全 60 格 × 7 方法） | 2–4 GPU 时 | 本次 20 格 ≈ 0.7–1.3 GPU 时 |
| Bootstrap（主检验 + 次要） | 8–12 CPU 时 | 按 20/60 比例 ≈ 2.7–4 CPU 时 |
| L2 阶梯 eval-only | 4–8 GPU 时 | 按比例 ≈ 1.3–2.7 GPU 时 |

**合计量级：约 2–3 GPU 日 + 数 CPU 时**（单卡 8GB，协议 §3.5 结语口径）。

⚠️ **上述单价来自协议预算表，不是实测**。`adversarial_r9_attack_repro.md [manuscript-tree doc, not shipped here]:267,302`
已记录：`transfer_result.json` **没有 `train_time_sec` 字段**，论文也没有报告训练
wall-clock。**因此第 5 节的 pilot 阶段必须顺便量一次真实耗时**，再回来修正本表。

---

## 5. 分阶段执行与决策门

```
P0-a  改代码 + lockstep + 4 项验证           （半小时级，不重训）
  ↓
P0-b  PILOT：只重训 2 格 —— ptbxl_chapman/inceptiontime/seed42,43
      目的：① 量出单格真实 wall-clock
            ② 量出 ΔECE_OOD 的移动幅度
            ③ 量出早停选中 epoch 的位置变化（关键：验证"选得更晚"的假设）
  ↓
  ┌─ 移动 < 1 格的翻转阈值（例如 |Δ| < 0.002 且不改变 50/60 计数）
  │     → 可选择：只重训这 20 格 + 重算，或按"影响可忽略"登记为偏离
  ├─ 移动显著 → 全量 20 格
  └─ 无法复现（pilot 与原权重差异过大）→ 先查随机源/数据版本，不得带病推进
  ↓
P0-c  全量 20 格重训 → 重跑 2.2 全部族 → 重算 2.3 全部指标
  ↓
P0-d  改正文（NCV 5 处 + C5 叙事 + 所有 60 格聚合数）
  ↓
P0-e  最后：重建补充材料 SHA256SUMS（登记 14 个未登记表）→ 重新同步 ecg-release/results/
```

**为什么 pilot 是 2 格而不是 1 格**：单格无法区分"该格本身抖动"与"泄漏修复的系统性
位移"；2 格且都属同一 pair/arch，能在最小代价下给出方向性信号。

**为什么 P0-d 排在 P0-c 之后**：正文所有聚合数都由 60 格主表导出（`recompute_all_derived.py`
只读 `robustness_validation_5seeds.csv`）。先改正文后重训 = 必然返工。

**为什么 SHA256SUMS 排在最后**：当前已有 16 条哈希不匹配、14 个表未登记；任何一次重跑
都会再作废一批。清单只能在全部产物冻结后重建一次。

---

## 6. 不做的后果（供权衡）

| 不重训 | 后果 |
|---|---|
| 维持现状 | 20/60 格的 checkpoint 由"训练集上的早停"选出，协议 §4:82 的早停设计未生效；三库早停口径不一致且未披露。审稿人若自行加载 `splits/ptbxl_seed42.csv` 即可看到 `in_train_loader=yes` |
| 只披露不修 | 需在 Limitations 增补一条**未登记**偏离（现有 A2 ⑦ 只覆盖了 metric 选错，没覆盖 val 未留出），并把"患者级防泄漏"的表述降级 |
| 全修 | ≈2–3 GPU 日 + 正文全量数字重算 + 清单与发布仓重建 |

**注意**：协议 §2 的 train/cal/test 不交**没有被违反**，主终点的评估集是干净的——
所以这不是"结论必然错误"，而是"模型选择环节不合规且效果未知"。pilot 的作用就是把
"效果未知"变成"效果已知"，再决定投入。

---

## 7. 与本轮其他事项的依赖关系

```
P0-a/b/c/d  = 本方案（PTB-XL 重训主链）
P0-②        = 正文 NCV 5 处对账        ← 排在 P0-d 之后，否则返工
P1          = 补充材料 SHA256SUMS 重建  ← 排在最后
P2（已完成）= 移除 LOCO/空占位、OSF retrospective 披露、归档状态小节、release 通告修正
```

本轮已完成的 P2 项**不受重训影响**（措辞与文件移除类），可保留。

---

## 8. 执行记录（2026-10-05，随执行追加）

### 8.1 P0-a 完成：代码修复 + lockstep + 4 项验证

**代码改动（2 文件）**

| 文件 | 改动 |
|---|---|
| `scripts/train.py` | ① `pos['train']` 由 folds1-8 全量 `train_pos` 改为 `np.setdiff1d(train_pos, val_pos)`；② `assert_no_leakage` 的输入改为**由 `pos` 反推的患者集**（断言对象 ≡ 数据集对象，标记 `[VAL-LEAK-2026-10-05]`）；③ builder docstring 同步 |
| `scripts/export_splits.py` | `_split_ptbxl` 的 `in_train_loader` 改为 `(split=='train')`（⟺ fold≤8 且非 val 患者），与 builder lockstep；模块 docstring"as-used 语义"整段改写（保留历史口径说明与 2026-10-05 更正标记） |

**4 项验证（全部通过）**

| # | 验证 | 结果 |
|---|---|---|
| 1 | `splits/ptbxl_*` 10 文件 val 行 `in_train_loader` → `no` | ✅ 临时目录重导出后逐行 diff：10 文件共 21,397 行变化，**全部**是 val 行 yes→no（2141/2144/2162/2188/2175 + sub4 2103/2073/2122/2116/2173），0 意外变化；15 个 Chapman/CPSC 文件 SHA-256 **逐字节不变** |
| 2 | builder 打印的 train 记录数下降 ~12.5% | ✅ `--validate 42` 实测：`train(13006p/15051r) val(1859p/2141r)`；folds1-8=17192 → 15051，降 2141/17192=12.45%（患者 14865→13006，与 val 1859 患者相加吻合） |
| 3 | 断言对象 = 数据集对象 | ✅ 代码层面 `assert_no_leakage({k: patients_at(pos[k])})`；且 5 个 builder 变体在真数据上全部通过（exit 0，20/20 MATCH） |
| 4 | 单测锁死 | ✅ 新增 `tests/test_ptbxl_val_holdout.py`（合成 PTB-XL 形状数据）：6/6 passed（seed 42/45 × 3 用例：val 不在 train 加载器、train∪val==folds1-8、四 split 记录级+患者级不交、clusters_test 对齐、export lockstep）；全仓 `pytest tests` = **189 passed** |

**lockstep 交叉验证**：`python scripts/export_splits.py --validate 42` exit 0，
ptbxl / ptbxl_sub4 / chapman / chapman_sub4 / cpsc 五变体 train/val/cal/test 全部 MATCH
（builder 与 CSV 记录集逐集合相等）。

**注**：`splits/` 目录被 `.gitignore:14` 忽略（本来就不入库），本次 10 文件的更新在
磁盘上生效且有上述逐行 diff 证据。

### 8.2 PILOT 启动 + 试点格变更（seed42/43 → seed44/45）

**变更原因（新发现）**：`ptbxl_chapman` 与 `chapman_ptbxl` 的 inceptiontime
**seed42/43 四格是 d_model=32**（`backbone.proj` 出 32 通道，state_dict 184,587
参数），而其余 56 个 IT 格（含同 pair seed44-46）是 **d_model=64**（193,675/193,610）。
证据：全网格 checkpoint 扫描（`grid_survey.py`）；四格 `best_model.pt` mtime
2026-09-03 14:00–21:09（第一批 S1 实验，`run_s1.bat` 明示 `--d-model 32`），
seed44-46 是 09-06 02:00 的第二批；09-08 的 BCa10000 全网格重跑用了
`--load-model`（`rerun_bca10000.py:86`），所以宽度差异被原样保留。

受影响 20 格里 18 格是 d64、2 格是 d32。在 d32 格上量 Δ 会把"val 修复效应"
与"窄模型"混在一起，故 PILOT 改用 **seed44+45（d64，代表 18/20）**。

**可比性核验（无架构漂移）**：基线 seed44 ckpt 与当前代码构建的
`ECGClassifier(d_model=64, n_layers=2, K=5)` state_dict **逐键逐形状一致**
（55 键，0 缺失/0 多余/0 形状差，参数量同为 193,675）。`src/models/ecg_classifier.py`
最后改动于 dd96647（2026-09-08 21:53），但未改变模块结构。
（注意：`parameters()` 计数比 `state_dict()` 计数少 1,029 —— BatchNorm running
stats + log_temperature buffer，前者不算 BN 统计量；对比时必须用同一口径。）

**PILOT 命令**（`valleak_pilot_retrain.py [manuscript-tree script, not shipped here]`，新脚本）：
`eval_transfer.py --source ptbxl --target chapman --arch inceptiontime --seeds 44 45
--methods ts platt isotonic vector matrix dirichlet em_prior bbse_prior --epochs 50
--batch-size 16 --bootstrap 10000 --bci-method bca --n-jobs 8 --gpu-inference
--save-dir checkpoints/transfer_valleak_pilot`（独立目录，**不覆盖**原 checkpoint）。
与 `rerun_bca10000.py` 口径一致（ts=BCa/B=10000 已由 meta 核实）。

**执行环境备注**：eval_transfer.py:234 打印 `π̂_target`（U+0302）在 GBK 控制台
会 `UnicodeEncodeError`（第一次尝试即因此崩在 em_prior_pi，exit 1，2106.9s 白跑）。
launcher 已注入 `PYTHONUTF8=1 / PYTHONIOENCODING=utf-8`（只影响 stdio，不影响计算）。

### 8.3 P0-b PILOT 结果（2026-10-05 22:30 完成，双格）

口径：ptbxl_chapman / inceptiontime / d64 / epochs50 / batch16 / methods8 / BCa B=10000 /
n-jobs 8 / gpu-inference；两格 `reused_checkpoint=false`（全新训练）；
base 与 pilot 的 ts meta 逐项一致（n_bootstrap=10000, bci_method=bca, ts_fit=source_cal）。

| | seed44 | seed45 |
|---|---|---|
| 早停 epoch | 6 → **12** | 12 → **18** |
| val_ece（ckpt 内） | 0.0144 → 0.0182 | 0.0148 → 0.0367 |
| ts Δ_ID | **−0.0114**（CI 变为含 0） | **+0.0136**（CI 仍不含 0） |
| ts Δ_OOD | −0.0018 | +0.0082 |
| ts OOD 显著性 | True→True | True→True |
| 8 方法 OOD 显著性 | 全部不变 | **em_prior 翻转 True→False**（Δ=−0.0788）；bbse −0.0547 但未翻 |
| 8 方法均值 Δ_ID / Δ_OOD | −0.0083 / −0.0007 | +0.0095 / −0.0126 |

**判定**：

1. **训练随机性噪声 σ≈0.01**（同 seed 同配置两次独立训练的 OOD 差 0.0133），
   与单格 Δ 同量级 → 预注册决策门 `|Δ|<0.002` 在 n=2 下**不可裁决**，两格方向相反
   （ID：−0.0114 / +0.0136；OOD：−0.0018 / +0.0082）。
2. **在 n=2 下稳健的事实**：① ts OOD 显著性 2/2 不变（50/60 计数暂安全）；
   ② 早停 epoch 一致性 +6（泄漏使早停提前的机制得到方向一致的证实）；
   ③ 双格 ts 均值 Δ_OOD=+0.0032、Δ_ID=+0.0011——头条聚合数（+0.015414、50/60、
   1.9×、23/60 边界分支）都在噪声带内存活。
3. **但 P0-c 仍然必须做**，理由不是效应量而是**产物-正文一致性**：代码已修复，
   任何人从发布仓重跑这 20 格都会得到与正文不同的逐格数字（seed44 OOD
   +0.0203→+0.0185 已实测）。"登记偏离"分支只能覆盖措辞，覆盖不了 60 格主表、
   S3 per-experiment JSON 与全部派生族。
4. **实测成本修正（§4 表作废）**：单格 train+8 方法 BCa10000 评估 = **53 min**
   （RTX 5060 8GB，两格实测 51.5 / 54.6 min），20 格 ≈ **17.7 h ≈ 0.74 GPU 日**，
   远低于协议预算折算的 1.4–2.3 GPU 日。16 族连带重跑另计（多数为 bootstrap/CPU）。

**待拍板**：① 批准 P0-c 全量 20 格；② d32 四格是否顺带同质化为 d64
（其中 2 格在 20 格名单内自动完成，另 2 格 chapman_ptbxl IT seed42/43 需 +2 格 ≈ +1.8 h，推荐做）。
→ ①已批准（2026-10-07，见下节）；②部分批准：仅 20 格名单内的 2 格自动同质化。

### 8.4 P0-c 启动记录（2026-10-07）

**用户批准：20 格全量重训，分段执行。** 分段方案 = 按 pair×arch 分 4 段、每段 5 格
（实测 ~53 min/格 → 每段 ~4.5 h）：

| 段 | pair | arch | seeds |
|---|---|---|---|
| 1 | ptbxl_chapman | inceptiontime | 42–46 |
| 2 | ptbxl_chapman | resnet1d | 42–46 |
| 3 | ptbxl_cpsc | inceptiontime | 42–46 |
| 4 | ptbxl_cpsc | resnet1d | 42–46 |

执行器：`valleak_p0c_retrain.py [manuscript-tree script, not shipped here]`（每格独立调用 eval_transfer、逐格计时、
断点可续——已有 `transfer_result.json` 且 `reused_checkpoint=false` 的格自动跳过）。
输出到 `checkpoints/transfer_valleak_p0c`（不覆盖 canonical）；原 20 格已备份至
`checkpoints/_PRE_VALLEAK_BACKUP_20261007/`（24.6 MB，含 `SHA256SUMS_best_model.txt`）。
swap 与 16 族连带重跑在 4 段全部完成后统一执行。

**d32 决定**：本次批准范围为 20 格，`ptbxl_chapman` IT seed42/43 重训后即为 d64
（自动同质化）；`chapman_ptbxl` IT seed42/43 2 格**未包含**，是否补跑待用户单独拍板。


### 8.5 目标期刊决策（2026-10-05 用户确认）

**CMPB（Computer Methods and Programs in Biomedicine）不变**。依据：中科院 2026 新锐分区 2 区 Top / 2025 升级版大类 2 区；JCR 2026 四小类全 Q1（IF 6.4）；中科院预警名单 2020–2025 从未上榜、无 On Hold；`\journal{}`（main_bspc.tex:47）与 cover_letter.tex 已是该刊口径，转移成本为零。
注意：**CBM 已被中信所 2025-12-07 预警名单（103 本）收录，不得作为备选**；BSPC 小类生医工 3 区且 JCR Q1/Q2 摇摆，仅作末位兜底。唯一需作者自查项：所在单位对 CMPB 的认定文件。


### 8.6 "变弱"的机制分解（2026-10-08 实测验证，18 个干净对照格）

对 18 个 d64→d64 干净对照格做 raw/cal 分解（`methods.ts.ood.{raw,cal}`，
脚本 `mech_verify.py` 逻辑，数据见对话记录）：

| 量 | base（泄漏版） | new（修复版） | Δ |
|---|---|---|---|
| raw ECE (OOD，校准前) | **0.1760** | **0.1403** | **−0.0357** |
| TS ECE (OOD，校准后) | 0.1526 | 0.1362 | −0.0165 |
| TS 收益 (raw−cal) | 0.0234 | **0.0042** | −0.0192 |

**结论（数据支持，非假设）**：泄漏使早停观测"训练子集上的伪低 ECE"→ 早停过早
（epoch 6–12）→ 选中的 checkpoint 泛化差、raw ECE 高（0.176）；修复后早停盯真实
泛化 miscalibration → 停得更晚（12–18）→ checkpoint 的 raw ECE 系统性更低（0.140）。
两代模型经 TS 后几乎到达同一点（0.153 vs 0.136），起点下降 → 论文主终点（剩余可
校准空间）从 0.0234 缩到 0.0042。**缩水的不是 TS 的作用，而是"可被 TS 挽救的
miscalibration 总量"**；旧数字里相当一部分收益实为"上游模型选择失误 + TS 补救"，
其中补偿选择失误的功劳不应记在 TS 头上。若干新格 TS 收益为小负值（如 re/s42
−0.0069、in/s45 −0.0123）= 源 cal 上拟合的 T 对已良好校准的模型轻微过纠。
此分解可写入正文 Discussion（支撑"校准收益 ∝ 上游 raw miscalibration 水平"主线，
与 C5 门控呼应）。

### 8.7 连带发现（不在本方案范围，需单独拍板）

1. **论文 §Architecture 参数范围过期**：`main_bspc.tex:396` 称 InceptionTime
   "46,000–184,000 parameters"。实测：IT 主网格 = **184,587（4 格 d32 遗留）–
   193,675（d64）**；46,000 ≈ 46,504 = **被论文声明排除的 BiMamba toy**
   （`ptbxl_chapman/mamba/seed42`）。推断：该范围写于 09-03/09-04（当时只有
   d32 IT + mamba toy 两类 checkpoint），09-06 的 d64 批次到达后未更新。
2. **网格宽度异质性未披露**：60 格中 4 格（ptbxl↔chapman IT seed42/43）是
   d_model=32。若全量重训按当前默认（d64）执行，这 4 格会被"顺手"同质化为 d64
   —— 其中 `ptbxl_chapman` 2 格本就在 20 格名单内；`chapman_ptbxl` 2 格不在
   （其源库是 chapman，与 val 泄漏无关），是否连同重训**需拍板**（+2 格 ≈ +2×35min）。
3. 顺带确认：`transfer_result.json` 的非 ts 方法**没有 meta**（B/BCI 未记录），
   ts 全网格 BCa/B=10000（`methods.ts.meta` 逐格核实）。
