# ⚠️ 污染通告 — L2 移位族的全部产物

> **日期**：2026-09-17
> **受影响产物**
> - `results/l2_shift_full_390cells.csv`（聚合表，mtime **2026-09-12 22:05**）
> - `results/l2_shift_full_780cells_detail.csv`（明细表，同 mtime）
> - `checkpoints/transfer/*/*/seed*/l2_shift_results.json`（60 个，mtime **2026-09-10 ~ 09-13**）
> - 由后者派生的 `results/predictability_3arch.csv`（**见"派生关系"一节，情况特殊**）
> **未受影响**：`results/robustness_validation_5seeds.csv`（09-08，窗口前）、
> `results/deployment_metrics.csv`（09-05）、`results/deployment_holdout_recompute.csv`（09-08）、
> `results/c3_crossfit_results.csv`（09-06）、`results/real_prior_recovery.csv`（09-17）
> **状态**：**含 CPSC 的 40 个 cell 的数值不可用**；修正值**尚不存在**，需重跑
> **相关**：`results/_TEMPERATURE_CONTAMINATION_NOTICE.md`、
> `results/_ABLATION_TS_COMPONENTS_CONTAMINATION_NOTICE.md`、
> `docs/PROTOCOL_AMENDMENT_A3_CORPUS_IDENTITY.md`

## 根因：生成脚本读的是**运行时**常量，不是 checkpoint 自存的编码

`scripts/eval_l2_shift.py` L85：

```python
subspace = SUBSPACE_CPSC if num_classes == 4 else None
```

`SUBSPACE_CPSC` 是 `src/data/mapping.py` 的模块级常量。该脚本**没有**读取
`checkpoints/transfer/**/transfer_result.json` 里自存的 `label_map`
（那 40 个含 CPSC 的 cell 全部是 `{"CD":1,"MI":3,"NORM":0,"STTC":2}` = OLD）。

`SUBSPACE_CPSC` 的时间线（git 证据）：

| 提交 | 日期 | 取值 |
|---|---|---|
| `df9c914` | 2026-08-30 | `("NORM","CD","STTC")` |
| `dd96647` | 2026-09-08 | `("NORM","CD","STTC","MI")` ← **OLD** |
| `452b3bf` | 2026-09-14 | `("NORM","MI","STTC","CD")` ← **NEW** |
| `72b2e59` | 2026-09-16 | `("NORM","CD","STTC","MI")` ← 恢复 OLD |

L2 产物的 mtime 全部落在 **09-10 ~ 09-13**，即 **NEW 编码生效期内**
（NEW 值 09-14 才提交，但同一窗口内 09-10 生成的
`ablation_ts_components.csv` 已被三重指纹判定为污染，说明工作区在 09-10 已是 NEW）。
于是：**probs 来自 OLD 训练的 checkpoint，标签用 NEW 常量重建** → MI↔CD 互换。

## 经验判定（不依赖日期推断）

方法见 `scripts/verify_l2_shift_encoding.py`。要点：L2 有 13 档信号扰动，
其中 `noise24` 在**非 CPSC** 方向（chapman↔ptbxl，两种编码重合）上几乎不改变数值，
可作为**近恒等档**来标定该档的固有偏离；再用它判别 CPSC 方向属于哪种口径。

### ① 聚合/明细表（用 `raw_ece` 对 `smooth_ece`）

| 量 | 值 |
|---|---|
| 近恒等档 | `noise24`（非 CPSC 固有偏离 median **0.0007**） |
| CPSC 40 格：\|L2 − OLD(干净)\| median | **0.0987** |
| CPSC 40 格：\|L2 − 污染口径\| median | **0.0012** |
| 比值 | **79×** |
| 逐 cell 与污染口径更近 | **39/40** |

### ② 每 cell 的 `l2_shift_results.json`（用 `delta_ece` 对主终点）

注意该文件的 `delta_ece` 是**相反符号约定**（`post − raw`，见论文 §deployment 的说明），
故比较前需取负。非 CPSC 20 格给出固有偏离 median **0.0002**。

| 量 | 值 |
|---|---|
| CPSC 40 格：\|L2 − 干净\| median | **0.1693** |
| CPSC 40 格：\|L2 − 污染\| median | **0.0027** |
| 比值 | **62×** |
| 逐 cell 与污染口径更近 | **39/40** |

---

## ⚠️ 2026-09-17 第二轮对抗审查修正（判定不变，**表述须改**）

