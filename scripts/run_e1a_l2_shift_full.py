"""E1a: L2 移位安全率矩阵补齐实验（390 单元格 = 6方向 × 5种子 × 13档）。

=====================================================================
实验目标
=====================================================================
对 60 个 checkpoint（6方向 × 2架构 × 5种子）在 13 档 L2 先验移位下做
eval-only 校准评估，计算每档移位下 TS（温度缩放）改善 Brier reliability
的安全率，输出完整 390 单元格矩阵到 results/l2_shift_full_390cells.csv。

=====================================================================
核心主张（正方论证）
=====================================================================
1. 该实验设计正确：复用已验证的 eval_l2_shift.py 评估管线 + calibration.py
   原语库（经多轮对抗审查修复），保证单格评估的统计严谨性。
2. 安全率定义明确：safety = 1[TS_brier_rel < raw_brier_rel]，即温度缩放后
   Brier reliability 分量严格下降。Brier reliability 用 Murphy 分解
   （brier_parts，精确恒等式 Brier = Rel - Res + Unc）。
3. 390 单元格 = 6方向 × 5种子 × 13档，架构维度聚合（跨 resnet1d +
   inceptiontime 取安全率均值 ∈ {0, 0.5, 1.0}），与现有 157/390 进度吻合
   （24 checkpoint / 2 架构 = 12 方向×种子组合，12×13=156≈157）。
4. 断点续传：检查每个 checkpoint 的 l2_shift_results.json 是否已含全部 13 档
   ×所有方法，若是则跳过，支持中断后继续。

=====================================================================
关键假设
=====================================================================
A1. checkpoint 目录结构稳定：checkpoints/transfer/{src}_{tgt}/{arch}/seed{N}/best_model.pt
A2. 13 档 L2 移位由 src/data/l2_shifts.py:get_l2_shifts() 定义，不再变更
A3. top-label calibration 语义：maxprob + correctness mask（与 eval_l2_shift.py 一致）
A4. 安全率聚合：跨 2 架构取均值，反映"该方向×种子×档下 TS 改善的架构鲁棒性"
A5. mamba 仅 ptbxl_chapman/seed42,43（OOM 限制），作为附录不进入 390 主矩阵

=====================================================================
适用边界
=====================================================================
- 结论适用于 resnet1d + inceptiontime 两架构的迁移场景，不外推到 mamba
- 安全率是二值聚合量，不反映改善幅度（ΔBrier_rel 的绝对值另见详细 CSV）
- 13 档移位为合成变换（噪声档为合成噪声，非 PTB-XL nstdb 真实噪声）
- eval-only：不重训练，校准参数在 source cal split 拟合后固定应用到 target test

=====================================================================
推理链条
=====================================================================
R1. 60 checkpoint 全部存在（已验证目录结构）→ 评估层面 780 = 60×13 可全跑
R2. 复用 eval_l2_shift.py 的 shifted_eval + 模型加载逻辑 → 单格评估正确
R3. 增加 brier_parts 计算 raw/TS 的 reliability 分量 → safety 可计算
R4. 断点续传检查 l2_shift_results.json 完整性 → 中断可恢复
R5. 聚合 780 → 390（架构维度均值）→ 输出矩阵维度正确
R6. CSV 含方向/种子/档/架构/安全率/原始指标 → 可追溯可审计

=====================================================================
潜在攻击点（主动披露）
=====================================================================
P1. 安全率是二值量，丢失改善幅度信息 → 已在详细 CSV 保留 ΔBrier_rel 连续值
P2. 架构聚合取均值可能掩盖单架构失效 → 详细 CSV 保留每架构独立行
P3. Brier reliability 用 10 筱分箱估计，小样本有偏差 → 与 smooth_ece 互补报告
P4. mamba 仅 2 seed 不进主矩阵 → 结论不覆盖 mamba，已在边界声明
P5. 合成噪声档不等于真实 nstdb → 已在 l2_shifts.py docstring 声明限制
P6. 任务描述"bilstm"实为 inceptiontime → 按实际目录结构，已在脚本注释记录

用法:
    python scripts/run_e1a_l2_shift_full.py
    python scripts/run_e1a_l2_shift_full.py --force          # 强制重跑（忽略断点续传）
    python scripts/run_e1a_l2_shift_full.py --dry-run        # 只打印计划不执行
    python scripts/run_e1a_l2_shift_full.py --only ptbxl_chapman  # 只跑指定方向
"""
from __future__ import annotations
import argparse, json, sys, time, traceback, hashlib
from pathlib import Path
from itertools import product
import numpy as np
import torch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from src.models.ecg_classifier import ECGClassifier
from src.data.mapping import SUBSPACE_CPSC
from src.data.l2_shifts import get_l2_shifts, apply_shift, SEED_STRATEGY_VERSION, SEED_STRATEGY_VERSION
from src.utils.calibration_methods import CALIBRATION_METHODS
from src.utils.prior_shift import fit_em, fit_bbse
from src.utils.calibration import smooth_ece, brier_parts, brier_raw
from src.utils.encoding_guard import checkpoint_subspace, encoding_stamp
from train import (
    set_seed, evaluate, create_dataloader,
    build_ptbxl_datasets, build_chapman_datasets, build_cpsc_datasets,
)

