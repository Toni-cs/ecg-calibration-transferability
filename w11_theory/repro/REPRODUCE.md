# W11 第三方可复现包｜一条命令复跑 W1–W11

**状态**：合同级（contract-only）。**不含任何真实患者数据**；`CACHE_SCHEMA.json` 只定义 W12 真实队列的冻结格式，实际数据仍被 PhysioNet credentialed DUA 阻塞。

---

## 1. 干净容器（推荐）

```bash
# Python 3.10 + NumPy 2.2.6 + SciPy 1.15.3 + Matplotlib 3.10.9 + Pillow
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
export TZ='Asia/Shanghai'
cd /data/workspace/w11_theory/repro
python -u preflight.py                 # 必须 7/7
python -u verify_release_results.py    # 必须 12/12
```

`verify_release_results.py` 的第 9 门会**真实调用** `preflight.py`，第 12 门会校验本文档里的命令串并确认 1–11 门全过。任一门 FAIL 都会写出具体原因到 `results/verify_release_results.json`，不跳过、不改写检查。

---

## 2. 逐轮重跑（需要时）

所有随机性由固定种子控制，见 `SEED_MANIFEST.json`；主 bootstrap seed 统一 `20261106`。

```bash
cd /data/workspace
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1

# W7  60,000 场景（143 个不可变分片，时间盒续跑）
cd w7_60k   && python -u run_w7.py --box 175 && python -u analyze_w7.py && python -u make_report.py

# W9  10,000 确认 + 600 证伪
cd ../w9_lbst && python -u run_w9.py --box 175 && python -u run_w9.py --falsify --box 70 && python -u analyze_w9.py

# W10 20,000 确认 + 600 LOCO + 600 证伪
cd ../w10_continuous && python -u run_w10.py --tag main     --all --box 168 \
                      && python -u run_w10.py --tag loco     --all --box 100 \
                      && python -u run_w10.py --tag falsify  --all --box 100 \
                      && python -u analyze_w10.py

# W11 576 格理论网格 + 事后诊断
cd ../w11_theory/theory && python -u w11_theory.py && python -u w11_posthoc.py

# 最终验收
cd ../repro && python -u preflight.py && python -u verify_release_results.py
```

### W11-B 百级验收（360 条独立断言，可选但推荐）

```bash
cd /data/workspace/w11_theory
python -u scale/theory_assertions.py        # TH001-TH120
python -u repro/preflight_120.py            # PF001-PF120
python -u repro/verify_120.py               # VG001-VG120
python -u scale/run_w11b.py                 # 严格 S1/S2 哈希 + B1-B6（会真实重跑上面三个脚本）
python -u scale/make_w11b_figure.py
```

`run_w11b.py` 会在重跑三组脚本**之前**算一次 244 个原始数值产物（13 个终局 JSON + 231 个 shard npz）的 SHA256 快照 S1，**之后**再算一次 S2，`S1 == S2` 才通过 B5。三组脚本对原始产物只读。

> W11 原始验收是 `preflight.py` 7/7 与 `verify_release_results.py` 12/12；W11-B 是**额外的验收粒度扩展**（各 120 条），**不替换**原始验收，也不改变 W11 的理论 4/6 结论。

W1–W6、W8 为单轮脚本或诊断轮，产物与逐种子数值已随包冻结；W8 **未消耗任何确认性种子**，只复用 W7 的 60,000 条不可变分片。

---

## 3. 包内文件

| 文件 | 作用 |
|---|---|
| `environment.lock` | Python / NumPy / SciPy / Matplotlib / Pillow 版本、平台、字体、线程策略、时区 |
| `SEED_MANIFEST.json` | W1–W11 全部种子区间（含 debug 与「无新增种子」轮次），两两不重叠 |
| `WEIGHT_HASHES.sha256` | 全部内核 / 运行器 / 分析脚本 / 冻结预注册的 SHA256 |
| `CACHE_SCHEMA.json` | W12 真实队列 logits 缓存**契约**：字段、dtype、导联按名对齐、patient-level split、八条不变量、三项阻塞条件 |
| `DIRECTION_LEDGER.json` | W1–W11 全部主结论（含负面 / 否证），55 条 |
| `preflight.py` | 7 项断言，任何真实数据前向之前必须通过 |
| `verify_release_results.py` | 12 门发布验收 |
| `REPRODUCE.md` | 本文档 |

---

## 4. 12 门清单（PREREGISTRATION_W11.md §4 冻结）

1. `env_lock` — 锁定版本与运行时一致
2. `seed_manifest` — 区间 ≥20 且两两不重叠
3. `prereg_complete` — W2–W11 每轮至少一份冻结预注册
4. `shard_integrity` — W7/W9/W10 六组分片恰好连续、零重复、零缺口
5. `result_json` — 11 轮终局 JSON 存在、可解析、含结论字段或结构化结果块
6. `code_hash` — 哈希全一致且**所有** `.py` 均被清单覆盖
7. `figure_existence` — 每轮 ≥1 张非空 PNG
8. `cache_schema` — 契约字段齐全、八条不变量、明确标注 blocked_until
9. `preflight_7of7` — 真实子进程调用 `preflight.py`
10. `no_overclaim` — 扫描全部 md，禁止肯定式「达到一区 / SOTA / 已发表 / 真实队列已完成」越界断言（否定式允许）
11. `direction_ledger` — ≥30 条、≥8 条负面/否证、覆盖 ≥11 轮
12. `one_command_reproduce` — 命令已文档化且 1–11 门全过

---

## 5. 诚实边界

- `CACHE_SCHEMA.json` 是**契约，不是数据**：`1,145,814` 记录 / `≈395,122` 患者是**计划规模**，本包内没有任何真实波形、logits、患者 ID 或预训练权重
- W1–W11 全部为合成 toy 波形 + 对角 selective SSM（numpy 近似）+ 层级漂移代理；**不是**官方 Mamba-2 CUDA kernel
- 6 万 / 2 万 / 1 万个「种子」是独立 DGP 场景抽样，**不是患者 / 中心 / 记录**
- W11 的 A4 假设（pooled 中心已知）与 A5 高斯假设是本轮理论的显式限制，不得写成完整有限样本保证
- **12/12 PASS 不等于达到一区，也不等于通过同行评议**。真实百万级队列（PhysioNet DUA）、临床 + 生统合作者、第三方独立复跑、单位认定的最新分区名单仍是未完成的硬门槛
- W1–W11 均为内部实验，不得写成已发表算法或 SOTA
