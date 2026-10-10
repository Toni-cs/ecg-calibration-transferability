# P0 R2轮对抗性审查终审判定报告

> **终审代理交付**（任务 #88）。本报告综合 5 份反方攻击报告（`docs/p0r2_attack_p0_*.md`）和 5 份反反方审查报告（`docs/p0r2_counter_p0_*.md`），对 5 个 P0 项的 R2 轮修复做最终独立裁决。
> **审查日期**：2026-09-09
> **审查代理**：终审代理（GLM-5.2）
> **审查标准**：CBM 期刊（IF~7）审稿标准——代码正确性无懈可击、统计方法严谨、跨实验一致性声明透明、隐含假设显式化。
> **判定原则**：独立采信反反方审查报告的逐行代码验证结论，但做独立裁决。对每个 P0 项给出"通过 / 有条件通过 / 需R3修复"的三选一裁决。

---

## 1. 裁决总览表

| P0项 | R2核心修复 | 反反方判定 | 成立攻击数 | 最终裁决 | R3必修项数 |
|------|-----------|-----------|-----------|---------|-----------|
| P0-6+7 标签语义+ResNet1D+OOM备选 | F2/F1/F3+S7+M1+S1主路径全部正确 | 12成立+2部分成立 | 12 | **需R3修复** | 4（1致命+3严重） |
| P0-1 RNG种子遗漏 | 3处调用方传rng + UserWarning逻辑正确 | 2成立+1部分成立+1不成立 | 2 | **需R3修复** | 1（2中危合并） |
| P0-3 消融分箱n_bins | ece传n_bins + N_BINS=10 + 共享binning + 签名兼容 | 3成立+2部分成立+7不成立 | 3 | **需R3修复** | 2（2严重文档缺陷） |
| P0-8 ECE加权可靠性图 | F2 nan过滤 + F3 Guo引用删除 + F1+S2标签 + S3标题 | 5成立+3部分成立 | 5 | **需R3修复** | 2（1严重+1中等） |
| P0-4 brier_parts n_bins参数 | brier_parts签名 + ValueError守卫 + compute_all_metrics内部传参 | 3成立+5部分成立 | 3 | **需R3修复** | 2（2严重） |

**总体判定**：5 个 P0 项的 R2 轮核心修复均达成目标（第一轮的 9 个致命缺陷已全部消除），但每个 P0 项都存在需在论文投稿前修复的遗留缺陷。**全部 5 个 P0 项均需 R3 轮修复**，但修复量总体可控（必修约 11 项，约 40-55 行改动，涉及 6-8 个文件）。

---

## 2. 逐P0项详细裁决

### 2.1 P0-6+7：标签语义+ResNet1D+OOM备选

#### 裁决结论：**需R3修复**

#### 核心修复评价
R2 轮核心修复**达成目标**，经反反方独立逐行验证确认：
- ✅ **F2 标签语义错位**（第一轮最危险缺陷）：`SUBSPACE_CPSC = ("NORM", "MI", "STTC", "CD")` 与 `SUPERCLASSES[:4]` 完全一致，标签 1/3 语义互换已消除
- ✅ **F1 ResNet1D 变体激活**：`build_model` 用 `depth` 控制 `block_layers`，真正构造不同深度 backbone，`nn.Module.__setattr__` 自动管理参数注册，梯度可回传
- ✅ **F3 命令行参数生效**：levels 第一项用传入 `n_filters`/`use_checkpoint`
- ✅ **S7 levels 重复消除**：第一项 level=0 而非 level=1
- ✅ **M1 report_oom_level 条件**：Level 0 不误报 OOM
- ✅ **S1 全零行检测主路径**：cal_probs 和 ood_probs 两路径均检测并丢弃全零行，防 NaN

第一轮 3 致命 + 7 严重 → 第二轮 0 致命 + 6 严重（但攻击1达到 P0-致命级别）。

#### 遗留缺陷清单（按严重度排序）

