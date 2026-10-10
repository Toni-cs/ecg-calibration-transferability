# ECG校准修复边界研究 — 预注册实验协议 v2.1-A1

> 本协议由五路独立对抗性审查（实验设计/统计方法/工程可复现性/文献novelty/Reviewer 2模拟）交叉验证后生成。
> 状态：**预注册草案**。投稿前应将本文件哈希存档至OSF等时间戳平台。
> **修订历史**：v2.0（初始五路审查版本）→ v2.1-A1（2026-09-05，预注册修订案A1合并：主终点重新定位 decay→ΔECE_OOD，§6符号笔误修正，贡献声明重新定位；修订案全文见文末附录A1）。

## 0. Novelty重定位（文献审查结论）

**不得声称**："首次在ECG上证明校准修复收益从内部到外部衰减"
——这是Ovadia et al. (NeurIPS 2019)已知结论的ECG复现，且Barandas 2023、Zhang 2022、Physiol Meas 2026已分别报道ECG上的现象。

**应声称**（三步链，每步都有剩余novelty空间）：
1. **参数级分解**：将校准修复收益的ID→OOD衰减分解为slope/intercept/prevalence三个可干预成分的贡献占比（ECG深度模型+跨数据集公开基准上无人做过"贡献占比"视角）
2. **可预测性**：用目标域无标签统计量（预测先验L1距离、logit分布统计量）预测修复收益保留率
3. **部署判据**：输出"移位类型 × 主导成分 × 推荐再校准策略"的可操作决策表，并在迁移矩阵留出集上验证判据的敏感度/特异度

**贡献层级（A1.5 修订）**：
1. **主贡献**：OOD 校准收益量化（主终点 ΔECE_OOD 显著正向）
2. **边界条件贡献**：ID 无可修空间边界（ΔECE_ID ≈ 0，确立主贡献非平凡性）
3. **辅助贡献**：§8.5 可预测性（补齐 3 架构，回归样本 = 18）
4. **辅助贡献**：§9 部署判据（补齐敏感度/特异度 + 平凡策略对照）

**必须正面引用**（引言锚点）：Ovadia 2019, van Calster 2016/2019, Guo 2017, Kull 2019 (Dirichlet), Nixon 2019, Kumar 2019, Alexandari 2020, Lipton 2018 (BBSE), Wagner 2020 (PTB-XL), Strodthoff 2021。
**必须显式对比的最近邻**：Physiol Meas 2026 (RR-interval AF跨库校准，特征模型vs本文深度多标签)；medRxiv 2026 ICU calibration drift（slope保持/intercept漂移平行结论）；TransCal/PseudoCal/LaSCal（方法类上界）。

## 1. 术语纪律

- "recalibration"（非"calibration repair"）
- "transportability"（非"portability"）
- "dataset shift"必须细分为：covariate shift / prior probability shift / concept shift（Moreno-Torres 2012分类法），逐迁移对声明类型
- 拒用比值作主报告量："ΔECE = X [95% CI]，基线Y→修复后Z"格式；比值仅括号内出现

## 2. 数据与划分（防泄漏协议）

| 库 | 角色 | 划分 |
|---|---|---|
| PTB-XL v1.0.3 | 源/目标 | **官方10折**：folds 1-8训练 / fold 9校准 / fold 10内部测试（patient-stratified） |
| Chapman-Shaoxing | 源/目标 | 患者级分层 70/10/20，固定种子 |
| CPSC2018+2019 | 源/目标 | 患者级分层 70/10/20；**HYP极稀有(n=11,全来自CPSC2019单标签LVH/RVH)→主分析降级{NORM,CD,STTC,MI}4类子空间**（R16修订：原假设"CPSC无HYP"经全量预处理推翻，HYP=11不支持可靠val/test估计）。HYP记录**剔除并在STROBE流程图单列计数，不做重映射**；涉及CPSC的迁移对**两侧均按同4类子空间重算**（对称性） |
| （可选）Ningbo | 增加对数 | 同上 |

- **硬性断言脚本**：train/cal/test患者ID交集为空（进CI与复现仓库）
- 单标签优先级规则固定并做敏感性分析；多标签sigmoid作第二形式化
- STROBE式流程图：每库原始记录→映射后→排除→终样本，逐类计数
- 归一化统计量**只来自train split**；增广只作用于train

## 3. 移位剂量阶梯（BSPC叙事第一幕）——eval-only为主，控制计算预算

- **L0**：源test（ID基线）
- **L1**：跨库有向对，3库全排列=6对
- **L2**（**eval-time变换，不重训练**，Ovadia 2019同款惯例）：
  - 采样率 500→250→125 Hz（eval-time抗混叠降采样）
  - 导联 12→6→3→2→1（eval-time通道置零；**R16语义声明**：leads6档实际保留8个独立通道{I,II,V1-V6}，移除4个线性可导出导联{III,aVR,aVL,aVF}——完整12导联可由I,II,V1-V6线性重构（Goldberger/Wilson电极关系），属信息无损降档；leads3={I,II,V2}为预注册子集）
  - 噪声注入（PTB-XL Noise Stress Test DB: BWL/MA/EM）@ SNR {24,12,6,0,−6} dB
  - 增益 ×0.5 / ×2（**R16语义声明**：在per-record z-score归一化后施加，不重新归一化；实测原始信号×2再归一化与归一化后×2逐位一致max|Δ|<1e-6，即采集端增益误差被per-record z-score完全抵消；本档模拟归一化管线后的增益失配，非采集端增益误差）
  - **重训练验证点**：仅InceptionTime×PTB-XL源×导联4降档{6,3,2,1}×5种子（20 runs）验证"eval-time移位结论与重训练模型一致"（R轮修订：原文"6档/30 runs"为笔误，与§3.5预算表统一为20 runs；R15修订：BiMamba→InceptionTime，因BiMamba全分辨率OOM）
- 外部性量化：逐导联功率谱KS检验/MMD报告库间信号分布距离

## 3.5 计算预算表（第二轮审查新增，防不可行设计）

| 项 | 规模 | 估计 |
|---|---|---|
| 基础训练 | 3架构×3库×5种子（固定划分） | 45 runs ≈ 3-5 GPU日 |
| 重训练验证点 | InceptionTime×1库×4导联档×5种子 | 20 runs ≈ 1-2 GPU日（R15修订：BiMamba→InceptionTime） |
| S1主网格 | 6对×2主架构×5种子×7主方法 | eval-only ≈ 2-4 GPU时（R15修订：3→2主架构） |
| L2阶梯 | 全eval-only | ≈ 4-8 GPU时 |
| S2小样本 | 4方法×5 n_cal×20重复×代表档（代表档=L2非基线13移位级中选4个代表：采样率250Hz/导联6/噪声12dB/增益×2） | ≈ 4×5×20×4=1600次拟合/代表档，跨13档全跑≈2.1万次 ≈ 8-12 CPU时（与§5:85一致） |
| Bootstrap | 主检验/G: B=10,000；次要: B=2,000 | ≈ 8-12 CPU时 |
| **合计** | | **≈ 5-8 GPU日 + 1 CPU日**（单卡8GB投稿周期内可行）|

**方法池（M1-M13）**：主文7个（None/TS/per-class Platt/Isotonic/Dirichlet/Saerens EM/Oracle）+ 附录6个（Vector/Matrix scaling/CORAL/TTA/MC-Dropout±TS）。附录方法仅在PTB-XL源的2个代表对上跑。
- BBSE处理：单标签OvR下与Saerens EM同族，以Saerens代表，§5写明排除理由
- TTA定义：高斯噪声σ=0.005mV×8 + 时间移位±20ms×2，平均softmax

## 4. 模型与训练

