# ⚠️ 污染通告：`deployment_loco_validation.*`（E1b LOCO 跨语料库泛化验证）

**判定：CONTAMINATED（全部 135 cells × 13 指标）**
**根因：标签编码错位（模型 OLD / 标签 NEW），与 `_L2_SHIFT_CONTAMINATION_NOTICE.md` 同源。**

---

## 1. 涉事产物

| 文件 | mtime | 状态 |
|---|---|---|
| `results/deployment_loco_validation.csv` | 2026-09-11 18:23 | ❌ 污染（全量，1755 行） |
| `results/deployment_loco_validation.json` | 2026-09-11（已重建） | ❌ 污染（records 同源） |
| `results/deployment_loco_validation_smoke.csv` / `.json` | 2026-09-09 17:24 | ❌ 污染（冒烟，n 更小） |
| `paper/submission/supplementary/S2_result_tables/deployment_loco_validation.csv` | 打包时 09-13 | ❌ 污染（随包分发） |

污染窗口 = **2026-09-09 20:26:34 → 2026-09-16 20:48:18**（本地时）。
09-11 落在窗口内。

## 2. 证据链（三条独立，全部可复现）

### 证据 A —— CSV 自证：`label_map` 字段是 NEW 编码
```
$ head -11 results/deployment_loco_validation.csv | tail -1
holdout_ptbxl,ptbxl,Germany,chapman+cpsc,USA+China,42,ts,loco_ensemble,4,2120,3006,0.4018867924528302,
  "{""NORM"": 0, ""MI"": 1, ""STTC"": 2, ""CD"": 3}",brier_reliability_raw,...
```
`label_map = {"NORM":0,"MI":1,"STTC":2,"CD":3}` = `SUBSPACE_CPSC` 的 **NEW** 顺序
（OLD 应为 `{"NORM":0,"CD":1,"STTC":2,"MI":3}`）。

### 证据 B —— checkpoint 自证：模型是 OLD
```
$ python -c "import json;print(json.load(open('checkpoints/transfer/cpsc_chapman/inceptiontime/seed42/transfer_result.json'))['subspace'])"
['NORM', 'CD', 'STTC', 'MI']        # OLD
```
4 个含 CPSC 的源方向（`chapman_cpsc` / `cpsc_chapman` / `cpsc_ptbxl` / `ptbxl_cpsc`）
自存 `subspace` 全为 OLD；`transfer_result.json` 的 mtime = **2026-09-08 17:10–20:42**，
**早于污染窗口**。另 2 个方向（`chapman_ptbxl` / `ptbxl_chapman`）为 5 类，
`subspace=None`，走 `SUPERCLASSES`，不受影响。

### 证据 C —— 这些模型在别处已被证明"需要 OLD 标签"
同一批 checkpoint 产出的 `checkpoints/e2_probs_cache/*.npz`：

```
4 类 cell（40 个）：
  原样标签   逐位命中 transfer_result.json 的 ood_acc:   1/40   max|d|=1.998e-01
  swap13 后  逐位命中:                                  40/40  max|d|=0.000e+00
5 类 cell（22 个）：
  原样标签   逐位命中:                                  20/22  （2 例外是 ptbxl_chapman/mamba 的 09-02 遗留残缺 checkpoint）
  swap13 后  逐位命中:                                   3/22
```
即：**这批模型要求的标签编码是 OLD**。E1b 却喂给它 NEW 标签 → 错位。

## 3. 机制（代码级）

`scripts/run_e1b_loco_validation.py`：

```python
num_classes, subspace = _num_classes_and_subspace(sources, holdout)   # 取运行时 SUBSPACE_CPSC
label_map = {c: i for i, c in enumerate(subspace)}                    # → 09-11 时 = NEW
tgt_ds, _ = _build(holdout, tgt_dir, seed, args.limit, subspace=subspace)   # 目标域标签 = NEW
...
probs = _align_probs_to_subspace(probs, ckpt_nc, num_classes, subspace)     # 5→4 列映射也按 NEW
```
模型是 09-08 的 OLD 训练产物；输出列 j 的语义是 OLD 类 j。
标签却按 NEW 构造 → 逐样本配对错位（MI↔CD 互换，占 CPSC 测试集 38.3%）。

