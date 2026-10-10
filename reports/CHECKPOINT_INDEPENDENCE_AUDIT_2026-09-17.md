# 检查点独立性审计（2026-09-17）

> 起因：MEMORY 里挂着一项待办 ——「查 `cpsc_chapman`/`cpsc_ptbxl` 在 seed42/43 的 `cal_probs` md5 相同（4 格独立性存疑）」。
> 本文把它查到闭合。**结论：确实存在重复，影响可量化，且可修。**

## 一、结论先行

**`cpsc→chapman` 与 `cpsc→ptbxl` 在 `inceptiontime` 的 seed 42/43 上，源模型是同一个文件。**

| 检查点对 | md5(前 12) | mtime | 大小 |
|---|---|---|---|
| `cpsc_chapman/inceptiontime/seed42` vs `cpsc_ptbxl/inceptiontime/seed42` | `6ee3b3995d5b`（同） | 均 09-04 16:11:51 | 均 795189 |
| `cpsc_chapman/inceptiontime/seed43` vs `cpsc_ptbxl/inceptiontime/seed43` | `2cbada61a0ce`（同） | 均 09-04 16:11:51 | 均 795189 |

**全网格去重**：64 个 `best_model.pt` 中**只有这 2 组重复**（`md5sum` 全量比对）。
⇒ 主网格 60 格里，**58 个不同的源模型**，不是 60 个。

## 二、数值层面的确证（不是只靠哈希）

从 `results/robustness_validation_5seeds.csv` 取这 4 格，**ID 域数值逐位相同**：

| method | cpsc→chapman s42 | cpsc→ptbxl s42 | |
|---|---|---|---|
| ts | `0.00292486617218520` | `0.00292486617218520` | 同 |
| platt | `-6.1e-05` | `-6.1e-05` | 同 |
| isotonic | `-0.005093` | `-0.005093` | 同 |
| vector | `-0.00216` | `-0.00216` | 同 |
| matrix | `0.00699` | `0.00699` | 同 |
| dirichlet | `0.006937` | `0.006937` | 同 |
| **em_prior** | `-0.201076` | `-0.007045` | **不同** |
| **bbse_prior** | `-0.067948` | `0.00232` | **不同** |

OOD 域全部不同（目标域不同），seed43 同型。

**这个模式本身就是佐证**：前 6 个方法只用**源域 cal** 拟合 → 同一模型 + 同一 cal split ⇒ 结果必然逐位相同；
`em_prior`/`bbse_prior` 要**目标域先验** → 依赖目标 ⇒ 不同。若这两个文件只是「碰巧相似」，不可能在前 6 个方法上逐位相等。

## 三、为什么会这样（根因，两层）

### 第一层：只有 cpsc 源**可能**共享

`eval_transfer.py:139-142` 在复用检查点时会校验类别数，不匹配直接 `raise`：

```python
ckpt_nc = ckpt.get("num_classes")
if ckpt_nc is not None and ckpt_nc != num_classes:
    raise RuntimeError(f"Checkpoint num_classes={ckpt_nc} ≠ 当前 num_classes={num_classes}。...")
```

而 `num_classes = min(源库类别数, 目标库类别数)`（`eval_transfer.py:101-102`）。按 pair 的实际 K：

| 源 | 目标 A | 目标 B | 两个目标的 K | 能否共享同一源模型 |
|---|---|---|---|---|
| **cpsc** | chapman (K=4) | ptbxl (K=4) | **都是 4** | ✅ **能** |
| chapman | cpsc (K=4) | ptbxl (K=5) | 4 vs 5 | ❌ 不能 |
| ptbxl | chapman (K=5) | cpsc (K=4) | 5 vs 4 | ❌ 不能 |

⇒ **只有 cpsc 源存在共享的可能**。这也正好解释了「为什么只有 cpsc 源出现重复」。

### 第二层：共享是**有意为之**，但只做了一半

`scripts/launch_seed43_transfers.py` 给两个 cpsc 任务都传了 **`--load-model`**（「复用已训练
`best_model.pt` 跳过重训」）：

