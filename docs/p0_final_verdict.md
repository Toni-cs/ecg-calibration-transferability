# P0 修复终审判定报告

> **终审代理交付**（任务 #72）。本报告综合 7 份反方攻击报告（`docs/p0_attack_p0_*.md`）和 7 份反反方回应报告（`docs/p0_counter_p0_*.md`），对 8 个 P0 级修复做最终独立判定。
> **审查日期**：2026-09-09
> **审查代理**：终审代理（GLM-5.2）
> **审查标准**：CBM 期刊（IF~7）审稿标准——要求代码正确性无懈可击、统计方法严谨、跨实验一致性声明透明、隐含假设显式化。
> **判定原则**：独立读取每份报告原文，对每个攻击点给出成立/不成立/部分成立的独立判定，不依赖任何预汇总。

---

## 总览

| P0 问题 | 最终状态 | 致命攻击数 | 严重攻击数 | 需回炉? | 修补量 |
|---------|---------|-----------|-----------|---------|--------|
| P0-1 rng 噪声注入 | 部分通过 | 0 | 2 | 是 | 3 处修复 + 论文声明 |
| P0-2 NCV CI | 通过 | 0 | 0 | 否 | 3 项防御性增强 |
| P0-3 E2 消融逻辑 | 部分通过 | 0 | 2 | 是（补充修复） | 2 行修复 + 文档同步 |
| P0-4 brier_parts n_bins | 部分通过 | 1 | 1 | 是 | 1 行必修 + 3 项建议 |
| P0-5 全局 Brier | 通过 | 0 | 0 | 否 | 2 项改进建议 |
| P0-6+7 E5 OOM+迁移 | 不通过 | 3 | 7 | 是（必须回炉） | 大量修复（见清单） |
| P0-8 ECE 加权 | 不通过 | 3 | 5 | 是（必须回炉） | 3-4 处修复 |

**总体判定**：
- **2 个 P0 可关闭**（P0-2、P0-5）：核心修复逻辑正确，无致命/严重代码缺陷，附带改进建议非阻塞。
- **3 个 P0 需轻量修补**（P0-1、P0-3、P0-4）：核心方向正确但存在遗漏或不一致，修补量小（1-3 行）。
- **2 个 P0 必须回炉重修**（P0-6+7、P0-8）：存在多个致命缺陷，修复引入了比原 bug 更严重的静默错误。

---

## 逐项判定

### P0-1: rng 噪声注入

**最终状态**: 需回炉重修（轻量）

**判定理由**:

反方提出 5 个攻击点，反反方确认**全部技术成立**。经终审独立判定：

| 攻击 | 反方定级 | 反反方核验 | 终审判定 | 成立性 |
|------|---------|-----------|---------|--------|
| 1. eval_l2_shift.py L44 遗漏修复 | 严重 | 成立 | **严重** | 成立 |
| 2. run_e4_temperature_analysis.py L307 遗漏修复 | 严重 | 成立 | **严重** | 成立 |
| 3. 固定 seed=42 跨实验噪声相关性 | 严重 | 部分成立（中-严重） | **中-严重** | 部分成立 |
| 4. rng=None 静默保留 bug | 轻微 | 成立 | **轻微** | 成立 |
| 5. 多进程安全隐患 | 轻微 | 成立 | **轻微（潜在）** | 成立 |

**核心问题**：正方仅修复了 3 个调用方中的 1 个（`run_e1a_l2_shift_full.py`），遗漏 `eval_l2_shift.py` 和 `run_e4_temperature_analysis.py` 两处。全局 grep 确认 `apply_shift` 仅 3 处调用方，正方修复了 1/3。这是修复不完整的硬伤，非风格问题。

**攻击 3 的独立校准**：固定 seed=42 在校准研究中是合法的 controlled experiment 设计（控制噪声变量以隔离模型训练方差）。但反反方正确指出：严重度取决于论文声明措辞。若论文声明"跨 5 seed 稳定性反映整体鲁棒性"则当前设计有缺陷；若声明"反映模型训练稳定性（噪声固定）"则可接受。**跨噪声档使用同一噪声的不同 SNR 缩放是合理的配对设计（paired design），不应视为缺陷**——反方此子攻击略显过度。