# =====================================================================
# 实验配置
# =====================================================================
DATASET_BUILDERS = {
    "ptbxl": build_ptbxl_datasets,
    "chapman": build_chapman_datasets,
    "cpsc": build_cpsc_datasets,
}
DATASET_NUM_CLASSES = {"ptbxl": 5, "chapman": 5, "cpsc": 4}
DATASET_PATHS = {
    "ptbxl": str(ROOT / "data" / "ptbxl_processed"),
    "chapman": str(ROOT / "data" / "chapman_processed_v2"),
    "cpsc": str(ROOT / "data" / "cpsc_processed"),
}

# 6 个迁移方向（source→target）
DIRECTIONS = [
    ("ptbxl", "chapman"),
    ("ptbxl", "cpsc"),
    ("chapman", "ptbxl"),
    ("chapman", "cpsc"),
    ("cpsc", "ptbxl"),
    ("cpsc", "chapman"),
]

# 2 个主架构（任务描述"bilstm"实为 inceptiontime，按实际 checkpoint 目录）
# 注意：mamba 仅 ptbxl_chapman/seed42,43（OOM），作为附录不进 390 主矩阵
ARCHS = ["resnet1d", "inceptiontime"]

# 5 个种子
SEEDS = [42, 43, 44, 45, 46]

# 8 个校准方法（与 eval_l2_shift.py 默认一致，保证与已有结果兼容）
# 任务描述的 8 方法名映射：identity→none(隐含raw), ts→ts, vector_ts→vector,
# matrix_ts→matrix, ensemble_ts→em_prior, beta_ts→platt, dirichlet_ts→dirichlet,
# temperature_scaling→ts(同)。安全率仅依赖 ts，方法集丰富度供详细 CSV 用。
METHODS = ["ts", "platt", "isotonic", "vector", "matrix", "dirichlet", "em_prior", "bbse_prior"]

# 13 档 L2 移位（运行时从 get_l2_shifts() 获取，此处仅文档）
# fs250, fs125, leads6, leads3, leads2, leads1,
# noise24, noise12, noise6, noise0, noise-6, gain0.5, gain2.0

CKPT_ROOT = ROOT / "checkpoints" / "transfer"
RESULTS_DIR = ROOT / "results"
OUT_CSV_390 = RESULTS_DIR / "l2_shift_full_390cells.csv"
OUT_CSV_780 = RESULTS_DIR / "l2_shift_full_780cells_detail.csv"  # 详细附录
OUT_SUMMARY_JSON = RESULTS_DIR / "l2_shift_full_summary.json"

# F1-r2 fix: 显式 n_bins 常量，与 run_e3_brier_dcr_ncv.py 对齐，避免依赖默认值
N_BINS = 10

# P0-1 R8-1修复：SEED_STRATEGY_VERSION 已提取至 src/data/l2_shifts.py 共享模块，
# 消除双点定义 DRY 违反（此处 import 见文件头）。


# =====================================================================
# 辅助函数
# =====================================================================
def _maxprob(p: np.ndarray) -> np.ndarray:
    """top-label 置信度"""
    return np.asarray(p).max(axis=1)


def _bin(p: np.ndarray, labels: np.ndarray) -> np.ndarray:
    """top-label correctness mask（二分类：预测是否正确）"""
    return (np.asarray(p).argmax(1) == np.asarray(labels)).astype(float)


