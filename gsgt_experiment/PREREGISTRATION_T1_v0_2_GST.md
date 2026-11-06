# T1 预注册修订 v0.2｜方法主线由 PARI 改为 GST

**冻结时间**：2026-11-05
**前置**：`PREREGISTRATION_T1_draft.md` v0.1（W1 后写，保留）
**依据**：W2 探索性 + 两批独立确认性复现（`gsgt_confirmatory_results.json`、`gsgt_v1_1_results.json`、`w2_pooled_summary.json`）

---

## 1. 主线变更（终局，不可再改）

| | v0.1 | **v0.2（本版）** |
|---|---|---|
| 主线方法 | PARI（患者内重复测量配对、单标量 T） | **GST：按可观测部署群分别无标签拟合 T_g** |
| 估计目标 | 1 维 | **G 维**（cart_id / site / 年份 / 导联子集） |
| 图正则 | 无 | **明确删除**（两批确认性实验均显示轻微有害） |
| 患者内配对 | 核心机制 | **删除**（W1 已否证，无一致优势、A1 无效） |

**删除图正则的证据（必须写进论文 Limitations / Negative Results）**：
- 图收缩贡献：v1.0 **+0.00021**、v1.1 **+0.00047** ECE（两批均为正 = 有害）
- F-B 打乱图：v1.0 **+0.00338**、v1.1 **−0.00348**，**两批独立种子方向翻转**，效应不可复现
- 群结构化解释总增益 **100.8%**（图收缩为负贡献）

**结论**：`GSGT` 完整包按 v1.1 冻结条款 `all_pass=False`，**不得作为论文级方法主张**；保留的是其**无图版本 GST**。

---

## 2. GST 定义（冻结）

给定部署元数据定义的 G 个群，源域已校准参考直方图 `h_ref`：

```
Psi_g(T) = || h_g(softmax(z_g / T)) - h_ref ||^2     # 无标签
T_hat_g  = argmin_T Psi_g(T)                          # 每群独立，网格 + 抛物线细化
```

- **不**学 embedding→T 映射（区别 MD-TS）
- **不**需要 domain label 训练、不做未见域外推
- **不**改模型、post-hoc、冻结 encoder
- **不**从 3 个标量恢复条件正确率曲线（不触碰 Transfer Gap 不可识别性）

逐记录 logits 由冻结 encoder 一次性前向缓存；全部校准实验在 logits 上零 GPU 重跑。

---

## 3. T1 事前注册终点（覆盖 v0.1 的 H1）

### 主终点
`ΔECE = ECE(GST) − ECE(GLOBAL)`，GLOBAL = 全体 pooled 单温度（即原项目 TS / W1 pooled）。

**通过需同时满足**：
1. `mean ΔECE ≤ −0.020`（跨 ≥ 3 类外验 × 5 seeds）
2. **跨外验折的 paired bootstrap**（抽样单位 = 外验折/种子，B=10,000）95% CI 上界 < 0
   > 抽样单位错配是 W2 v1.0 判 False 的原因，本版从一开始就固定为跨折 bootstrap
3. 至少 3 类非 in-sample 外验：leave-one-site / leave-one-cart / leave-one-year
4. **患者级 block bootstrap** 报告所有 CI（1,145,814 记录 ≠ 独立样本）

### 次要终点
- 每群 T̂_g 分布、群间 I²、E5 单温度后悔曲线（0 → 0.156）
- 对照：SOURCE / GLOBAL / INDEP=GST / SHRINK-GLOBAL / BCTS / BBSE / MD-TS / ECL / Wang et al. / oracle
- 最小标注预算 n̂_cal、BCC 证书（含降级路径）
- 阵发性标签层、慢性层**分开报告**，即使不利

### 分层（事前）
慢性/结构性 vs 阵发；site；cart_id；年份；导联子集；采样率；性别/年龄（若可得）。

---

## 4. 证伪（T1 必须执行）

| ID | 操作 | 预期 |
|---|---|---|
| T-F1 | 把所有群合并为 1 群 | GST 退化为 GLOBAL，优势消失 |
| T-F2 | 随机置换 `group_id` | GST 优势消失（证明元数据而非偶然分箱） |
| T-F3 | 群内温度同质子层 | GST ≈ GLOBAL |
| T-F4 | 标签本体映射敏感性（A4 battery） | 结论不随映射翻转 |
| T-F5 | 导联下标错位对照 | 校准显著改变（证明按名对齐必要） |

---

## 5. 失败条款（终局）

| 触发 | 处置 |
|---|---|
| 主终点任一条件不满足 | GST 降级为探索性；回到 BCC + 1.15M 系统验证 + E5 问题结论 |
| T-F1/F2 不符 | 删除「部署群携带校准信息」因果解释 |
| BCC 理论界未证出 | 明写「无理论保证」 |
| DUA 未获批 | CODE-15% 单队列 T1-mini，规模声明下调 |
| 任一发生 | **如实发表负面结果**，不撤稿、不换指标、不选择性报告 |

**不再修订预注册**。W2 已有 v1.0 / v1.1 两轮条款修正，T1 不接受第三次。

---

## 6. 必须随论文公开的历史结果（不得删除）

1. W1：PARI 无一致优势、F4 显示 A1 无效（`pari_synthetic_results.json` / `pari_diagnostic_results.json`）
2. W2 v1.0：**H1 = False**（单种子 bootstrap CI 跨零），`gsgt_confirmatory_results.json`
3. W2 v1.1：`all_pass = False`（F-B 失败），图收缩两批均有害、F-B 方向翻转
4. W2 首轮探索性因「标签被固定为主类」导致 ORACLE 反而最差，已由 F0 门槛拦截并修正

> 这段审计史不是瑕疵，是可复现性与负面结果披露的一部分；原项目已有更正账本的先例。

---

## 7. 数据 / 准入（不变）

MIMIC-IV-ECG 800,035 / 161,352（PhysioNet credentialed DUA）+ CODE-15% 345,779 / 233,770（CC BY 4.0）= **1,145,814 记录 / ≈395,122 患者**。`preflight.py` 七项断言全部通过方可前向，含导联按名对齐、患者级切分、A3 轨道覆盖、CODE-15% 歧义阴性排除、固定刻度统计、预注册时间戳早于首个前向、有效样本量声明。

分区与期刊目标以单位认定最新名单为准；W2 为合成验证，**不得外推为真实数据结论**。

**签署**：作者 ______ ／ 统计合作者 ______ ／ 临床合作者 ______
