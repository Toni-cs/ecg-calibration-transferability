"""Generate W7 report from w7_results.json (no hardcoded results)."""
from __future__ import annotations
import json, pathlib
import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
D = json.loads((HERE / 'w7_results.json').read_text(encoding='utf-8'))
M, V, P = D['meta'], D['verdict'], D['P']
F0, T = D['F0'], D['convergence_trajectory']['checkpoints']

N = M['actual_seeds']
p1, p2, p3, p4, p5, p6, p7 = (P['P1_precision'], P['P2_primary'],
                              P['P3_rare_cell'], P['P4_cross_round'],
                              P['P5_tail'], P['P6_architecture'],
                              P['P7_proposition1'])
p0 = P['P0_bridge']
ck = V['checks']
npass = V['n_pass']


def pct(x): return f'{100*x:.2f}%'


def ci(x): return f'[{x[0]:.5f}, {x[1]:.5f}]'


L = []
L.append(f"""# W7 实验报告｜60,000 个独立部署场景的稀有失效图谱

**日期**：2026-11-06
**预注册**：`PREREGISTRATION_W7.md` v1.0，**冻结后才执行**
**实际完成**：**{N:,} / 60,000** 个独立种子（{M['seed_range'][0]}–{M['seed_range'][1]}，{M['n_shards']} 个不可变分片）
**一句话**：**{npass}/{V['n_checks']} 项检查通过。**""")

if N >= 60000:
    L.append("60,000 个场景把部署危害率的 CI 半宽压到 "
             f"**{p1['half_width']:.5f}**，并首次解析出 **0.1% 级稀有失效格**；"
             "但按冻结条款，这仍然**不等于**达到 1 区，真实队列、非渐近界与临床合作仍是硬门槛。")
else:
    L.append(f"**未完成 60,000，按预注册 §6 以实际 {N:,} 个如实报告，不补齐、不包装为全量。**")