独立审查代理复核后确认 **CONTAMINATED 判定成立**，但推翻了三处表述：

1. **「79×」是跨 13 个移位档的选择效应**，不是单一比值。实测该比值范围
   **1.0×–79.1×**，79× 是取最大档。**诚实的说法**：
   > 在**低扰动档**上，CPSC 40 格 **100%（39/39 有效格）** 指向污染口径；
   > 唯一例外 `chapman->cpsc/inceptiontime/43` 是**精确平局**
   > （OLD = 污染 = 0.3308，差 0.0000）。

   注：40 格里只有 39 格「有效」，因为 1 格是平局而非反例。

2. **「`noise24` 是恒等档/近恒等变换」不成立**。它是 13 档中**扰动最小**的一档
   （非 CPSC 20 格 `median|ΔECE| = 0.000726`，次小 `noise12 = 0.003501`，4.8×），
   但仍是 **SNR=24 dB 的加性混合噪声**（`src/data/l2_shifts.py:135` 按**功率比**
   定义，σ_n/σ_s = 0.0631；`max|Δ| = 0.211`）。用它标定"固有偏离"是合理的，
   但不可称其为恒等。

3. **「逐 cell 39/40」在 ① 表里的含义**是 `raw_ece` vs `smooth_ece` 的 L2 ECE
   @ noise24 判定，**与 `swap13` 复现 `ood_acc` 的 40/40 是两件不同的事**，
   不可互相引用（曾因此把准确率的结论误记成 39/40）。

**未受影响的结论**：污染判定、受污染文件清单、以及"必须重跑"的处置。

个例（最清晰）：`cpsc_ptbxl/resnet1d/44` 在 `noise24` 档
`L2 = −0.2898`，污染口径 `−0.2900`（Δ=0.0002），干净口径 `+0.0049`（Δ=0.2947）。

**两个独立产物族、两种独立判定方法、同一个结论。**

## 派生关系：`predictability_3arch.csv` 的情况特殊

`scripts/step2_predictability.py` 读的正是 `l2_shift_results.json`。
但 `results/predictability_3arch.csv` 的 mtime 是 **2026-09-05 23:46** —— **窗口之前**，
即它由**污染前的**输入生成。论文引用的合并 LOO R² = −0.096、CI 上界 0.104
与该文件逐位一致。

然而那些**输入文件已被 09-10~09-13 的污染版覆盖**。实测重跑
（2026-09-17）给出：

| 口径 | TS LOO R² | 95% CI | 上界 < 0.5？ |
|---|---|---|---|
| 论文 / 09-05 历史文件（干净输入，**输入已丢失**） | **−0.0958** | [−0.7199, **+0.1038**] | 是 |
| 重跑于当前污染输入 | **+0.0321** | [−0.7206, **+0.2919**] | 是 |

**结论方向不变**（两种口径都触发预注册失败分支），但论文引用的
`0.104` 在仓库内**已不可复现**；当前输入给出 `0.292`。

**当前处置**：
- `results/predictability_3arch.csv` = **历史（干净输入）版本**，作为论文数字的存档。
- `results/predictability_3arch.CONTAMINATED_INPUTS.csv` = 污染输入下的重跑结果，并存留痕。
- 待 L2 网格按钉死编码重跑后，两者都应被**同一次运行、同一编码**的权威产物替换。

## 待决

1. **重跑 L2 网格**（60 cell × 13 档 × 8 方法）：需 GPU，约数小时。跑完后
   `l2_shift_results.json`、两张 `l2_shift_full_*` 表、`predictability_3arch.csv`
   应一并重生，并重算论文所有引用它们的数字。
2. **`eval_l2_shift.py` 的口径缺陷应修**：改为优先读 checkpoint 自存的 `label_map`，
   与 `run_e2_ablation_discrimination.py` 的处理方式对齐；否则下次改动
   `SUBSPACE_CPSC` 会再次静默污染。建议加断言：
   运行时编码必须等于 `transfer_result.json` 的 `label_map`，否则 raise。
3. 论文中引用 `l2_shift_full_390cells.csv` 的两处（L1206、L1917）目前只是
   **覆盖度声明**，不承载数值；已在正文加注说明该产物待按钉死编码重生。

## 复现

```bash
cd D:/A1/ecg-lab-v2
/c/python/python.exe scripts/verify_l2_shift_encoding.py     # 判定，写出 verdict json
/c/python/python.exe scripts/step2_predictability.py         # 重跑（会覆盖 CSV，先备份）
```