**修补清单**:
1. **[scripts/eval_l2_shift.py:36-44]** `shifted_eval` 函数内循环外创建 `rng = np.random.RandomState(42)`，`apply_shift(sig, shift, rng=rng)` 传 rng
2. **[scripts/run_e4_temperature_analysis.py:293-307]** `shifted_probs_labels` 函数内循环外创建 `rng = np.random.RandomState(42)`，`apply_shift(sig, shift, rng=rng)` 传 rng
3. **[src/data/l2_shifts.py:180]** `apply_shift` 中对 `rng is None and shift["type"] == "noise"` 发出 `UserWarning`（防御性修复，防止未来再次遗漏）
4. **[论文/代码 docstring]** 明确声明"噪声实现固定为 seed 42，跨 seed 方差仅反映模型训练变异，不包含噪声方差分量"（攻击 3 的论文声明）
5. **[建议] [scripts/run_e1a_l2_shift_full.py:163-185]** 删除重复实现的 `shifted_eval`，改为 `from eval_l2_shift import shifted_eval`，消除"复制品与原件不一致"的架构性根因

**优先级**: 高（攻击 1+2 是存活的原 bug，必须立即修复）

---

### P0-2: NCV CI

**最终状态**: 通过

**判定理由**:

反方提出 9 个攻击点，反反方确认**0 个致命代码缺陷**。经终审独立判定：

| 攻击 | 反方定级 | 反反方核验 | 终审判定 | 成立性 |
|------|---------|-----------|---------|--------|
| F1. CI 跨越0 反噬 | 致命 | 不成立（范畴错误） | **不成立（作为代码攻击）** | 不成立 |
| F2. brier_parts 未传 n_bins | 致命 | 部分成立（夸大） | **部分成立（风格问题）** | 部分成立 |
| S1. NCV 跨脚本定义不一致 | 严重 | 成立（超范围） | **成立（独立 issue）** | 成立 |
| S2. BCa cluster 数少时不稳定 | 严重 | 部分成立（仅冒烟） | **部分成立** | 部分成立 |
| S3. jackknife 全 NaN 静默降级 | 严重 | 成立 | **成立** | 成立 |
| S4. "符号相反→伪造"推理跳跃 | 严重 | 部分成立（论证表述） | **部分成立** | 部分成立 |
| M1. 冒烟 B=500 偏少 | 轻微 | 成立 | **成立** | 成立 |
| M2. z0 饱和零宽 CI | 轻微 | 成立 | **成立** | 成立 |
| M3. 空 bin reliability 低估 | 轻微 | 成立（预存） | **成立（预存）** | 成立 |

**关键判定**：
- **F1 不成立作为代码攻击**：CI 跨越0 是修复正确工作并揭示真相的标志，非 bug。反方将"科学结论的不利性"等同于"代码缺陷"是范畴错误。但正方应在论文中如实报告 NCV CI 跨越0，降级为"探索性观察"。
- **F2 严重性被夸大**：当前 `brier_parts` 默认 n_bins=10 与 E3 的 N_BINS=10 数值完全一致，P0-4 的 F1（签名不接受 n_bins）已修复。仅是显式传参的风格问题，非当前 bug。
- **S3 是真实边界失效**：`_bca_interval` 中 jackknife 全 NaN 时 `a` 静默退化为 0，BCa 降级无警告。虽非 P0-2 独有（`benefit_inference` 共用），但 P0-2 新增了第二个调用点，增加触发面。建议修补。

**修补清单**: 无必修项。3 项防御性增强建议（非阻塞）：
1. **[建议] [scripts/run_e1b_loco_validation.py 顶部]** 定义 `N_BINS = 10` 常量，`_ncv_stat` 和点估计显式传 `n_bins=N_BINS`（F2）
2. **[建议] [src/utils/calibration.py _bca_interval]** 加 `len(j) < 3` 检查，fallback 到 percentile CI 并警告（S3）
3. **[建议] [scripts/run_e1b_loco_validation.py L620]** BCa jackknife 前加 `len(units) < 30` 警告（S2）

**优先级**: 低（可关闭，防御性增强可后续采纳）

---

### P0-3: E2 消融逻辑

**最终状态**: 需补充修复（轻量，2 行）

**判定理由**:

反方提出 9 个攻击点，反反方确认**全部成立（含 2 个降级、3 个轻微）**。经终审独立判定：