def _brier_reliability(probs: np.ndarray, labels: np.ndarray) -> float:
    """Brier reliability 分量（Murphy 分解，10 等宽箱）。

    输入为 top-label 语义：probs=maxprob, labels=correctness mask。
    返回 reliability 分量（越小越校准）。
    """
    mp = _maxprob(probs) if probs.ndim == 2 else np.asarray(probs)
    corr = _bin(probs, labels) if probs.ndim == 2 else np.asarray(labels, dtype=float)
    _, rel, _, _ = brier_parts(mp, corr, n_bins=N_BINS)  # F1-r2 fix: explicit n_bins
    return float(rel)


def shifted_eval(model, dataset, shift, device,
                 pair_id: str = None, arch: str = None, train_seed: int = None):
    """对 dataset 每条信号施加 shift 后评估 model（复用 eval_l2_shift.py 逻辑）。

    返回 (ood_probs, ood_labels)。
    """
    if pair_id is None or arch is None or train_seed is None:
        raise ValueError(
            "pair_id, arch, train_seed must be explicitly provided for reproducible seed derivation"
        )
    model.eval()
    all_probs, all_labels = [], []
    n = len(dataset)
    # P0-1 R3修复：基于实验参数派生噪声种子，确保跨实验/跨档/跨移位类型噪声独立。
    # 使用 hashlib.md5 代替内置 hash()，保证跨进程可复现（不受 PYTHONHASHSEED 影响）。
    # 派生键包含 pair_id|arch|train_seed|shift_name，不同实验/不同档/不同移位类型
    # 必然获得不同种子。注意：此变更使已有 l2_shift_results.json 不可精确复现，
    # 需重跑受影响实验（见 docs/p0r2_final_verdict.md §2.2）。
    noise_seed = int(
        hashlib.md5(f"{pair_id}|{arch}|{train_seed}|{shift['name']}".encode()).hexdigest()[:8], 16
    ) % (2**32)
    rng = np.random.RandomState(noise_seed)
    for i in range(n):
        x, y = dataset[i]
        sig = x.numpy()
        sig_s = apply_shift(sig, shift, rng=rng)
        # F2修复：降采样变长输入resample回原始长度，模拟低频信息丢失但保持长度一致。
        # shift_downsample 将 500Hz→250Hz/125Hz，长度减半/减为1/4，模型期望固定长度输入。
        # resample 回原长保留降采样后的低频成分，高频信息已不可逆丢失，符合"降档"语义。
        if sig_s.shape[-1] != sig.shape[-1]:
            from scipy.signal import resample
            sig_s = resample(sig_s, sig.shape[-1], axis=-1).astype(np.float32)
        x_s = torch.from_numpy(sig_s).unsqueeze(0).to(device)
        with torch.no_grad():
            _, probs = model(x_s)
            probs = probs.cpu().numpy()
        all_probs.append(probs[0])
        all_labels.append(int(y))
    return np.array(all_probs), np.array(all_labels)


def load_model(ckpt_path: Path, arch: str, num_classes: int,
               d_model: int = 64, n_layers: int = 2, device=None):
    """加载 checkpoint 到 ECGClassifier（复用 eval_l2_shift.py 逻辑）。"""
    if device is None:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    ckpt = torch.load(ckpt_path, weights_only=False, map_location=device)
    sd = ckpt["model_state_dict"]
    ckpt_nc = ckpt.get("num_classes")
    if ckpt_nc is not None and ckpt_nc != num_classes:
        raise RuntimeError(f"Checkpoint num_classes={ckpt_nc} != {num_classes}")
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
    model = ECGClassifier(in_channels=12, d_model=inferred_d_model,
                          n_layers=inferred_n_layers, num_classes=num_classes,
                          dropout=0.1, backbone_type=arch).to(device)
    model.load_state_dict(sd)
    return model, ckpt.get("epoch", "?"), inferred_d_model, inferred_n_layers


def build_datasets(source: str, target: str, seed: int, subspace):
    """构建 source cal + target test 数据集。"""
    src_builder = DATASET_BUILDERS[source]
    tgt_builder = DATASET_BUILDERS[target]
    if source == "cpsc":
        src_ds, _ = src_builder(DATASET_PATHS[source], seed, limit=None)
    else:
        src_ds, _ = src_builder(DATASET_PATHS[source], seed, limit=None, subspace=subspace)
    if target == "cpsc":
        tgt_ds, _ = tgt_builder(DATASET_PATHS[target], seed, limit=None)
    else:
        tgt_ds, _ = tgt_builder(DATASET_PATHS[target], seed, limit=None, subspace=subspace)
    return src_ds, tgt_ds


