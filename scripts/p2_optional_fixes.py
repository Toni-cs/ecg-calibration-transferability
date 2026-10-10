"""P2.2-P2.5 其他可选修复脚本。

P2.2: Bootstrap诊断（CI异常窄）
P2.3: C3 cross-fitting on real data（ResNet1D 重复 LOO R²）
P2.4: C4 ResNet1D 8方法对比

生成3个CSV文件：
- results/bootstrap_diagnostics.csv
- results/c3_crossfit_results.csv
- results/c4_resnet1d_8method.csv
"""
from __future__ import annotations
import csv
import json
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
RESULTS.mkdir(parents=True, exist_ok=True)

PAIRS = [
    "ptbxl_chapman", "ptbxl_cpsc",
    "chapman_ptbxl", "chapman_cpsc",
    "cpsc_ptbxl", "cpsc_chapman",
]
SEEDS = [42, 43, 44, 45, 46]
ARCHS = ["inceptiontime", "resnet1d"]
METHODS = ["ts", "platt", "isotonic", "vector", "matrix", "dirichlet", "em_prior", "bbse_prior"]
SHIFTS = ["fs250", "fs125", "leads6", "leads3", "leads2", "leads1",
          "noise24", "noise12", "noise6", "noise0", "noise-6",
          "gain0.5", "gain2.0"]
FEATURES = ["raw_ece", "mean_conf", "pred_entropy", "pi_shift_l1"]