| 攻击 | 反方定级 | 反反方核验 | 终审判定 | 成立性 |
|------|---------|-----------|---------|--------|
| F1. ECE 未传 n_bins=N_BINS | 致命 | 成立（降级严重） | **严重** | 成立 |
| F2. N_BINS=15 与全代码库不一致 | 致命 | 成立（降级严重） | **严重** | 成立 |
| S1. docstring 嵌套符号未更新 | 严重 | 成立 | **严重** | 成立 |
| S2. 分箱变量语义偏移 H(TS(p)) | 严重 | 成立 | **严重** | 成立 |
| S3. Stage3=Stage2 度量退化 | 严重 | 部分成立（降级中等） | **中等** | 部分成立 |
| S4. variant="binned" 命名误导 | 严重 | 成立 | **严重** | 成立 |
| M1. cal split in-sample 未标注 | 轻微 | 成立 | **轻微** | 成立 |
| M2. N_BINS 命名易混淆 | 轻微 | 成立 | **轻微** | 成立 |
| M3. 顺序拟合假设未声明 | 轻微 | 成立 | **轻微** | 成立 |

**核心判定**：
- **核心消融逻辑正确**：Stage 2 先 TS 再 binned-T 的嵌套关系 Θ_1⊂Θ_2⊂Θ_3 成立，P0-1 的原始问题（Stage 2 实现 binned only 破坏嵌套）已被有效解决。反反方经独立验证确认。
- **F1、F2 降级为严重（非致命）**：两者均为修复不完整或跨实验一致性问题，不影响 E2 内部消融的核心逻辑。"致命"应保留给"核心消融逻辑错误"。
- **F1 代码证据确凿**：L321 `ece(max_prob, correct)` 未传 n_bins，使用默认 10 箱，而 L315 `brier_parts(..., n_bins=N_BINS)` 用 15 箱。同一函数内两个校准指标分箱粒度不一致。
- **F2 推荐方案 A**：N_BINS=15 改为 10，与全代码库对齐。10 是校准评估的社区标准（Guo et al. 2017, Kumar et al. 2019 均用 10）。

**修补清单**:
1. **[scripts/run_e2_ablation_discrimination.py L321]** `ece(max_prob, correct)` → `ece(max_prob, correct, n_bins=N_BINS)`（F1，1 行）
2. **[scripts/run_e2_ablation_discrimination.py L131]** `N_BINS = 15` → `N_BINS = 10`，注释更新为"与 E3/E4/E6 及库默认一致"（F2，1 行）
3. **[建议] [L17]** docstring 嵌套符号更新为 `Θ_2 = {T_global, T_1..T_5}`（S1）
4. **[建议] [L31]** 假设 A1 声明分箱变量为 H(TS(p)) + E4 不可比声明（S2）
5. **[建议] [L520]** variant 名 `"binned"` → `"ts_binned"`（S4，需下游同步）
6. **[建议] [L679]** 汇总声明 `Δ(Stage3−Stage2)≡0 by construction`（S3）

**优先级**: 中（F1+F2 需在论文投稿前修复，2 行改动）

---

### P0-4: brier_parts n_bins

**最终状态**: 需回炉重修（轻量，1 行必修）

**判定理由**:

反方提出 8 个攻击点，反反方确认 **F2 是真实致命 bug**。经终审独立判定：

| 攻击 | 反方定级 | 反反方核验 | 终审判定 | 成立性 |
|------|---------|-----------|---------|--------|
| F1. 5 处调用方遗漏 n_bins | 致命 | 部分成立（夸大） | **严重（工程稳健性）** | 部分成立 |
| F2. compute_all_metrics L768 漏传 | 致命 | 成立 | **致命** | 成立 |
| F3. E2 用 N_BINS=15 不一致 | 严重 | 部分成立（归因有误） | **轻微（P0-3 职责）** | 部分成立 |
| F4. 跨实验分箱数不一致 | 严重 | 部分成立（非 P0-4 职责） | **轻微（实验设计决策）** | 部分成立 |
| S1. 无 n_bins 输入验证 | 严重 | 成立 | **严重（防御性）** | 成立 |
| S2. n_bins=0 时 reliability=0 | 严重 | 成立（与 S1 同一问题） | **严重（与 S1 合并）** | 成立 |
| S3. 测试因 F2 而失效 | 严重 | 成立 | **严重** | 成立 |
| M1. E6 不调用 brier_parts | 轻微 | 成立 | **轻微** | 成立 |
| M2. n_bins=浮点数崩溃 | 轻微 | 成立 | **轻微** | 成立 |
| M3. E1b 注释代码未传 n_bins | 轻微 | 成立 | **轻微** | 成立 |