def expected_encoding_for(source: str, target: str) -> str:
    """某方向在当前运行时口径下应有的编码戳（用于断点续传判定）。"""
    num_classes = min(DATASET_NUM_CLASSES[source], DATASET_NUM_CLASSES[target])
    runtime_subspace = SUBSPACE_CPSC if num_classes == 4 else None
    return encoding_stamp(num_classes, runtime_subspace)


def is_checkpoint_complete(run_dir: Path, seed: int, shift_names: list,
                           expected_encoding: str | None = None) -> bool:
    """断点续传检查：l2_shift_results.json 是否已含该 seed 的全部 13 档×所有方法。

    判据：
    0. **编码戳匹配**（2026-09-17 新增）：文件顶层 `label_encoding` 必须等于
       `expected_encoding`。缺失或不符一律视为不完整 → 强制重跑。
       这一条是必需的：09-10~09-12 产出的 60 份 JSON 全部是在**新编码**下算出的
       污染值，而它们同样满足下面 1/2 两条判据。若不加此判据，断点续传会
       静默复用污染结果，护栏形同虚设。
       （`expected_encoding=None` 时不检查，仅供不关心编码的清单/巡检使用。）
    1. seed_strategy 版本匹配（P0-1 R5修复 A1+A5）：per-seed __seed_strategy__ 字段
       （seed{N}.__seed_strategy__）必须等于 SEED_STRATEGY_VERSION（"md5_v1"）。
       旧结果（legacy_42 / 缺失）视为不完整，需重跑，避免新旧种子策略混用。
    2. seed{N} 键下包含全部 13 档名，且每档含 ts 方法的 cal_ece。
       safety 字段可选（R7修复 Attack-5）：缺失时聚合默认0并标注 safety_source=not_computed，
       不视为不完整，避免 eval_l2_shift.py（不计算 Brier）产出被反复重跑。
    """
    out_path = run_dir / "l2_shift_results.json"
    if not out_path.exists():
        return False
    try:
        data = json.loads(out_path.read_text(encoding="utf-8"))
    except Exception:
        return False
    # 判据0：编码戳
    if expected_encoding is not None and data.get("label_encoding") != expected_encoding:
        return False
    sk = f"seed{seed}"
    if sk not in data:
        return False
    seed_data = data[sk]
    # P0-1 R5修复（A1+A5）：per-seed seed_strategy 版本检查
    if seed_data.get("__seed_strategy__") != SEED_STRATEGY_VERSION:
        return False
    for sn in shift_names:
        if sn not in seed_data:
            return False
        cell = seed_data[sn]
        # 必须含 raw_ece 和 ts.cal_ece（安全率计算依赖）
        if "raw_ece" not in cell or "ts" not in cell or "cal_ece" not in cell["ts"]:
            return False
        # safety 字段可选（R7修复 Attack-4+8）：缺失时不视为不完整，
        # 聚合时由 aggregate_to_390 L462 用 .get("safety", None) 容错并标注 safety_source。
        # 注意：此处不修改 cell（消除死代码 Attack-4 + 谓词函数副作用 Attack-8），
        # 默认值与来源标注在 aggregate_to_390 处理，保持 is_checkpoint_complete 为纯谓词函数。
        if "safety" not in cell:
            pass  # 缺失safety不视为不完整，聚合时默认None并标注safety_source=not_computed
    return True