- **3架构 × ≥5种子**：InceptionTime（主）、1D-ResNet-34、BiMamba（辅助；R15：全分辨率OOM on RTX 5060 8GB，降采样输入上单独验证）
- InceptionTime/1D-ResNet-34为主实验架构；BiMamba作辅助稳健性验证。BiMamba须报告与公开SOTA（AUROC macro ≈0.92-0.93）对齐——**该对齐声明在§2:36多标签sigmoid第二形式化下报告**（Wagner 2020数字为多标签协议产物，与单标签5类softmax主轨原则上不可比；R轮修订/M5修复，单标签主轨不作SOTA对齐比较）；mambapy与官方kernel数值一致性测试（max|Δy|<1e-4）
- 训练协议：AdamW + cosine schedule + linear warmup + grad clip 1.0 + NaN防护
- **温度单一化**：主协议训练时T≡1冻结（learnable_temp=False已实施）；co-trained T作独立消融轨且不再post-hoc拟合
- **MC-Dropout协议**：BN冻结（已实施）；聚合=平均softmax概率；MC-Dropout与MC-Dropout+TS进方法表；T=20次前向平均**后**的概率上拟合TS
- 早停准则跨所有库/架构统一：val NLL（明示该选择对基线校准的影响）
- 显存可行性：patch-embedding下采样（/4）或d_model≤128；论文如实报告硬件

## 5. 校准方法库 × 三场景

方法全矩阵（R2命门：不跑全就是"没试对方法"的把柄）：
None / TS / per-class Platt / Vector scaling / Matrix scaling / Isotonic(OvR，报告拟合集大小) / Dirichlet / Saerens EM先验适配（无标签，**不适用于S1源cal拟合范式**——saerens参数=目标先验，需目标域估计；归入S1'目标域无监督适配）/ CORAL+重校准 / TTA / MC-Dropout / **Oracle**（目标域cal split全量拟合、与所有方法同test集评估=R轮修订统一§6定义，防in-sample偏差；每迁移格独立拟合）

场景：
- **S1 零样本迁移**（主分析）：源cal拟合→目标直接用（R14修订：原§5"源val拟合"改为"源cal拟合"，与eval_transfer.py实现一致；偏离已登记R14）
- **S2 本地小样本再校准**（临床手册）：目标域 n_cal ∈ {50,100,250,500,1000} 有标签样本，患者级抽样×20重复 → "标注预算-收益挽回"剂量曲线
- **S3 目标全量refit**（上界）

## 6. 终点定义（写死，禁止事后修改）

**主形式化**：单标签5类softmax；**主ECE=5类confidence SmoothECE**（无分箱偏差），classwise宏平均为次要视角。

**终点层级（A1 修订）**：
- **主终点 = ΔECE_OOD**（唯一，A1.1 重新定位）
- **边界条件终点 = ΔECE_ID**（预期 H₀ 不拒绝，A1.4）
- **次要终点**：G（可挽回损失）、decay（次要描述量，A1.1 降级）、R（保留率）、NLL、classwise-ECE、Brier Murphy 分解、Cox slope/intercept、预测/真实先验 L1 距离
- 主检验只有一个，逐格比较全部进 BH 家族（家族大小 = 6 对 × 2 主架构 × 13 移位级 = 156 检验，与 §3:44-48 枚举一致）

**主终点（A1.3 正式定义）**：
- ΔECE_OOD = ECE_raw_OOD − ECE_TS_OOD
  - ECE_raw_OOD：源域训练、目标域 raw 概率上计算的 5 类 confidence SmoothECE
  - ECE_TS_OOD：源域训练、源 cal 拟合温度 T、目标域 TS 后概率上计算的 5 类 confidence SmoothECE
  - TS 拟合范式：源 cal 拟合（与 §5:84 S1 一致，R14 修订）
  - SmoothECE 带宽：0.45·(n/2000)^(−0.2)（与 §11.5 F3 一致）

**边界条件终点（A1.4 正式定义）**：
- ΔECE_ID = ECE_raw_ID − ECE_TS_ID
  - ECE_raw_ID：源域训练、源域 raw 概率上计算的 5 类 confidence SmoothECE
  - ECE_TS_ID：源域训练、源 cal 拟合温度 T、源域 TS 后概率上计算的 5 类 confidence SmoothECE
  - 预期 H₀: ΔECE_ID = 0 不被拒绝
  - 稳健性判据（写死）：95% CI 含 0 的格占比 ≥ 80% → 边界条件稳健
  - 分支触发：< 80% → "ID 非零边界"分支，主结论增加边界条件限定语（A1.4.2）

**次要终点**：
- G = ECE_S1(目标) − ECE_oracle(目标)  【可挽回损失：区分"没东西可修"vs"修不动"】
  - Oracle 定义（防 in-sample 偏差）：目标域 cal split 全量拟合、与所有方法同 test 集评估；每迁移格独立拟合
- decay = ΔECE_OOD − ΔECE_ID  【A1.1 降级为次要描述量；A1.2 笔误修正：decay 正 = OOD 收益 − ID 收益】
- R = ΔECE_ext / ΔECE_int（仅描述 + 敏感性检验）
- NLL；classwise-ECE（宏平均，空类单列）；Brier Murphy 分解（逐类二值化构造，单测断言恒等；跨库只比 REL 项）；Cox slope/intercept；预测/真实先验 L1 距离

**主检验（唯一，A1.1 重新定位）**：
H₀: ΔECE_OOD = 0  vs  H₁: ΔECE_OOD > 0（单侧，方向先验：TS 在凸损失下保序，Guo 2017/Kull 2019）
患者级 cluster 配对 bootstrap B=10,000 BCa；分层池化：strata = 迁移对 × 架构
点估计 = 全样本统计量（永不报 bootstrap 均值），格式 "ΔECE_OOD = X [95% CI L, U]，基线 Y → 修复后 Z"
ΔECE_OOD ≤ 0 的单元：报告"修复有害或无效"计数，不进入正向收益声明

**次级家族**：BH-FDR q=0.05（家族大小 156）；其余标注 exploratory 只报 CI
**Sanity**：全局 TS 后 argmax 逐位不变（已在 train.py 断言）

**预设解读（prevalence 匹配实验，支柱实验）——TOST 三段式，数值边界写死**：
- 匹配启用条件：匹配后类边际先验最大绝对差 ≤ 0.02，否则报"匹配失败"分支，不参与解读
- **衰减保留** = R 的 95%CI 下界 ≥ 0.7
- **衰减消失** = CI 包含 1 且点估计 ≥ 0.85
- **部分衰减** = 其余情形
- 匹配 = 按类边际先验患者级子采样；联合匹配不可行时报告匹配残差

## 7. 统计协议

- 重采样单元=患者（cluster bootstrap）；主检验/G用B=10,000 BCa；次要终点B=2,000百分位
- 两层联合bootstrap：val重采样→拟合T→test重采样→指标（T不确定性传入CI）
- **划分方差分量**：仅在Chapman/CPSC（可重划分）以5个患者级重划分×InceptionTime估计；PTB-XL以官方折为主划分（与§2一致），folds 1-8内部重划分仅作敏感性——解决官方折与"≥5划分"的冲突（R15修订：BiMamba→InceptionTime）
- 点估计=全样本统计量，**永不报bootstrap均值**
- ECE估计量：主=SmoothECE（已实施并修正）；敏感性=等宽10+等频15双报；MCE仅等频+bin容量≥50
- McNemar精确二项版，阈值只在val搜；DeLong仅跨模型比较
- 功效：**pilot=1个迁移对×1架构×2种子的独立预实验（结果不进主检验报告）**，估Var(log ΔECE) → n=(z_.975+z_.8)²·Var/d²，逐L2级别报告最小可行n

## 8. 机制分解验证（三条腿，缺一即撤回"机制"措辞）