**核心判定**：
- **F2 是真实致命 bug**：`compute_all_metrics()` L768 调用 `brier_parts(probs, labels)` 漏传 n_bins，而同函数内 L765 `bootstrap_ece` 和 L771 `mce` 都传了 n_bins。这是 P0-4 修复最直接的内部遗漏——修复了 `brier_parts` 签名却未更新同文件内调用，与 P0-4 修复目标（解决分箱不一致）直接矛盾。反方构造的反例 `compute_all_metrics(n_bins=5)` 确实会让 ECE/MCE 用 5 bin、Brier 用 10 bin。
- **F1 降级为严重**：5 处调用方未传 n_bins，但当前默认值=原始硬编码=10，行为完全等价，无任何数值变化。是工程稳健性问题而非当前 bug。
- **F3/F4 归因有误**：E2 用 N_BINS=15 是 P0-3 修补的有意选择，不是 P0-4 引入。反方将 P0-3 的行为变更归咎于 P0-4。

**修补清单**:
1. **[src/utils/calibration.py L768]** `brier_parts(probs, labels)` → `brier_parts(probs, labels, n_bins=n_bins)`（F2，必修，1 行）
2. **[建议] [src/utils/calibration.py L586 后]** 加输入验证 `if not isinstance(n_bins, (int, np.integer)) or n_bins < 1: raise ValueError(...)`（S1/S2）
3. **[建议] [tests/test_model.py]** 补充直接测试 `brier_parts(n_bins=5)` 与 `compute_all_metrics` 的 n_bins 一致性测试（S3）
4. **[建议] [scripts/run_e1a_l2_shift_full.py L159 + run_e1b_loco_validation.py L552/553/593/594]** 5 处显式传 `n_bins=10`（F1）

**优先级**: 高（F2 是必修项，1 行改动）

---

### P0-5: 全局 Brier

**最终状态**: 通过

**判定理由**:

反方提出 7 个指定攻击点 + 2 个严重攻击点 + 3 个轻微攻击点。反反方确认**核心修复逻辑无懈可击**。经终审独立判定：

| 攻击 | 反方定级 | 反反方核验 | 终审判定 | 成立性 |
|------|---------|-----------|---------|--------|
| 1. 全局计算是否真在 test 集上 | 无攻击点 | 不成立（正确） | **不成立** | 不成立 |
| 2. BRIER_N_BINS=10 vs N_BINS=5 | 无攻击点 | 不成立（正确） | **不成立** | 不成立 |
| 3. Δrel 字段符号方向 | 无攻击点 | 不成立（正确） | **不成立** | 不成立 |
| 4. 控制台汇总是否用 per-bin 均值 | 无攻击点 | 不成立（正确） | **不成立** | 不成立 |
| 5. CSV 新字段完整性 | 轻微 | 部分成立 | **轻微** | 部分成立 |
| 6. brier_parts 调用的 n_bins | 无攻击点 | 不成立（正确） | **不成立** | 不成立 |
| 7. id_probs_binned 变量来源 | 无攻击点 | 不成立（正确） | **不成立** | 不成立 |
| A. 跨 CSV 字段名冲突 | 严重 | 成立 | **严重（建议改进）** | 成立 |
| B. 只比较 Brier reliability | 严重 | 部分成立 | **部分成立（A5 假设体现）** | 部分成立 |
| C. DIST_STATS 字段滥用 | 轻微 | 成立（原有问题） | **轻微** | 成立 |
| D. BRIER_N_BINS 不可配置 | 轻微 | 成立 | **轻微** | 成立 |
| E. 内部变量名 "global" 双重含义 | 轻微 | 成立 | **轻微** | 成立 |

**核心判定**：
- **7 个指定攻击点中 6 个无懈可击**：反方自己承认"未发现可攻击点"，反反方经独立验证确认。全局计算确实在整个 test 集上一次计算，BRIER_N_BINS=10（评估分箱）与 N_BINS=5（干预分箱）维度不同不冲突，Δrel 符号方向正确，控制台汇总用全局 Δrel 非 per-bin 均值，brier_parts 显式传 n_bins=10，id_probs_binned 来源正确。
- **攻击 A 成立但非阻塞**：两个 CSV 同名字段 `id_rel_binned_T` 语义不同（全局 vs 箱级），会误导下游分析。建议重命名但非修复缺陷。
- **攻击 B 部分成立**：数学论证正确（Δrel<0 不保证整体 Brier 改善），但这是 docstring A5 显式假设的体现（"Brier reliability 是 binned-T 评估的合理指标"），非 P0-5 引入的 bug。正方已显式声明假设，符合学术规范。