**所有 13 个指标（Brier / smooth ECE / DCR / NCV / ood_acc / ΔECE）都建立在
(probs, labels) 配对上，因此全部失效。**

## 4. 影响面

- **论文正文：不引用**。`grep -n "LOCO" paper/main_bspc.tex` 无命中（只有一处
  `deployment_holdout_recompute.csv`，是另一个文件）。→ **主文数字不受此表影响。**
- **补充材料 S2 表**：受影响。`README.md` 称 S2 为 "Aggregate result tables
  underlying every number in the main text"，本表属多余但会随包分发 → 投稿前必须重跑。
- **协议层**：`docs/adversarial_r1_attack_e1b.md:186-188` 已另有一条独立发现 ——
  R5 预注册要求 Youden J ≈ 0 作为失败标准，但脚本**根本不计算 Youden J**。
  该协议/实现不匹配与本次污染是**两个独立缺陷**，修复时须一并处理。

## 5. 修复方案

1. **不要再用运行时 `SUBSPACE_CPSC` 构造标签。** 改为从**源 checkpoint 自存的
   `subspace`** 读取该折的编码（4 类方向取 4 类 checkpoint 的 `subspace`；
   若两个源都是 5 类，才退回 `SUPERCLASSES`）。
2. 编码护栏（`src/utils/encoding_guard.py`）从"发现不一致就 raise"升级为
   "以 checkpoint 为准自愈 + 记录所用编码"。
3. 修复后重跑 `--arch inceptiontime`（30 个 checkpoint 全部在位，见 §6）。
4. 重跑后同步更新补充材料包并**重签 `SHA256SUMS.txt`**。

## 6. 重跑前置条件核查（已确认满足）

```
6 个方向 × 5 个种子 = 30 个 inceptiontime checkpoint，transfer_result.json 全部在位
$ for f in chapman_ptbxl ptbxl_chapman ptbxl_cpsc cpsc_ptbxl chapman_cpsc cpsc_chapman; do
    for s in 42 43 44 45 46; do
      [ -f "checkpoints/transfer/$f/inceptiontime/seed$s/transfer_result.json" ] || echo MISS $f $s
    done; done
（无输出 → 全部在位）
```

## 7. 附：JSON 的意外损毁与恢复

2026-09-17 18:33，一个对抗性审查代理误运行了 `run_e1b_loco_validation.py`，
把 `results/deployment_loco_validation.json` 覆盖为 3 条 `fatal: 编码护栏` skip 记录，
并同时覆盖了 `.csv`。

- **`.csv` 已恢复**：从 `paper/submission/supplementary/S2_result_tables/` 取回，
  sha256 = `fbc1d763ae9fc992f261dd8a636c2e3025daf3eb6cd0680232bb9026d529ed45`
  **与 `SHA256SUMS.txt` 逐位一致** ✅
- **`.json` 已重建**：`scripts/reconstruct_loco_json.py` 从上述已校验 CSV 重建
  1755 条 records（= 135 cells × 13 指标），meta 从 CSV 头部注释恢复
  （`arch=inceptiontime, seeds=[42,43,44,45,46], methods=['ts','platt','vector'],
  bootstrap=10000, bci_method=bca`）。round-trip 校验浮点 `max|diff| = 0.000e+00`，
  与 CSV 独立再比对 **0 处不符**。
- 被摧毁的原始版本留档为 `results/deployment_loco_validation.DESTROYED_BY_ATTACKER.json`。

⚠️ **该重建恢复的是"污染版"的审计痕迹，不是有效结果。** 有效结果需按 §5 重跑。

---
*登记时间：2026-09-17*