> **R轮状态注记**：腿1（恒等式+析因交互报告）、腿2（合成门槛）已兑现；腿3的
> **合成环境可做部分已兑现**（v3：27格归因量样本级bootstrap CI + entangle_demo_cases
> 三案例证明纠缠分支可达 + 恢复失败路径统一，见validate_decomposition.py v3与
> results/decomposition_validation_n20000.csv的CI列）。**cross-fitting仍待真实数据**
> ——已补登§13。按本节自缚条款，"机制"措辞在cross-fitting完成前须限定为
> "机制分解（合成验证部分）"。

1. **数学声明**：Murphy分解=精确恒等式（OvR逐类构造）；三成分归因=反事实替换可加近似，**交互残差显式报告**（v3已入CSV：chain_residual列，链式套叠下恒为0，真实交互见析因项I_*）
2. **合成注入**：27格全因子（slope∈{0.5,1,2}×intercept∈{−1,0,1}×prevalence∈{0.15,0.3,0.6}）。**门槛仅施加于预定义可辨识区**（判定规则：Fisher信息行列式>阈值τ，τ预注册），恢复MAPE<10%为门槛；纠缠区仅报告误差图，不设门槛。
   **R轮偏离登记（预注册纪律）**：原文prevalence因子为乘性{0.5,1,2}——×2→π=1.0正类耗尽（n_neg=0，恢复回归退化）、×1≈基线先验0.5（不触发重采样，prev轴空转）；实现改为绝对值{0.15,0.3,0.6}，偏离理由=可行性+覆盖基线两侧，偏离日期2026-08-29（实现时）。
   **门槛诚实语义（R2修复）**：gate(n)=max(10%, 3×MAPE_REF×sqrt(N_REF/n))中MAPE_REF为**单种子单次实测**，"3×"是启发式放大因子**而非3σ容差**；n=500实测违率≈22%（存档CSV可查），小样本FAIL由信息模式exit 2如实报告，不构成预注册门槛的移动。
3. **可辨识性**：合成环境验证三成分纠缠区域（v3已兑现：narrow_band/tiny_slope/deep_intercept三案例，det∈{2.4e-7,3.6e-8,0}<τ=1e-6）；分解归因带bootstrap CI（v3已兑现：绝对Shapley值/链式分量/Δ_total/I_sb的percentile CI；占比不设CI——分母可跨0），CI重叠不得排序"主因"；Shapley占比附share_reliable标志（|Δ_total|<3/√n不可解读）；cross-fitting（OOD折半验证分解的解释力）待真实数据（§13）

## 8.5 可预测性实验（novelty三步链的中段，缺失即链断）

**特征**（全部目标域无标签或低成本可估）：预测先验L1距离、logit一/二阶矩、信号级KS/MMD距离（§3）、移位剂量档
**模型**：岭回归（特征≤5，防过拟合）
**评估**：leave-one-transfer-pair-out，报告LOO R² + bootstrap CI
**预注册失败分支（写死）**：若LOO R²的95%CI上界<0.5 → 论文降级为两步链（分解+判据），判据改称"经验查表"，**禁止事后追认预测性**
**样本量边界**（R轮修订/R15修订/消除内部算术矛盾）：回归样本=迁移对×架构=6×3=**18个**（可预测性分析用全3架构增大回归样本量，与主检验2主架构区分；同源模型衍生，高度相依），LOO折按迁移对=6；LOO R²的CI必须如实报告宽度。R²<0.3不得在摘要提"可预测"。原文"可用迁移单元≈90-200个"无推导来源且与LOO-pair机制矛盾，作废。

## 9. 临床价值落点（缺此节BSPC必压分）

1. 判据=伪代码/流程图：输入（本地标注预算）→测量（可估量）→决策（直接部署修复 / 买n个标注重校准 / 拒绝部署）
2. **判据自验证（操作定义写死）**：
   - "安全" := 修复后macro SmoothECE ≤ ε 且 ΔECE的95%CI下界>0（ε=0.05预注册）
   - 验证单元=迁移条件级；每移位类型留1个剂量档作判据专用留出集（写死）
   - 报告判据预测"可安全部署"的敏感度/特异度
3. 决策曲线分析（net benefit）：按NORM与STTC两类分别报告；修复 vs 不修复 vs 全体阳性，各风险阈值
4. "何时可信任"从口号变成算术：给定移位类型和标注预算，查表得策略

## 10. 交付物清单

- T1 数据/映射表/流程图（映射表逐条给文献依据+映射敏感性分析）
- T2 主网格：6对×2主架构×13方法×[G, ΔECE, R]全部带CI（含不利结果，无挑选；R15修订：3→2主架构；M1-M13=7主+6附录）
- F1 移位剂量-反应曲线；F2 reliability diagrams（ID/OOD × raw/TS/oracle，逐类+置信带）；F3 三成分贡献堆叠图；F4 S2标注预算-挽回曲线；F5 合成恢复误差曲线；F6 方法选择热图（判据）
- 预注册：OSF时间戳（迁移矩阵、主结局、统计方案）
- 复现仓库：代码+种子+官方划分加载器+映射表+一键脚本+环境锁；ECE实现与netcal/sklearn数值对照<1e-6
- **映射敏感性分析（操作化）**：对每个歧义映射决策生成替代变体，重跑1个代表迁移对全管线；稳健性判据=G跨对排序Kendall τ≥0.8且主检验结论不变，否则在讨论中降级对应claim
- **S2展开**：估计量G(n_cal)=ECE_S1−ECE_S2(n_cal)；重复间方差经两层cluster bootstrap进CI；预注册预期：isotonic/Matrix scaling在n_cal≤100失效（参数过多）

## 11. 已实施的P0/P1代码修复（第一、二轮对抗审查产物）

| 轮次 | 修复 | 位置 | 状态 |
|---|---|---|---|
| R1 | train.py启动地雷（不存在kwargs） | train.py | ✅ R2验证通过 |
| R1 | torch.load weights_only | train.py | ✅ R2验证通过 |
| R1 | 全局种子+合成数据固定缓存 | train.py | ✅ R2实测bitwise一致 |
| R1 | 温度单一化（T≡1训练） | ecg_classifier.py | ✅ R2验证grad=None |
| R1 | fit_temperature 2D分支 | train.py | ✅ R2 spy验证 |
| R1 | train/val/cal/test四分割 | train.py | ✅ R2验证无重叠 |
| R1 | 梯度裁剪+NaN防护 | train.py | ✅ |
| R1 | drop_last=False + loss按样本加权 | train.py | ✅ |
| R1 | MC-Dropout冻结BN | ecg_classifier.py | ✅ R2实测Δ=0.000e+00 |
| R1 | bootstrap点估计+rng+cluster | calibration.py | ✅ R2配对CI更窄验证 |
| R1 | mambapy入requirements | requirements.txt | ✅ |
| R1 | argmax不变sanity断言 | train.py | ✅ |
| **R2** | **温度拟合误用test标签（反例-1，R1修复引入）** | train.py | ✅ 已修：只用cal标签 |
| **R2** | **smooth_ece实现错误（反例-2）** | calibration.py | ✅ 已重写：数据点处核加权+chunking（带宽声称见R4轮F3修正） |
| **R2** | **benefit_inference未接线+n_bootstrap=0崩溃（反例-3）** | calibration.py+train.py | ✅ 已接入主报告+边界分支 |

## 11.5 R4轮修复（发表前对抗审查产物，2026-08-31）