**修补清单**: 无必修项。2 项改进建议（非阻塞）：
1. **[建议] [scripts/run_e4_temperature_analysis.py L563/L569/L801-803]** 将 `binned_temperature_exploratory.csv` 的箱级字段 `id_rel_binned_T` → `id_rel_binned_T_within_bin`，`ood_rel_binned_T` → `ood_rel_binned_T_within_bin`（攻击 A）
2. **[建议] [L519 后]** 补充整体 Brier score 的 Δ（`id_delta_brier_binned_vs_global`），控制台同时报告 Δrel 和 ΔBrier（攻击 B）

**优先级**: 低（可关闭，改进建议可后续采纳）

---

### P0-6+7: E5 OOM + 迁移

**最终状态**: 不通过（必须回炉重修）

**判定理由**:

反方提出 14 个攻击点（3 致命 + 7 严重 + 4 轻微），反反方确认**全部成立**（含 2 个范围/机制修正）。经终审独立判定：

| 攻击 | 反方定级 | 反反方核验 | 终审判定 | 成立性 |
|------|---------|-----------|---------|--------|
| F1. Level 3 ResNet1D 死代码 | 致命 | 成立 | **致命** | 成立 |
| F2. 标签语义错位 MI↔CD | 致命 | 成立（范围修正 4→2 方向） | **致命（最危险）** | 成立 |
| F3. 命令行参数静默失效 | 致命 | 成立 | **致命** | 成立 |
| S1. 截断重归一化 NaN 风险 | 严重 | 成立 | **严重** | 成立 |
| S2. 4→5 方向丢弃 HYP 样本 | 严重 | 成立（机制修正） | **严重** | 成立 |
| S3. 截断后语义偷换 | 严重 | 成立 | **严重** | 成立 |
| S4. 截断后概率分布扭曲 | 严重 | 成立 | **严重** | 成立 |
| S5. build_model dead import/depth 忽略 | 严重 | 成立 | **严重** | 成立 |
| S6. cal 集截断 T 在子集拟合 | 严重 | 成立 | **严重** | 成立 |
| S7. levels 列表两个 Level 1 | 严重 | 成立 | **严重** | 成立 |
| M1. report_oom_level 条件错误 | 轻微 | 成立 | **轻微** | 成立 |
| M2. 截断警告不充分 | 轻微 | 成立 | **轻微** | 成立 |
| M3. config 死参数 | 轻微 | 成立 | **轻微** | 成立 |
| M4. bootstrap CI 可能低估方差 | 轻微 | 成立 | **轻微** | 成立 |

**核心判定**：

- **F2 是本次全部 P0 审查中最危险的缺陷**：`SUPERCLASSES=("NORM","MI","STTC","CD","HYP")` 中 MI=1/CD=3，但 `SUBSPACE_CPSC=("NORM","CD","STTC","MI")` 中 CD=1/MI=3。标签 1 和 3 语义互换。P0-7 截断只做数值截断不做语义重映射，导致 ptbxl→cpsc 和 chapman→cpsc 两个方向的 MI/CD 预测全部算错。**这是隐式静默错误——实验运行完成、产出 CSV、无任何报错，但结果完全无意义**。P0-7 用更严重的错误（标签错位）替换了原 bug（IndexError 显性崩溃），违背了"修复不应引入新缺陷"的基本原则。

- **F1 确认成立**：Level 3 的 ResNet1D 变体（depth=3/5/7, width=32/64/128）无法被激活。`_train_adapter` 闭包只提取 n_filters/use_checkpoint，忽略 arch/depth/width；`train_single` 签名不接受 arch_override。三个 Level 3 变体全部退到 Level 4，"4 级 OOM 链"实际只有 2 级工作。P0-6 修复的核心承诺（激活 4 级备选链）未兑现。

- **F3 确认成立**：`try_train_with_oom_fallback` 的 n_filters/use_checkpoint 形参在函数体内完全未使用，备选配置由硬编码 levels 列表决定。`python scripts/run_e5_inception_lite.py --n-filters 32` 的用户参数被静默丢弃。

- **反反方修正 1（F2 影响范围）**：反方称 4 个方向受影响，实际只有 2 个方向（ptbxl→cpsc, chapman→cpsc）。cpsc→ptbxl 和 cpsc→chapman 方向的 source/target 编码一致（均用 SUBSPACE_CPSC），不受 F2 影响（但受 S2 影响——HYP 样本被 filter_subspace 丢弃）。**此修正不减弱 F2 的致命性**：2 个方向的迁移评估结果完全无意义，仍需 P0 级返工。

- **反反方修正 2（S2 机制）**：反方称"target 标签 4 的样本被 `ood_labels >= num_classes` 丢弃"，实际 HYP 样本在 `build_dataset` → `filter_subspace` 阶段就被剔除。效果相同（HYP 不评估），但机制描述不准确。

