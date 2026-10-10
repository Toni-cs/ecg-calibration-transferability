# BiMamba 网格暂停 + 污染产物重跑（2026-09-17 晚）

## 一、为什么暂停网格

两个都要 GPU，不能并行，而**优先级不同**：

| | 污染重跑 | BiMamba 第 3 架构 |
|---|---|---|
| 性质 | **正确性必需** —— 论文现在引用的 NCV/DCR、L2 安全率、判别指标全部来自窗口内产物 | **增强项** —— 回应"仅 2 种架构"的审稿意见 |
| 现状 | 未跑 | 1/30 完成，剩 ≈128.8 h（≈5.4 天） |

决定：**先跑重跑，网格后置**。

## 二、网格暂停状态（可无损恢复）

- 已完成 **1/30**：`chapman_cpsc/mamba/seed42`（4.44 h）。
- 被中止 **1 格**：`chapman_ptbxl/mamba/seed42`（中止于 epoch 4；`best_model.pt` 是半成品，
  恢复时会被覆盖，**无需手工清理**）。
- 中止进程：主控 Windows PID **17324**、子进程 **25984**（`ps -W` 显示的 1330 / 4220288 是
  **MSYS PID**，直接拿它去 `taskkill` 会报"没有找到进程"——这是本次踩到的坑）。

**恢复命令**（脚本自带断点续跑，按 `transfer_result.json` 是否含 `label_map` 且方法数完整判完成）：

```bash
/c/python/python.exe scripts/run_mamba_grid.py          # 跑满 30 格，已完成的自动跳过
```

**恢复前建议先降本**：实测瓶颈**不是 bootstrap，是训练本身**。
`scripts/train.py:577` 的 `--batch_size` 默认 **16**，12,143 条 → **759 步/epoch**；
实测 **≈19 min/epoch**（18:43→19:57 走完 4 epoch）⇒ **≈1.5 s/步**，与脚本自述的
"单步 1.39 s" 吻合。13–15 epoch 早停 × 19 min ≈ **4.1–4.8 h/格**。

> ⚠️ 此前（R3 阶段）判断"瓶颈是 bootstrap"是**错的**：bootstrap（8 方法 × OOD/ID × B=10000）
> 只在分钟级。**降本杠杆是 batch size，不是 bootstrap。**

chunked+checkpoint 在 B=16 仅占 0.74 GB，8.5 GB 卡余量充足；提到 B=64 可把步数降到
190/epoch，理论 ~4× 加速（5.4 天 → ~1.3 天）。代价是优化轨迹变化，
**必须在修订案 A4 里书面声明"batch 只影响优化过程，不改变统计量定义"**。

## 三、重跑链

启动脚本 `scripts/rerun_contaminated_chain.sh`，串行，顺序 = 论文价值降序：

| 序 | 步骤 | 命令 | 产物 |
|---|---|---|---|
| 1 | **E3 全量 n** | `run_e3_brier_dcr_ncv.py --regen` | `c1_brier_reliability*.csv`、`c1_dcr_ncv*.csv` |
| 2 | **E1a L2 网格** | `run_e1a_l2_shift_full.py --force` | `l2_shift_full_390cells.csv` 等 |
| 3 | **E2 判别表** | `run_e2_ablation_discrimination.py --no-cache` | `ablation_ts_components.csv`、`discrimination_metrics_60exp.csv` |
| 4 | E4 温度族 | `run_e4_temperature_analysis.py` | 温度分布 CSV |
| 5 | E6 可靠性图 | `run_e6_reliability_diagrams.py --all` | 60 张图 |
| 6 | E1b LOCO | `run_e1b_loco_validation.py` | `deployment_loco_validation.*` |

- 主日志 `logs/rerun_master.log`，逐步日志 `logs/rerun_<name>.log`。
- **污染原件已备份**为 `results/*.bak_contaminated`（共 11 个文件），未删除。

> **LOCO 优先级最低**：`grep -c LOCO paper/main_bspc.tex` = **0**，论文根本没引用它。
> 而论文 **已如实标注** E3 是 n=20 子样本口径（"E3-subsample … $n_{id}=n_{ood}=20$ patients"），
> 所以 E3 全量 n 的价值是**去掉那条 caveat**，不是修一个隐藏错误。

## 四、重跑后的验收检查（必做）

1. **E2 一致性交叉验证（最强的一条）**：重跑出的 `ablation_ts_components.csv` 的
   `stage=raw` 行必须复现 **`0.036–0.357, mean 0.211`** —— 这正是论文现在引用的值。
   若复现 → 新表与 `ablation_ts_components.OLD_ENCODING.csv` 同口径，论文数值无需再动；
   若不复现 → 说明重跑口径仍有问题，**必须停下排查，不得直接用新表**。
2. 每份新产物登记**编码戳**（`label_map`/`subspace`）与**规模 n**。
3. E3 全量后，同步更新论文 §Net benefit decision curve summary 的
   "E3-subsample / n=20 / protocol-distinct" 表述。
4. E1a 全量后统一 **157 / 390** 的口径表述（现磁盘为 5 种子全量）。
5. 重跑产物入补充材料包后，**重签 `SHA256SUMS.txt`**（当前 159/159 OK）。

## 五、R3 期间的附带损伤（已修复，需记录）

R3 的一个对抗代理运行了 `run_e1b_loco_validation.py`，**覆盖了
`results/deployment_loco_validation.json`** —— 违反了"只读"前提。
已由 `scripts/reconstruct_loco_json.py` 从 sha256 校验通过的 CSV 重建
（`csv_sha256 = fbc1d763ae9fc992f261dd8a636c2e3025daf3eb6cd0680232bb9026d529ed45`），
原 CSV 内容未变。重建文件的 `label_map` 仍是 **NEW 编码** ⇒ E1b 依然需要重跑（已排入链尾）。

> 教训：给对抗代理下"只读"指令时，应同时**用文件系统权限或副本目录约束**，
> 而不是仅靠提示词。后续对抗轮次应把 `results/` 设为只读，或让代理只在
> `_attack_scratch/` 下工作。
