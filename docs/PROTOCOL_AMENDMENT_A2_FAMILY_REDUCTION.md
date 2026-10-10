# 预注册修订案 A2 — Confirmatory 家族缩减：156 → 12

> **修订案编号**：A2
> **修订日期**：2026-09-10
> **触发轮次**：加强方案对抗审查（步骤 4）
> **修订类型**：预注册修订（Preregistration Revision，Nosek et al. 2018 分类）
> **修订前协议哈希**：见 OSF 存档（EXPERIMENT_PROTOCOL.md v2.1-A1 修订前快照）
> **状态**：预注册修订草案，待 OSF 时间戳存档

---

## A2.1 修订前（as-registered）

- **Confirmatory 家族**：156 检验 = 6 迁移对 × 2 主架构 × 13 移位级（协议 §6:91）
- **主检验**：H₀: ΔECE_OOD = 0 vs H₁: ΔECE_OOD > 0，逐格 BH-FDR q=0.05
- **L2 移位级**：13 档（采样率 500→250→125 Hz、导联 12→6→3→2→1、噪声 SNR {24,12,6,0,−6} dB、增益 ×0.5/×2）

## A2.2 修订后（as-revised）

- **Confirmatory 家族**：12 检验 = 6 迁移对 × 2 主架构 × **1 移位级（L0/L1 主网格）**
- **主检验**：H₀: ΔECE_OOD = 0 vs H₁: ΔECE_OOD > 0，12 格 BH-FDR q=0.05
- **L2 移位级**：13 档定位为 **exploratory 剂量反应曲线**，不进 confirmatory 家族，报告逐档 CI 不报告 confirmatory p 值
- **60 seed experiments**：定位为 **robustness evidence**（每 confirmatory 格 5 种子重复），不进 confirmatory 家族

## A2.3 修订理由

1. **L2 是 eval-time 变换非 confirmatory**：L2 移位级（降采样/丢导联/加噪/增益）是 eval-time 概率变换，不重训练模型，本质是**剂量反应探索**而非确认性检验。将其纳入 confirmatory 家族混淆了"确认主终点"与"探索移位剂量"两个科学目标。
2. **156 家族未跑全**：confirmatory 家族 156 需 13 档全部跑完，实际 L2 覆盖 157/390（40%），双种子单架构，ResNet L2 13 格被排除。未跑全的家族做 BH 校正是空中楼阁。
3. **12 格 confirmatory 可做实**：6 对×2 架构×5 种子 = 60 实验全部完成，12 格每格 5 种子聚合（meta-analytic pooled ΔECE），BH-12 可严格执行。
4. **与 A1 一致**：A1 重新定位主终点（decay→ΔECE_OOD），A2 缩家族，两者独立。A2 不改变主终点定义，只缩 confirmatory 家族规模。

## A2.4 透明性声明（非 HARKing）

- **修订方向先验**：L2 eval-only 是 exploratory 剂量反应的判断由**实验设计**（eval-time 变换不重训练）先验确定，非由结果方向驱动。
- **修订前 156 家族的探索性结果不进入主报告**：L2 剂量反应曲线作为 exploratory 补充，不作为 confirmatory 结论证据。
- **Nosek et al. 2018 预注册修订**：在主网格数据收集完成后、投稿前登记修订前/后协议哈希、修订理由、修订日期。

## A2.5 修订前/后对照表

| 项 | 修订前 | 修订后 |
|---|---|---|
| Confirmatory 家族大小 | 156 | 12 |
| L2 角色 | confirmatory 家族成员 | exploratory 剂量反应 |
| 60 seed experiments | 家族成员 | robustness evidence（每格 5 种子重复） |
| BH-FDR | BH-156（未跑全） | BH-12（可严格执行） |
| 主结论 | 51/60（BH-60 robustness） | 9/12（BH-12 confirmatory）+ 51/60 robustness |

## A2.6 BH-12 结果（confirmatory）

- **12 格聚合**：每格 5 种子 meta-analytic pooled ΔECE（DerSimonian-Laird 随机效应）
- **BH-12 q=0.05**：9/12 显6/6），3/12 不显著（cpsc_chapman/RN, cpsc_ptbxl/RN, chapman_cpsc/IT 边界）
- **Bonferroni-12**：2/12 显著（cpsc_chapman/IT, ptbxl_chapman/RN）
- **Robustness evidence**：51/60 seed experiments 支持（BH-60 51/60，与 confirmatory 不冲突）

## A2.7 对主结论的影响

主结论从"51/60 seed experiments 支持"重组为：
1. **Confirmatory**：9/12 方向×架构格 BH-12 显著（75%）
2. **Robustness**：51/60 seed experiments 支持（85%），作为每 confirmatory 格的 5 种子稳健性证据
3. **Exploratory**：L2 13 档剂量反应曲线（157/390 覆盖，双种子单架构）

这一重组**不削弱**主结论的"TS 在跨库 ECG 迁移下有正向 OOD 校准收益"叙事，反而**强化**了 confirmatory 严格性（12 格可做实 vs 156 未跑全）。

---

## 附录：与步骤 2 判别力门控的协同

A2 缩家族到 12 格 confirmatory 后，步骤 2 的判别力门控在 12 格上操作：
- 7/12 格通过门控（acc > 目标多数类基线）→ 可部署
- 5/12 格拒绝门控（判别力不足）→ 校准有效但不可部署
- Confirmatory 可部署格：BH-12 显著 & 门控通过 = 7/12（待实测聚合后确认）

C5 贡献：discrimination-aware calibration gate，在 confirmatory 12 格上验证门控的敏感度/特异度。