**修补清单**（按优先级排序）:

1. **[src/data/mapping.py L80]** `SUBSPACE_CPSC = ("NORM", "CD", "STTC", "MI")` → `SUBSPACE_CPSC = ("NORM", "MI", "STTC", "CD")`（F2，统一编码顺序与 SUPERCLASSES[:4] 一致，消除根因。需重跑 cpsc 训练）
2. **[scripts/run_e5_inception_lite.py train_single 签名 L268-275]** 增加 `arch_override=None, depth=None, width=None` 参数，传给 `build_model`（F1）
3. **[scripts/run_e5_inception_lite.py _train_adapter L607-612]** 传递 `arch_override=params.get("arch"), depth=params.get("depth"), width=params.get("width")`（F1）
4. **[scripts/run_e5_inception_lite.py build_model resnet1d 路径 L236-248]** 用 depth 构造真正的不同 backbone：`block_layers = block_layers_map.get(depth or 5, (2,2,2,2))`，直接构造 `ECGResNet1D` 并注入（F1+S5）
5. **[scripts/run_e5_inception_lite.py try_train_with_oom_fallback L169-179]** levels 列表第一项用传入的 n_filters/use_checkpoint：`(0, {"n_filters": n_filters, "use_checkpoint": use_checkpoint}, "用户指定配置")`（F3）
6. **[scripts/run_e5_inception_lite.py L414-415]** 截断重归一化前检查全零行，丢弃并警告（S1）
7. **[scripts/run_e5_inception_lite.py L169]** levels 第一项 level 改为 0（S7）
8. **[scripts/run_e5_inception_lite.py L183]** report_oom_level 条件改为 `if level > 0`（M1，配合 S7）
9. **[scripts/run_e5_inception_lite.py result dict]** 增加 `n_dropped_cal`, `n_dropped_ood`, `truncated`, `subspace_filtered` 字段（S3/M2）
10. **[建议] [scripts/run_e5_inception_lite.py]** 4→5 方向在 CSV 中标注 `n_dropped_hyp` 字段，明确"仅在 target 前4类上评估"（S2）

**优先级**: 最高（F2 标签语义错位是最危险缺陷，必须立即修复）

---

### P0-8: ECE 加权

**最终状态**: 不通过（必须回炉重修）

**判定理由**:

反方提出 11 个攻击点（3 致命 + 5 严重 + 3 轻微），反反方确认**全部成立**。经终审独立判定：

| 攻击 | 反方定级 | 反反方核验 | 终审判定 | 成立性 |
|------|---------|-----------|---------|--------|
| F1. "weighted avg ECE" ≠ 全局 ECE | 致命 | 成立 | **致命** | 成立 |
| F2. nan 传播 | 致命 | 成立 | **致命** | 成立 |
| F3. Guo et al. 2017 引用错误 | 致命 | 成立 | **致命** | 成立 |
| S1. 曲线 bin 级 vs ECE 方向级加权 | 严重 | 成立 | **严重** | 成立 |
| S2. 图例标签未说明权重 | 严重 | 成立 | **严重** | 成立 |
| S3. 标题与图例矛盾 | 严重 | 成立 | **严重** | 成立 |
| S4. nan ece 未过滤 | 严重 | 成立（F2 同因） | **严重** | 成立 |
| S5. 缺 bin_confidences 加权平均 | 严重 | 成立 | **严重** | 成立 |
| M1. 0.05 差异显著性 | 轻微 | 部分成立 | **轻微** | 部分成立 |
| M2. 单图 vs 汇总图语义不一致 | 轻微 | 成立 | **轻微** | 成立 |
| M3. 未报告 Brier/MCE | 轻微 | 成立（超范围） | **轻微** | 成立 |

**核心判定**：

- **F1 数学严格成立**：`_weighted_ece` 计算方向级加权平均 `Σ(N_dir×ECE_dir)/ΣN_dir`，但图例标注"weighted avg ECE"让读者理解为全局 ECE `Σ_bin(n_bin/N)×|conf-acc|`。反例已用 Python 复现：两方向偏差相反时，加权平均 ECE=0.1，全局 ECE=0.0，差 0.1，相对误差 ∞。ECE 含绝对值，`|x|+|y| ≠ |x+y|`，加权平均与绝对值不可交换。