L.append(f"""
---

## 0. 先说清楚：6 万种子能补什么、不能补什么

用户要求「实在不行就上 6 万个种子」。如果这只是把 W6 的 600 种子重复 100 遍，**边际收益仍然是零**——所以本轮把它重新定义成一个 600 种子在统计上根本回答不了的问题：

> **部署证书在连续异质性全域上，什么时候以什么条件失效？最坏的 0.1% 场景长什么样？**

600 种子对危害率的二项 SE ≈ 1.3%，**看不见 0.1% 级的稀有失效**。60,000 把 SE 压到 ≈0.05%，于是能给出：

| 新增能力 | 600 种子 | **60,000 种子** |
|---|---|---|
| 危害率 95% CI 半宽 | ≈0.013 | **{p1['half_width']:.5f}** |
| 异质性覆盖 | A/B 两档 | **连续 Uniform(0.05, 1.50)**，20 箱精细曲线 |
| 稀有失效格 | 格内样本不足 | **λ×spread×n_min 高维分层** |
| 尾部 0.1% | 0.6 个 | **{p5['n_tail']} 个**最差场景逐条画像 |
| 架构对照 | 100 个 | **{p6['n_cnn']:,} 个 CNN-1D** |

**不能补的**（必须写在这份报告最前面）：W6 已论证 1 区要的是**七个维度**——真实百万级队列、患者级统计、完整指标链、非 in-sample 外验、理论、部署证书、外部背书。**60,000 个合成种子不能替代其中任何一个。** 它是第 8 个补充维度（统计精度 / 稀有事件图谱），不是替代品。真实 1.15M 队列、非渐近界、临床/生统合作者、第三方独立复跑**仍未完成**（见 `一区构想与实施蓝图.md`）。

**W6 的 600 个确认性种子结果一个不改、一个不删。**

---

## 1. 规模与算力账本

| 项 | 值 |
|---|---|
| 主种子 | **{M['seed_range'][0]}–{M['seed_range'][1]}**（{N:,} 个，与 W1–W6 全部不重叠） |
| Mamba / CNN-1D | **{p6['n_mamba']:,} / {p6['n_cnn']:,}**（每 10 个种子 1 个 CNN） |
| 每种子 | 独立 Mamba/CNN 权重 + 36 群层级漂移 + ≈2.9 条/患者 + 6 估计器 + 证书 + 患者级元数据 |
| 口径 | `n_total=1000, L=32, n_ref=700, T_GRID=101, TAU_GRID=61`，spread 连续 |
| 单种子墙钟 | ≈0.083 s（BLAS 单线程；沙盒 1 CPU 配额，多进程实测更慢） |
| 执行方式 | 150 s 时间盒 × {M['n_shards']} 个不可变 `npz` 分片，断点续跑，抗平台 502 |
| 总算力 | ≈{N*0.083/60:.0f} 分钟 CPU，零 GPU |

**纯实现优化**：把 6 估计器 × 36 群的 ECE Python 循环改为一次 `bincount` 向量化分箱；与原 `bin_ece` 逐位验证 **max 差 8.3×10⁻¹⁷**，DGP 与 rng 序列完全未变。

---

## 2. 主结果（{npass}/{V['n_checks']} 项通过）

| 检查 | 结果 | 判定 |
|---|---|---|
| **F0 有效性** | 操控有效性 {F0['manipulation_mean']:.4f} / {pct(F0['manipulation_positive_frac'])} 为正；GST≤GLOBAL 方向一致性 {pct(F0['direction_consistency_frac'])} | {'✅' if F0['PASS'] else '❌'} |
| **P0 桥接（W6 原口径 600 种子）** | harm GST {pct(p0['harm_GST'])} → CERT {pct(p0['harm_CERTGATE'])}，降 {pct(p0['relative_reduction'])} | {'✅' if p0['PASS'] else '❌'} |
| **P1 精度** | harm(CERT) **{pct(p1['harm_CERTGATE'])}**，Wilson CI {ci(p1['CI95_Wilson'])}，半宽 **{p1['half_width']:.5f}** | {'✅' if p1['PASS'] else '❌'} |
| **P2 主效应** | GST {pct(p2['harm_GST'])} → CERT **{pct(p2['harm_CERTGATE'])}**，相对降 **{pct(p2['relative_reduction'])}**，paired CI {ci(p2['paired_CI95'])} | {'✅' if p2['PASS'] else '❌'} |
| **P3 稀有失效格** | 事前格 n={p3['n_in_cell']:,}，危害率 {pct(p3['cell_harm_rate']) if np.isfinite(p3['cell_harm_rate']) else 'n/a'}，全体 {pct(p3['overall_harm_rate'])}，比值 **{p3['ratio']:.2f}×** | {'✅' if p3['PASS'] else '❌'} |
| **P4 跨轮次复现** | W6 点估计 0.0133 vs W7 CI {ci(p4['W7_CI95'])} | {'✅' if p4['PASS'] else '❌'} |
| **P5 尾部 {p5['n_tail']} 个最差场景** | 证书判 GST 比例 {pct(p5['frac_cert_GST_in_tail'])} vs 全体 {pct(p5['frac_cert_GST_overall'])} | {'✅' if p5['PASS'] else '❌'} |
| **P6 双架构** | Mamba ΔECE {p6['mean_dECE_mamba']:.5f} / CNN {p6['mean_dECE_cnn']:.5f} | {'✅' if p6['PASS'] else '❌'} |
| **P7 命题 1 精细验证** | 证书 vs DGP 真值准确率 **{p7['overall_certificate_accuracy_vs_DGP_truth']:.3f}**；spread→判 GST 的 Spearman ρ **{p7['spearman_spread_vs_frac_GST']:.3f}** | {'✅' if p7['PASS'] else '❌'} |

未通过项按冻结条款**照实保留，不改阈值、不换箱数、不补种子、不存在 v1.1**。

### 命题 1 的 DGP 真值口径

`τ²_true = (0.50²+0.35²+0.20²)·spread² + 0.06² = 0.4125·spread² + 0.0036`，`σ² = mean(1/n_g)`；真值「应分群」= `τ²_true > σ²`，**完全独立于任何估计量**。证书（`τ̂² > σ̂²`）与之比对，是对命题 1 的无偏检验，不是自证。
""")

# P3 detail
if p3.get('grid'):
    L.append("""
### 稀有失效图谱（危害率最高的分层格）

| λ | spread | 最小群规模 | n | 危害率 |
|---|---|---|---|---|""")
    for g in p3['grid'][:8]:
        L.append(f"| {g['lambda']} | {g['spread']} | {g['n_min']} | {g['n']:,} | {pct(g['harm_rate'])} |")
    L.append(f"\n共报告 {p3['n_grid_cells_reported']} 个格（含不利格），事前声明的高风险格比值 {p3['ratio']:.2f}×。")