def load_existing_results(run_dir: Path) -> dict:
    """加载已有 l2_shift_results.json（若存在）。"""
    out_path = run_dir / "l2_shift_results.json"
    if out_path.exists():
        try:
            return json.loads(out_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


# =====================================================================
# 单 checkpoint × 全 13 档评估
# =====================================================================
def evaluate_one_checkpoint(source: str, target: str, arch: str, seed: int,
                            shifts: list, device, force: bool = False) -> dict:
    """对单个 (source, target, arch, seed) checkpoint 跑全部 13 档评估。

    返回该 seed 的结果字典 {shift_name: {raw_ece, ts:{...}, safety, ...}}。
    若断点续传命中且 force=False，直接返回已有结果。
    """
    run_dir = CKPT_ROOT / f"{source}_{target}" / arch / f"seed{seed}"
    ckpt_path = run_dir / "best_model.pt"
    shift_names = [s["name"] for s in shifts]

    # ---------- 编码护栏 ----------
    # 必须在断点续传判定**之前**：本脚本原先用运行时的 SUBSPACE_CPSC 重建标签，
    # 而 checkpoint 是旧编码训练的 → 09-10~09-12 产出的 60 份 l2_shift_results.json
    # 与两张 l2_shift_full_* 表全部被污染（MI↔CD 互换）。
    # 现在：① 以 checkpoint 自存 subspace 为准并断言与运行时一致（不符即 raise）；
    #       ② 把编码戳写进 JSON，且断点续传要求戳匹配 → 旧污染文件不再被复用。
    num_classes = min(DATASET_NUM_CLASSES[source], DATASET_NUM_CLASSES[target])
    runtime_subspace = SUBSPACE_CPSC if num_classes == 4 else None

    # ⚠️ checkpoint 存在性判定必须排在编码护栏**之前**：
    # 护栏要读 checkpoint 自存的 transfer_result.json，checkpoint 不在就没有
    # provenance 可读；否则"checkpoint 缺失"这条正常跳过路径会变成 raise
    # （D4，2026-09-17 对抗审查发现）。
    if not ckpt_path.exists():
        print(f"[skip] {ckpt_path} not found")
        return {}

    subspace = checkpoint_subspace(run_dir, num_classes, runtime_subspace)
    encoding = encoding_stamp(num_classes, subspace)

    # 断点续传（要求编码戳匹配 → 旧污染文件不再被复用）
    if not force and is_checkpoint_complete(run_dir, seed, shift_names,
                                            expected_encoding=encoding):
        existing = load_existing_results(run_dir)
        print(f"[resume] {source}->{target}/{arch}/seed{seed} 已完整，跳过")
        return existing[f"seed{seed}"]

    t0 = time.time()
    print(f"\n[run] {source}->{target}/{arch}/seed{seed}")

    # 加载模型
    model, epoch, dm, nl = load_model(ckpt_path, arch, num_classes, device=device)
    print(f"  loaded ckpt (epoch={epoch}, d_model={dm}, n_layers={nl})")

    # 构建数据集
    set_seed(seed)
    src_ds, tgt_ds = build_datasets(source, target, seed, subspace)

    # source cal split 上拟合校准参数（eval-only，不重训练）
    cal_loader = create_dataloader(src_ds["cal"], batch_size=64, shuffle=False, num_workers=0)
    cal_ev = evaluate(model, cal_loader, device, compute_calibration=False)
    cal_probs, cal_labels = cal_ev["probs"], cal_ev["labels"]

    # 先验估计所需
    cal_pi = np.bincount(cal_labels, minlength=num_classes).astype(float)
    cal_pi = cal_pi / cal_pi.sum()

    seed_results = {}
    for shift in shifts:
        t1 = time.time()
        # 对 target test 施加 shift 后评估
        ood_probs, ood_labels = shifted_eval(
            model, tgt_ds["test"], shift, device,
            pair_id=f"{source}_{target}", arch=arch, train_seed=seed,
        )

        # 原始指标
        raw_ece = smooth_ece(_maxprob(ood_probs), _bin(ood_probs, ood_labels))
        raw_brier_rel = _brier_reliability(ood_probs, ood_labels)
        raw_brier_raw = float(brier_raw(_maxprob(ood_probs), _bin(ood_probs, ood_labels)))
        mean_conf = float(np.mean(np.max(ood_probs, axis=1)))
        pred_entropy = float(np.mean(
            -np.sum(ood_probs * np.log(np.clip(ood_probs, 1e-12, 1)), axis=1)))
        ood_pi_hat = np.mean(ood_probs, axis=0)
        pi_shift_l1 = float(np.sum(np.abs(ood_pi_hat - cal_pi)))

        cell = {
            "raw_ece": float(raw_ece),
            "raw_brier_rel": raw_brier_rel,
            "raw_brier_raw": raw_brier_raw,
            "mean_conf": mean_conf,
            "pred_entropy": pred_entropy,
            "pi_shift_l1": pi_shift_l1,
        }

        # TS 安全率默认 0（若 ts 失败则保持 0）
        ts_brier_rel = raw_brier_rel  # 默认无改善
        safety = 0

        for mname in METHODS:
            try:
                if mname in CALIBRATION_METHODS:
                    fit_fn, apply_fn, _ = CALIBRATION_METHODS[mname]
                    params = fit_fn(cal_probs, cal_labels)
                    if params is None:
                        cell[mname] = {"cal_ece": float(raw_ece),
                                       "delta_ece": 0.0, "status": "skipped"}
                        continue
                    cal_probs_m = apply_fn(ood_probs, params)
                    protocol = "S1"
                elif mname in ("em_prior", "bbse_prior"):
                    fit_fn = fit_em if mname == "em_prior" else fit_bbse
                    result = fit_fn(cal_probs, cal_labels, ood_probs)
                    if result is None:
                        cell[mname] = {"cal_ece": float(raw_ece),
                                       "delta_ece": 0.0, "status": "skipped"}
                        continue
                    w = result["pi_hat"] / np.maximum(result["pi_train"], 1e-12)
                    adj = ood_probs * w[None, :]
                    cal_probs_m = adj / adj.sum(axis=1, keepdims=True)
                    protocol = "S1'"
                else:
                    continue

                cal_ece = smooth_ece(_maxprob(cal_probs_m), _bin(cal_probs_m, ood_labels))
                cal_brier_rel = _brier_reliability(cal_probs_m, ood_labels)
                cell[mname] = {
                    "cal_ece": float(cal_ece),
                    "delta_ece": float(cal_ece - raw_ece),
                    "cal_brier_rel": float(cal_brier_rel),
                    "delta_brier_rel": float(cal_brier_rel - raw_brier_rel),
                    "protocol": protocol,
                }

                # 安全率：TS 改善 Brier reliability（严格下降）
                if mname == "ts":
                    ts_brier_rel = float(cal_brier_rel)
                    safety = 1 if ts_brier_rel < raw_brier_rel else 0
            except Exception as e:
                cell[mname] = {"cal_ece": float(raw_ece), "delta_ece": 0.0,
                               "status": f"error: {type(e).__name__}: {e}"}

        cell["safety"] = safety
        cell["ts_brier_rel"] = float(ts_brier_rel)
        cell["brier_rel_improvement"] = float(raw_brier_rel - ts_brier_rel)
        seed_results[shift["name"]] = cell

        dt = time.time() - t1
        print(f"  [{shift['name']}] raw_ece={raw_ece:.4f} raw_brier_rel={raw_brier_rel:.4f} "
              f"ts_brier_rel={ts_brier_rel:.4f} safety={safety} ({dt:.1f}s)")

    # 保存到 checkpoint 目录（与 eval_l2_shift.py 兼容的格式）
    existing = load_existing_results(run_dir)
    sk = f"seed{seed}"
    if sk not in existing:
        existing[sk] = {}
    existing[sk].update(seed_results)
    # P0-1 R5修复（A1+A5）：写入 per-seed seed_strategy 版本标记，供 is_checkpoint_complete 校验
    existing[sk]["__seed_strategy__"] = SEED_STRATEGY_VERSION
    # 编码戳（2026-09-17）：顶层记录本文件是在哪套标签编码下算出的。
    # 下游（step2_predictability.py / is_checkpoint_complete）据此拒绝污染文件。
    existing["label_encoding"] = encoding
    out_path = run_dir / "l2_shift_results.json"
    out_path.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"  saved {out_path} (total {time.time()-t0:.1f}s)")
    return seed_results