| 优先级 | 攻击点 | 文件 | 行号 | 改动内容 |
|--------|--------|------|------|---------|
| **P0-致命** | 攻击1: tgt_clusters未同步截断，benefit_inference IndexError | scripts/run_e5_inception_lite.py | L443后 + L463后 | 截断后 `tgt_clusters = tgt_clusters[ood_keep]`；S1全零行丢弃后 `tgt_clusters = tgt_clusters[~ood_zero_rows]` |
| **P0-严重** | 攻击5: cal空数组未提前返回，fit_temperature返回nan静默传播 | scripts/run_e5_inception_lite.py | L463后、L466前 | 加 `if len(cal_probs)==0` 和 `if len(ood_probs)==0` 检查并提前返回带 error 字段的 dict |
| **P0-严重** | 攻击2: result dict缺少截断统计字段（S3/M2未完成） | scripts/run_e5_inception_lite.py | L500-514 | 增加 `n_dropped_cal`/`n_dropped_ood`/`truncated`/`subspace_filtered` 字段 |
| **P0-严重** | 攻击3+4: info dict缺少arch_override/depth/width，CSV arch列失真 | scripts/run_e5_inception_lite.py | L368-380 | `info["arch"]` 用 `arch_display`，增加 `arch_override`/`depth`/`width` 字段 |
| P0-中等 | 攻击6: ood空数组未提前返回（部分成立，nan非崩溃） | scripts/run_e5_inception_lite.py | L463后 | 与攻击5合并修复 |
| P0-中等 | 攻击7: n_dropped_cal未含全零行数，日志不一致 | scripts/run_e5_inception_lite.py | L449-452 | S1修复块内累计 `n_dropped_cal += n_zero_cal` |
| P0-轻微 | 攻击14: docstring未同步更新 | src/data/mapping.py L6 + scripts/train.py L497 | - | 旧顺序 `{NORM,CD,STTC,MI}` → 新顺序 `{NORM,MI,STTC,CD}` |
| P0-轻微 | 攻击8-12: 工程改进（build_model浪费/width=0 falsy/大小写敏感/死参数/Level重复） | scripts/run_e5_inception_lite.py | 多处 | 可选改进 |

#### R3修复建议
**必修4项**（按优先级）：
1. **[P0-致命]** `scripts/run_e5_inception_lite.py` L443后添加 `tgt_clusters = tgt_clusters[ood_keep]`；L458-462 的 `if ood_zero_rows.any():` 块内添加 `tgt_clusters = tgt_clusters[~ood_zero_rows]`。这是本轮最关键修复——不修则 5→4 方向迁移实验运行时 benefit_inference 的 cluster bootstrap 会 IndexError 或产生错误结果。
2. **[P0-严重]** `scripts/run_e5_inception_lite.py` L463后、L466前加空数组检查：
   ```python
   if len(cal_probs) == 0:
       print(f"[WARN] {source}→{target} seed={seed}: cal 集截断后为空，跳过 TS 校准")
       return {"source": source, "target": target, "seed": seed, "arch": ARCH_NAME,
               "error": "cal set empty after truncation", "skipped": True}
   if len(ood_probs) == 0:
       print(f"[WARN] {source}→{target} seed={seed}: ood 集截断后为空，跳过迁移评估")
       return {"source": source, "target": target, "seed": seed, "arch": ARCH_NAME,
               "error": "ood set empty after truncation", "skipped": True}
   ```
3. **[P0-严重]** `scripts/run_e5_inception_lite.py` L500-514 result dict 增加字段：
   ```python
   "n_dropped_cal": int(n_dropped_cal),
   "n_dropped_ood": int(n_dropped_ood),
   "truncated": bool((n_dropped_cal + n_dropped_ood) > 0),
   "subspace_filtered": bool(num_classes < max(DATASET_NUM_CLASSES[source], DATASET_NUM_CLASSES[target])),
   ```
4. **[P0-严重]** `scripts/run_e5_inception_lite.py` L368-380 info dict 修改：
   ```python
   arch_display = arch_override if arch_override else ARCH_NAME
   info = {
       "dataset": dataset, "seed": seed,
       "arch": arch_display,
       "arch_override": arch_override,
       "depth": depth, "width": width,
       ...,
   }
   ```

---

### 2.2 P0-1：RNG种子遗漏

#### 裁决结论：**需R3修复**

#### 核心修复评价
R2 轮核心修复**达成目标**：
- ✅ 3 处直接调用方全部传 rng（`eval_l2_shift.py` / `run_e1a_l2_shift_full.py` / `run_e4_temperature_analysis.py`）
- ✅ UserWarning 触发条件 `if rng is None and t == "noise":` 逻辑正确
- ✅ 第一轮修复未被破坏
- ✅ P0-1 原始修复目标达成：单档内每条信号获得不同噪声

但 A1/A2 成立，属于"修复范围外的独立问题"——跨实验/跨档噪声独立性未解决。

#### 遗留缺陷清单

| 优先级 | 攻击点 | 文件 | 行号 | 改动内容 |
|--------|--------|------|------|---------|
| **P0-严重** | A1+A2: 硬编码42跨实验共享 + 函数内创建导致跨档噪声基底相同 | scripts/eval_l2_shift.py L41 + scripts/run_e4_temperature_analysis.py L303 + scripts/run_e1a_l2_shift_full.py L174 | - | 改为 `RandomState(hash(pair,arch,seed,shift_name))` 派生种子 |
| P0-轻微 | A3: Warning消息"Each signal"表述不精确 | src/data/l2_shifts.py | L193-199 | 改进消息文本（可选） |
| P0-轻微 | A4附注: 模块docstring调用规范 | src/data/l2_shifts.py | L1-20 | 补充调用规范（文档增强） |