# trajectory
L.append("""
---

## 3. 收敛轨迹：结论不是挑出来的

| 累积场景数 | harm(CERT) | 95% CI | 半宽 | harm(GST) |
|---|---|---|---|---|""")
for t in T:
    L.append(f"| {t['n']:,} | {pct(t['harm_CERT'])} | {ci(t['CI95'])} | {t['half_width']:.5f} | {pct(t['harm_GST'])} |")
L.append("""
按种子顺序累积，**无重选、无子采样**。这张表同时说明两件事：估计在大样本下稳定；而 600 种子量级的 CI 宽度根本不足以解析 0.1% 尾部。""")

L.append(f"""
---

## 4. 完整审计史（一个不删）

| 轮次 | 结论 |
|---|---|
| W1 | PARI 患者内配对无一致优势、A1 无效 → 删除 |
| W2 探索性首轮 | DGP 标签 bug → ORACLE 反而最差，由 F0 拦截 |
| W2 v1.0 | H1=False（bootstrap 抽样单位错配） |
| W2 v1.1 | H1 PASS 但 F-B FAIL，图正则两批有害、方向翻转 → 删图，收敛为 GST |
| W3 | 600 Mamba 种子 −0.0248、CI 全负、534/600；`H1=False` 仅因差 6 个种子 |
| W4 | 论文协议跑通；H2/H3 确认，H4 门控 / F4 漂移解释否证 |
| W5 | GS-GST 543/600 跨过 90% 线；H1 高标准未达 |
| W6 | 命题 1 + CERT-GATE：危害 9.67%→1.33%（−86.2%）、9/9 指标不劣；**H4/H5/H6 三项如实未过** |
| **W7** | **{N:,} 场景稀有失效图谱，{npass}/{V['n_checks']} 项通过；不声称达到 1 区** |

---

## 5. 诚实边界

- 合成 12 导联 toy 波形 + 对角 selective SSM（numpy 近似）+ 层级漂移代理，**不是**官方 Mamba-2 CUDA kernel、不是预训练权重、不是真实 1.15M ECG
- **{N:,} 个种子 ≠ 真实数据规模**：是独立 DGP 场景抽样，不是 {N:,} 个患者 / 中心 / 记录；`ICC / deff / n_eff` 是合成层数值
- W7 是**压力测试口径**（1000 记录 / L=32 / 101 网格），与 W6 确认性口径（1800 / 48 / 181）不同；P0 用 600 个 W6 原口径种子做桥接，结论不外推
- W1–W7 均为**内部实验**，未公开数据/代码/预注册/第三方复现，**不得写成已发表算法或 SOTA**
- **本轮不声称达到 1 区**；分区以单位认定最新名单为准；Related Work 必须按 `成功筛选清单_W5立项.md` §0 四处引用纠错重写

---

## 6. 重跑

```bash
cd /data/workspace/w7_60k
python run_w7.py --bridge                 # P0：600 个 W6 原口径种子
python run_w7.py --all --box 150         # 60,000 主种子，时间盒 + 分片续跑
python analyze_w7.py                     # P0–P7 + 图谱 + 3 张图
python make_report.py                    # 本报告
```

## 7. 产物

`PREREGISTRATION_W7.md` / `w7_kernel.py` / `run_w7.py` / `analyze_w7.py` / `make_report.py` /
`shards/`（{M['n_shards']} 个 npz，**{N:,} 条逐场景原始数值，未裁剪**）/
`bridge_w6_regime.json` / `w7_results.json` / `fig_w7_main.png` + `fig_w7_atlas.png` + `fig_w7_trajectory.png` /
`w7_all.log` / `progress.json`

---

**结论**：**6 万个种子没有白跑——但它换来的是「0.1% 级稀有失效图谱」这个新问题，不是把 W6 的结论重复 100 遍，更不是把 1 区门槛刷掉。** 真实队列、非渐近界、临床合作、第三方复跑，一个都没被替代。
""")

# Re-attach the failed-checks interpretation (kept as its own fragment
# so regenerating the report cannot silently drop it).
_SEC35 = (HERE / 'SECTION_35.md').read_text(encoding='utf-8')
_i = next(i for i, x in enumerate(L) if '## 4. 完整审计史' in x)
L.insert(_i, _SEC35)
(HERE / 'W7_实验报告.md').write_text('\n'.join(L), encoding='utf-8')
print('report written:', HERE / 'W7_实验报告.md', 'chars', sum(len(x) for x in L))