# =====================================================================
# 聚合输出
# =====================================================================
def aggregate_to_390(all_results: dict, shifts: list) -> tuple:
    """聚合 780 评估 → 390 单元格矩阵 + 780 详细行。

    all_results: {(source,target,arch,seed): {shift_name: cell}}
    返回 (rows_390, rows_780)
    """
    rows_780 = []
    # 390 聚合键: (source, target, seed, shift_name) → 跨架构收集 safety
    agg = {}

    for (source, target, arch, seed), seed_res in all_results.items():
        if not seed_res:
            continue
        for shift in shifts:
            sn = shift["name"]
            if sn not in seed_res:
                continue
            cell = seed_res[sn]
            # P0-1 R7修复（Attack-6+7）：safety 默认 None 表示"从未计算"（如 eval_l2_shift 产出），
            # 与 safety=0（计算了且 TS 未改善）区分。safety_source 标注来源，消除聚合偏置透明度不足。
            safety = cell.get("safety", None)
            safety_source = "computed" if "safety" in cell else "not_computed"
            raw_ece = cell.get("raw_ece", float("nan"))
            raw_brier_rel = cell.get("raw_brier_rel", float("nan"))
            ts_brier_rel = cell.get("ts_brier_rel", float("nan"))
            brier_impr = cell.get("brier_rel_improvement", float("nan"))
            ts_delta_ece = cell.get("ts", {}).get("delta_ece", float("nan"))

            # 780 详细行
            rows_780.append({
                "direction": f"{source}->{target}",
                "source": source,
                "target": target,
                "arch": arch,
                "seed": seed,
                "shift": sn,
                "shift_type": shift["type"],
                "raw_ece": raw_ece,
                "raw_brier_rel": raw_brier_rel,
                "ts_brier_rel": ts_brier_rel,
                "ts_delta_ece": ts_delta_ece,
                "brier_rel_improvement": brier_impr,
                "safety": safety if safety is not None else 0,  # CSV中0表示未计算或TS未改善
                "safety_source": safety_source,  # P0-1 R7修复（Attack-6+7）：标注safety来源
            })

            # 390 聚合
            key = (source, target, seed, sn)
            if key not in agg:
                agg[key] = {"safeties": [], "raw_ece": [], "raw_brier_rel": [],
                            "brier_impr": [], "ts_delta_ece": [], "archs": [],
                            "safety_sources": []}
            agg[key]["safeties"].append(safety if safety is not None else 0)  # 保守聚合：None→0
            agg[key]["raw_ece"].append(raw_ece)
            agg[key]["raw_brier_rel"].append(raw_brier_rel)
            agg[key]["brier_impr"].append(brier_impr)
            agg[key]["ts_delta_ece"].append(ts_delta_ece)
            agg[key]["archs"].append(arch)
            agg[key]["safety_sources"].append(safety_source)

    rows_390 = []
    for (source, target, seed, sn), v in sorted(agg.items()):
        n_arch = len(v["safeties"])
        safety_rate = float(np.mean(v["safeties"])) if n_arch else float("nan")
        # P0-1 R8-2修复（Attack-8）：safety_source_summary 使主矩阵 safety_rate 聚合透明，
        # 标注 n_computed/n_arch（如 "2/2 computed" 表示两架构均实算，"1/2 computed" 表示一架构缺失）
        n_computed = int(np.sum([s == "computed" for s in v["safety_sources"]]))
        rows_390.append({
            "direction": f"{source}->{target}",
            "source": source,
            "target": target,
            "seed": seed,
            "shift": sn,
            "n_archs": n_arch,
            "archs": "+".join(v["archs"]),
            "safety_rate": safety_rate,           # ∈ {0, 0.5, 1.0}（2架构）
            "safety_count": int(np.sum(v["safeties"])),
            "safety_source_summary": f"{n_computed}/{n_arch} computed",  # R8-2：聚合来源透明化
            "raw_ece_mean": float(np.nanmean(v["raw_ece"])),
            "raw_brier_rel_mean": float(np.nanmean(v["raw_brier_rel"])),
            "brier_impr_mean": float(np.nanmean(v["brier_impr"])),
            "ts_delta_ece_mean": float(np.nanmean(v["ts_delta_ece"])),
        })

    return rows_390, rows_780


