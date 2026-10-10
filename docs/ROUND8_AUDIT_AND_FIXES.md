# 独立对抗审计（第 8 轮）与修复记录 — 2026-09-07

> **R9 格式与书写对抗修复（2026-09-07 第二批）**：六路写作/格式攻击（结构流/LaTeX/术语/
> 数字一致性/语言质量/引用规范）交叉对质后修复。要点：① 模板从 IEEEtran conference
> 迁移为 elsarticle（CBM 投稿格式，review 单栏 12pt，45 页，关键词/数据可用性声明/
> 利益冲突声明补齐）；② Discussion 边界小节与结论节两处旧 C2 框架整段清除（"is
> confirmed / +0.0006 / leaking / zero ID upper bound"全部撤换为分支触发口径）；
③ 幻数 −0.0110→−0.0128、"10/10 双方向"→仅 PTB-XL→CPSC（9/10）、tab:methods
> Fragile dir 列按复算重写为 Neg. dirs（EM 3/Isotonic 2/Matrix 2/Dirichlet 1/BBSE 1）、
> 240/156 族口径统一（156=shift 层族；480=方法格空间）、157 格口径统一并注明
> +1 残格来源；④ 部署节：ΔECE 符号翻转显式披露、DCA 结果补交付（0.1209 vs
> 0.0999；90% 分位转负）、留出重算四值全部呈现（+0.16/−0.03/+0.02/−0.14）；
⑤ 参考文献：杜撰条目替换为已核验真实文献（barandas→Information Fusion 2024
> doi:10.1016/j.inffus.2023.101978；zhang2022→Vranken 2021 doi:10.1093/ehjdh/ztab045；
> strodthoff/vancalster2019 纠正；占位条目→Haekal 2026 doi:10.1088/1361-6579/ae99aa
> 与 Patel & Beedala 2026 preprint），新增 goldberger2000/morenotorres2012/
> transcal/pseudocal/lascal 五条，6 条悬空 bibitem 全部落实 \cite，引号/DOI/arXiv
> 统一；⑥ 语言批量修复（em-dash、mismatch 统一、ResNet1D 首现定义、BiMamba 统一、
> percent 格式、时态统一、嵌入正文 Cover Letter 删除、摘要压缩至 250 词、5 图
> 1 表补正文引用）；⑦ 术语纪律：recalibration 统一（5 处 repair 残留清除）、4 类
> 全网格偏离登记、S1/S1′ 定义、次要终点交付状态标注。终态：45 页 review 版编译
> 通过、0 undefined、无 >50pt overfull、banned-pattern 全扫为零。

> 审计方式：三轮对抗（6 路攻击 → 辩护者/第二攻击者/复审仲裁 → 端到端重演+管线审计），
> 所有指控经独立复算裁决；本文件记录最终裁决、已执行修复、遗留事项。
> 底层数据封口：`cpsc_chapman/resnet1d/seed44` 全栈重演（checkpoint→数据→TS→SmoothECE）
> 与 transfer_result.json 一致至 ~1e-17；960 个 method×domain 块恒等式零例外。

## 一、已执行修复（main.tex @ 2026-09-07，pdflatex 11 页编译通过）