```python
(common + ["--source","cpsc", ..., "--target","ptbxl",   ..., "--load-model"], "cpsc_ptbxl_seed43"),
(common + ["--source","cpsc", ..., "--target","chapman", ..., "--load-model"], "cpsc_chapman_seed43"),
```

而 `eval_transfer.py` 的 `--load-model` **只在自己 `run_dir` 里找检查点**（第 105-109 行），
不跨 target。所以要让 `--load-model` 生效，必须先**手工把 cpsc 源模型拷到另一个 target 的 run_dir**。

证据链完整：
- 两个文件 mtime **精确到纳秒相同**（`16:11:51.0685109009`）——两次训练不可能同纳秒完成 ⇒ 拷贝；
- inode 不同 ⇒ 不是硬链接，是实体拷贝；
- `--load-model` 的存在 ⇒ 拷贝是**有意的**。

**但只对 seed 42/43 做了，seed 44–46 没做**（那两格是分别训练的）。⇒ **网格构造口径不自洽**：
同一个源（cpsc）、同一个 K（4）、同样两个目标，6 个格子里 4 个共享、6 个不共享。

### 附带发现：训练不可逐位复现

`scripts/train.py:596` 调 `set_seed(args.seed)`，而 `set_seed(seed, deterministic: bool = False)`
（第 51 行）的 `deterministic` **默认 False** ⇒ **cuDNN 非确定性开启**。
所以「分别训练」的格子之间权重必然不同 —— 这也反过来说明 seed42/43 那两组的逐位相同
**只可能**来自拷贝。投稿的可复现性声明应如实写明，或改用 `deterministic=True` 重训
（代价：慢、且现有结果全部作废）。

## 四、影响评估

| 维度 | 是否受影响 |
|---|---|
| **主终点 ΔECE_OOD**（60 格，51/60 正，+0.015863） | **不受影响** —— OOD 用目标域 test，4 格的 OOD 值互不相同 |
| ID 对照终点（60 格，47/60 正，+0.008264） | **轻微夸大**：有效独立格数是 **58** 而非 60 |
| 拟合温度 T 的分布（60 格） | **轻微**：2 个 T 值被重复计入 |
| 「60 个种子实验」的措辞 | 应改为「58 个不同源模型 / 60 格」或修好后维持 60 |

量级很小（ID 终点本就是对照项，不是主主张），但**属于必须披露或修复的事实**。

## 五、修复：已执行「重训」方案

**决策**：重训 `cpsc_ptbxl/inceptiontime/seed{42,43}`，使 60 格对应 **60 个不同的源模型**。
（保留 `cpsc_chapman` 侧不动；两侧对称，任选一侧即可。）

理由：论文的分析单元是 (pair, arch, seed) 格。两对格子共享模型会让 ID 对照终点的
有效样本量变成 58 而论文写 60，CI 会偏窄。重训 2 个检查点即可恢复「60 格 = 60 模型」。

**为什么不选「披露」**：披露虽诚实，但会留下「为什么同源同种子有两个格子 ID 值逐位相同」
这个审稿人必然会问的问题，且掩盖了口径不自洽。重训成本低（2 次训练），收益是干净。

**为什么不反向统一（把 44–46 也改成共享）**：那会作废 6 个已训练模型，改动面更大，
且「源模型应目标无关」这一点在两种做法下都成立（训练数据完全相同，只是随机性不同）。

**执行步骤**（2026-09-17 晚）：

1. 停掉正在跑的污染重跑链（E3 已完成，E1a 刚启动）；
2. 备份：`results/_pre_retrain_baseline_20260917/`（E3 四个 CSV）、
   `checkpoints/_retrain_backup_20260917/seed{42,43}/`（旧 ckpt + 旧 transfer_result.json）、
   `results/robustness_validation_5seeds.csv.bak_pre_retrain`（主表，主终点唯一来源）；