#### R3修复建议
**必修1项**（A1+A2合并修复，采用反反方推荐的方案B）：
- **文件1**: `scripts/eval_l2_shift.py`
  - L41: 将 `rng = np.random.RandomState(42)` 改为基于实验参数派生种子
  - `shifted_eval` 函数签名增加 `pair_id=None, arch=None, train_seed=None` 参数
  - L127 调用处传入 `pair_id=f"{args.source}_{args.target}", arch=args.arch, train_seed=seed`
  - 派生公式：`noise_seed = abs(hash((pair_id, arch, train_seed, shift["name"]))) % (2**32)`
- **文件2**: `scripts/run_e4_temperature_analysis.py` L303 同样改造
- **文件3**: `scripts/run_e1a_l2_shift_full.py` L174 同样改造
- **注意**: 此改动会影响已有 `l2_shift_results.json` 的可复现性，需在实验报告中显式声明种子派生策略变更，并重跑受影响实验。

---

### 2.3 P0-3：消融分箱n_bins

#### 裁决结论：**需R3修复**

#### 核心修复评价
R2 轮核心代码修复**达成目标**，经反反方独立验证确认：
- ✅ F1 必修：L321 `ece(max_prob, correct, n_bins=N_BINS)` 已显式传 n_bins
- ✅ F2 必修：L131 `N_BINS = 10` + 注释更新为"与 E3/E4/E6 及库默认一致"
- ✅ ece 函数签名接受 n_bins（calibration.py L199）
- ✅ brier_parts 与 ece 共享 N_BINS（L315+L321 同用 N_BINS）
- ✅ 文件内无其他 ece() 漏传（grep 仅 L321）
- ✅ brier_parts 输入验证防御性充分（L603-604）

**代码层面：优秀**。但**文档层面：不完整**——P0-3 修补清单中 4 项"建议项"（S1/S2/S3/S4）全部未执行，导致 2 处文档-代码语义偏移和 1 处科学诚实性缺陷。

#### 遗留缺陷清单

| 优先级 | 攻击点 | 文件 | 行号 | 改动内容 |
|--------|--------|------|------|---------|
| **P0-严重** | B2: docstring嵌套符号Θ_2缺T（数学上Θ_1⊄Θ_2不成立） | scripts/run_e2_ablation_discrimination.py | L17 | `Θ_2 = {T_1..T_5}` → `Θ_2 = {T, T_1..T_5}`，Θ_3同步 |
| **P0-严重** | B3: 假设A1分箱变量H(p) → H(TS(p))（隐含假设未显式化） | scripts/run_e2_ablation_discrimination.py | L31-34 | 更新A1描述 + 添加E4不可比声明 |
| P0-中等 | B5: Stage3−Stage2≡0未声明（科学诚实性缺陷） | scripts/run_e2_ablation_discrimination.py | L679 | print中追加"≡0 by construction"说明 |
| P0-轻微 | B1: E4命名混淆N_BINS=5 vs BRIER_N_BINS=10 | scripts/run_e2_ablation_discrimination.py | L131 | 注释改为"E4对应BRIER_N_BINS=10" |
| P0-轻微 | B4: variant="binned"命名误导 | scripts/run_e2_ablation_discrimination.py | L520 | 改名为"ts_binned"（需下游同步，可选） |

#### R3修复建议
**必修2项**（高优先级文档缺陷，违反CBM"隐含假设显式化"要求）：
1. **[P0-严重]** `scripts/run_e2_ablation_discrimination.py` L17：
   ```python
   # 原文:
       Θ_1 = {T}                    ⊂ Θ_2 = {T_1..T_5}        ⊂ Θ_3 = {T_1..T_5, τ_1..τ_K}
   # 改为:
       Θ_1 = {T}                    ⊂ Θ_2 = {T, T_1..T_5}     ⊂ Θ_3 = {T, T_1..T_5, τ_1..τ_K}
   ```
2. **[P0-严重]** `scripts/run_e2_ablation_discrimination.py` L31-34：
   ```python
   # 原文:
   A1. binned temperature 的分箱变量=预测分布熵 H(p)=−Σp_k log p_k。
       假设：不确定度高的样本段需要不同的锐度校准...
   # 改为:
   A1. binned temperature 的分箱变量=TS 校准后预测分布熵 H(TS(p))=−Σ p'_k log p'_k，
       其中 p'=TS(p)（Stage 1 的温度缩放输出）。注意：E4 的 binned-T 分箱变量
       为 H(p)（对原始概率分箱），两者分箱变量不同，不可直接比较。
       假设：不确定度高的样本段需要不同的锐度校准...
   ```

**建议1项**（中优先级，可选）：
3. `scripts/run_e2_ablation_discrimination.py` L679：print 中追加 `≡0 by construction: threshold只改argmax不改概率` 说明

---

### 2.4 P0-8：ECE加权可靠性图

#### 裁决结论：**需R3修复**