- **F2 确认成立**：`np.average([0.2, nan], weights=[1000, 0]) = nan`。即使空方向权重为 0，nan 仍污染整体。触发场景现实（OOD 测试集缺失、checkpoint 缺失、`--limit=0`）。

- **F3 确认成立**：Guo et al. 2017 的 ECE 是单模型 bin 级加权 `Σ_b(n_b/N)×|acc(b)-conf(b)|`，不是多方向 ECE 的方向级加权平均。把"单模型 ECE 的 bin 加权定义"套用到"多方向 ECE 的方向加权平均"上并声称是 Guo et al. 标准定义，是概念混淆。CBM 期刊审稿人会当场抓出。

- **三种 ECE 数值验证**（反反方用 Python 复现）：简单平均=0.200，方向级加权平均=0.118，汇总曲线重算 ECE=0.082，三者互不相等。

**修补清单**（推荐方案 B，最小改动，3-4 处）:

1. **[scripts/run_e6_reliability_diagrams.py L437-443]** `_weighted_ece` 过滤 nan：`valid = np.isfinite(eces) & (weights > 0)`，`return float(np.average(eces[valid], weights=weights[valid]))`（F2+S4）
2. **[scripts/run_e6_reliability_diagrams.py L451/L456]** 图例标签改为 `size-weighted mean ECE`（F1+S2+M2）
3. **[scripts/run_e6_reliability_diagrams.py L433-436]** 注释删除 Guo 引用，改为诚实描述："这是方向级加权平均（跨方向按 n_total 加权），非 Guo et al. 2017 的原始 ECE 定义（单模型 bin 级加权）。方向级加权平均 ECE ≠ 全局 ECE"（F3+S1）
4. **[scripts/run_e6_reliability_diagrams.py L474-476]** 标题改为 `"curve: bin-count weighted; ECE: n_total-weighted mean"`（S3）
5. **[论文 Method 部分]** 补充一句话："汇总图 ECE 报告各方向 ECE 的样本数加权平均（size-weighted mean of per-direction ECE），非合并所有样本后重算的全局 ECE"

**方案选择论证**：方案 A（汇总曲线重算 ECE）数学更优但改动大（扩展 `_weighted_avg` 返回值签名，改多处调用，回归风险中）。方案 B（诚实标注 + 过滤 nan）改动小（3-4 处字符串/逻辑改动，零回归风险）。**Q2 补充阶段推荐方案 B**；若未来期刊要求严格全局 ECE，再迁移到方案 A。

**优先级**: 高（3 个致命缺陷，F2 nan 传播会让汇总图直接报废，F3 引用错误会被审稿人当场抓出）

---

## 回炉优先级排序

1. **P0-6+7（最高优先级）**: F2 标签语义错位是最危险缺陷——隐式静默错误替换显式崩溃，2 个迁移方向结果完全无意义且无报错。F1 Level 3 死代码使 P0-6 核心承诺未兑现。F3 命令行参数静默失效。共 3 致命 + 7 严重，必须立即返工。

2. **P0-8**: 3 个致命缺陷——F1 语义偏移（读者误以为全局 ECE）、F2 nan 传播（汇总图报废）、F3 Guo 引用错误（审稿人当场抓出）。推荐方案 B，3-4 处改动，零回归风险。

3. **P0-1**: 2 处遗漏修复（eval_l2_shift.py L44 + run_e4_temperature_analysis.py L307），原 bug 在这两个脚本中仍然存活。修复量小（2 处 + 1 处防御性警告），但属修复不完整的硬伤。

4. **P0-4**: 1 行必修修复（calibration.py L768 漏传 n_bins 给 brier_parts），与 P0-4 修复目标直接矛盾。改动最小但必须修复。

5. **P0-3**: 2 行修复（L321 ECE 传 n_bins + L131 N_BINS=15→10），核心消融逻辑正确但分箱不一致需在论文投稿前修复。

---

## 可关闭 P0 的防御性增强建议

### P0-2
1. **F2 显式传参**：E1b 顶部定义 `N_BINS = 10` 常量，`_ncv_stat` 和点估计显式传 `n_bins=N_BINS`，与 E3 对齐
2. **S3 边界保护**：`_bca_interval` 中加 `len(j) < 3` 检查，fallback 到 percentile CI 并警告（同时惠及 ΔECE 的 `benefit_inference`）
3. **S2 cluster 下限**：BCa jackknife 前加 `len(units) < 30` 警告，建议改用 percentile
4. **[论文]** 如实报告 NCV CI 跨越0，降级 NCV 为"探索性观察"（F1 科学诚实性）