def write_csv(rows: list, path: Path, fieldnames: list):
    """写 CSV（UTF-8，带表头）。"""
    import csv
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})
    print(f"wrote {len(rows)} rows -> {path}")


# =====================================================================
# 主流程
# =====================================================================
def main():
    ap = argparse.ArgumentParser(description="E1a: L2 移位安全率矩阵补齐（390 单元格）")
    ap.add_argument("--force", action="store_true", help="强制重跑，忽略断点续传")
    ap.add_argument("--dry-run", action="store_true", help="只打印计划不执行")
    ap.add_argument("--only", default=None,
                    help="只跑指定方向（如 ptbxl_chapman），格式 src_tgt")
    ap.add_argument("--archs", nargs="+", default=ARCHS, help="架构列表")
    ap.add_argument("--seeds", nargs="+", type=int, default=SEEDS, help="种子列表")
    args = ap.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"device: {device}")
    print(f"ROOT: {ROOT}")

    shifts = get_l2_shifts()
    shift_names = [s["name"] for s in shifts]
    print(f"shifts ({len(shifts)}): {shift_names}")

    # 构建任务清单
    tasks = []
    for (source, target) in DIRECTIONS:
        if args.only and args.only != f"{source}_{target}":
            continue
        for arch in args.archs:
            for seed in args.seeds:
                run_dir = CKPT_ROOT / f"{source}_{target}" / arch / f"seed{seed}"
                ckpt_path = run_dir / "best_model.pt"
                if not ckpt_path.exists():
                    print(f"[warn] missing ckpt: {ckpt_path}")
                    continue
                tasks.append((source, target, arch, seed))

    print(f"\n总任务数: {len(tasks)} (期望 60 = 6方向×2架构×5种子)")
    print(f"目标矩阵: {len(DIRECTIONS)*len(args.seeds)*len(shifts)} 单元格 "
          f"(= {len(DIRECTIONS)}方向 × {len(args.seeds)}种子 × {len(shifts)}档)")

    if args.dry_run:
        print("\n[dry-run] 任务清单:")
        for t in tasks:
            complete = is_checkpoint_complete(
                CKPT_ROOT / f"{t[0]}_{t[1]}" / t[2] / f"seed{t[3]}", t[3], shift_names,
                expected_encoding=expected_encoding_for(t[0], t[1]))
            print(f"  {t[0]}->{t[1]} {t[2]} seed{t[3]} "
                  f"{'[complete]' if complete else '[pending]'}")
        return

    # 执行评估
    all_results = {}
    n_done, n_skip, n_fail = 0, 0, 0
    t_start = time.time()

    for idx, (source, target, arch, seed) in enumerate(tasks, 1):
        run_dir = CKPT_ROOT / f"{source}_{target}" / arch / f"seed{seed}"
        if not args.force and is_checkpoint_complete(
                run_dir, seed, shift_names,
                expected_encoding=expected_encoding_for(source, target)):
            existing = load_existing_results(run_dir)
            all_results[(source, target, arch, seed)] = existing.get(f"seed{seed}", {})
            n_skip += 1
            continue

        try:
            seed_res = evaluate_one_checkpoint(
                source, target, arch, seed, shifts, device, force=args.force)
            all_results[(source, target, arch, seed)] = seed_res
            n_done += 1
        except Exception as e:
            print(f"[FAIL] {source}->{target}/{arch}/seed{seed}: {type(e).__name__}: {e}")
            traceback.print_exc()
            n_fail += 1

        # 进度报告
        elapsed = time.time() - t_start
        print(f"[progress] {idx}/{len(tasks)} done={n_done} skip={n_skip} "
              f"fail={n_fail} elapsed={elapsed:.0f}s")

    # 聚合输出
    print("\n=== 聚合输出 ===")
    rows_390, rows_780 = aggregate_to_390(all_results, shifts)

    # 390 主矩阵
    write_csv(rows_390, OUT_CSV_390, [
        "direction", "source", "target", "seed", "shift",
        "n_archs", "archs", "safety_rate", "safety_count", "safety_source_summary",  # R8-2：聚合来源透明化
        "raw_ece_mean", "raw_brier_rel_mean", "brier_impr_mean", "ts_delta_ece_mean",
    ])

    # 780 详细附录
    write_csv(rows_780, OUT_CSV_780, [
        "direction", "source", "target", "arch", "seed", "shift", "shift_type",
        "raw_ece", "raw_brier_rel", "ts_brier_rel", "ts_delta_ece",
        "brier_rel_improvement", "safety", "safety_source",  # P0-1 R7修复（Attack-6+7）：增加safety_source列
    ])

    # 汇总 JSON
    n_safe = sum(1 for r in rows_390 if r["safety_rate"] >= 0.5)
    summary = {
        "total_390_cells": len(rows_390),
        "target_390_cells": len(DIRECTIONS) * len(args.seeds) * len(shifts),
        "total_780_evals": len(rows_780),
        "target_780_evals": len(tasks) * len(shifts),
        "n_safe_cells": n_safe,
        "safe_rate_overall": float(n_safe / len(rows_390)) if rows_390 else 0.0,
        "n_done": n_done, "n_skip": n_skip, "n_fail": n_fail,
        "elapsed_sec": time.time() - t_start,
        "methods": METHODS,
        "archs": args.archs,
        "seeds": args.seeds,
    }
    OUT_SUMMARY_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_SUMMARY_JSON.write_text(json.dumps(summary, indent=2, ensure_ascii=False),
                                encoding="utf-8")
    print(f"\nsummary -> {OUT_SUMMARY_JSON}")
    print(json.dumps(summary, indent=2, ensure_ascii=False))

    # 完成度报告
    target_390 = len(DIRECTIONS) * len(args.seeds) * len(shifts)
    print(f"\n=== 完成度 ===")
    print(f"390 矩阵: {len(rows_390)}/{target_390} "
          f"({100*len(rows_390)/target_390:.1f}%)")
    print(f"780 评估: {len(rows_780)}/{len(tasks)*len(shifts)}")
    print(f"安全格 (safety_rate>=0.5): {n_safe}/{len(rows_390)}")
    if rows_390:
        print(f"总体安全率: {100*n_safe/len(rows_390):.1f}%")


if __name__ == "__main__":
    main()