#### 核心修复评价
R2 轮核心修复**达成目标**，经反反方独立验证确认：
- ✅ F2 nan 过滤核心逻辑：`valid = np.isfinite(eces) & (weights > 0)` 数学正确，权重归一化由 `np.average` 自动处理
- ✅ F3 Guo 错误引用删除：L436 已删除，L435 保留正确对比引用
- ✅ F1+S2 标签修改：L454/L459 已从 `weighted avg ECE` 改为 `size-weighted mean ECE`
- ✅ S3 标题修改：L477-479 已明确区分"曲线加权"和"ECE 加权"

第一轮 3 致命 + 5 严重 → 第二轮 0 致命 + 1 严重 + 1 中等。但 S3 修复（标题修改）未与 F1+S2 修复（图例修改）协调，引入了 1 个新的严重不一致。

#### 遗留缺陷清单

| 优先级 | 攻击点 | 文件 | 行号 | 改动内容 |
|--------|--------|------|------|---------|
| **P0-严重** | A1: 标题vs图例术语不一致（n_total-weighted vs size-weighted） | scripts/run_e6_reliability_diagrams.py | L454/L459/L478 | 3处统一为`sample-count weighted mean ECE` |
| P0-中等 | A3: nan过滤静默无警告 | scripts/run_e6_reliability_diagrams.py | L444前 | 加 `warnings.warn` 提示被过滤方向 |
| P0-轻微 | A8: docstring未同步"非全局ECE"语义 | scripts/run_e6_reliability_diagrams.py | L439 | docstring同步关键语义 |
| P0-轻微 | A5: 标题用代码变量名n_total | scripts/run_e6_reliability_diagrams.py | L478 | 与A1合并修复 |
| P0-轻微 | A6: L13 H1 Guo引用概念混淆（预存） | scripts/run_e6_reliability_diagrams.py | L13 | 区分"文献约定"和"正方假设" |
| P0-轻微 | A2: "size"词语歧义 | scripts/run_e6_reliability_diagrams.py | L454/L459 | 与A1合并修复 |
| P0-轻微 | A4: np.isfinite过滤inf（当前代码不可能产生inf） | scripts/run_e6_reliability_diagrams.py | L443 | 可选防御性增强 |
| P0-轻微 | A7: weights为nan的隐式过滤（当前代码不可能产生nan权重） | scripts/run_e6_reliability_diagrams.py | L443 | 可选可读性增强 |

#### R3修复建议
**必修2项**（零回归风险，3-5处字符串/警告改动）：
1. **[P0-严重]** `scripts/run_e6_reliability_diagrams.py` 3处字符串统一：
   - L454: `size-weighted mean ECE` → `sample-count weighted mean ECE`
   - L459: `size-weighted mean ECE` → `sample-count weighted mean ECE`
   - L478: `n_total-weighted mean` → `sample-count weighted mean`
   - 同时解决 A1（不一致）+ A2（歧义）+ A5（代码变量名）
2. **[P0-中等]** `scripts/run_e6_reliability_diagrams.py` L444前插入 nan 过滤警告：
   ```python
   if not valid.all():
       excluded = np.where(~valid)[0]
       warnings.warn(
           f"_weighted_ece: {len(excluded)} 方向因 ECE=nan/inf 或 n_total=0 被排除: {excluded.tolist()}",
           UserWarning, stacklevel=2
       )
   ```

**建议1项**（低优先级，可选）：
3. `scripts/run_e6_reliability_diagrams.py` L439 docstring 同步"非全局 ECE"语义

---

### 2.5 P0-4：brier_parts n_bins参数

#### 裁决结论：**需R3修复**

#### 核心修复评价
R2 轮核心修复**达成目标**，经反反方独立验证确认：
- ✅ brier_parts 签名添加 n_bins 参数（L586）
- ✅ brier_parts ValueError 守卫（L603-604）
- ✅ compute_all_metrics 内部调用传 n_bins（L770）
- ✅ 默认值一致性（brier_parts L586 vs compute_all_metrics L747，均为 10）
- ✅ numpy 整数类型支持（isinstance 检查包含 np.integer）
- ✅ 浮点数 n_bins 正确触发 ValueError

第一轮 1 致命 + 1 严重 → 第二轮 0 致命 + 2 严重。核心 bug 已修复，但修复引入了 2 个新的真实缺陷。

#### 遗留缺陷清单

| 优先级 | 攻击点 | 文件 | 行号 | 改动内容 |
|--------|--------|------|------|---------|
| **P0-严重** | S3-r2: 新增ValueError守卫无对应测试 | tests/test_model.py | L198后新增 | 补充test_brier_parts_n_bins_validation测试 |
| **P0-严重** | N2-r2: ece/mce无n_bins守卫导致行为不一致 | src/utils/calibration.py | L763后 | compute_all_metrics入口处统一添加n_bins验证守卫 |
| P0-轻微 | F1-r2: 5处调用方仍遗漏n_bins（当前无数值bug） | scripts/run_e1a_l2_shift_full.py L159 + run_e1b_loco_validation.py L552/553/593/594 | - | 显式传n_bins=10（风格问题，可选） |
| P0-轻微 | M3-r2: E1b注释代码未传n_bins | scripts/run_e1b_loco_validation.py | L585 | 清理注释代码或改为带n_bins的注释 |
| P0-轻微 | N1-r2: compute_all_metrics的7处调用方未传n_bins | 多文件 | - | 显式传n_bins=10（风格问题，可选） |
| P0-轻微 | N3-r2: isinstance检查接受bool | src/utils/calibration.py | L603 | 排除bool（Python语言通用特性，可选） |
| P0-轻微 | N4-r2: 类型注解与运行时检查不一致 | src/utils/calibration.py | L586 | 改为Union[int, np.integer]（可选） |
| P0-轻微 | 默认值风险: 硬编码10无模块级常量 | src/utils/calibration.py | 模块顶部 | 定义DEFAULT_N_BINS=10（可选） |