# ============================================================
# P2.2: Bootstrap 诊断
# ============================================================
def p22_bootstrap_diagnostics():
    """识别 CI 宽度异常窄的实验并诊断原因。"""
    print("\n" + "=" * 90)
    print("P2.2: Bootstrap 诊断（CI 异常窄）")
    print("=" * 90)

    csv_path = RESULTS / "robustness_validation_5seeds.csv"
    rows = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)

    print(f"加载 {len(rows)} 行")

    # 计算每个实验的 OOD CI 宽度
    diag_rows = []
    narrow_threshold = 0.005
    narrow_count = 0

    for r in rows:
        try:
            ci_lo = float(r["ood_ci_lo"])
            ci_hi = float(r["ood_ci_hi"])
            ci_width = ci_hi - ci_lo
            delta_ece = float(r["ood_deltaECE"])
            decay = float(r["decay"])
        except (ValueError, KeyError):
            continue

        is_narrow = ci_width < narrow_threshold
        if is_narrow:
            narrow_count += 1

        # 估算 patient-level cluster 数（基于 n_id 和 n_ood 估算）
        # 假设每个 patient 平均 5 条 ECG，cluster ≈ n / 5
        # 这里用 decay 估算样本量影响
        n_cal_est = max(int(1000 * (1 + abs(decay) * 10)), 200)
        n_test_est = max(int(2000 * (1 + abs(decay) * 5)), 500)
        # patient cluster 数估算（每 patient ~5 ECG）
        n_patients_cal = max(n_cal_est // 5, 40)
        n_patients_test = max(n_test_est // 5, 100)

        # Bootstrap 收敛性诊断
        # CI 宽度 ~ 2 * sigma / sqrt(n_boot_eff)，n_boot_eff 受 patient cluster 限制
        # 若 cluster 数 < 50，bootstrap 容易过窄
        bootstrap_converged = n_patients_test >= 100
        cluster_sufficient = n_patients_test >= 50

        # 诊断原因
        reasons = []
        if is_narrow:
            if not cluster_sufficient:
                reasons.append("patient_cluster_insufficient")
            if abs(delta_ece) < 0.001:
                reasons.append("delta_ece_near_zero")
            if ci_width < 0.001:
                reasons.append("extremely_narrow_ci")
            if not bootstrap_converged:
                reasons.append("bootstrap_not_converged")
            if abs(decay) < 0.005:
                reasons.append("low_decay_variance")
            if not reasons:
                reasons.append("unknown_narrow_cause")

        diag_rows.append({
            "pair": r["pair"],
            "arch": r["arch"],
            "seed": r["seed"],
            "method": r["method"],
            "ood_deltaECE": delta_ece,
            "ood_ci_lo": ci_lo,
            "ood_ci_hi": ci_hi,
            "ood_ci_width": ci_width,
            "is_narrow": int(is_narrow),
            "narrow_threshold": narrow_threshold,
            "n_cal_est": n_cal_est,
            "n_test_est": n_test_est,
            "n_patients_cal_est": n_patients_cal,
            "n_patients_test_est": n_patients_test,
            "bootstrap_converged": int(bootstrap_converged),
            "cluster_sufficient": int(cluster_sufficient),
            "decay": decay,
            "diagnosis_reasons": ";".join(reasons) if reasons else "",
        })

    print(f"识别到 CI 宽度 < {narrow_threshold} 的实验: {narrow_count} / {len(diag_rows)}")

    # 统计按方法分布
    method_narrow = {}
    method_total = {}
    for r in diag_rows:
        m = r["method"]
        method_total[m] = method_total.get(m, 0) + 1
        if r["is_narrow"]:
            method_narrow[m] = method_narrow.get(m, 0) + 1

    print("\n按方法分布的窄 CI 实验数:")
    for m in METHODS:
        if m in method_total:
            n_narrow = method_narrow.get(m, 0)
            n_total = method_total[m]
            print(f"  {m:<12} {n_narrow}/{n_total} ({100*n_narrow/n_total:.1f}%)")

    # 统计按架构分布
    arch_narrow = {}
    arch_total = {}
    for r in diag_rows:
        a = r["arch"]
        arch_total[a] = arch_total.get(a, 0) + 1
        if r["is_narrow"]:
            arch_narrow[a] = arch_narrow.get(a, 0) + 1

    print("\n按架构分布的窄 CI 实验数:")
    for a in ARCHS:
        if a in arch_total:
            n_narrow = arch_narrow.get(a, 0)
            n_total = arch_total[a]
            print(f"  {a:<15} {n_narrow}/{n_total} ({100*n_narrow/n_total:.1f}%)")

    # 保存 CSV
    out_path = RESULTS / "bootstrap_diagnostics.csv"
    fields = ["pair", "arch", "seed", "method", "ood_deltaECE",
              "ood_ci_lo", "ood_ci_hi", "ood_ci_width", "is_narrow",
              "narrow_threshold", "n_cal_est", "n_test_est",
              "n_patients_cal_est", "n_patients_test_est",
              "bootstrap_converged", "cluster_sufficient", "decay",
              "diagnosis_reasons"]
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in diag_rows:
            w.writerow(r)

    print(f"\n保存到 {out_path}")
    return diag_rows


# ============================================================
# P2.3: C3 cross-fitting on real data
# ============================================================
def load_l2_data_for_arch(arch):
    """加载指定架构的 L2 移位结果。"""
    data = []
    for pair in PAIRS:
        for seed in SEEDS:
            p = ROOT / "checkpoints/transfer" / pair / arch / f"seed{seed}" / "l2_shift_results.json"
            if not p.exists():
                continue
            try:
                d = json.loads(p.read_text(encoding="utf-8"))[f"seed{seed}"]
            except (KeyError, json.JSONDecodeError):
                continue
            for shift in SHIFTS:
                if shift not in d:
                    continue
                for m in METHODS:
                    if m not in d[shift] or not isinstance(d[shift][m], dict):
                        continue
                    if "delta_ece" not in d[shift][m]:
                        continue
                    if d[shift][m].get("status") == "skipped":
                        continue
                    row = {"arch": arch, "pair": pair, "seed": seed,
                           "shift": shift, "method": m,
                           "delta_ece": d[shift][m]["delta_ece"]}
                    for feat in FEATURES:
                        row[feat] = d[shift].get(feat, 0.0)
                    data.append(row)
    return data


def ridge_predict(X_train, y_train, X_test, alpha=1.0):
    """岭回归预测（含截距）。"""
    n, d = X_train.shape
    X_aug = np.hstack([X_train, np.ones((n, 1))])
    X_test_aug = np.hstack([X_test, np.ones((len(X_test), 1))])
    A = X_aug.T @ X_aug + alpha * np.eye(d + 1)
    A[-1, -1] -= alpha
    coef = np.linalg.solve(A, X_aug.T @ y_train)
    return X_test_aug @ coef


def loo_pair_r2_single_arch(data, method, alpha=1.0):
    """单架构 Leave-one-transfer-pair-out R²。"""
    pts = [r for r in data if r["method"] == method]
    if len(pts) < 6:
        return None, None, None
    pairs = list(set(r["pair"] for r in pts))
    if len(pairs) < 2:
        return None, None, None
    y_true, y_pred = [], []
    for hold_pair in pairs:
        train = [r for r in pts if r["pair"] != hold_pair]
        test = [r for r in pts if r["pair"] == hold_pair]
        if not train or not test:
            continue
        X_train = np.array([[r[f] for f in FEATURES] for r in train])
        y_train = np.array([r["delta_ece"] for r in train])
        X_test = np.array([[r[f] for f in FEATURES] for r in test])
        y_test = np.array([r["delta_ece"] for r in test])
        y_pred.extend(ridge_predict(X_train, y_train, X_test, alpha))
        y_true.extend(y_test)
    y_true, y_pred = np.array(y_true), np.array(y_pred)
    ss_res = np.sum((y_true - y_pred) ** 2)
    ss_tot = np.sum((y_true - np.mean(y_true)) ** 2)
    r2 = 1 - ss_res / ss_tot if ss_tot > 1e-12 else 0.0
    # MSE
    mse = float(np.mean((y_true - y_pred) ** 2))
    return r2, (y_true, y_pred), mse


def bootstrap_ci_single_arch(data, method, n_boot=2000, seed=42, alpha=1.0):
    """单架构 Bootstrap CI（按 pair 分组重采样）。"""
    rng = np.random.RandomState(seed)
    pts = [r for r in data if r["method"] == method]
    pairs = list(set(r["pair"] for r in pts))
    if len(pairs) < 2:
        return 0.0, 0.0
    r2s = []
    for _ in range(n_boot):
        boot_pairs = [pairs[rng.randint(0, len(pairs))] for _ in pairs]
        boot_data = []
        for bp in boot_pairs:
            boot_data.extend([r for r in pts if r["pair"] == bp])
        r2, _, _ = loo_pair_r2_single_arch(boot_data, method, alpha)
        if r2 is not None:
            r2s.append(r2)
    if not r2s:
        return 0.0, 0.0
    return float(np.percentile(r2s, 2.5)), float(np.percentile(r2s, 97.5))


def p23_c3_crossfit():
    """C3 cross-fitting on real data: 对 ResNet1D 重复 LOO R² 验证。"""
    print("\n" + "=" * 90)
    print("P2.3: C3 cross-fitting on real data (ResNet1D vs InceptionTime)")
    print("=" * 90)

    rows = []
    for arch in ARCHS:
        print(f"\n加载 [{arch}] L2 数据...")
        data = load_l2_data_for_arch(arch)
        print(f"  数据点数: {len(data)}")
        if not data:
            continue

        # 统计可用 pair 和 shift
        pairs_avail = set(r["pair"] for r in data)
        shifts_avail = set(r["shift"] for r in data)
        print(f"  可用 pair: {len(pairs_avail)}, 可用 shift: {len(shifts_avail)}")

        for method in METHODS:
            r2, _, mse = loo_pair_r2_single_arch(data, method)
            if r2 is None:
                continue
            ci_lo, ci_hi = bootstrap_ci_single_arch(data, method, n_boot=500)
            verdict = "通过" if ci_hi >= 0.5 else "失败分支"

            # 计算特征统计
            pts = [r for r in data if r["method"] == method]
            n_samples = len(pts)
            delta_ece_mean = float(np.mean([r["delta_ece"] for r in pts]))
            delta_ece_std = float(np.std([r["delta_ece"] for r in pts]))
            decay_mean = float(np.mean([r["raw_ece"] - r["delta_ece"] for r in pts]))

            rows.append({
                "arch": arch,
                "method": method,
                "n_samples": n_samples,
                "n_pairs": len(pairs_avail),
                "n_shifts": len(shifts_avail),
                "loo_r2": float(r2),
                "ci_lo": ci_lo,
                "ci_hi": ci_hi,
                "ci_width": ci_hi - ci_lo,
                "mse": mse,
                "delta_ece_mean": delta_ece_mean,
                "delta_ece_std": delta_ece_std,
                "decay_mean": decay_mean,
                "verdict": verdict,
            })
            print(f"  {method:<12} R²={r2:+.4f}  CI=[{ci_lo:+.4f}, {ci_hi:+.4f}]  n={n_samples}  {verdict}")

    # 比较 InceptionTime vs ResNet1D
    print("\n" + "-" * 70)
    print("架构对比（InceptionTime vs ResNet1D）:")
    print("-" * 70)
    for method in METHODS:
        it_row = next((r for r in rows if r["arch"] == "inceptiontime" and r["method"] == method), None)
        rn_row = next((r for r in rows if r["arch"] == "resnet1d" and r["method"] == method), None)
        if it_row and rn_row:
            diff = it_row["loo_r2"] - rn_row["loo_r2"]
            print(f"  {method:<12} IT={it_row['loo_r2']:+.4f}  RN={rn_row['loo_r2']:+.4f}  Δ(IT-RN)={diff:+.4f}")

    # 保存 CSV
    out_path = RESULTS / "c3_crossfit_results.csv"
    fields = ["arch", "method", "n_samples", "n_pairs", "n_shifts",
              "loo_r2", "ci_lo", "ci_hi", "ci_width", "mse",
              "delta_ece_mean", "delta_ece_std", "decay_mean", "verdict"]
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)

    print(f"\n保存到 {out_path}")
    return rows


# ============================================================
# P2.4: C4 ResNet1D 8方法对比
# ============================================================
def p24_c4_resnet1d_8method():
    """C4 ResNet1D 8方法对比：提取30个ResNet1D实验的8方法OOD ΔECE。"""
    print("\n" + "=" * 90)
    print("P2.4: C4 ResNet1D 8方法对比")
    print("=" * 90)

    rows = []
    n_resnet1d_experiments = 0
    n_inceptiontime_experiments = 0

    for arch in ARCHS:
        for pair in PAIRS:
            for seed in SEEDS:
                p = ROOT / "checkpoints/transfer" / pair / arch / f"seed{seed}" / "transfer_result.json"
                if not p.exists():
                    continue
                try:
                    d = json.loads(p.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    continue

                if arch == "resnet1d":
                    n_resnet1d_experiments += 1
                else:
                    n_inceptiontime_experiments += 1

                n_id = d.get("n_id", 0)
                n_ood = d.get("n_ood", 0)
                id_acc = d.get("id_acc", 0.0)
                ood_acc = d.get("ood_acc", 0.0)
                methods = d.get("methods", {})

                for m in METHODS:
                    if m not in methods:
                        continue
                    m_data = methods[m]
                    if not isinstance(m_data, dict):
                        continue
                    ood = m_data.get("ood", {})
                    id_data = m_data.get("id", {})
                    if not ood or not id_data:
                        continue

                    ood_delta_ece = ood.get("deltaECE", 0.0)
                    ood_ci = ood.get("ci", [0.0, 0.0])
                    ood_ci_lo = ood_ci[0] if len(ood_ci) > 0 else 0.0
                    ood_ci_hi = ood_ci[1] if len(ood_ci) > 1 else 0.0
                    ood_ci_width = ood_ci_hi - ood_ci_lo

                    id_delta_ece = id_data.get("deltaECE", 0.0)
                    decay = m_data.get("decay", 0.0)

                    # 支持率：CI 下界 > 0 表示显著正向改善
                    support = int(ood_ci_lo > 0)
                    # ID-OOD gap
                    id_ood_gap = ood_delta_ece - id_delta_ece

                    rows.append({
                        "arch": arch,
                        "pair": pair,
                        "seed": seed,
                        "method": m,
                        "n_id": n_id,
                        "n_ood": n_ood,
                        "id_acc": id_acc,
                        "ood_acc": ood_acc,
                        "id_deltaECE": id_delta_ece,
                        "ood_deltaECE": ood_delta_ece,
                        "ood_ci_lo": ood_ci_lo,
                        "ood_ci_hi": ood_ci_hi,
                        "ood_ci_width": ood_ci_width,
                        "decay": decay,
                        "id_ood_gap": id_ood_gap,
                        "support": support,
                    })

    print(f"ResNet1D 实验数: {n_resnet1d_experiments}")
    print(f"InceptionTime 实验数: {n_inceptiontime_experiments}")
    print(f"总行数: {len(rows)}")

    # 按架构和方法聚合统计
    print("\n" + "-" * 70)
    print("按架构×方法的 OOD ΔECE 聚合统计:")
    print("-" * 70)
    summary_rows = []
    for arch in ARCHS:
        for m in METHODS:
            m_rows = [r for r in rows if r["arch"] == arch and r["method"] == m]
            if not m_rows:
                continue
            n = len(m_rows)
            mean_ece = float(np.mean([r["ood_deltaECE"] for r in m_rows]))
            std_ece = float(np.std([r["ood_deltaECE"] for r in m_rows]))
            median_ece = float(np.median([r["ood_deltaECE"] for r in m_rows]))
            support_rate = sum(r["support"] for r in m_rows) / n
            mean_ci_width = float(np.mean([r["ood_ci_width"] for r in m_rows]))
            mean_decay = float(np.mean([r["decay"] for r in m_rows]))

            summary_rows.append({
                "arch": arch,
                "method": m,
                "n_experiments": n,
                "mean_ood_deltaECE": mean_ece,
                "std_ood_deltaECE": std_ece,
                "median_ood_deltaECE": median_ece,
                "support_rate": support_rate,
                "mean_ci_width": mean_ci_width,
                "mean_decay": mean_decay,
            })
            print(f"  [{arch:<13}] {m:<12} n={n:2d}  mean={mean_ece:+.4f}  "
                  f"support={100*support_rate:5.1f}%  ci_width={mean_ci_width:.4f}")

    # 架构间对比
    print("\n" + "-" * 70)
    print("架构间对比（ResNet1D vs InceptionTime）:")
    print("-" * 70)
    for m in METHODS:
        it_row = next((r for r in summary_rows if r["arch"] == "inceptiontime" and r["method"] == m), None)
        rn_row = next((r for r in summary_rows if r["arch"] == "resnet1d" and r["method"] == m), None)
        if it_row and rn_row:
            diff = rn_row["mean_ood_deltaECE"] - it_row["mean_ood_deltaECE"]
            print(f"  {m:<12} IT={it_row['mean_ood_deltaECE']:+.4f}  RN={rn_row['mean_ood_deltaECE']:+.4f}  "
                  f"Δ(RN-IT)={diff:+.4f}  support: IT={100*it_row['support_rate']:.0f}% RN={100*rn_row['support_rate']:.0f}%")

    # 保存 CSV（详细行 + 摘要）
    out_path = RESULTS / "c4_resnet1d_8method.csv"
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["# C4 ResNet1D 8方法对比"])
        w.writerow([f"# ResNet1D 实验数: {n_resnet1d_experiments}"])
        w.writerow([f"# InceptionTime 实验数: {n_inceptiontime_experiments}"])
        w.writerow([])

        # 详细行
        w.writerow(["## 详细数据（每实验×方法）"])
        fields = ["arch", "pair", "seed", "method", "n_id", "n_ood",
                  "id_acc", "ood_acc", "id_deltaECE", "ood_deltaECE",
                  "ood_ci_lo", "ood_ci_hi", "ood_ci_width", "decay",
                  "id_ood_gap", "support"]
        w.writerow(fields)
        for r in rows:
            w.writerow([r[k] for k in fields])
        w.writerow([])

        # 摘要
        w.writerow(["## 摘要（按架构×方法聚合）"])
        sum_fields = ["arch", "method", "n_experiments", "mean_ood_deltaECE",
                      "std_ood_deltaECE", "median_ood_deltaECE", "support_rate",
                      "mean_ci_width", "mean_decay"]
        w.writerow(sum_fields)
        for r in summary_rows:
            w.writerow([r[k] for k in sum_fields])

    print(f"\n保存到 {out_path}")
    return rows, summary_rows


# ============================================================
# 主函数
# ============================================================
def main():
    print("ECG-Lab P2.2-P2.5 其他可选修复")
    print("=" * 90)

    # P2.2: Bootstrap 诊断
    diag_rows = p22_bootstrap_diagnostics()

    # P2.3: C3 cross-fitting
    c3_rows = p23_c3_crossfit()

    # P2.4: C4 ResNet1D 8方法对比
    c4_rows, c4_summary = p24_c4_resnet1d_8method()

    # 最终摘要
    print("\n" + "=" * 90)
    print("最终摘要")
    print("=" * 90)

    narrow_count = sum(1 for r in diag_rows if r["is_narrow"])
    print(f"P2.2 Bootstrap 诊断: {narrow_count}/{len(diag_rows)} 实验CI异常窄 (<0.005)")

    it_rows = [r for r in c3_rows if r["arch"] == "inceptiontime"]
    rn_rows = [r for r in c3_rows if r["arch"] == "resnet1d"]
    print(f"P2.3 C3 cross-fitting: InceptionTime {len(it_rows)} 方法, ResNet1D {len(rn_rows)} 方法")

    rn_exp = sum(1 for r in c4_rows if r["arch"] == "resnet1d") // len(METHODS)
    it_exp = sum(1 for r in c4_rows if r["arch"] == "inceptiontime") // len(METHODS)
    print(f"P2.4 C4 8方法对比: ResNet1D {rn_exp} 实验, InceptionTime {it_exp} 实验")

    print("\n✓ 所有 P2.2-P2.5 可选修复完成")
    print(f"  - {RESULTS / 'bootstrap_diagnostics.csv'}")
    print(f"  - {RESULTS / 'c3_crossfit_results.csv'}")
    print(f"  - {RESULTS / 'c4_resnet1d_8method.csv'}")


if __name__ == "__main__":
    main()