### P0-5
1. **攻击 A 字段重命名**：将 `binned_temperature_exploratory.csv` 的箱级字段 `id_rel_binned_T` → `id_rel_binned_T_within_bin`，`ood_rel_binned_T` → `ood_rel_binned_T_within_bin`，消除跨 CSV 同名冲突。同步修正 docstring L76-79
2. **攻击 B 补充整体 Brier**：在 `dist_record` 中补充 `id_delta_brier_binned_vs_global`，控制台同时报告 Δrel 和 ΔBrier，让读者自行判断 binned-T 是否在 reliability 和整体 Brier 上一致改善
3. **[可选] 攻击 D**：添加 `--brier-n-bins` 参数，与 `--n-bins` 对称，支持 Brier reliability 箱数敏感性分析
4. **[可选] 攻击 E**：将内部变量 `id_rel_binned_global` 重命名为 `id_rel_binned_overall`，消除 "global" 语义双重含义

---

## 下一步行动建议

### 立即行动（本周内）

1. **P0-6+7 F2 修复**：修改 `src/data/mapping.py` 的 `SUBSPACE_CPSC` 顺序为 `("NORM", "MI", "STTC", "CD")`，与 `SUPERCLASSES[:4]` 一致。重跑 cpsc 训练和 2 个受影响迁移方向（ptbxl→cpsc, chapman→cpsc）。这是全部 P0 中最危险的缺陷，**优先于一切其他工作**。

2. **P0-8 方案 B 修复**：3-4 处改动（过滤 nan + 改标签 + 删 Guo 引用 + 改标题），零回归风险，可立即提交。

3. **P0-1 攻击 1+2 修复**：`eval_l2_shift.py` 和 `run_e4_temperature_analysis.py` 两处遗漏修复，每处 2 行改动，修复后删除 `run_e1a` 中的重复实现改为导入。

### 论文投稿前（1-2 周内）

4. **P0-4 F2 修复**：`calibration.py` L768 一行改动，必修。

5. **P0-3 F1+F2 修复**：`run_e2_ablation_discrimination.py` 两行改动（L321 + L131），同步更新 docstring（S1/S2/S4）。

6. **P0-6+7 F1+F3+S5 修复**：激活 Level 3 ResNet1D 真正变体 + 命令行参数生效 + build_model depth 生效。工作量中等（~30 行），需回归测试。

7. **P0-1 攻击 3 论文声明**：在论文和代码 docstring 中明确声明"噪声实现固定为 seed 42，跨 seed 方差仅反映模型训练变异"。

### 防御性增强（可后续迭代）

8. **P0-2 三项增强**：F2 显式传参 + S3 边界保护 + S2 cluster 下限警告。

9. **P0-5 两项改进**：字段重命名 + 补充整体 Brier。

10. **P0-6+7 S1-S7+M1-M4**：NaN 防护、截断标注、语义声明、levels 编号修正等，可在 F2 修复后批量处理。

### 质量保证

11. **补充测试**：P0-4 S3 建议补充直接测试 `brier_parts(n_bins=5)` 与 `compute_all_metrics` 的 n_bins 一致性测试，以能捕获 F2 类 bug。

12. **全局 grep 审计**：对 `apply_shift`、`brier_parts`、`compute_all_metrics` 等关键函数做全局调用方扫描，确认无遗漏未传参调用方。

---

## 终审声明

本报告由终审代理独立撰写，综合了 7 份反方攻击报告和 7 份反反方回应报告的全文内容，对每个攻击点给出了成立/不成立/部分成立的独立判定。判定标准为 CBM 期刊（IF~7）审稿要求：代码正确性无懈可击、统计方法严谨、跨实验一致性声明透明、隐含假设显式化。

**关键发现**：
- 反方攻击整体质量高，14 份报告均有代码实证，无臆测。
- 反反方回应客观诚实，对成立的攻击承认并给修补方案，对夸大的攻击给反驳证据。
- 两处反方攻击被反反方修正（非反驳）：P0-6+7 F2 影响范围 4→2 方向、S2 机制描述偏差。这些修正不改变攻击的成立性。
- 最危险的缺陷是 P0-6+7 F2（标签语义错位），它用隐式静默错误替换了显式崩溃，违背了修复的基本原则。

**最终判定**：8 个 P0 中 2 个可关闭（P0-2、P0-5）、3 个需轻量修补（P0-1、P0-3、P0-4）、2 个必须回炉重修（P0-6+7、P0-8）。回炉优先级：P0-6+7 > P0-8 > P0-1 > P0-4 > P0-3。