| # | 修复 | 位置 |
|---|------|------|
| 1 | 摘要 BCa→percentile 操作口径（BCa 仅 3 格敏感性） | abstract |
| 2 | 摘要单侧方向改为"经验先验，非定理"（引 Ovadia 2019；自家 9 个显著负格） | abstract |
| 3 | **C2 结论方向纠正**：预注册判据（CI 含 0 ≥80%）实测 29/60=48.3%，未通过；触发 A1.4.2 分支（此前写 "confirmed: 10/10 cells"） | abstract / C2 贡献块 / §sec:boundary / 结论 |
| 4 | tab:boundary 重做为 12 层（6 对×2 架构）真实表：Mean/Min-CI-lo/Max-CI-hi/CI∩0；删除不可复现的 "Std 0.0069"，Min 列不再把点估计冒充 CI 下界 | tab:boundary |
| 5 | "+0.0006 CI lower bound"（实为点估计）相关句子全部撤换 | C2 block / §boundary |
| 6 | "TS 凸损失保序⇒ECE 非增"伪定理全文撤除（Introduction/Methods/结论 5 处改为经验不对称） | 多处 |
| 7 | Methods "B=10,000 BCa" 与 Table I/Fig.1 注 → percentile（BCa 3 格 + 承诺 revision 补跑）；"不改变 60 格符号"改为"仅 3/60 验证" | Methods/表注/图注/fig1 图例文字（generate_figures.py 已改并重生成图） |
| 8 | Methods 预注册判据行加"实测 48.3%，分支已触发" | §pre-registered endpoints |
| 9 | "EM most fragile overall" → "EM 与 Matrix 在 InceptionTime 并列最弱（15/30）；ResNet 上 Matrix 17/30 最弱、EM 19/30"（图注同步） | §method_boundary ×3 |
| 10 | tab:arch_robust Mean 行 +0.0195/+0.0164/+0.0180 → **+0.0152/+0.0165/+0.0159**；Total Std 0.0148→0.0145 | tab:arch_robust |
| 11 | 部署 specificity 括号反向纠正（20% 正确排除/80% 误标）+ **in-sample 披露**（Youden 在同批 1230 格搜索；留出重算 2/4 移位类型 Youden≤0） | §deployment |
| 12 | 安全判据标签纠正（声称 CI 判据实为点估计判据 delta_ece<−0.01；L2 无 per-cell CI 故预注册 CI 判据不可算）+ L2 覆盖率披露（157/390、双种子、单架构、ResNet L2 13 格被排除） | §deployment |
| 13 | tab:trivial 口径修正（1230 为 always-none/always-buy 的格数；always-TS n=157、lookup n=155 并说明 2 格被丢） | tab:trivial |
| 14 | 反例计数 "all 6 transfer pairs"→"5 of the 6" | §counterexamples |
| 15 | 反例图注 "Eight (red) co-occur" → 6/9 acc≤0.50、7/9 gap≥0.18（启发式倾向非门槛） | fig:counterexamples |
| 16 | CE1 机制 (b) 修正（0.3160 是 5 seed 最低但仍为大 ECE——失败原因是温度失配而非空间不足）；CE2 的 0.4779 标注为 accuracy（raw ECE=0.3144）；CE4 删除 "(near chance)" | §counterexamples |
| 17 | 结论部署条件改写（acc≤0.5 为 6/9、gap≥0.18 为 7/9 的启发式倾向，3 个反例 acc>0.5 直接否定"全称"） | 结论 |
| 18 | CI 宽度三数 → 实测 2.1e-5~1.23e-2（median 1.2e-3）；n_cal≈5000 → 1027–2099 记录/1027–1873 患者；披露 52/60 is_narrow 与 6 个退化宽度支持格（剔除后 45/60=75%：IT 24/30、RN 21/30）；披露 JSON 无 bootstrap 溯源字段 | §statistical notes |
| 19 | 参考文献：vancalster2016 标题/期刊纠正（真实标题 "…was defined: from utopia to empirical data", J Clin Epidemiol 74:167-176）；nosek2019prereg → PNAS 2018；两个 2026 占位条目标注 [Placeholder]；protocolv21a1 撤回 OSF 归档声称（改为 hash manifest 本地快照+公开存档进行中） | bibliography |
| 20 | Cover letter：BCa 措辞、C2 分支措辞、反例模式措辞、Nosek 年份、裸域名（osf.io/、github.com/）撤回，改为"随投稿提供协议/哈希清单/代码，公开归档进行中" | cover_letter.tex |
| 21 | Nosek 2019→2018（正文 3 处）、"theory prior"→empirical（引言/Methods/结论 5 处） | 多处 |

## 二、遗留事项（按优先级）