#### R3修复建议
**必修2项**（论文投稿前必须修复的真实缺陷）：
1. **[P0-严重]** `tests/test_model.py` L198后新增测试方法：
   ```python
   def test_brier_parts_n_bins_validation(self):
       from src.utils.calibration import brier_parts
       probs = np.random.rand(100)
       labels = (np.random.rand(100) > 0.5).astype(float)
       # 直接测试 n_bins 参数生效
       b5 = brier_parts(probs, labels, n_bins=5)
       b10 = brier_parts(probs, labels, n_bins=10)
       assert b5 != b10
       # 测试 numpy 整数类型
       b_np = brier_parts(probs, labels, n_bins=np.int64(10))
       assert b_np == b10
       # 测试 ValueError 守卫
       for bad_n_bins in [0, -1, 1.5, "10"]:
           with pytest.raises(ValueError):
               brier_parts(probs, labels, n_bins=bad_n_bins)
   ```
2. **[P0-严重]** `src/utils/calibration.py` L763后（compute_all_metrics 函数体开头）统一添加 n_bins 验证守卫：
   ```python
   def compute_all_metrics(
       probs: np.ndarray,
       labels: np.ndarray,
       n_bins: int = 10,
       n_bootstrap: int = 1000
   ) -> dict:
       if not isinstance(n_bins, (int, np.integer)) or n_bins < 1:
           raise ValueError(f"n_bins must be a positive integer, got {n_bins}")
       probs = np.asarray(probs)
       labels = np.asarray(labels)
       ...
   ```
   这消除修复引入的 ece/mce 与 brier_parts 行为不一致（修复前一致地错，修复后 brier_parts 抛异常而 ece/mce 仍静默）。

---

## 3. R3轮统一修复优先级清单

将所有 P0 项的 R3 必修项合并，按以下优先级排序：

### P0-致命（会导致运行时崩溃或数值错误）

| 序号 | P0项 | 攻击点 | 文件 | 行号 | 改动内容 | 改动量 |
|------|------|--------|------|------|---------|--------|
| 1 | P0-6+7 | 攻击1 | scripts/run_e5_inception_lite.py | L443后 + L463后 | tgt_clusters同步截断 | 2行 |
| 2 | P0-6+7 | 攻击5 | scripts/run_e5_inception_lite.py | L463后、L466前 | cal/ood空数组检查并提前返回 | 8行 |

**小计**：2项，约10行改动，1个文件

### P0-严重（CBM审稿标准下必须在论文投稿前修复）

| 序号 | P0项 | 攻击点 | 文件 | 行号 | 改动内容 | 改动量 |
|------|------|--------|------|------|---------|--------|
| 3 | P0-6+7 | 攻击2 | scripts/run_e5_inception_lite.py | L500-514 | result dict增加截断统计字段 | 4行 |
| 4 | P0-6+7 | 攻击3+4 | scripts/run_e5_inception_lite.py | L368-380 | info dict增加arch_override/depth/width | 5行 |
| 5 | P0-1 | A1+A2 | scripts/eval_l2_shift.py + run_e4_temperature_analysis.py + run_e1a_l2_shift_full.py | L41/L303/L174 | RandomState(hash(pair,arch,seed,shift_name))派生种子 | 12行 |
| 6 | P0-3 | B2 | scripts/run_e2_ablation_discrimination.py | L17 | docstring嵌套符号Θ_2补T | 1行 |
| 7 | P0-3 | B3 | scripts/run_e2_ablation_discrimination.py | L31-34 | 假设A1分箱变量H(p)→H(TS(p)) | 3行 |
| 8 | P0-8 | A1 | scripts/run_e6_reliability_diagrams.py | L454/L459/L478 | 3处字符串统一为sample-count weighted mean ECE | 3行 |
| 9 | P0-4 | S3-r2 | tests/test_model.py | L198后 | 补充test_brier_parts_n_bins_validation | 12行 |
| 10 | P0-4 | N2-r2 | src/utils/calibration.py | L763后 | compute_all_metrics入口n_bins守卫 | 2行 |

**小计**：8项，约42行改动，6个文件

### P0-中等（影响可读性/可维护性但非阻塞）

