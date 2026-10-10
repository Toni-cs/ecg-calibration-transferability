# 污染通告：`c1_brier_reliability*.csv` / `c1_dcr_ncv*.csv`（E3 族）

**状态**：⚠️ **原始产物已判废（冒烟规模 + 污染窗口）；随包件已于 2026-09-17 全量重跑，
但论文正文 5 处仍引旧数 —— 未闭合**
**新增日期**：2026-09-17　**本通告更新**：2026-10-05（重跑完成后同步状态）
**受影响产物**（原始判废件均 mtime **2026-09-10 12:29**；
随包件现为 mtime **2026-09-17 21:17 / 21:18**，见 §5.1）：

| 文件 | 行数 | 问题 |
|---|---|---|
| `results/c1_brier_reliability.csv` | 60 | 每行 `n_id = n_ood = 20` |
| `results/c1_brier_reliability_summary.csv` | 6 指标 | 同上 |
| `results/c1_dcr_ncv_multiclass.csv` | 60 | 同上 |
| `results/c1_dcr_ncv_summary.csv` | 5 指标 | 同上 |

**论文引用处**：§ncv_discussion（OOD NCV `+0.008125`、ID NCV `−0.006292`）、
贡献清单 (xv)、DCR `+0.016667` —— 共 5 处。

---

## 1. 一句话结论

这一族的输入是 `checkpoints/transfer/**/e3_probs.npz`，而**全部 60 份该缓存
mtime = 2026-09-10 12:24**（落在污染窗口 09-09~09-16 内），且每个 split
**只有 n=20 条**。因此这 4 个产物同时有两个独立缺陷：**标签编码错位** 与
**冒烟规模**。论文引用的 3 个数值必须重跑后才能重新引用。

---

## 2. 证据一：规模（n=20）

`e3_probs.npz` 逐份形状：

```
cal_probs (20,4)  cal_labels (20,)  id_probs (20,4)  id_labels (20,)
ood_probs (20,4)  ood_labels (20,)  T (1,)  num_classes (1,)
```

`c1_brier_reliability.csv` 亦自报 `n_id=20, n_ood=20`（60 行全部如此）。
即：**每个 checkpoint 的 cal / ID / OOD 三个 split 各只有 20 条记录**。

生产者 `run_e3_brier_dcr_ncv.py` 的 `--limit` 默认 `None`（应为全量），
但该批缓存显然用了很小的 `--limit`（`limit // 4 <= 20` ⇒ `limit <= 83`）。
无论具体值为何，n=20 的 OOD 集上的 reliability / DCR / NCV 都是噪声主导，
**不能支撑 60-checkpoint 的汇总统计量**（`t=5.4220`、`p=1.15e-06` 等）。

---

## 3. 证据二：编码

生产者同一句缺陷代码：

```python
K = get_num_classes(source, target)
subspace = SUBSPACE_CPSC if K == 4 else None      # 运行时（09-10 = NEW）
```

而 checkpoint 是 09-08 的 OLD 编码 ⇒ 4 类方向的标签 MI↔CD 错位
（与 `discrimination_metrics_60exp.csv` 同一模式，见
`results/_DISCRIMINATION_CONTAMINATION_NOTICE.md`，那里有逐位实证：
同一批 probs 换回 OLD 标签后 AUROC 由 0.642 变为 0.861）。

---

## 4. 论文暴露清单（需重跑后替换）

| 数值 | 出现次数 | 出处 |
|---|---|---|
| OOD NCV `+0.008125` | 3 | `c1_dcr_ncv_summary.csv` 第 3 行 |
| ID NCV `−0.006292` | 1 | 同上第 4 行 |
| DCR OOD `+0.016667` | 1 | 同上第 1 行 |

**注**：论文 L1909 曾把 C1 称作 "Brier reliability main claim"，
但 `c1_brier_reliability.csv` 自身给出的是 **44/60 为正**，而非 C1 的 51/60。
该标错名已于 2026-09-17 修正为按 C1 的真实定义（Primary OOD benefit，ΔECE_OOD）表述。

---

## 5. 处置

1. **已做**：给 `run_e3_brier_dcr_ncv.py` 加编码护栏（读写两侧），
   `e3_probs.npz` 落盘时写入 `label_encoding` 戳，读缓存时校验；无戳即拒绝。
2. **已做（2026-09-17 21:17 / 21:18）**：以全量 `--limit` 重跑 E3，重生这 4 个 CSV。
   随包件现自报全量 `n_id=2172, n_ood=4050`（不再是 `n=20`），并已同步进本仓
   `results/`。**待核**：本通告未记录重跑件的 `label_encoding` 戳校验结果，
   引用前应补一次确认。
3. **未做（当前唯一开口）**：论文正文 5 处仍引判废件的数值，需按新表替换：

   | 位置 | 正文（判废件） | 重跑后随包表 |
   |---|---|---|
   | `main_bspc.tex:1848` OOD NCV | `+0.008125`, p=0.019 | `+0.000293`, CI `[+0.000093,+0.000493]`, p=4.82e-03 |
   | `main_bspc.tex:1851` ID NCV | `−0.006292`, p=0.016 "significantly negative" | `−0.000042`, CI `[−0.000176,+0.000092]`, **p=0.531，不显著** |
   | 同上效应量 | d = +0.31 / −0.32 | d = +0.3782 / −0.0813 |
   | `main_bspc.tex:1822-1828` 分方向 DCR/NCV | CPSC→PTBXL `+0.0625/+0.0312`、CPSC→Chapman `+0.0375/+0.0188`、Chapman→CPSC `−0.0150/−0.0075` | `+0.001132/+0.000566`、`+0.000594/+0.000297`、`+0.000024/+0.000012`（**由负转正，≈0**） |
   | `main_bspc.tex:2238-2240`、`:2322-2323` | 同 `:1848/:1851` | 同上 |

   两处结论性影响：**ID NCV 的"显著为负"在新表下不成立**；**`Chapman→CPSC`
   不再是负方向**，`:1827-1829` "被 C5 判别门正确拒绝"的叙事失去数据支撑。

   上表数值由 `c1_dcr_ncv_multiclass.csv`（60 行）独立复算得到，与
   `c1_dcr_ncv_summary.csv` 逐位一致（NCV OOD t=2.9294 / NCV ID t=−0.6300）。

4. **在正文替换完成前**，这 4 个文件可作主结果引用（自报全量、日期已过窗口），
   但**正文中由判废件产生的 3 个数值不可引用**。