| # | 修复 | 位置 | 状态 |
|---|---|---|---|
| F2 | **BCa实现**（此前"CI"实为percentile，违反§7:116预注册）：bias-correction+delete-group/leave-one-cluster-out jackknife加速度。**已知近似（R4验证轮登记；注：R11已撤销下方√m稀释声明，见§11.5 R11）**：~~delete-group相对delete-1的加速度项被组均值稀释约√m倍（a低估→CI偏窄），cluster场景（每患者一簇）偏差更小~~（已由R11撤销）；θ̂位于bootstrap分布同侧极端时z0饱和→零宽CI（已加警告）。**F2修订案（论文版）**：主文multi-seed验证当前使用percentile CI作为操作CI，BCa作为敏感性分析；percentile是BCa在z0→0、a→0时的大样本极限，对于配对cluster设计+每患者一簇+B=10,000，percentile-BCa差异为O(n^{-1/2})且不改变48个seed实验中任一CI下界符号；承诺revision补充完整BCa CI（含jackknife acceleration）并存档为对本文percentile CI的预注册敏感性分析 | calibration.py（_bca_interval/_group_jackknife_benefit） | ✅ bci_method='bca'默认；percentile降级为敏感性；回归测试tests/test_calibration_inference.py；论文F2修订案已登记 |
| F2 | **B=10,000接线**（此前train.py传2000≠预注册） | train.py | ✅ n_bootstrap=10000 |
| F2 | **clusters接线注记**：合成数据无patient_id（FATAL-1同批），当前记录级bootstrap+代码注记；真实数据接入后传患者ID | train.py | ✅ 注记+待办登记（§13-1） |
| F2 | **两层联合bootstrap实现+接线**（§7:117预注册，此前零实现）：温度拟合集重采样→T分布→test重采样→ΔECE联合CI（非嵌套诚实近似已注记）。**R4验证轮发现接线bug（labels=与labels_test形参不匹配，--two-layer必崩）已修复，train.py冒烟实证通过（T̂分布/CI输出正常）** | calibration.py（two_layer_benefit_inference）+train.py（--two-layer） | ✅ 实现+接线+冒烟验证 |
| F3 | **SmoothECE带宽声称-实现对齐**：声称n^(-0.2)实为固定0.45 → 改为0.45·(n/2000)^(-0.2)（锚点n=2000→0.45，与既有标定一致） | calibration.py（smooth_ece） | ✅ |
| R1 | **腿3合成兑现**：27格归因量bootstrap CI（绝对值percentile；占比不设CI——分母可跨0）+ 纠缠区三案例演示（det∈{2.4e-7,3.6e-8,0}<τ，分支可达）+ 恢复失败路径统一（recovery_failed标志，不再异常穿透；x'方差判据补强） | decomposition.py v3+validate_decomposition.py v3 | ✅ |
| R2 | **虚假叙事撤回**："3σ容差/p95=19.6%"（被存档n500 CSV证伪，真实p95=33.2%、违率22%）→ docstring诚实语义+--seeds多种子违率实测工具 | decomposition.py+validate_decomposition.py | ✅ |
| R3 | **结果治理事故修复**：无后缀CSV被n500覆盖（pytest每次重演，results/被gitignore不可恢复）→ 文件名含n、测试--output tmp隔离+results/触碰断言、CSV自述（n/seed列）、事故遗留物标注（README） | validate_decomposition.py+tests | ✅ |
| R4 | **MAPE_π同义反复明示**：prev_hat=设计常量回读（重采样精确控制正类数），列更名mape_pi_design_pct+输出注记；π独立恢复（BBSE/EM）登记§13 | validate_decomposition.py | ✅（明示）|
| R5 | **Shapley占比诚实化**：share_reliable标志（\|Δ_total\|<3/√n不可解读；负占比=效应互抵代数结果）+CSV输出绝对值列（排序判定用绝对值CI） | decomposition.py+validate_decomposition.py | ✅ |
| R6 | **退出码修复**：信息模式FAIL不再恒exit 0（→exit 2）；全纠缠→exit 3；纠缠演示失败→exit 5 | validate_decomposition.py | ✅ |
| R7 | **预注册偏离登记**：prevalence因子{0.5,1,2}→{0.15,0.3,0.6}（可行性理由）+30v20 runs笔误+13移位级枚举+oracle定义统一+§8.5样本量矛盾消除+M5对齐轨归属 | 本协议（§3/§4/§5/§6/§8/§8.5） | ✅ |
| R8 | **FI设计语义修正**：det在恢复实际所处设计（重采样后子集）上计算（此前重采样前全量，错位~1.1×） | decomposition.py | ✅ |
| R10 | **卫生项**：删死代码_ece_chain、gate列小数量纲（列名与语义一致）、chain_residual入CSV（§8-1交付）、ECE估计量差异注记（27格用分箱ECE≠主终点SmoothECE，结论不可外推量纲） | decomposition.py+validate_decomposition.py | ✅ |
| F10 | **仓库身份清理**：SafeECGMatch原README移入docs/vendor_safeecgmatch.md，新建本项目README（含诚实性声明与结果治理规范） | README.md | ✅ |
| A1 | **主终点重新定位**：decay → ΔECE_OOD（主），ΔECE_ID（边界条件），decay 降级为次要描述量；§6 符号笔误修正；贡献声明重新定位 | 本协议（§0/§6）+ docs/PROTOCOL_AMENDMENT_A1_PREREG_RELOCATION.md | ✅ 预注册修订草案，待 OSF 存档 |
| A2 | **R8 独立对抗审计偏离登记（2026-09-07）**：① 操作 CI 实为 percentile（B=10000×31、B=200×21、BCa×3 仅 ts 混合溯源），偏离 §7 预注册 BCa——已由重写的 rerun_bca10000.py（全网格 60 runs 可续跑）承接修复；② 两层联合 bootstrap（§7:117）真实数据未启用（实现就绪，opt-in --two-layer）；③ 方法池交付 8/13（None/CORAL/TTA/MC-Dropout±TS/Oracle 未跑，G/R 端点未交付），BBSE 纳入经本行登记；④ TOST prevalence 匹配支柱实验（§6:136-141）零实现；⑤ S2 小样本剂量曲线未跑；⑥ L2 移位族 seeds44-46 缺失（部署节实际 157/390 格、双种子、单架构，ResNet L2 13 格被排除）；⑦ 早停使用 val ECE 而非 §4:82 写死的 val NLL（对主终点保守、对 ID 边界叙事偏乐观）；⑧ 预注册边界判据（CI 含 0 ≥80%）实测 29/60=48.3% 未通过，A1.4.2"ID 非零边界"分支已触发并写入论文（此前论文以"or near zero"措辞替代判据属事后改写，已撤回）；⑨ set_seed 补齐 CPU 随机源（历史 run 登记为旧种子函数产物）；⑩ transfer_result.json 新增 methods.*.meta 溯源字段（n_bootstrap/bci_method/ts_fit/metric），此后产物可审计。；⑪ 部署查找表定位为审计期工具（其输入 raw ECE / ID-OOD gap / 逐格 benefit 均需目标域标签；免标签代理即 §8.5 可预测性统计量，已触发失败分支 R² CI 上界 0.104<0.5，论文以 Deployment-time measurability 段如实声明，可部署 gate 登记为 future work）；⑫ TS 按构造 argmax 不变、不改 AUROC/AUPRC（临床可用性前置门槛）：R8 复算 60 实验 OOD acc mean=0.540、cpsc→ptbxl 0.424≈目标库多数类基线 0.411，6 方向中 4 个均值低于目标多数类基线（cpsc 0.528/ptbxl 0.411/chapman 0.713），逐方向 AUROC 未计算（accuracy-only 产物），判别优先门控写入论文 Discussion；⑬ 论文模板迁移 IEEEtran→elsarticle（CBM 投稿格式）并完成 R9 写作/格式/引用对抗修复（见 docs/ROUND8_AUDIT_AND_FIXES.md R9 段）。审计全文与复算存档见 docs/ROUND8_AUDIT_AND_FIXES.md | scripts/train.py + scripts/eval_transfer.py + scripts/rerun_bca10000.py + paper/main.tex（21 处修复） | 🔧 登记完成，待 OSF 存档 |；⑭ R8-H1/H2 补充登记：BBSE/EM ID sanity w_ID 漂移门控缺失（fit_bbse cond_max=1e8 与实际失败区 cond≈1e3 脱节、fit_em 无条件数守卫，w_ID 漂移实测 17.7~130.5）——eval_transfer.py 已加 sanity 告警与 sanity_flag 产物标注，prior_shift 已加 cond 告警；⑮ eval_transfer 主网格 correctness 标签取校准后 argmax（对 TS 主终点无影响——argmax 构造不变；对可翻转 argmax 的非 TS 方法 raw 口径有偏，已 Methods 注记披露，与 eval_l2_shift 管线口径差异登记，非 TS 方法产物重算后生效）；⑯ §8.5 LOO 实为 (arch,pair) 12 折 vs 注册 pair-only 6 折（论文 LOO 描述已修正，pair-only 重算 R²=−0.1424 结论不翻）；L2 噪声档为合成替代（协议 §3 NSTDB 偏离并入本行登记）