| 序号 | P0项 | 攻击点 | 文件 | 行号 | 改动内容 | 改动量 |
|------|------|--------|------|------|---------|--------|
| 11 | P0-6+7 | 攻击6 | scripts/run_e5_inception_lite.py | L463后 | ood空数组检查（与攻击5合并） | 0行（合并） |
| 12 | P0-6+7 | 攻击7 | scripts/run_e5_inception_lite.py | L449-452 | n_dropped_cal累计全零行数 | 2行 |
| 13 | P0-8 | A3 | scripts/run_e6_reliability_diagrams.py | L444前 | nan过滤warnings.warn | 5行 |
| 14 | P0-3 | B5 | scripts/run_e2_ablation_discrimination.py | L679 | Δ≡0 by construction声明 | 1行 |

**小计**：4项，约8行改动，2个文件

### P0-轻微（建议性改进）

| 序号 | P0项 | 攻击点 | 文件 | 改动内容 |
|------|------|--------|------|---------|
| 15 | P0-6+7 | 攻击14 | src/data/mapping.py L6 + scripts/train.py L497 | docstring同步SUBSPACE_CPSC新顺序 |
| 16 | P0-6+7 | 攻击8-12 | scripts/run_e5_inception_lite.py | build_model浪费/width=0 falsy/大小写敏感/死参数/Level重复 |
| 17 | P0-8 | A5/A6/A8 | scripts/run_e6_reliability_diagrams.py | 标题变量名/Guo引用/docstring同步 |
| 18 | P0-8 | A2/A4/A7 | scripts/run_e6_reliability_diagrams.py | size歧义/inf过滤/nan权重（与A1合并或可选） |
| 19 | P0-4 | F1-r2/N1-r2 | 多文件 | 12处调用方显式传n_bins=10（风格问题） |
| 20 | P0-4 | M3-r2/N3-r2/N4-r2/默认值 | src/utils/calibration.py + scripts/run_e1b_loco_validation.py | 注释清理/bool排除/类型注解/模块常量 |
| 21 | P0-3 | B1/B4 | scripts/run_e2_ablation_discrimination.py | E4命名消歧/variant改名（需下游同步） |
| 22 | P0-1 | A3/A4 | src/data/l2_shifts.py | Warning消息改进/docstring调用规范 |

**小计**：8类，约20-30行改动（可选）

### R3轮总修复量预估

| 优先级 | 项数 | 改动行数 | 涉及文件数 |
|--------|------|---------|-----------|
| P0-致命 | 2 | ~10 | 1 |
| P0-严重 | 8 | ~42 | 6 |
| P0-中等 | 4 | ~8 | 2 |
| P0-轻微（可选） | 8类 | ~20-30 | 5 |
| **必修合计** | **14** | **~60** | **7** |
| **全部合计** | **22** | **~80-90** | **8** |

---

## 4. 总体评价

### 4.1 R2轮对抗性审查是否收敛

**显著收敛但未完全收敛**。

各 P0 项收敛情况：

| P0项 | 第一轮致命 | 第一轮严重 | 第二轮致命 | 第二轮严重 | 收敛状态 |
|------|-----------|-----------|-----------|-----------|---------|
| P0-6+7 | 3 | 7 | 0 | 6（含1个P0-致命遗留） | 部分收敛（核心修复达成，但S1修复引入新致命遗留） |
| P0-1 | 0 | 2 | 0 | 2（中危） | 收敛（核心修复达成，遗留中危） |
| P0-3 | 2 | 4 | 0 | 2（文档缺陷） | 收敛（代码层面完全通过，遗留文档缺陷） |
| P0-8 | 3 | 5 | 0 | 1（呈现缺陷） | 收敛（核心修复达成，S3引入新不一致） |
| P0-4 | 1 | 1 | 0 | 2（测试+守卫） | 收敛（核心bug已修复，遗留测试+一致性） |

**关键观察**：
- 第一轮 9 个致命缺陷已**全部消除**——这是 R2 轮的最大成就
- 但 R2 轮修复过程中**引入了新的遗留问题**：
  - P0-6+7 的 S1 修复未同步截断 tgt_clusters（新 P0-致命）
  - P0-8 的 S3 修复引入标题-图例新矛盾（新 P0-严重）
  - P0-4 的 ValueError 守卫未覆盖 ece/mce（新 P0-严重，行为不一致）
- 这些"修复引入的新问题"是 R2 轮未完全收敛的主因

### 4.2 是否需要R3轮

**需要R3轮**。

理由：
1. **P0-6+7 攻击1 是 P0-致命级别**：tgt_clusters 未同步截断会导致 benefit_inference 的 cluster bootstrap IndexError 或错误结果。这是运行时崩溃风险，必须在论文投稿前修复。
2. **8 个 P0-严重级别遗留**：涵盖 CSV 不可追溯（P0-6+7 攻击2/3+4）、统计有效性有偏（P0-1 A1+A2）、文档-代码语义偏移（P0-3 B2/B3）、呈现不一致（P0-8 A1）、测试覆盖不足（P0-4 S3-r2）、行为不一致（P0-4 N2-r2）。这些在 CBM 期刊审稿标准下都必须修复。
3. **无 P0 项可完全关闭**：5 个 P0 项均有需 R3 修复的遗留缺陷，无一可标记为"通过"。

