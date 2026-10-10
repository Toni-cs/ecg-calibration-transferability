"""E1b: LOCO 跨语料库泛化验证（3折 Leave-One-Corpus-Out）

==========================================================================
实验目标
==========================================================================
对3个语料库 (PTB-XL Germany / Chapman-Shaoxing USA / CPSC2018 China)，
每次留出1个作为目标域，用其余2个训练的模型评估校准迁移效果。
这是探索性验证（exploratory），不是 confirmatory 预注册主检验。

==========================================================================
近似方案（关键设计决策，需显式声明）
==========================================================================
真正的 LOCO 需要用 2 个源域数据合并训练一个新模型。现有 60 个 checkpoint
都是成对迁移（1源→1目标），重新训练 3折×5seeds 的 LOCO 模型成本高。

本脚本采用 **源域集成 + 合并校准** 近似：
  - 模型层：对留出目标域 T，复用现有 M_{S1→T} 和 M_{S2→T} 两个 checkpoint，
    在 T 的 test 上做 softmax 概率平均（ensemble 近似联合训练）。
  - 校准层：把 S1_cal 和 S2_cal 的预测概率与标签 concatenate，拟合统一 TS
    参数 T_unified，应用到目标域 ensemble probs。
  - 评估：在目标域 test 上计算 Brier reliability 改善、DCR、NCV，
    并对比单源 baseline（只用1个源域 checkpoint）。

==========================================================================
为什么这个近似合理（推理链条）
==========================================================================
1. 模型集成近似多源训练：ensemble (model averaging) 是 multi-source 训练的
   标准近似。2个源域模型的 softmax 平均，近似于在 S1∪S2 上训练的模型的预测。
   理论依据：Deep Ensemble (Lakshminarayanan 2017) 在 OOD 上优于单模型，
   且概率平均对分布外鲁棒性有 PAC-Bayes 保证（Reuning 2020）。
2. 校准参数共享：TS 是单参数全局方法，在 S1_cal∪S2_cal 上拟合的 T，与在
   S1∪S2 训练的模型的 cal split 上拟合的 T，差异主要来自模型预测分布的
   偏移。ensemble 已部分吸收这个偏移（双峰分布被平均平滑）。
3. 保守性：近似方案的 OOD 性能上限是真 LOCO，下限是单源 best。
   - 上界：真 LOCO 用全部 S1∪S2 数据训练，模型容量充分利用 → 性能 ≥ ensemble
   - 下界：ensemble ≥ max(M_S1→T, M_S2→T) 单源 best（集成不劣于成员）
   若近似已显示 TS 有 Brier reliability 改善，真 LOCO 只会更好。

==========================================================================
关键假设（近似有效性前提）
==========================================================================
A1. 集成近似假设：2个源域模型的 softmax 概率平均 ≈ 在 S1∪S2 上训练的模型的
    预测。当源域间分布差异大时，ensemble 可能比联合训练更保守（低估 LOCO 性能）。
A2. 校准迁移假设：在 S1_cal∪S2_cal 上拟合的 TS 参数，迁移到目标域的有效性，
    与真 LOCO 模型的 cal split 上拟合的 TS 参数相近。若源域间 cal 分布双峰严重，
    TS 单参数可能欠拟合 → 也报告 vector/platt 作敏感性。
A3. 标签空间对齐：涉及 CPSC 时用 4 类子空间 (SUBSPACE_CPSC)，与 eval_transfer.py
    协议§2 对称降级一致。5类折 (PTB↔Chapman) 与 4类折 (含CPSC) 不可直接比较。
A4. checkpoint 可用性：假设 6 个 pair 的 inceptiontime checkpoint 都存在
    （已验证 5 seeds 齐全）。缺失时跳过该 fold-seed 并记录。

==========================================================================
适用边界（LOCO 结论的适用范围）
==========================================================================
B1. 结论适用于 "2源集成→1目标" 的 LOCO 近似，不直接等同于 "合并2源数据重训
    →1目标" 的真 LOCO。论文中需注明 "ensemble-based LOCO approximation"。
B2. 3个语料库的地理/设备覆盖（德国/美国/中国）是 LOCO 泛化声明的最大范围。
    不能外推到第4个未见语料库。
B3. 探索性验证，不作为 confirmatory 结论。p 值未预注册，CI 仅作描述。

==========================================================================
DCR / NCV 定义
==========================================================================
DCR (Deployment Calibration Rate) = 在目标域上，校准后 Brier reliability
    < SAFE_RELIABILITY_THRESHOLD 的样本比例。衡量 "可安全部署" 的覆盖率。
NCV (Net Calibration Value) = 校准带来的 Brier reliability 改善净收益
    = reliability_raw - reliability_cal（正值=改善），按患者级 cluster
    bootstrap 出 CI。

==========================================================================
输出
==========================================================================
results/deployment_loco_validation.csv
  每行 = (fold, holdout, sources, seed, method, scenario, metric, value,
          ci_lo, ci_hi, n_target, num_classes, note)
  scenario ∈ {loco_ensemble, single_source_S1, single_source_S2}
  metric   ∈ {brier_reliability_raw, brier_reliability_cal,
              delta_reliability, smooth_ece_raw, smooth_ece_cal,
              delta_ece, dcr, ncv, ood_acc}

==========================================================================
调用
==========================================================================
    python scripts/run_e1b_loco_validation.py
    # 冒烟：--seeds 42 --bootstrap 500
    # 快速：--bci-method percentile --gpu-inference

依赖：eval_transfer.py 的 _build / 模型加载逻辑、calibration.py 的
      brier_parts / smooth_ece / benefit_inference、calibration_methods.py
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import warnings
from pathlib import Path
from typing import Any

import numpy as np
import torch

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.models.ecg_classifier import ECGClassifier  # noqa: E402
from src.utils.calibration import (  # noqa: E402
    brier_parts, brier_raw, smooth_ece, smooth_ece_gpu, benefit_inference,
    _bca_interval,
)
from src.utils.calibration_methods import CALIBRATION_METHODS  # noqa: E402
from train import (  # noqa: E402
    set_seed, evaluate, create_dataloader,
    build_ptbxl_datasets, build_chapman_datasets, build_cpsc_datasets,
)
from src.data.mapping import SUBSPACE_CPSC, SUPERCLASSES  # noqa: E402
from src.utils.encoding_guard import checkpoint_subspace  # noqa: E402

# ==========================================================================
# 实验配置（预注册常量，研究者自由度显式化）
# ==========================================================================
DATASET_BUILDERS = {
    "ptbxl": build_ptbxl_datasets,
    "chapman": build_chapman_datasets,
    "cpsc": build_cpsc_datasets,
}
DATASET_NUM_CLASSES = {"ptbxl": 5, "chapman": 5, "cpsc": 4}
DATASET_DIRS = {
    "ptbxl": "data/ptbxl_processed",
    "chapman": "data/chapman_processed_v2",
    "cpsc": "data/cpsc_processed",
}
DATASET_GEO = {
    "ptbxl": "Germany",
    "chapman": "USA",
    "cpsc": "China",
}

# 3折 LOCO：每次留出1个语料库作为目标域，用其余2个作为源域
LOCO_FOLDS = [
    {"holdout": "ptbxl",   "sources": ["chapman", "cpsc"]},
    {"holdout": "chapman", "sources": ["ptbxl",   "cpsc"]},
    {"holdout": "cpsc",    "sources": ["ptbxl",   "chapman"]},
]

# 部署安全判据阈值（与 step3_deployment.py 对齐）
SAFE_RELIABILITY_THRESHOLD = 0.05   # DCR: 校准后 Brier reliability < 0.05 → 可部署
SAFE_DELTA_ECE = -0.01              # NCV: ΔECE < -0.01 → 校准有益 > 1%

# Brier 分解分箱数（与 run_e3_brier_dcr_ncv.py 的 N_BINS 对齐）
# P0-2 修复：显式传 n_bins=N_BINS，避免依赖 brier_parts 默认值（默认 10），
# 保证 E1b 与 E3 在分箱参数上语义一致、未来调整单点可控。
N_BINS = 10

# 默认配置
DEFAULT_ARCH = "inceptiontime"
DEFAULT_SEEDS = [42, 43, 44, 45, 46]
DEFAULT_METHODS = ["ts", "platt", "vector"]  # TS主方法 + 敏感性
DEFAULT_SAVE_DIR = "checkpoints/transfer"


# ==========================================================================
# 数据构建（复用 eval_transfer.py 的 _build 逻辑）
# ==========================================================================
def _build(dataset: str, data_dir: str, seed: int, limit: int | None,
           subspace: tuple | None = None):
    """构建四分割；返回 (datasets, clusters_test)

    subspace：若提供（如SUBSPACE_CPSC），ptbxl/chapman 按子空间过滤降级
    （协议§2对称重算）；cpsc 始终用 SUBSPACE_CPSC（内置4类）。
    """
    builder = DATASET_BUILDERS[dataset]
    if dataset == "cpsc":
        ds, clusters = builder(data_dir, seed, limit=limit)
    elif subspace is not None:
        ds, clusters = builder(data_dir, seed, limit=limit, subspace=subspace)
    else:
        ds, clusters = builder(data_dir, seed, limit=limit)
    return ds, clusters


def _num_classes_and_subspace(source_names: list[str], target_name: str):
    """推断 num_classes 与 subspace（协议§2：涉及CPSC→4类对称降级）。

    LOCO 场景：num_classes = min(所有源域, 目标域) 的 num_classes。
    """
    all_names = list(source_names) + [target_name]
    nc = min(DATASET_NUM_CLASSES[n] for n in all_names)
    subspace = SUBSPACE_CPSC if nc == 4 else None
    return nc, subspace


# ==========================================================================
# 模型加载（复用 eval_transfer.py 的 checkpoint 加载逻辑）
# ==========================================================================
def _load_model_from_ckpt(ckpt_path: Path, arch: str, num_classes: int,
                          d_model: int, n_layers: int, device: torch.device):
    """从成对迁移 checkpoint 加载模型，返回 (model, meta)。

    修补（LOCO 5类→4类降级）：用 checkpoint 自身的 num_classes 加载模型
    （而非 LOCO 折的 num_classes），前向后由 _align_probs_to_subspace 降级。
    这样 5 类 checkpoint (chapman→ptbxl) 可复用于 4 类 LOCO 折 (含 CPSC)。

    meta 包含 d_model/n_layers/epoch/val_ece/ckpt_num_classes 供调试。
    """
    ckpt = torch.load(ckpt_path, weights_only=False, map_location=device)
    sd = ckpt["model_state_dict"]

    # 从 state_dict 推断 checkpoint 的 num_classes（checkpoint 未存该字段）
    # 分类头是 classifier 下最后一个 2D weight，shape [num_classes, hidden]
    import re
    classifier_weights = []
    for k in sd:
        m = re.match(r"classifier\.(\d+)\.weight", k)
        if m and sd[k].ndim == 2:
            classifier_weights.append((int(m.group(1)), int(sd[k].shape[0])))
    if classifier_weights:
        classifier_weights.sort()
        ckpt_nc = classifier_weights[-1][1]  # 最后一层的 out_dim = num_classes
    else:
        ckpt_nc = num_classes  # 回退到 LOCO 折的 num_classes

    # 从 state_dict 推断 d_model / n_layers（与 eval_transfer.py 一致）
    if arch == "mamba":
        inferred_d_model = sd["backbone.stem.0.weight"].shape[0]
        import re
        layer_ids = {re.match(r"backbone\.layers\.(\d+)\.", k).group(1)
                     for k in sd if re.match(r"backbone\.layers\.(\d+)\.", k)}
        inferred_n_layers = len(layer_ids)
    elif "backbone.proj.weight" in sd:
        inferred_d_model = sd["backbone.proj.weight"].shape[0]
        inferred_n_layers = n_layers
    else:
        inferred_d_model = d_model
        inferred_n_layers = n_layers

    # 用 checkpoint 的 num_classes 构建模型（而非传入的 num_classes）
    model = ECGClassifier(in_channels=12, d_model=inferred_d_model,
                          n_layers=inferred_n_layers, num_classes=ckpt_nc,
                          dropout=0.1, backbone_type=arch).to(device)
    try:
        model.load_state_dict(sd)
    except RuntimeError as e:
        raise RuntimeError(
            f"load_state_dict 失败（疑似 num_classes 不匹配）: {e}") from e

    meta = {
        "d_model": inferred_d_model,
        "n_layers": inferred_n_layers,
        "epoch": ckpt.get("epoch", "?"),
        "val_ece": ckpt.get("val_ece", "?"),
        "ckpt_num_classes": ckpt_nc,
    }
    return model, meta


def _align_probs_to_subspace(probs: np.ndarray, ckpt_num_classes: int,
                              loco_num_classes: int,
                              subspace: tuple | None) -> np.ndarray:
    """把 checkpoint 输出概率对齐到 LOCO 折的标签空间。

    场景：
    - ckpt_num_classes == loco_num_classes：直接返回（无需对齐）
    - ckpt_num_classes=5, loco_num_classes=4（含 CPSC 的折）：
      保留 SUBSPACE_CPSC=(NORM,CD,STTC,MI) 在 5 类 SUPERCLASSES=(NORM,MI,STTC,CD,HYP)
      中的列索引，丢弃 HYP 列，重归一化。
    - 其他情况：抛 ValueError（不应发生）

    Args:
        probs: (n, ckpt_num_classes) 概率矩阵
        ckpt_num_classes: checkpoint 的类别数
        loco_num_classes: LOCO 折的类别数
        subspace: LOCO 折的 subspace（如 SUBSPACE_CPSC）

    Returns:
        (n, loco_num_classes) 对齐后的概率矩阵
    """
    if ckpt_num_classes == loco_num_classes:
        return probs

    if ckpt_num_classes == 5 and loco_num_classes == 4 and subspace is not None:
        # 5 类 SUPERCLASSES=(NORM,MI,STTC,CD,HYP) → 4 类 SUBSPACE_CPSC=(NORM,CD,STTC,MI)
        # 找出 subspace 每个类在 SUPERCLASSES 中的索引
        keep_idx = [SUPERCLASSES.index(c) for c in subspace]
        aligned = probs[:, keep_idx]
        # 重归一化（丢弃 HYP 列后概率和 < 1）
        aligned = aligned / aligned.sum(axis=1, keepdims=True)
        return aligned

    raise ValueError(
        f"无法对齐概率: ckpt_num_classes={ckpt_num_classes} → "
        f"loco_num_classes={loco_num_classes}, subspace={subspace}")


def _align_labels_to_subspace(labels: np.ndarray, ckpt_num_classes: int,
                              loco_num_classes: int,
                              subspace: tuple | None) -> np.ndarray:
    """把 checkpoint 标签对齐到 LOCO 折的标签空间。

    5 类标签 (0=NORM,1=MI,2=STTC,3=CD,4=HYP) → 4 类标签 (0=NORM,1=CD,2=STTC,3=MI)
    通过 subspace 在 SUPERCLASSES 中的索引映射。

    若标签为 HYP（被丢弃的类），返回 -1（后续过滤）。
    """
    if ckpt_num_classes == loco_num_classes:
        return labels

    if ckpt_num_classes == 5 and loco_num_classes == 4 and subspace is not None:
        # 构建 5类索引 → 4类索引 的映射
        # SUPERCLASSES=(NORM,MI,STTC,CD,HYP), SUBSPACE_CPSC=(NORM,CD,STTC,MI)
        # 5类: 0=NORM,1=MI,2=STTC,3=CD,4=HYP
        # 4类: 0=NORM,1=CD,2=STTC,3=MI
        label_map_5to4 = {}
        for new_idx, cls_name in enumerate(subspace):
            old_idx = SUPERCLASSES.index(cls_name)
            label_map_5to4[old_idx] = new_idx
        # HYP (old_idx=4) 不在映射中 → -1
        mapped = np.array([label_map_5to4.get(int(l), -1) for l in labels])
        return mapped

    raise ValueError(
        f"无法对齐标签: ckpt_num_classes={ckpt_num_classes} → "
        f"loco_num_classes={loco_num_classes}, subspace={subspace}")


def _ckpt_path_for_pair(source: str, target: str, arch: str, seed: int,
                        save_dir: str) -> Path:
    """成对迁移 checkpoint 路径：checkpoints/transfer/{source}_{target}/{arch}/seed{seed}/best_model.pt"""
    return Path(save_dir) / f"{source}_{target}" / arch / f"seed{seed}" / "best_model.pt"


# ==========================================================================
# 校准拟合/应用（复用 eval_transfer.py 的 fit_apply_method）
# ==========================================================================
def fit_apply_method(method_name: str, fit_probs: np.ndarray,
                     fit_labels: np.ndarray, test_probs: np.ndarray):
    """在 fit 分布上拟合校准方法，应用到 test 分布 → 校准后概率。"""
    if method_name == "none":
        return test_probs
    fit_fn, apply_fn, _ = CALIBRATION_METHODS[method_name]
    params = fit_fn(fit_probs, fit_labels)
    if params is None:  # 小样本/过参数化预注册失效 → 返回原概率
        return test_probs
    return apply_fn(test_probs, params)


# ==========================================================================
# 辅助：max-prob / correctness
# ==========================================================================
def _maxprob(p: np.ndarray) -> np.ndarray:
    return np.asarray(p).max(axis=1)


def _correctness(p: np.ndarray, labels: np.ndarray) -> np.ndarray:
    return (np.asarray(p).argmax(1) == np.asarray(labels)).astype(float)


# ==========================================================================
# 核心：单折 LOCO 评估
# ==========================================================================
def run_loco_fold(args, fold: dict, seed: int) -> list[dict]:
    """运行单折 LOCO 评估，返回多行结果记录。

    流程：
    1. 推断 num_classes / subspace
    2. 对每个源域 S_i：
       a. 加载 M_{S_i→holdout} checkpoint
       b. 在 S_i 的 cal split 上前向 → (cal_probs_i, cal_labels_i)
       c. 在 holdout 的 test 上前向 → (tgt_probs_i, tgt_labels)
    3. LOCO ensemble：
       a. 模型集成：tgt_probs_ensemble = mean(tgt_probs_1, tgt_probs_2)
       b. 校准合并：合并 cal_probs_1 ∪ cal_probs_2 → 拟合 TS → 应用到 ensemble
       c. 评估 Brier reliability 改善、DCR、NCV
    4. 单源 baseline：分别用 cal_probs_i 拟合 → 应用到 tgt_probs_i
    5. 返回所有 (method, scenario, metric) 行
    """
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    set_seed(seed)

    holdout = fold["holdout"]
    sources = fold["sources"]
    num_classes, runtime_subspace = _num_classes_and_subspace(sources, holdout)

    # ---------- 编码护栏（自愈式，2026-09-17 重写）----------
    # 本折加载的是**既有** checkpoint M_{S_i→holdout}。它们输出列的语义由
    # **训练时**的编码决定，所以标签必须按 checkpoint 自存的 subspace 重建，
    # 而不是运行时常量。原先用运行时常量 → 09-11 产出的
    # results/deployment_loco_validation.csv 全表污染：该 CSV 的 `label_map`
    # 字段自己就写着 NEW 编码，而 checkpoint 自存的是 OLD（mtime 09-08）。
    # 参见 results/_LOCO_CONTAMINATION_NOTICE.md。
    #
    # D2 修复（2026-09-17 对抗审查）：原实现把折级的 num_classes=4 硬套到每个
    # 源 checkpoint 上，于是 5 类 checkpoint（ptbxl_chapman 等，本来就没有
    # `subspace` 字段）被误判成"未记录 subspace"而 raise，整折变 FATAL。
    # 现改为：
    #   * 按**该 checkpoint 自己的** subspace 长度判断它对本折有无发言权；
    #   * 缺 provenance → 记入 degraded，**不静默放行**；
    #   * 与运行时不一致 → 采用 checkpoint 的（自愈）并打印告警；
    #   * 两个源给出的编码互相矛盾 → 跳过该折（无法同时满足）。
    from src.utils.encoding_guard import load_checkpoint_subspace

    def _stored_of(src_name):
        return load_checkpoint_subspace(
            _ckpt_path_for_pair(src_name, holdout, args.arch, seed,
                                args.save_dir).parent)

    resolved, degraded, seen = None, [], {}
    for _s in sources:
        _stored = _stored_of(_s)
        seen[_s] = _stored
        if _stored is None:
            degraded.append(f"{_s}:无 provenance")
            continue
        if len(_stored) != num_classes:
            continue          # 类别数与折不同（如 5 类 ckpt 用于 4 类折）→ 无发言权
        if resolved is None:
            resolved = _stored
        elif tuple(resolved) != tuple(_stored):
            return [_skip_record(
                fold, seed, num_classes,
                "fatal: 源域 checkpoint 自存编码互相矛盾，无法同时满足："
                + "; ".join(f"{k}={v}" for k, v in seen.items()))]

    if num_classes == 4:
        if resolved is None:
            return [_skip_record(
                fold, seed, num_classes,
                "fatal: 4 类折但无任何源 checkpoint 提供可用 provenance"
                f"（{'; '.join(degraded) or '全部为 5 类'}），"
                "拒绝在无 provenance 时重算")]
        subspace = resolved
        if (runtime_subspace is not None
                and tuple(subspace) != tuple(runtime_subspace)):
            print(f"  [编码护栏·自愈] 运行时 SUBSPACE_CPSC="
                  f"{tuple(runtime_subspace)} ≠ checkpoint 自存 "
                  f"{tuple(subspace)} → 采用 checkpoint 的编码重建标签")
    else:
        subspace = None

    label_map = ({c: i for i, c in enumerate(subspace)} if subspace
                 else {c: i for i, c in enumerate(SUPERCLASSES)})

    print(f"\n{'='*70}")
    print(f"LOCO fold: holdout={holdout} ({DATASET_GEO[holdout]}), "
          f"sources={sources} ({[DATASET_GEO[s] for s in sources]}), "
          f"num_classes={num_classes}, seed={seed}")
    print(f"{'='*70}")

    # ---------- 构建目标域 test 数据（只需 test split） ----------
    tgt_dir = str(_PROJECT_ROOT / DATASET_DIRS[holdout])
    tgt_ds, tgt_clusters = _build(holdout, tgt_dir, seed, args.limit,
                                  subspace=subspace)
    tgt_loader = create_dataloader(tgt_ds["test"], args.batch_size,
                                   shuffle=False, num_workers=args.num_workers)

    # ---------- 对每个源域：加载 checkpoint + 前向推断 ----------
    src_cal_probs_list = []   # 每个源域的 cal probs
    src_cal_labels_list = []  # 每个源域的 cal labels（应一致，取首个）
    tgt_probs_list = []       # 每个源域模型在目标域 test 上的 probs
    tgt_labels_ref = None     # 目标域 test labels（所有源域模型同序，取首个）
    loaded_sources = []       # 成功加载的源域名

    for src in sources:
        src_dir = str(_PROJECT_ROOT / DATASET_DIRS[src])
        ckpt_path = _ckpt_path_for_pair(src, holdout, args.arch, seed, args.save_dir)
        if not ckpt_path.exists():
            print(f"  [SKIP] {src}→{holdout} checkpoint 不存在: {ckpt_path}")
            continue

        # 加载源域模型（在源域上训练，用于评估目标域）
        # 注意：用 checkpoint 自身的 num_classes 加载（可能是5类），
        # 前向后由 _align_probs_to_subspace 降级到 LOCO 折的 num_classes（4类）
        try:
            model, meta = _load_model_from_ckpt(
                ckpt_path, args.arch, num_classes,
                args.d_model, args.n_layers, device)
        except RuntimeError as e:
            print(f"  [SKIP] {src}→{holdout} 加载失败: {e}")
            continue
        ckpt_nc = meta["ckpt_num_classes"]
        print(f"  [LOAD] {src}→{holdout}: {ckpt_path.name} "
              f"(epoch={meta['epoch']}, val_ece={meta['val_ece']}, "
              f"d_model={meta['d_model']}, ckpt_nc={ckpt_nc})")

        # 源域 cal split 前向（用于拟合校准参数）
        # _build 已用 subspace 过滤 → cal labels 已是 LOCO 折的 4 类标签
        # 但 5 类 checkpoint 模型输出 5 类概率 → 需对齐到 4 类
        src_ds, _ = _build(src, src_dir, seed, args.limit, subspace=subspace)
        src_cal_loader = create_dataloader(src_ds["cal"], args.batch_size,
                                           shuffle=False, num_workers=args.num_workers)
        cal_eval = evaluate(model, src_cal_loader, device,
                            compute_calibration=False)
        cal_probs_aligned = _align_probs_to_subspace(
            cal_eval["probs"], ckpt_nc, num_classes, subspace)
        src_cal_probs_list.append(cal_probs_aligned)
        src_cal_labels_list.append(cal_eval["labels"])  # 已是4类标签

        # 目标域 test 前向（用同一模型）
        tgt_eval = evaluate(model, tgt_loader, device,
                            compute_calibration=False)
        tgt_probs_aligned = _align_probs_to_subspace(
            tgt_eval["probs"], ckpt_nc, num_classes, subspace)
        tgt_probs_list.append(tgt_probs_aligned)
        if tgt_labels_ref is None:
            tgt_labels_ref = tgt_eval["labels"]  # 已是4类标签
        else:
            # 验证目标域 labels 一致（同序加载，应完全相同）
            assert np.array_equal(tgt_labels_ref, tgt_eval["labels"]), \
                "目标域 test labels 在不同源域模型前向间不一致（数据加载顺序问题）"
        loaded_sources.append(src)

    if len(loaded_sources) < 2:
        print(f"  [WARN] 仅加载 {len(loaded_sources)} 个源域 checkpoint，"
              f"无法做 LOCO ensemble，跳过该 fold-seed")
        return [_skip_record(fold, seed, num_classes,
                             reason=f"only_{len(loaded_sources)}_sources_loaded")]

    # ---------- LOCO ensemble ----------
    # 模型集成：softmax 概率平均
    tgt_probs_ensemble = np.mean(tgt_probs_list, axis=0)
    # 校准合并：concatenate 所有源域 cal probs + labels
    merged_cal_probs = np.concatenate(src_cal_probs_list, axis=0)
    merged_cal_labels = np.concatenate(src_cal_labels_list, axis=0)

    tgt_labels = tgt_labels_ref
    tgt_clusters_arr = np.asarray(tgt_clusters)
    n_target = len(tgt_labels)
    ood_acc_ensemble = float((tgt_probs_ensemble.argmax(1) == tgt_labels).mean())

    print(f"\n  LOCO ensemble: n_target={n_target}, "
          f"ood_acc={ood_acc_ensemble:.4f}, "
          f"merged_cal_n={len(merged_cal_labels)}")

    records = []
    rng = np.random.default_rng(seed)
    metric_fn = smooth_ece_gpu if args.gpu_inference else smooth_ece

    # ---------- 对每个校准方法评估 ----------
    for mname in args.methods:
        print(f"\n  [method={mname}] LOCO ensemble 评估中...")

        # === LOCO ensemble 场景 ===
        recs = _eval_scenario(
            scenario="loco_ensemble",
            fold=fold, seed=seed, mname=mname,
            fit_probs=merged_cal_probs, fit_labels=merged_cal_labels,
            test_probs=tgt_probs_ensemble, test_labels=tgt_labels,
            test_clusters=tgt_clusters_arr,
            num_classes=num_classes, label_map=label_map,
            ood_acc=ood_acc_ensemble,
            metric_fn=metric_fn, rng=rng,
            args=args,
        )
        records.extend(recs)

        # === 单源 baseline 场景 ===
        for i, src in enumerate(loaded_sources):
            single_ood_acc = float(
                (tgt_probs_list[i].argmax(1) == tgt_labels).mean())
            recs = _eval_scenario(
                scenario=f"single_source_{src}",
                fold=fold, seed=seed, mname=mname,
                fit_probs=src_cal_probs_list[i],
                fit_labels=src_cal_labels_list[i],
                test_probs=tgt_probs_list[i], test_labels=tgt_labels,
                test_clusters=tgt_clusters_arr,
                num_classes=num_classes, label_map=label_map,
                ood_acc=single_ood_acc,
                metric_fn=metric_fn, rng=rng,
                args=args,
            )
            records.extend(recs)

    return records


def _eval_scenario(scenario: str, fold: dict, seed: int, mname: str,
                   fit_probs: np.ndarray, fit_labels: np.ndarray,
                   test_probs: np.ndarray, test_labels: np.ndarray,
                   test_clusters: np.ndarray,
                   num_classes: int, label_map: dict,
                   ood_acc: float,
                   metric_fn, rng: np.random.Generator,
                   args: argparse.Namespace) -> list[dict]:
    """评估单个 (scenario, method) 的所有指标，返回多行记录。

    指标：
    - brier_reliability_raw / brier_reliability_cal / delta_reliability
    - smooth_ece_raw / smooth_ece_cal / delta_ece (带 CI)
    - dcr (Deployment Calibration Rate)
    - ncv (Net Calibration Value, = delta_reliability 带 CI)
    - ood_acc
    """
    holdout = fold["holdout"]
    sources = fold["sources"]
    sources_str = "+".join(sources)

    # 校准拟合/应用
    try:
        cal_probs = fit_apply_method(mname, fit_probs, fit_labels, test_probs)
    except Exception as e:
        warnings.warn(f"[{scenario}/{mname}] 校准拟合失败: {e}，跳过")
        return [_skip_record(fold, seed, num_classes,
                             reason=f"{scenario}_{mname}_fit_failed")]

    # --- Brier reliability (Murphy 分解) ---
    raw_mp = _maxprob(test_probs)
    cal_mp = _maxprob(cal_probs)
    raw_correct = _correctness(test_probs, test_labels)
    cal_correct = _correctness(cal_probs, test_labels)

    brier_raw_total, rel_raw, res_raw, unc_raw = brier_parts(raw_mp, raw_correct, n_bins=N_BINS)
    brier_cal_total, rel_cal, res_cal, unc_cal = brier_parts(cal_mp, cal_correct, n_bins=N_BINS)
    delta_reliability = rel_raw - rel_cal  # 正值=改善

    # --- Smooth ECE (主终点度量，带 cluster bootstrap CI) ---
    ece_raw = float(metric_fn(raw_mp, raw_correct))
    ece_cal = float(metric_fn(cal_mp, cal_correct))

    # benefit_inference 出 ΔECE 的 BCa CI
    ben = benefit_inference(
        raw_mp, cal_mp, cal_correct,
        metric=metric_fn, n_bootstrap=args.bootstrap, rng=rng,
        clusters=test_clusters, bci_method=args.bci_method,
    )
    delta_ece = ben["benefit"]
    delta_ece_ci = ben["benefit_ci"]

    # --- DCR (Deployment Calibration Rate) ---
    # 校准后 Brier reliability < 阈值 的比例
    # 逐样本 reliability 需分箱，这里用全局 reliability 作为部署判据
    # DCR = 1{rel_cal < threshold}（fold 级判据）
    # 分样本 DCR：用每个样本的 (p-y)^2 作为逐样本 Brier，校准后 < 阈值的比例
    per_sample_brier_cal = (cal_mp - cal_correct) ** 2
    per_sample_brier_raw = (raw_mp - raw_correct) ** 2
    dcr_cal = float(np.mean(per_sample_brier_cal < SAFE_RELIABILITY_THRESHOLD))
    dcr_raw = float(np.mean(per_sample_brier_raw < SAFE_RELIABILITY_THRESHOLD))

    # --- NCV (Net Calibration Value) ---
    # = delta_reliability（Brier Murphy 分解的 reliability 分量之差，正值=改善）
    # 修复（P0-2）：此前 ncv_ci = delta_ece_ci 是统计推断伪造——NCV 与 ΔECE 是
    # 不同统计量（reliability vs smooth_ece），复用 ΔECE 的 CI 无任何统计学依据。
    # 现为 NCV 实现独立的 cluster bootstrap CI，统计量计算与 point estimate
    # (delta_reliability) 完全一致：
    #   ncv = brier_parts(raw_mp, raw_correct)[1] - brier_parts(cal_mp, cal_correct)[1]
    # CI 方法与 ΔECE 对齐：bca（默认，含 leave-one-cluster-out jackknife 加速度）
    # 或 percentile。注意 raw 端用 raw_correct、cal 端用 cal_correct（与 point
    # estimate 一致；校准可能改变 argmax，故两端 correctness 独立）。
    ncv_point = delta_reliability

    def _ncv_stat(rmp, rcor, cmp, ccor):
        """NCV = reliability_raw - reliability_cal（Brier Murphy reliability 分量）。"""
        _, rel_r, _, _ = brier_parts(rmp, rcor, n_bins=N_BINS)
        _, rel_c, _, _ = brier_parts(cmp, ccor, n_bins=N_BINS)
        return rel_r - rel_c

    n_tgt = len(test_labels)
    if args.bootstrap > 0:
        # cluster 重采样（与 benefit_inference 一致：患者级 cluster bootstrap）
        if test_clusters is not None:
            uniq_clusters = np.unique(test_clusters)
            cluster_indices = {c: np.where(test_clusters == c)[0]
                               for c in uniq_clusters}
            def _draw_ncv():
                chosen = rng.choice(uniq_clusters, size=len(uniq_clusters),
                                    replace=True)
                return np.concatenate([cluster_indices[c] for c in chosen])
        else:
            def _draw_ncv():
                return rng.choice(n_tgt, n_tgt, replace=True)

        boot_ncvs = np.empty(args.bootstrap)
        for b in range(args.bootstrap):
            idx = _draw_ncv()
            boot_ncvs[b] = _ncv_stat(raw_mp[idx], raw_correct[idx],
                                      cal_mp[idx], cal_correct[idx])

        if args.bci_method == "bca":
            # leave-one-cluster-out / delete-group jackknife（与 ΔECE 一致）
            if test_clusters is not None:
                units = np.unique(test_clusters)
                member_idx = [np.where(test_clusters == u)[0] for u in units]
            else:
                g = min(100, n_tgt)
                perm = np.random.default_rng(0).permutation(n_tgt)
                member_idx = np.array_split(perm, g)
            jacks = np.empty(len(member_idx))
            for k, idxs in enumerate(member_idx):
                keep = np.ones(n_tgt, dtype=bool)
                keep[idxs] = False
                if keep.sum() < 10:
                    jacks[k] = np.nan
                    continue
                jacks[k] = _ncv_stat(raw_mp[keep], raw_correct[keep],
                                      cal_mp[keep], cal_correct[keep])
            ncv_ci = _bca_interval(ncv_point, boot_ncvs, jacks, 0.95)
        else:
            ncv_ci = (float(np.percentile(boot_ncvs, 2.5)),
                      float(np.percentile(boot_ncvs, 97.5)))
    else:
        ncv_ci = (float('nan'), float('nan'))

    # --- 组装记录 ---
    base = {
        "fold": f"holdout_{holdout}",
        "holdout": holdout,
        "holdout_geo": DATASET_GEO[holdout],
        "sources": sources_str,
        "sources_geo": "+".join(DATASET_GEO[s] for s in sources),
        "seed": seed,
        "method": mname,
        "scenario": scenario,
        "num_classes": num_classes,
        "n_target": len(test_labels),
        "n_fit": len(fit_labels),
        "ood_acc": ood_acc,
        "label_map": json.dumps(label_map, ensure_ascii=False),
    }

    records = []
    # Brier reliability
    records.append({**base, "metric": "brier_reliability_raw",
                    "value": rel_raw, "ci_lo": "", "ci_hi": "",
                    "note": "Murphy decomposition reliability component"})
    records.append({**base, "metric": "brier_reliability_cal",
                    "value": rel_cal, "ci_lo": "", "ci_hi": "",
                    "note": "Murphy decomposition reliability component"})
    records.append({**base, "metric": "delta_reliability",
                    "value": delta_reliability, "ci_lo": "", "ci_hi": "",
                    "note": "reliability_raw - reliability_cal (positive=improvement)"})
    # Brier total
    records.append({**base, "metric": "brier_raw_total",
                    "value": brier_raw_total, "ci_lo": "", "ci_hi": "",
                    "note": "REL-RES+UNC"})
    records.append({**base, "metric": "brier_cal_total",
                    "value": brier_cal_total, "ci_lo": "", "ci_hi": "",
                    "note": "REL-RES+UNC"})
    # Smooth ECE
    records.append({**base, "metric": "smooth_ece_raw",
                    "value": ece_raw, "ci_lo": "", "ci_hi": "",
                    "note": "smooth_ece_0.45*(n/2000)^-0.2"})
    records.append({**base, "metric": "smooth_ece_cal",
                    "value": ece_cal, "ci_lo": "", "ci_hi": "",
                    "note": "smooth_ece_0.45*(n/2000)^-0.2"})
    records.append({**base, "metric": "delta_ece",
                    "value": delta_ece,
                    "ci_lo": delta_ece_ci[0], "ci_hi": delta_ece_ci[1],
                    "note": f"BCa cluster bootstrap B={args.bootstrap}"})
    # DCR
    records.append({**base, "metric": "dcr_raw",
                    "value": dcr_raw, "ci_lo": "", "ci_hi": "",
                    "note": f"frac(per_sample_brier_raw < {SAFE_RELIABILITY_THRESHOLD})"})
    records.append({**base, "metric": "dcr_cal",
                    "value": dcr_cal, "ci_lo": "", "ci_hi": "",
                    "note": f"frac(per_sample_brier_cal < {SAFE_RELIABILITY_THRESHOLD})"})
    records.append({**base, "metric": "dcr_improvement",
                    "value": dcr_cal - dcr_raw, "ci_lo": "", "ci_hi": "",
                    "note": "dcr_cal - dcr_raw (positive=calibration expands deployable set)"})
    # NCV
    records.append({**base, "metric": "ncv",
                    "value": ncv_point,
                    "ci_lo": ncv_ci[0], "ci_hi": ncv_ci[1],
                    "note": f"Net Calibration Value = delta_reliability (independent cluster bootstrap CI, B={args.bootstrap}, {args.bci_method})"})
    # OOD acc
    records.append({**base, "metric": "ood_acc",
                    "value": ood_acc, "ci_lo": "", "ci_hi": "",
                    "note": "argmax accuracy on target test"})

    print(f"    [{scenario}/{mname}] rel_raw={rel_raw:.4f} → rel_cal={rel_cal:.4f} "
          f"(Δrel={delta_reliability:+.4f}) | "
          f"ECE_raw={ece_raw:.4f} → ECE_cal={ece_cal:.4f} "
          f"(ΔECE={delta_ece:+.4f} [{delta_ece_ci[0]:+.4f},{delta_ece_ci[1]:+.4f}]) | "
          f"DCR={dcr_raw:.3f}→{dcr_cal:.3f}")

    return records


def _skip_record(fold: dict, seed: int, num_classes: int,
                 reason: str) -> dict:
    """生成跳过记录。"""
    return {
        "fold": f"holdout_{fold['holdout']}",
        "holdout": fold["holdout"],
        "holdout_geo": DATASET_GEO[fold["holdout"]],
        "sources": "+".join(fold["sources"]),
        "sources_geo": "+".join(DATASET_GEO[s] for s in fold["sources"]),
        "seed": seed,
        "method": "",
        "scenario": "skipped",
        "num_classes": num_classes,
        "n_target": 0,
        "n_fit": 0,
        "ood_acc": "",
        "label_map": "",
        "metric": "skip_reason",
        "value": "",
        "ci_lo": "",
        "ci_hi": "",
        "note": reason,
    }


# ==========================================================================
# 主函数
# ==========================================================================
def main():
    ap = argparse.ArgumentParser(
        description="E1b: LOCO 跨语料库泛化验证（3折 Leave-One-Corpus-Out）")
    ap.add_argument("--arch", default=DEFAULT_ARCH,
                    choices=["mamba", "resnet1d", "inceptiontime"],
                    help=f"模型架构（默认 {DEFAULT_ARCH}，与现有 checkpoint 对齐）")
    ap.add_argument("--seeds", nargs="+", type=int, default=DEFAULT_SEEDS,
                    help=f"随机种子列表（默认 {DEFAULT_SEEDS}）")
    ap.add_argument("--methods", nargs="+", default=DEFAULT_METHODS,
                    help=f"校准方法子集（默认 {DEFAULT_METHODS}）")
    ap.add_argument("--d-model", "--d_model", dest="d_model",
                    type=int, default=64,
                    help="Hidden dimension（仅用于推断新模型；从 checkpoint 推断优先）")
    ap.add_argument("--n-layers", type=int, default=2,
                    help="层数（仅用于推断新模型；从 checkpoint 推断优先）")
    ap.add_argument("--batch-size", type=int, default=16)
    ap.add_argument("--num-workers", type=int, default=0,
                    help="DataLoader 多线程数据加载（0=单线程）")
    ap.add_argument("--bootstrap", type=int, default=10000,
                    help="cluster bootstrap 次数（默认 10000；冒烟可减到 500）")
    ap.add_argument("--bci-method", default="bca", choices=["bca", "percentile"],
                    help="CI 方法：bca(默认,含jackknife)或percentile(快)")
    ap.add_argument("--gpu-inference", action="store_true",
                    help="smooth_ece 用 GPU 实现（无 CUDA 自动回退 CPU）")
    ap.add_argument("--save-dir", default=DEFAULT_SAVE_DIR,
                    help=f"成对迁移 checkpoint 根目录（默认 {DEFAULT_SAVE_DIR}）")
    ap.add_argument("--limit", type=int, default=None,
                    help="冒烟截断（限制每语料库样本数）")
    ap.add_argument("--output", default="results/deployment_loco_validation.csv",
                    help="输出 CSV 路径（默认 results/deployment_loco_validation.csv）")
    args = ap.parse_args()

    # cwd 无关锚定（2026-10-04 修复）：--save-dir 为相对路径时锚定到项目根。
    # 事故背景：从非项目根 cwd 启动时 checkpoint 路径全部失效 → 编码护栏
    # "无 provenance" → 15/15 条 skip（备份见
    # results/deployment_loco_validation.csv.bad_cwd_skip15_20261004.csv）。
    # 输出路径本就用 _PROJECT_ROOT 锚定，此处对齐 checkpoint 侧，消除不对称。
    _sd = Path(args.save_dir)
    if not _sd.is_absolute():
        args.save_dir = str(_PROJECT_ROOT / _sd)

    print("=" * 70)
    print("E1b: LOCO 跨语料库泛化验证")
    print("=" * 70)
    print(f"架构: {args.arch}")
    print(f"种子: {args.seeds}")
    print(f"方法: {args.methods}")
    print(f"Bootstrap: B={args.bootstrap}, CI={args.bci_method}")
    print(f"GPU 推断: {args.gpu_inference}")
    print(f"3折 LOCO:")
    for fold in LOCO_FOLDS:
        nc, sub = _num_classes_and_subspace(fold["sources"], fold["holdout"])
        print(f"  - holdout={fold['holdout']} ({DATASET_GEO[fold['holdout']]}) "
              f"← sources={fold['sources']} "
              f"({[DATASET_GEO[s] for s in fold['sources']]}) "
              f"num_classes={nc}")

    # ---------- 运行所有 fold × seed ----------
    all_records: list[dict] = []
    for fold in LOCO_FOLDS:
        for seed in args.seeds:
            try:
                recs = run_loco_fold(args, fold, seed)
                all_records.extend(recs)
            except Exception as e:
                print(f"\n[FATAL] fold={fold}, seed={seed} 失败: {e}")
                import traceback
                traceback.print_exc()
                all_records.append(_skip_record(fold, seed, 0,
                                                reason=f"fatal: {e}"))

    # ---------- 写 CSV ----------
    out_path = _PROJECT_ROOT / args.output
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # CSV 列顺序
    columns = [
        "fold", "holdout", "holdout_geo", "sources", "sources_geo",
        "seed", "method", "scenario", "num_classes", "n_target", "n_fit",
        "ood_acc", "label_map", "metric", "value", "ci_lo", "ci_hi", "note",
    ]

    with open(out_path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        # 头部注释
        w.writerow(["# E1b: LOCO 跨语料库泛化验证"])
        w.writerow(["# 设计: 源域集成(softmax平均) + 合并校准(源cal拼接拟合TS)"])
        w.writerow(["# 近似: ensemble-based LOCO approximation (非真LOCO重训)"])
        w.writerow([f"# 架构: {args.arch}, 种子: {args.seeds}, 方法: {args.methods}"])
        w.writerow([f"# Bootstrap: B={args.bootstrap}, CI={args.bci_method}"])
        w.writerow([f"# DCR阈值: per_sample_brier < {SAFE_RELIABILITY_THRESHOLD}"])
        w.writerow([f"# NCV: delta_reliability (独立cluster bootstrap CI, B={args.bootstrap}, {args.bci_method})"])
        w.writerow([f"# 生成时间: {np.datetime64('now', 's')}"])
        w.writerow([])

        # 列名
        w.writerow(columns)

        # 数据行
        for rec in all_records:
            w.writerow([rec.get(c, "") for c in columns])

    print(f"\n{'='*70}")
    print(f"结果已保存到 {out_path}")
    print(f"总记录数: {len(all_records)}")
    print(f"{'='*70}")

    # ---------- 汇总打印 ----------
    _print_summary(all_records, args)

    # ---------- 同时保存 JSON（便于后续分析） ----------
    out_json = out_path.with_suffix(".json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump({
            "meta": {
                "arch": args.arch,
                "seeds": args.seeds,
                "methods": args.methods,
                "bootstrap": args.bootstrap,
                "bci_method": args.bci_method,
                "safe_reliability_threshold": SAFE_RELIABILITY_THRESHOLD,
                "safe_delta_ece": SAFE_DELTA_ECE,
                "approximation": "ensemble_based_LOCO (softmax avg + merged cal fit)",
                "generated_at": str(np.datetime64("now", "s")),
            },
            "records": all_records,
        }, f, indent=2, ensure_ascii=False, default=str)
    print(f"JSON 详情已保存到 {out_json}")


def _print_summary(records: list[dict], args: argparse.Namespace):
    """汇总打印：每折每方法的 LOCO vs 单源对比。"""
    print("\n" + "=" * 70)
    print("LOCO vs 单源 baseline 汇总（delta_reliability 均值 ± std）")
    print("=" * 70)

    # 按 (holdout, method, scenario) 聚合 delta_reliability
    from collections import defaultdict
    groups = defaultdict(list)
    for r in records:
        if r["metric"] == "delta_reliability" and r["value"] != "":
            key = (r["holdout"], r["method"], r["scenario"])
            groups[key].append(float(r["value"]))

    holdouts = sorted({k[0] for k in groups})
    methods = sorted({k[1] for k in groups})
    scenarios = ["loco_ensemble"] + [s for s in sorted({k[2] for k in groups})
                                     if s != "loco_ensemble"]

    for holdout in holdouts:
        print(f"\n  holdout={holdout} ({DATASET_GEO[holdout]}):")
        header = f"    {'method':<10} " + "".join(f"{s:>22}" for s in scenarios)
        print(header)
        for mname in methods:
            row = f"    {mname:<10} "
            for sc in scenarios:
                vals = groups.get((holdout, mname, sc), [])
                if vals:
                    row += f" {np.mean(vals):+.4f}±{np.std(vals):.4f}(n={len(vals)})"
                else:
                    row += f" {'N/A':>22}"
            print(row)

    # DCR 汇总
    print("\n" + "=" * 70)
    print("DCR 汇总（dcr_cal 均值，越高越好）")
    print("=" * 70)
    dcr_groups = defaultdict(list)
    for r in records:
        if r["metric"] == "dcr_cal" and r["value"] != "":
            key = (r["holdout"], r["method"], r["scenario"])
            dcr_groups[key].append(float(r["value"]))

    for holdout in holdouts:
        print(f"\n  holdout={holdout} ({DATASET_GEO[holdout]}):")
        for mname in methods:
            for sc in scenarios:
                vals = dcr_groups.get((holdout, mname, sc), [])
                if vals:
                    print(f"    {mname:<10} {sc:<22} DCR_cal={np.mean(vals):.4f} (n={len(vals)})")


if __name__ == "__main__":
    main()