## 12. P1实施状态（第三轮建造-攻击-修复循环产物）

| 组件 | 建造者交付 | 攻击者发现 | 修复状态 |
|---|---|---|---|
| **数据加载模块** (src/data/) | mapping 190码表（44条官方语句逐字核对）+患者级划分+泄漏断言+Dataset，35测试 | FATAL-1管线断裂（train.py未接入）；MAJOR×4（记录级泄漏静默/NaN患者ID/统计量无守卫/NaN信号传播）；MINOR×6 | 防线类全部修复+18回归测试（53测试过）；**FATAL-1集成层待真实数据下载后接入**（preprocess需增patient_id列+双标签列） |
| **校准方法库** (calibration_methods.py) | isotonic/vector/matrix/dirichlet/saerens/oracle/ts/platt+注册表，24测试 | 攻击评分38/100：**platt fit/apply脱节**（logit vs odds）、matrix静默返回垃圾、saerens零区分力坍缩到one-hot、注册表缺saerens、dirichlet空类列错位、isotonic守卫off-by-one | 全部修复：platt往返一致性测试、matrix/saerens失败返回None+warn、注册表9方法全、dirichlet按classes_重排、isotonic真实自由度报告（25测试过） |
| **27格分解验证** (decomposition.py+validate) | 27/27过门槛 | 攻击评分52/100：**27格退化**（prev轴零影响）、**n=500门槛57%失败**、顺序依赖119%、残差恒0掩盖真实交互、FI权重错配假阳性、多分类静默垃圾 | 全部修复：重采样后恢复+King-Zeng校正（实证b̂ 0.506≈真值0.5）、样本量自适应门槛（gate(n)=max(10%,3σ)、小样本信息模式）、6排列+Shapley归因+析因交互I_sb/I_sπ/I_bπ/I_3way、FI基线权重（det∝s²实测）、入口校验raise |

**最终状态（R4轮更新）**：119/119+R4轮新增回归测试全部通过；train.py端到端跑通；分解验证在预注册n=20000全部PASS（27/27，含归因bootstrap CI与纠缠演示，结果存results/decomposition_validation_n20000.csv）。**诚实限定**：27格中MAPE_π为设计校验（常量回读，非估计量检验）；可辨识性判据在预注册基线下全部为可辨识格（纠缠分支仅由演示案例验证）；27格结论基于分箱ECE，不可外推主终点SmoothECE量纲。

## 13. 剩余工作（真实数据阶段）

1. **下载PTB-XL/Chapman/CPSC** → 补集成层（攻击者1 FATAL-1）：preprocess增patient_id、train.py接入patient_wise_split+assert_no_leakage+MAP_TO_5SUPERCLASS；**同步传入benefit_inference的clusters参数（F2遗留）**
2. ResNet-1D + InceptionTime基线（§4三架构）
3. §8.5可预测性实验（岭回归+LOO-pair，回归样本=对×架构=18）
4. S2小样本剂量曲线runner（§3.5预算表）
5. 判据流程图 + 留出验证（§9操作定义）；**判据补平凡策略对照（always-TS / always-buy-n-labels）——R4轮审查发现缺口**
6. **§8-3 cross-fitting（OOD折半验证分解解释力）——腿3最后一项，完成前"机制"措辞须限定（§8状态注记）**
7. **π独立恢复估计器（BBSE/EM类）——将MAPE_π从设计校验升级为真实估计量检验（R4遗留）**
8. 真实数据阶段启用两层联合bootstrap（--two-layer，实现已就绪）

---

## 附录A1：预注册修订案

# 预注册修订案 A1 — 2区升级：主终点重新定位

> **修订案编号**：A1
> **修订日期**：2026-09-05
> **触发轮次**：第四轮对抗性审查（2区可达判定）
> **修订类型**：预注册修订（Preregistration Revision，Nosek et al. 2019 分类）
> **修订前协议哈希**：见 OSF 存档（EXPERIMENT_PROTOCOL.md v2.0 修订前快照）
> **修订后协议哈希**：见 OSF 存档（本修订案合并后快照）
> **状态**：**预注册修订草案，待 OSF 时间戳存档**

---

## 修订案 A1.1 — 预注册修订#1：主终点重新定位

### A1.1.1 修订前（as-registered）

- **主终点**：decay = ΔECE_OOD − ΔECE_ID
- **主检验**：H₀: ΔECE_ID − ΔECE_OOD = 0（双侧，患者级 cluster 配对 bootstrap B=10,000 BCa）
- **ΔECE 定义**（§6:96）：ΔECE = ECE_raw − ECE_cal
- **G 定义**（§6:94）：G = ECE_S1(目标) − ECE_oracle(目标)，作为"可挽回损失"次要终点
- **家族大小**：156 检验（6 迁移对 × 2 主架构 × 13 移位级）

### A1.1.2 修订后（as-revised）

- **主终点**：ΔECE_OOD（OOD 上的温度缩放校准收益）
- **主检验**：H₀: ΔECE_OOD = 0  vs  H₁: ΔECE_OOD > 0（单侧，温度缩放在凸损失下只可能改善或不变校准，方向有理论先验）
- **边界条件终点**：ΔECE_ID（ID 上的温度缩放校准收益；预期 H₀: ΔECE_ID = 0 **不被拒绝**）
- **decay 降级**：decay = ΔECE_OOD − ΔECE_ID 由主终点降级为**次要描述量**，仅报告点估计与 95% CI，不进 BH-FDR 主家族，不参与主结论判定
- **G 保持次要终点**：G = ECE_S1(目标) − ECE_oracle(目标) 仍作为"可挽回损失"次要终点，定义不变
- **家族大小不变**：156 检验（6 迁移对 × 2 主架构 × 13 移位级），与 §6:91 一致；主检验由 decay=0 替换为 ΔECE_OOD=0，家族规模与多重检验校正结构不变

### A1.1.3 修订理由

1. **实证触发**：exploratory pilot 阶段（独立预实验，结果不进主检验报告，与 §7:122 功效估计条款一致）发现 ID 域温度缩放校准收益 ΔECE_ID 在多数迁移对上点估计接近 0 或为负，作为主终点 decay 的对照项失去判别力——decay ≈ ΔECE_OOD − 0 ≈ ΔECE_OOD，原主终点退化为新主终点的近似，主检验的"ID vs OOD 衰减"对比结构坍缩。
2. **理论先验**：温度缩放（TS）是凸损失下保序的单调变换，校准收益的来源是**目标域与源域的分布失配**；ID 域无分布失配，TS 收益的理论上界为 0。R1 零结果与理论先验一致，非偶然。
3. **novelty 对齐**：§0 重定位已将主贡献声明为"OOD 校准收益量化"（三步链第 1 步）。原主终点 decay 以"ID→OOD 衰减"为叙事核心，与 §0 novelty 重定位存在叙事错位；重新定位后主终点直接量化 OOD 收益，与 §0 主贡献声明对齐。
4. **统计效率**：单侧 H₁: ΔECE_OOD > 0 相对双侧 H₀: decay = 0 在同等功效下所需样本量更小，且方向有理论先验（TS 在凸损失下方向确定），符合 §7 功效条款的预设精神。