### 4.3 R3轮修复量预估

- **必修项**：14 项（2 P0-致命 + 8 P0-严重 + 4 P0-中等）
- **必修改动行数**：约 60 行
- **必修涉及文件数**：7 个
  - scripts/run_e5_inception_lite.py（P0-6+7，约 19 行）
  - scripts/eval_l2_shift.py + scripts/run_e4_temperature_analysis.py + scripts/run_e1a_l2_shift_full.py（P0-1，约 12 行）
  - scripts/run_e2_ablation_discrimination.py（P0-3，约 4 行）
  - scripts/run_e6_reliability_diagrams.py（P0-8，约 8 行）
  - tests/test_model.py（P0-4，约 12 行）
  - src/utils/calibration.py（P0-4，约 2 行）
- **可选改动**：约 20-30 行（P0-轻微建议项）
- **预估工时**：必修约 2-3 小时（含验证），可选约 1-2 小时

### 4.4 R3轮修复建议执行顺序

1. **第一优先**：P0-6+7 攻击1（tgt_clusters 同步截断）——2 行改动，消除运行时崩溃风险
2. **第二优先**：P0-6+7 攻击5（空数组检查）——8 行改动，消除静默 nan 传播
3. **第三优先**：P0-4 N2-r2（compute_all_metrics 入口守卫）——2 行改动，消除行为不一致
4. **第四优先**：P0-8 A1（3处字符串统一）——3 行改动，零回归风险
5. **第五优先**：P0-3 B2+B3（docstring 修复）——4 行改动，消除文档-代码偏移
6. **第六优先**：P0-1 A1+A2（rng 种子派生）——12 行改动，需重跑受影响实验
7. **第七优先**：P0-6+7 攻击2+3+4（result/info dict 字段）——9 行改动，CSV 可追溯
8. **第八优先**：P0-4 S3-r2（补充测试）——12 行改动，测试覆盖
9. **第九优先**：P0-中等 4 项——8 行改动
10. **第十优先**：P0-轻微 可选项——按需

---

## 5. 对抗透明性记录

### 5.1 被驳回的反方攻击及驳回理由

| P0项 | 攻击点 | 反方定级 | 反反方判定 | 驳回理由 |
|------|--------|---------|-----------|---------|
| P0-3 | C2 | 成立（非P0-3职责） | 不成立 | 越界审查——E1a/E1b 的 brier_parts 调用属于 P0-4 职责范围 |
| P0-1 | A4 | 低危 | 不成立 | 反方自承"不是缺陷，而是防御性编程合理实践"，不构成攻击 |
| P0-3 | B1 | 严重 | 部分成立（降级轻微） | E2注释上下文已消歧，E4命名是预存问题非P0-3引入 |
| P0-3 | B4 | 严重 | 部分成立（降级中等） | 代码注释已显式文档化，改名有下游影响 |
| P0-8 | A2 | 严重 | 部分成立（降级中等） | 语境强烈约束语义，"会导致论文被拒"缺乏依据 |
| P0-8 | A4 | 中等 | 部分成立（降级轻微） | inf ECE 在当前代码路径下不可能产生 |
| P0-8 | A7 | 轻微 | 部分成立（降级轻微） | n_total 恒为 int，nan 权重不可能出现 |
| P0-4 | F1-r2 | 严重 | 部分成立（降级轻微） | 当前无数值 bug，纯属未来防御性推测，定级虚高 |
| P0-4 | N1-r2 | 严重 | 部分成立（降级轻微） | 同 F1-r2，不影响任何当前数值结果 |
| P0-6+7 | 攻击6 | 严重 | 部分成立（降级中等） | 空数组不崩溃而返回 nan，"崩溃"严重程度被夸大 |
| P0-6+7 | 攻击13 | 轻微 | 部分成立（维持轻微） | S1的==0检测对主要威胁正确且充分，near-zero是独立数值问题 |

### 5.2 正方修补的所有点及修补方式