3. 删除 `cpsc_ptbxl/inceptiontime/seed{42,43}/` 下的 **全部** 产物 —— 不只是 `best_model.pt`，
   还包括旧模型派生的缓存 `e3_probs.npz`、`e6_probs.npz`、`l2_shift_results.json`
   （漏删会让下游读到旧模型的缓存）；
4. 重训：`scripts/retrain_cpsc_ptbxl_it_seed42_43.py`，口径严格复刻被替换的 `transfer_result.json`：
   `--arch inceptiontime --source cpsc --target ptbxl --seeds 42 43`、
   `--epochs 50 --gpu-inference --bootstrap 10000 --bci-method bca --n-jobs 8`、
   8 个方法（ts/platt/isotonic/vector/matrix/dirichlet/em_prior/bbse_prior）；
5. 重建主表：`generate_robustness_report_v2.py`（它才是 60 格 480 行表的写出者；
   `generate_robustness_report.py` 是只覆盖 10 格的旧版，勿用）；
6. 重跑污染重跑链（E3 → E1a → E2 → E4 → E6 → E1b）。

**验收（关键）**：重跑 E3 后与 `_pre_retrain_baseline_20260917/` 逐行比对 ——
**应当只有 `cpsc_ptbxl/inceptiontime/seed{42,43}` 相关行发生变化，其余 58 格逐位不变**。
若不止 2 格变化，说明重训引入了额外扰动，必须停下排查。

**其他方案（未采用，留档）**：
- *A. 仅披露*：在 Methods/Limitations 写明 4 格共享同一源检查点、ID 终点逐位相同。成本最低但留隐患。
- *C. `deterministic=True` 全量重训*：最彻底，但作废现有 60 格全部结果，投稿前不可行。

## 六、本次审计中我自己犯的一个错（记录以免重犯）

第一轮用 `md5(np.asarray(d['num_classes']).tobytes())` 比对类别数，得到「62 个文件全部相同」的假结论。
**根因**：`num_classes` 存成 0-d **object** 数组，`.tobytes()` 取到的是**指针**，小整数被 Python 驻留 ⇒ 哈希必然相同。
改成 `int(np.asarray(nc).ravel()[0])` 后真相是：**K=5 恰好当且仅当 pair = {chapman, ptbxl}**，其余为 K=4 —— 与论文披露一致。

> 与之前 `smooth_ece` 误传类别索引是同一类错误：**工具用错口径会产出看起来很硬的假信号**。
> 教训：任何「哈希/数值全部相同」的结论，先怀疑自己的测量口径，再看数据。

## 七、复现命令

```bash
# 全网格检查点去重
find checkpoints/transfer -name best_model.pt | sort | \
  while read f; do echo "$(md5sum "$f" | cut -c1-12)  $f"; done | \
  awk '{print $1}' | sort | uniq -d

# 缓存一致性（同 (source,seed) 的 cal_labels / 同 (target,seed) 的 test_labels）
"C:/python/python.exe" - <<'PY'
import numpy as np, hashlib, glob, os, collections
def md5(a): return hashlib.md5(np.ascontiguousarray(np.asarray(a)).tobytes()).hexdigest()
recs=[]
for f in sorted(glob.glob('checkpoints/e2_probs_cache/*.npz')):
    p=os.path.basename(f)[:-4].split('_')
    d=np.load(f,allow_pickle=True)
    recs.append((p[0],p[1],p[2],p[3],md5(d['cal_labels']),md5(d['test_labels'])))
for i,key in ((0,'source'),(1,'target')):
    g=collections.defaultdict(set)
    for r in recs: g[(r[i],r[3])].add(r[4] if i==0 else r[5])
    print(key,'不一致组:',[k for k,v in g.items() if len(v)>1])
PY
```

**已知的正确解释（不是缺陷）**：源=chapman/ptbxl 时 `cal_labels` 跨目标不同 —— 因为 K=4/K=5 的类别子空间不同，
HYP 是否剔除会改变患者级四分割（`chapman_cpsc` cal n=1979 vs `chapman_ptbxl` cal n=2025）。
源=cpsc 时 K 恒为 4 ⇒ 划分一致。