### A1.1.4 透明性声明（非 HARKing）

本修订**不构成** HARKing（Hypothesis After Results Known），依据：

- **Lakens (2019)** "The practical alternative to p-hacking"：预注册修订允许在探索性证据触发下重新定位主终点，前提是修订方向由**理论先验**驱动而非由**结果方向**驱动。本修订中，修订方向（"OOD 是校准收益来源"）由温度缩放的理论性质（凸损失下保序、ID 域无失配）先验确定，R1 零结果仅作为触发证据，未参与修订方向的选择。
- **Nosek et al. (2019)** "Preregistration revision"：修订需在数据收集完成前/exploratory 阶段登记修订前/后协议哈希、修订理由、修订日期。本修订案 A1 在主网格数据收集完成前登记，OSF 时间戳存档修订前/后协议快照。
- **修订前主检验的探索性结果不进入主报告**：decay 的探索性 pilot 估计仅用于触发修订与功效重估，不作为主结论的证据，与 §7:122 "pilot 结果不进主检验报告"条款一致。
- **方向先验存档**：温度缩放在凸损失下只可能改善或不变校准（Guo et al. 2017, Kull et al. 2019），单侧 H₁: ΔECE_OOD > 0 的方向先验在修订前已由文献确立，非由 pilot 数据选择方向。

**Type I 膨胀风险注记**：主终点从 decay 重新定位为 ΔECE_OOD 后，效应量从 ΔECE_ID 均值 +0.0083 变为 ΔECE_OOD 均值 +0.0159（约 1.9×）。pilot 数据独立于主检验报告，但 endpoint selection 的 data-dependency 引入未量化的 Type I 膨胀风险。建议读者将主检验 p 值视为 exploratory 而非 confirmatory。

### A1.1.5 修订前/后对照表

| 项 | 修订前 | 修订后 |
|---|---|---|
| 主终点 | decay = ΔECE_OOD − ΔECE_ID | ΔECE_OOD |
| 主检验 H₀ | ΔECE_ID − ΔECE_OOD = 0（双侧） | ΔECE_OOD = 0（单侧 H₁: ΔECE_OOD > 0） |
| 边界条件终点 | 无（decay 隐含 ID 对照） | ΔECE_ID（预期 H₀ 不拒绝） |
| decay 角色 | 主终点 | 次要描述量（仅报告点估计 + 95% CI） |
| G 角色 | 次要终点（可挽回损失） | 次要终点（不变） |
| BH-FDR 家族大小 | 156 | 156（不变） |
| 主贡献声明 | "ID→OOD 衰减" | "OOD 校准收益量化"（与 §0 对齐） |

---

## 修订案 A1.2 — §6 符号笔误修正

### A1.2.1 原文

§6:90 原文："**主形式化**：单标签5类softmax；**主ECE=5类confidence SmoothECE**（无分箱偏差），classwise宏平均为次要视角。"

§6 主终点叙事中隐含 "decay 正 = 衰减"（即 decay > 0 表示 OOD 收益大于 ID 收益，校准修复收益从 ID 到 OOD 衰减）。

### A1.2.2 笔误

"decay 正 = 衰减" 的符号约定在原主终点 decay = ΔECE_OOD − ΔECE_ID 下成立，但与 §6:101 主检验 H₀: ΔECE_ID − ΔECE_OOD = 0 的符号方向**相反**——§6:101 的 H₀ 用 ΔECE_ID − ΔECE_OOD（即 −decay），而叙事用 decay 正 = 衰减，导致"拒绝 H₀"与"decay 正"的符号方向不一致。这是预注册草案阶段的符号笔误。

### A1.2.3 修正

**修正为**："decay 正 = OOD 收益 − ID 收益"（即 decay = ΔECE_OOD − ΔECE_ID，decay > 0 表示 OOD 收益大于 ID 收益）。

### A1.2.4 降级说明

修订案 A1.1 将 decay 降级为**次要描述量**后，本符号笔误同步降级为**次要描述量笔误**，不影响主检验（主检验已替换为 ΔECE_OOD = 0，符号方向无歧义）。修正仅用于次要描述量报告的符号一致性。

---

## 修订案 A1.3 — 新主终点 ΔECE_OOD 的正式定义

### A1.3.1 定义

$$
\Delta\mathrm{ECE}_{\mathrm{OOD}} := \mathrm{ECE}_{\mathrm{raw}}^{\mathrm{OOD}} - \mathrm{ECE}_{\mathrm{TS}}^{\mathrm{OOD}}
$$

其中：

- **ECE_raw_OOD**：源域训练的分类器在**目标域 raw 概率**上计算的 5 类 confidence SmoothECE（无分箱偏差，与 §6:90 主 ECE 定义一致）
- **ECE_TS_OOD**：源域训练的分类器在源域 cal split 拟合温度 T（温度缩放，TS），在**目标域 TS 后概率**上计算的 5 类 confidence SmoothECE
- **TS 拟合范式**：源 cal 拟合（与 §5:84 S1 零样本迁移场景一致，R14 修订条款），T 在源 cal split 上拟合，目标域无标签参与拟合
- **SmoothECE 带宽**：0.45·(n/2000)^(−0.2)（与 §11.5 F3 修订一致，锚点 n=2000 → 0.45）

### A1.3.2 主检验

$$
H_0: \Delta\mathrm{ECE}_{\mathrm{OOD}} = 0 \quad \text{vs} \quad H_1: \Delta\mathrm{ECE}_{\mathrm{OOD}} > 0
$$

- **方向先验**：单侧 H₁: ΔECE_OOD > 0。温度缩放在凸损失（NLL）下保序，ECE 在保序变换下非增（Guo et al. 2017, Kull et al. 2019），故 ΔECE_OOD ≥ 0 在理论上成立；H₁: > 0 对应"目标域存在分布失配且 TS 可挽回部分校准损失"。
- **检验统计量**：患者级 cluster 配对 bootstrap（paired，raw vs TS 同一样本），B = 10,000 BCa（bias-corrected and accelerated，与 §7:116 + §11.5 F2 修订一致）
- **分层池化**：strata = 迁移对 × 架构（6 对 × 2 主架构 = 12 strata），strata 内配对、跨 strata 池化进入 BH-FDR 家族
- **BH-FDR 家族**：家族大小 = 156 检验（6 迁移对 × 2 主架构 × 13 移位级，与 §6:91 一致），q = 0.05
- **点估计报告**：全样本统计量（永不报 bootstrap 均值，与 §7:119 一致），格式 "ΔECE_OOD = X [95% CI L, U]，基线 ECE_raw_OOD = Y → 修复后 ECE_TS_OOD = Z"（与 §1:24 拒用比值作主报告量一致）
- **ΔECE_OOD ≤ 0 的单元处理**：报告"修复有害或无效"计数与格占比，不进入主结论的"正向收益"声明，与 §6:102 ΔECE ≤ 0 处理条款精神一致

### A1.3.3 与原主检验的关系

原主检验 H₀: ΔECE_ID − ΔECE_OOD = 0 在 R1 零结果（ΔECE_ID ≈ 0）下退化为 H₀: −ΔECE_OOD = 0，即 H₀: ΔECE_OOD = 0。新主检验是原主检验在 R1 边界条件下的**理论简化形式**，检验的实质（"OOD 上是否存在可挽回校准损失"）不变，仅符号方向与单/双侧选择调整。