| P0项 | R2修补点 | 修补方式 | 验证状态 |
|------|---------|---------|---------|
| P0-6+7 | F2 标签语义错位 | SUBSPACE_CPSC顺序改为(NORM,MI,STTC,CD) | ✅ 反反方独立验证 |
| P0-6+7 | F1 ResNet1D变体 | build_model用depth控制block_layers | ✅ 反反方独立验证 |
| P0-6+7 | F3 命令行参数生效 | levels第一项用传入n_filters/use_checkpoint | ✅ 反反方独立验证 |
| P0-6+7 | S7 levels重复消除 | 第一项level=0而非level=1 | ✅ 反反方独立验证 |
| P0-6+7 | M1 report_oom_level条件 | Level 0不误报OOM | ✅ 反反方独立验证 |
| P0-6+7 | S1 全零行检测 | cal_probs和ood_probs两路径均检测丢弃 | ✅ 反反方独立验证（但不完整） |
| P0-1 | 3处调用方传rng | eval_l2_shift/run_e1a/run_e4均传rng | ✅ 反反方独立验证 |
| P0-1 | UserWarning逻辑 | if rng is None and t=="noise" | ✅ 反反方独立验证 |
| P0-3 | F1 ece传n_bins | L321 ece(max_prob,correct,n_bins=N_BINS) | ✅ 反反方独立验证 |
| P0-3 | F2 N_BINS=10 | L131 N_BINS=10 + 注释更新 | ✅ 反反方独立验证 |
| P0-8 | F2 nan过滤 | valid=np.isfinite(eces)&(weights>0) | ✅ 反反方独立验证 |
| P0-8 | F3 Guo引用删除 | L436已删除，L435保留正确对比引用 | ✅ 反反方独立验证 |
| P0-8 | F1+S2 标签修改 | L454/L459改为size-weighted mean ECE | ✅ 反反方独立验证 |
| P0-8 | S3 标题修改 | L477-479区分曲线加权和ECE加权 | ✅ 反反方独立验证（但引入新矛盾） |
| P0-4 | brier_parts签名 | L586添加n_bins参数 | ✅ 反反方独立验证 |
| P0-4 | ValueError守卫 | L603-604 isinstance+n_bins<1检查 | ✅ 反反方独立验证 |
| P0-4 | compute_all_metrics内部传参 | L770传n_bins | ✅ 反反方独立验证 |

### 5.3 R2轮引入的新问题

| P0项 | 新问题 | 引入原因 | 严重度 |
|------|--------|---------|--------|
| P0-6+7 | tgt_clusters未同步截断 | S1修复只截断probs/labels未截断clusters | P0-致命 |
| P0-8 | 标题-图例术语新矛盾 | S3修复改标题未与F1+S2图例协调 | P0-严重 |
| P0-4 | ece/mce与brier_parts行为不一致 | ValueError守卫只在brier_parts添加 | P0-严重 |
| P0-4 | 新增代码路径无测试 | ValueError守卫和numpy整数支持未加测试 | P0-严重 |

---

## 6. 置信度评估

**置信度：高**

理由：
- 反方在全部攻击维度上均经反反方逐行代码验证，无稻草人论证、无臆测
- 5 份反反方审查报告均基于代码实测（read/grep 工具直接读取文件内容），证据扎实
- R2 轮核心修复的正确性经反反方独立验证确认（F2/F1/F3/S7/M1/S1 等）
- 遗留缺陷的严重度评估经反反方修正后合理（部分反方定级被夸大，已降级）
- 对抗过程体现了实质性：反方发现真实问题，反反方验证并修正定级，终审独立裁决

**残余疑点**：
- P0-1 A1+A2 的修复需重跑受影响实验，重跑后的数值变化需在 R3 轮验证
- P0-6+7 攻击1 的修复（tgt_clusters 同步截断）会改变 benefit_inference 的 cluster bootstrap 结果，需在 R3 轮验证修复后数值正确
- P0-3 B3 的修复（声明 E4 不可比）需确认是否影响论文中跨实验对比结论的措辞

这些残余疑点可在 R3 轮修复后通过轻量验证解决，不影响当前裁决的置信度。

---

## 7. 终审声明

本报告由终审代理独立撰写，综合了 5 份反方攻击报告和 5 份反反方审查报告的全文内容，对每个 P0 项给出了"通过 / 有条件通过 / 需R3修复"的独立裁决。判定标准为 CBM 期刊（IF~7）审稿要求：代码正确性无懈可击、统计方法严谨、跨实验一致性声明透明、隐含假设显式化。

**关键发现**：
- R2 轮核心修复显著收敛：第一轮 9 个致命缺陷已全部消除
- 但 R2 轮修复过程引入了 4 个新问题（1 P0-致命 + 3 P0-严重），是未完全收敛的主因
- 5 个 P0 项均需 R3 轮修复，但修复量可控（必修约 60 行，7 个文件）
- 反方攻击整体质量高，反反方审查客观诚实，对抗过程实质性

**最终判定**：5 个 P0 项的 R2 轮修复**全部需 R3 轮修复**。R3 轮修复优先级：P0-6+7 攻击1（P0-致命）> P0-6+7 攻击5 + P0-4 N2-r2 + P0-8 A1 + P0-3 B2+B3（P0-严重）> P0-1 A1+A2 + P0-6+7 攻击2+3+4 + P0-4 S3-r2（P0-严重）> P0-中等 4 项 > P0-轻微可选项。

**R3 轮预估**：必修 14 项约 60 行改动 7 个文件，工时约 2-3 小时（含验证）。修复后预计可全部关闭 5 个 P0 项。