### P0（投稿前必须）
1. **BCa 敏感性补跑——已完成（2026-09-08）**：全网格 60/60 runs 全部成功（logs/bca10000_full.log 全部 [ret=0]）；BCa vs percentile **符号一致 60/60**、支持数不变（51/60，IT 27/30、RN 24/30）、9 反例集合不变、点估计逐位一致；**边界条件口径更新**：ΔECE_ID CI 含 0 = **23/60 = 38.3%**（percentile 时代 29/60=48.3%，结论方向不变，判据未通过更甚）；论文已全面升级为 BCa 操作口径（摘要/Methods/边界节/tab:boundary/结论），robustness_validation_5seeds.csv 的 ts 行已同步为 BCa CI，transfer_result.json 全部 60 格带 meta(n_bootstrap=10000, bci_method=bca)。：60 实验全部以 `--bootstrap 10000 --bci-method bca` 重跑 eval-only（GPU ≈ 1-2 天），或按当前论文措辞仅作 revision 承诺。命令模板：
   `python scripts/eval_transfer.py --source <src> --target <tgt> --arch <a> --seed <s> --methods ts --bootstrap 10000 --bci-method bca`
   注意 `rerun_bca10000.py` 只重写 ts 且 skip 判据读不存在的键——先修该脚本再跑。
2. **transfer_result.json 增加溯源字段**（n_boot、bci_method、T、cal split 大小）——修 eval_transfer.py 一行 `meta={...}` 即可，此后所有重跑自动可审计。
3. **部署判据留出版**：把表4换成 leave-shift-type-out 数字（非留出档选阈值→留出档评估；已预计算：downsample +0.168 / leads2 −0.031 / noise +0.040 / gain −0.143），或按协议 §9 执行专用留出档。
4. **OSF 归档落地**：上传协议 v2.1-A1 + A1 修订案 + 当前代码哈希 → 用真实 OSF 链接替换 paper/cover_letter 中的占位语；git commit + tag（当前 150 文件未入库、快照哈希已漂移）。
5. **登记偏离**（协议 §11.5 追加行）：percentile 操作 CI、两层 bootstrap 未启用、13→8 方法、BBSE 纳入、S2/TOST/次要终点未交付、L2 双种子覆盖、早停 val ECE（协议 §4:82 写死 val NLL）。

### P1（显著提升）
6. Oracle/G 端点：eval_transfer 加 oracle 分支并跑全网格（G = ECE_S1 − ECE_oracle）。
7. L2 seeds 44-46 补跑（eval_l2_shift.py，eval-only）后更新部署节。
8. 两层联合 bootstrap `--two-layer` 至少在 12 个 (pair,arch) 代表格运行。
9. bootstrap_diagnostics.csv 的 n_patients/cluster 列改为真实测量（regen 脚本现返回常量）。
10. set_seed 补 `torch.manual_seed/np.random.seed/random.seed`（历史 run 登记为旧种子函数产物）。
11. 幽灵引用（barandas2023/zhang2022/physiolmeas2026/medrxiv2026）替换为可核验文献，或从 novelty 支撑句中移除。
12.协议 §8.5 可预测性：按注册 6 折（pair-only）重算（已预计算 ts R²=−0.1424，CI 上界仍 <0.5，结论不翻）并修正 LOO 描述。

### P2（增强）
13. 预注册支柱 TOST prevalence 匹配：实现或正式撤回该支柱。
14. 边界条件触发分支后，补 decay 对照终点表（探索性）。
15. 概率判定/内部报告（zone2_*.md、final_arbitration_v6.md）加"基于 48 实验快照，已被 60 实验世界取代"的版本标注，防止后续误引。

## 三、审计关键数字存档（复算口径）

- 主结果：51/60（IT 27/30、RN 24/30）；9 反例（3 新增来自 RN seeds44-46）
- 脆弱支持剔除后：45/60=75%（IT 24/30、RN 21/30）；退化宽度 6 格（最小 2.1e-5）
- 边界：29/60=48.3% CI 含 0；28/60 id_ci_lo>0；ID mean +0.0083 vs OOD +0.0159（1.9×）
- 12 层聚合（pair×arch 均值，SE=sd/√5）：raw 9/12 → BH 9/12 → Bonferroni 2/12；BH-60=51/60（伪 p 层）
- 实验级 CI 普查：B=10000-percentile 31 / B=200-percentile 21 / BCa 3（仅 ts，混合溯源）/ 无日志 5
- 合并：RE-DL 0.014771 [0.014051,0.015490]；FE 病态（IT 0.000406、RN −0.000573，退化 CI 权重垄断）已由论文披露
- Fisher p=0.4716；0.0064=1/157（点估计判据）；部署留出重算 Youden：+0.168/−0.031/+0.040/−0.143（1230格池正式复算，见 results/deployment_holdout_recompute.csv）