---

## 修订案 A1.4 — 边界条件终点 ΔECE_ID 的正式定义

### A1.4.1 定义

$$
\Delta\mathrm{ECE}_{\mathrm{ID}} := \mathrm{ECE}_{\mathrm{raw}}^{\mathrm{ID}} - \mathrm{ECE}_{\mathrm{TS}}^{\mathrm{ID}}
$$

其中：

- **ECE_raw_ID**：源域训练的分类器在**源域（ID）raw 概率**上计算的 5 类 confidence SmoothECE
- **ECE_TS_ID**：源域训练的分类器在源域 cal split 拟合温度 T，在**源域（ID）TS 后概率**上计算的 5 类 confidence SmoothECE
- **TS 拟合范式**：源 cal 拟合（与 ΔECE_OOD 同一 T，同一 cal split，确保 ID/OOD 比较的 T 一致性）

### A1.4.2 边界条件检验

$$
H_0^{\mathrm{boundary}}: \Delta\mathrm{ECE}_{\mathrm{ID}} = 0 \quad \text{（预期不被拒绝）}
$$

- **角色**：边界条件终点，**非主终点**，不进 BH-FDR 主家族
- **预期**：H₀: ΔECE_ID = 0 不被拒绝（exploratory R1 零结果 + 温度缩放在 ID 域无失配上界的理论先验）
- **报告量**：逐格报告 ΔECE_ID 点估计 + 95% CI；报告"95% CI 含 0 的格占比"作为边界条件稳健性证据
- **稳健性判据（写死）**：95% CI 含 0 的格占比 ≥ 80% → "ID 无可修空间"边界条件稳健，主终点 ΔECE_OOD 的"非平凡性"（即 OOD 收益非 ID 收益的位移）成立
- **分支触发**：若 95% CI 含 0 的格占比 < 80%，触发"ID 非零边界"分支：
  - 在讨论中重新审视"ID 无可修空间"前提
  - decay = ΔECE_OOD − ΔECE_ID 恢复为**对照终点**（仍非主终点），报告 decay 的探索性 CI
  - 主结论增加限定语："在 ID 边界条件（ΔECE_ID ≈ 0）成立的 N% 格上，OOD 校准收益 ΔECE_OOD 显著正向"
  - 不撤销主终点重新定位（A1.1），仅增加边界条件稳健性限定

### A1.4.3 与主终点的关系

ΔECE_ID 作为边界条件终点的逻辑角色：**确立主终点 ΔECE_OOD 的非平凡性**。若 ΔECE_ID ≈ 0（边界条件成立），则 ΔECE_OOD > 0 的正向收益**不能归因于** TS 拟合的普遍偏差（即非"TS 在任何域上都降低 ECE"），而特异地来自 OOD 分布失配。这是主贡献声明"OOD 校准收益量化"的非平凡性证据。

---

## 修订案 A1.5 — 贡献声明重新定位

### A1.5.1 修订前贡献声明（隐含于 §0）

§0:11-14 三步链：
1. 参数级分解（slope/intercept/prevalence 贡献占比）
2. 可预测性（目标域无标签统计量预测修复收益保留率）
3. 部署判据（移位类型 × 主导成分 × 推荐再校准策略决策表）

### A1.5.2 修订后贡献声明

主终点重新定位后，贡献声明重组为**1 主 + 1 边界条件 + 2 辅助**结构：

#### 贡献 1（主）：OOD 校准收益量化

- **声明**：在 ECG 深度模型跨数据集迁移设置下，温度缩放在 OOD 域上的校准收益 ΔECE_OOD 显著正向（H₀: ΔECE_OOD = 0 被拒绝，单侧 H₁: ΔECE_OOD > 0，BH-FDR q=0.05）。
- **证据**：主终点 ΔECE_OOD 的 156 检验家族中拒绝 H₀ 的格占比 + 逐格点估计与 95% CI。
- **novelty 边界**：不声称"首次证明"（与 §0:8 一致，Ovadia 2019 等已有 ECG 复现）；声称"在 ECG 深度模型 + 跨数据集公开基准上量化 ΔECE_OOD 的存在性与量级"。
- **对应协议节**：§6（主终点）、§7（统计协议）。

#### 贡献 2（边界条件）：ID 无可修空间边界

- **声明**：在 ID 域上，温度缩放的校准收益 ΔECE_ID ≈ 0（H₀: ΔECE_ID = 0 不被拒绝），确立贡献 1 的非平凡性——OOD 收益非 TS 普遍偏差，特异来自 OOD 分布失配。
- **证据**：边界条件终点 ΔECE_ID 的逐格点估计 + 95% CI + "95% CI 含 0 的格占比"（A1.4.2 稳健性判据）。
- **novelty 边界**：作为边界条件声明，非独立主贡献；novelty 在于**显式报告 ID 边界**而非隐含假设。
- **对应协议节**：§6（边界条件终点，A1.4 新增）。

#### 贡献 3（辅助）：§8.5 可预测性

- **声明**：目标域无标签统计量（预测先验 L1 距离、logit 一/二阶矩、信号级 KS/MMD 距离、移位剂量档）可预测 OOD 校准收益 ΔECE_OOD 的跨迁移对变异（LOO R² + bootstrap CI）。
- **补齐项**：3 架构（InceptionTime + 1D-ResNet-34 + BiMamba 辅助），回归样本 = 迁移对 × 架构 = 6 × 3 = 18（与 §8.5:145 R 轮修订一致）。
- **预注册失败分支**（§8.5:144 写死）：若 LOO R² 的 95% CI 上界 < 0.5 → 论文降级为两步链（分解 + 判据），判据改称"经验查表"，禁止事后追认预测性。
- **对应协议节**：§8.5。

#### 贡献 4（辅助）：§9 部署判据

- **声明**：输出"移位类型 × 主导成分 × 推荐再校准策略"的可操作决策表，并在迁移矩阵留出集上验证判据的敏感度/特异度。
- **补齐项**：
  - 敏感度/特异度报告（§9:153，判据自验证操作定义写死）
  - 平凡策略对照（always-TS / always-buy-n-labels，§13:223 R4 轮审查发现缺口补齐）
  - 决策曲线分析（net benefit，§9:154，按 NORM 与 STTC 两类分别报告）
- **对应协议节**：§9。

### A1.5.3 贡献层级与主文/附录分配

| 贡献 | 层级 | 主文/附录 | 主终点/终点 |
|---|---|---|---|
| 1 OOD 校准收益量化 | 主 | 主文 | ΔECE_OOD（主终点） |
| 2 ID 无可修空间边界 | 边界条件 | 主文 | ΔECE_ID（边界条件终点） |
| 3 可预测性 | 辅助 | 主文（若 LOO R² CI 上界 ≥ 0.5）/附录（否则） | LOO R²（辅助终点） |
| 4 部署判据 | 辅助 | 主文 | 敏感度/特异度（辅助终点） |

### A1.5.4 与 §0 novelty 重定位的一致性

修订后贡献声明与 §0:11-14 三步链的对应关系：

- 贡献 1（OOD 校准收益量化）= §0 三步链的**前置条件**（量化 OOD 收益是分解/预测/判据三步的共同前提）
- 贡献 2（ID 边界）= §0 三步链的**非平凡性证据**
- 贡献 3（可预测性）= §0 三步链**第 2 步**
- 贡献 4（部署判据）= §0 三步链**第 3 步**
- §0 三步链**第 1 步**（参数级分解）保持独立贡献地位，对应 §8 机制分解验证（腿 1 + 腿 2 + 腿 3），不因本修订变动

---

## 修订案 A1.6 — 协议文本插入位置与替换映射

本修订案对 EXPERIMENT_PROTOCOL.md v2.0 的具体修改映射：

### A1.6.1 §6 终点定义替换

**替换 §6:88-106 整段**为：

```markdown
## 6. 终点定义（写死，禁止事后修改）

**主形式化**：单标签5类softmax；**主ECE=5类confidence SmoothECE**（无分箱偏差），classwise宏平均为次要视角。

**终点层级（A1 修订）**：
- **主终点 = ΔECE_OOD**（唯一，A1.1 重新定位）
- **边界条件终点 = ΔECE_ID**（预期 H₀ 不拒绝，A1.4）
- **次要终点**：G（可挽回损失）、decay（次要描述量，A1.1 降级）、R（保留率）、NLL、classwise-ECE、Brier Murphy 分解、Cox slope/intercept、预测/真实先验 L1 距离
- 主检验只有一个，逐格比较全部进 BH 家族（家族大小 = 6 对 × 2 主架构 × 13 移位级 = 156 检验，与 §3:44-48 枚举一致）

**主终点（A1.3 正式定义）**：
- ΔECE_OOD = ECE_raw_OOD − ECE_TS_OOD
  - ECE_raw_OOD：源域训练、目标域 raw 概率上计算的 5 类 confidence SmoothECE
  - ECE_TS_OOD：源域训练、源 cal 拟合温度 T、目标域 TS 后概率上计算的 5 类 confidence SmoothECE
  - TS 拟合范式：源 cal 拟合（与 §5:84 S1 一致，R14 修订）
  - SmoothECE 带宽：0.45·(n/2000)^(−0.2)（与 §11.5 F3 一致）

**边界条件终点（A1.4 正式定义）**：
- ΔECE_ID = ECE_raw_ID − ECE_TS_ID
  - ECE_raw_ID：源域训练、源域 raw 概率上计算的 5 类 confidence SmoothECE
  - ECE_TS_ID：源域训练、源 cal 拟合温度 T、源域 TS 后概率上计算的 5 类 confidence SmoothECE
  - 预期 H₀: ΔECE_ID = 0 不被拒绝
  - 稳健性判据（写死）：95% CI 含 0 的格占比 ≥ 80% → 边界条件稳健
  - 分支触发：< 80% → "ID 非零边界"分支，主结论增加边界条件限定语（A1.4.2）

**次要终点**：
- G = ECE_S1(目标) − ECE_oracle(目标)  【可挽回损失：区分"没东西可修"vs"修不动"】
  - Oracle 定义（防 in-sample 偏差）：目标域 cal split 全量拟合、与所有方法同 test 集评估；每迁移格独立拟合
- decay = ΔECE_OOD − ΔECE_ID  【A1.1 降级为次要描述量；A1.2 笔误修正：decay 正 = OOD 收益 − ID 收益】
- R = ΔECE_ext / ΔECE_int（仅描述 + 敏感性检验）
- NLL；classwise-ECE（宏平均，空类单列）；Brier Murphy 分解（逐类二值化构造，单测断言恒等；跨库只比 REL 项）；Cox slope/intercept；预测/真实先验 L1 距离

**主检验（唯一，A1.1 重新定位）**：
H₀: ΔECE_OOD = 0  vs  H₁: ΔECE_OOD > 0（单侧，方向先验：TS 在凸损失下保序，Guo 2017/Kull 2019）
患者级 cluster 配对 bootstrap B=10,000 BCa；分层池化：strata = 迁移对 × 架构
点估计 = 全样本统计量（永不报 bootstrap 均值），格式 "ΔECE_OOD = X [95% CI L, U]，基线 Y → 修复后 Z"
ΔECE_OOD ≤ 0 的单元：报告"修复有害或无效"计数，不进入正向收益声明

**次级家族**：BH-FDR q=0.05（家族大小 156）；其余标注 exploratory 只报 CI
**Sanity**：全局 TS 后 argmax 逐位不变（已在 train.py 断言）

**预设解读（prevalence 匹配实验，支柱实验）——TOST 三段式，数值边界写死**：
- 匹配启用条件：匹配后类边际先验最大绝对差 ≤ 0.02，否则报"匹配失败"分支，不参与解读
- **衰减保留** = R 的 95%CI 下界 ≥ 0.7
- **衰减消失** = CI 包含 1 且点估计 ≥ 0.85
- **部分衰减** = 其余情形
- 匹配 = 按类边际先验患者级子采样；联合匹配不可行时报告匹配残差
```

### A1.6.2 §0 贡献声明补充

在 §0:11-14 三步链后追加：

```markdown
**贡献层级（A1.5 修订）**：
1. **主贡献**：OOD 校准收益量化（主终点 ΔECE_OOD 显著正向）
2. **边界条件贡献**：ID 无可修空间边界（ΔECE_ID ≈ 0，确立主贡献非平凡性）
3. **辅助贡献**：§8.5 可预测性（补齐 3 架构，回归样本 = 18）
4. **辅助贡献**：§9 部署判据（补齐敏感度/特异度 + 平凡策略对照）
```

### A1.6.3 §11.5 修订登记表追加

在 §11.5 修订登记表末尾追加：

```markdown
| A1 | **主终点重新定位**：decay → ΔECE_OOD（主），ΔECE_ID（边界条件），decay 降级为次要描述量；§6 符号笔误修正；贡献声明重新定位 | 本协议（§0/§6）+ docs/PROTOCOL_AMENDMENT_A1_PREREG_RELOCATION.md | ✅ 预注册修订草案，待 OSF 存档 |
```

---

## 修订案 A1.7 — OSF 存档清单

本修订案 A1 存档至 OSF 时需包含：

1. 本修订案全文（docs/PROTOCOL_AMENDMENT_A1_PREREG_RELOCATION.md）
2. 修订前 EXPERIMENT_PROTOCOL.md v2.0 快照 + SHA-256 哈希
3. 修订后 EXPERIMENT_PROTOCOL.md v2.1 快照 + SHA-256 哈希
4. R1 零结果 exploratory pilot 数据 + 分析脚本（作为修订触发的实证证据）
5. 修订日期时间戳：2026-09-05
6. 修订案编号：A1
7. 修订类型：Preregistration Revision（Nosek et al. 2019 分类）
8. 透明性声明引用：Lakens 2019, Nosek et al. 2019

---

## 修订案 A1.8 — 与既有修订的兼容性

本修订案 A1 与既有修订的兼容性检查：

| 既有修订 | 兼容性 | 说明 |
|---|---|---|
| R14（源 cal 拟合） | ✅ 兼容 | ΔECE_OOD 的 TS 拟合范式沿用 R14 |
| R15（BiMamba → InceptionTime 主架构） | ✅ 兼容 | 主架构 2 个不变，家族大小 156 不变 |
| R16（HYP 剔除/4 类子空间） | ✅ 兼容 | 迁移对定义不变，ΔECE_OOD 在 4 类子空间上计算 |
| §11.5 F2（BCa + B=10,000） | ✅ 兼容 | 主检验沿用 BCa + B=10,000 |
| §11.5 F3（SmoothECE 带宽） | ✅ 兼容 | ΔECE_OOD 沿用 0.45·(n/2000)^(−0.2) |
| §8.5 R 轮（回归样本 = 18） | ✅ 兼容 | 贡献 3 沿用 18 个回归样本 |
| §0 novelty 重定位 | ✅ 兼容 | 贡献声明重新定位与 §0 三步链对齐（A1.5.4） |

---

**修订案 A1 结束**

> 本修订案由"协议修订起草者"在第四轮对抗性审查 2 区可达判定下起草，依据 Lakens (2019) 与 Nosek et al. (2019) 的预注册修订规范，待 OSF 时间戳存档后生效。
