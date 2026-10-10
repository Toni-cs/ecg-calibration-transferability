"""三步链步骤 3：部署查找表 + DCA（协议§3:52-54，§9:152-154，§9:182-183）。

步骤 2 失败分支 → 降级两步链。两步链部署判据：直接用 L2 结果生成查找表。

修复（对抗审查 R3/R4/R5）：
- 按 shift 档 8 类汇总（非 shift_type 3 类，避免聚合假象）
- DCA 用预测变量阈值扫描（非 nb_ts≡nb_treat_all）
- 留出集：每移位类型留 1 档（downsample 留 fs125, lead_drop 留 leads2, gain 留 gain2.0）

§9 补齐（协议§9:182-183）：
- 表4：敏感度/特异度（判据预测"可安全部署"的性能）
- 表5：NORM/STTC 分层 DCA（若 l2_shift_results.json 含分层信息则分层报告，否则全样本+注明）
- 表6：安全判据汇总（安全 = ΔECE < -0.01 且 校准后 ECE < 0.05）
- 表7：平凡策略对照（always-TS / always-buy-n-labels）
"""
from __future__ import annotations
import csv
import json
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent.parent

PAIRS = [
    "ptbxl_chapman", "ptbxl_cpsc",
    "chapman_ptbxl", "chapman_cpsc",
    "cpsc_ptbxl", "cpsc_chapman",
]
SEEDS = [42, 43, 44, 45, 46]
ARCH = "inceptiontime"
METHODS = ["ts", "platt", "isotonic", "vector", "matrix", "dirichlet", "em_prior", "bbse_prior"]
SHIFTS = ["fs250", "fs125", "leads6", "leads3", "leads2", "leads1",
          "noise24", "noise12", "noise6", "noise0", "noise-6",
          "gain0.5", "gain2.0"]
HOLDOUT = {"downsample": "fs125", "lead_drop": "leads2", "noise": "noise0", "gain": "gain2.0"}
SHIFT_TYPES = {
    "fs250": "downsample", "fs125": "downsample",
    "leads6": "lead_drop", "leads3": "lead_drop", "leads2": "lead_drop", "leads1": "lead_drop",
    "noise24": "noise", "noise12": "noise", "noise6": "noise", "noise0": "noise", "noise-6": "noise",
    "gain0.5": "gain", "gain2.0": "gain",
}

# §9 安全判据阈值
SAFE_DELTA_ECE = -0.01   # ΔECE < -0.01 → 校准有益 > 1%
SAFE_CAL_ECE = 0.05      # 校准后 ECE < 0.05


def load_l2_data():
    """加载 L2 移位结果。

    返回 dict: (pair, seed, shift, method) -> {raw_ece, delta_ece, cal_ece, strata?}
    其中 strata 为可选的 {stratum_name: {raw_ece, delta_ece, cal_ece}} 分层信息。
    """
    data = {}
    for pair in PAIRS:
        for seed in SEEDS:
            p = ROOT / "checkpoints/transfer" / pair / ARCH / f"seed{seed}" / "l2_shift_results.json"
            if not p.exists():
                continue
            d = json.loads(p.read_text(encoding="utf-8"))[f"seed{seed}"]
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
                    entry = {
                        "raw_ece": d[shift]["raw_ece"],
                        "delta_ece": d[shift][m]["delta_ece"],
                        "cal_ece": d[shift][m].get("cal_ece", d[shift]["raw_ece"] + d[shift][m]["delta_ece"]),
                    }
                    # 探测分层信息（NORM/STTC）
                    if "strata" in d[shift]:
                        entry["strata"] = d[shift]["strata"]
                    data[(pair, seed, shift, m)] = entry
    return data


def bootstrap_ci(vals, n_boot=2000, seed=42):
    if len(vals) < 2:
        return float(np.mean(vals)) if len(vals) else 0.0, 0.0, 0.0
    rng = np.random.RandomState(seed)
    means = [np.mean(rng.choice(vals, len(vals))) for _ in range(n_boot)]
    return float(np.mean(vals)), float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def sens_spec_at_threshold(raw_ece_arr, beneficial_arr, threshold):
    """计算 raw_ece > threshold 预测'校准有益'的敏感度/特异度。

    有益 (positive) = ΔECE < -0.01
    预测 positive = raw_ece > threshold
    敏感度 = TP/(TP+FN) = P(pred+ | true+)
    特异度 = TN/(TN+FP) = P(pred- | true-)
    """
    pred_pos = raw_ece_arr > threshold
    true_pos = beneficial_arr
    tp = int((pred_pos & true_pos).sum())
    fn = int((~pred_pos & true_pos).sum())
    tn = int((~pred_pos & ~true_pos).sum())
    fp = int((pred_pos & ~true_pos).sum())
    sens = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    spec = tn / (tn + fp) if (tn + fp) > 0 else 0.0
    return sens, spec, tp, fp, tn, fn


def net_benefit(tp, fp, n, threshold_prob=0.3):
    """决策曲线净收益：NB = TP/N - FP/N * (t/(1-t))。"""
    t = threshold_prob
    return tp / n - fp / n * t / (1 - t)


def main():
    data = load_l2_data()
    print(f"加载 {len(data)} 个数据点\n")

    # ============================================================
    # 表1: 部署查找表
    # ============================================================
    print("=" * 100)
    print("表1: 部署查找表（shift 档 × method → ΔECE 均值 [95% CI]）")
    print("=" * 100)
    header = f"{'Shift':<10}" + "".join(f"{m:>11}" for m in METHODS) + f"  {'best':>8}"
    print(header)
    lookup = {}
    for shift in SHIFTS:
        row = f"{shift:<10}"
        best_method, best_mean = None, 0
        for m in METHODS:
            vals = [v["delta_ece"] for (p, s, sh, mm), v in data.items()
                    if mm == m and sh == shift]
            mean, ci_lo, ci_hi = bootstrap_ci(vals) if vals else (0, 0, 0)
            lookup[(shift, m)] = (mean, ci_lo, ci_hi)
            row += f" {mean:>+.4f}"
            if best_method is None or mean < best_mean:
                best_method, best_mean = m, mean
        row += f"  {best_method:>8}"
        print(row)

    # ============================================================
    # 表2: DCA（全样本决策曲线）
    # ============================================================
    print("\n" + "=" * 100)
    print("表2: DCA（Decision Curve Analysis）— 用 raw_ece 阈值预测'校准有益'")
    print("=" * 100)
    print(f"'有益' = ΔECE < {SAFE_DELTA_ECE}（改善 > 1%）。扫 raw_ece 阈值：若 raw_ece > threshold → 预测有益")
    print()
    all_raw = np.array([v["raw_ece"] for v in data.values()])
    all_ben = np.array([v["delta_ece"] < SAFE_DELTA_ECE for v in data.values()])
    n = len(all_raw)
    n_ben = int(all_ben.sum())
    print(f"总样本: {n}, 有益: {n_ben} ({n_ben/n*100:.1f}%)")
    print()
    print(f"{'Threshold':>10} {'TP':>6} {'FP':>6} {'NB_pred':>10} {'NB_treat_all':>12} {'NB_treat_none':>14}")
    dca_rows = []
    for t in np.percentile(all_raw, [10, 25, 50, 75, 90]):
        pred = all_raw > t
        tp = int((pred & all_ben).sum())
        fp = int((pred & ~all_ben).sum())
        nb_pred = net_benefit(tp, fp, n, 0.3)
        nb_all = net_benefit(n_ben, n - n_ben, n, 0.3)
        print(f"{t:>10.4f} {tp:>6} {fp:>6} {nb_pred:>10.4f} {nb_all:>12.4f} {0:>14.4f}")
        dca_rows.append({"threshold": float(t), "tp": tp, "fp": fp,
                         "nb_pred": nb_pred, "nb_treat_all": nb_all})

    # ============================================================
    # 表3: 留出集验证
    # ============================================================
    print("\n" + "=" * 100)
    print("表3: 留出集验证（每移位类型留 1 档，在留出集上计算判据性能）")
    print("=" * 100)
    holdout_rows = []
    for st, holdout_shift in HOLDOUT.items():
        train_shifts = [s for s in SHIFTS if SHIFT_TYPES[s] == st and s != holdout_shift]
        print(f"\n  {st}: 训练档={train_shifts}, 留出档={holdout_shift}")
        for m in METHODS:
            train_vals = [v["delta_ece"] for (p, s, sh, mm), v in data.items()
                          if mm == m and sh in train_shifts]
            holdout_vals = [v["delta_ece"] for (p, s, sh, mm), v in data.items()
                            if mm == m and sh == holdout_shift]
            if not train_vals or not holdout_vals:
                continue
            train_mean = np.mean(train_vals)
            holdout_mean = np.mean(holdout_vals)
            gap = holdout_mean - train_mean
            print(f"    {m:<10}: train={train_mean:+.4f}  holdout={holdout_mean:+.4f}  "
                  f"gap={gap:+.4f}")
            holdout_rows.append({"shift_type": st, "method": m,
                                 "train_mean": float(train_mean),
                                 "holdout_mean": float(holdout_mean),
                                 "gap": float(gap)})

    # ============================================================
    # 表4: 敏感度/特异度（§9:182-183）
    # ============================================================
    print("\n" + "=" * 100)
    print("表4: 敏感度/特异度（判据'raw_ece > threshold → 预测可安全部署'的性能）")
    print("=" * 100)
    print(f"真实标签: '可安全部署' = ΔECE < {SAFE_DELTA_ECE}（校准有益 > 1%）")
    print(f"预测标签: raw_ece > threshold")
    print()
    print(f"{'Threshold':>10} {'Sens':>8} {'Spec':>8} {'TP':>6} {'FP':>6} {'TN':>6} {'FN':>6} {'Youden':>8}")
    sens_spec_rows = []
    best_youden = -1.0
    best_threshold = None
    for t in np.percentile(all_raw, [5, 10, 15, 20, 25, 30, 40, 50, 60, 70, 75, 80, 85, 90, 95]):
        sens, spec, tp, fp, tn, fn = sens_spec_at_threshold(all_raw, all_ben, t)
        youden = sens + spec - 1
        print(f"{t:>10.4f} {sens:>8.4f} {spec:>8.4f} {tp:>6} {fp:>6} {tn:>6} {fn:>6} {youden:>8.4f}")
        sens_spec_rows.append({"threshold": float(t), "sensitivity": float(sens),
                               "specificity": float(spec), "tp": tp, "fp": fp,
                               "tn": tn, "fn": fn, "youden": float(youden)})
        if youden > best_youden:
            best_youden = youden
            best_threshold = float(t)
    print(f"\n  最优阈值（Youden 指数最大）: raw_ece > {best_threshold:.4f}, Youden = {best_youden:.4f}")

    # ============================================================
    # 表5: NORM/STTC 分层 DCA（§9:182-183）
    # ============================================================
    print("\n" + "=" * 100)
    print("表5: NORM/STTC 分层 DCA（按诊断 superclass 分层报告决策曲线）")
    print("=" * 100)
    # 检测是否存在分层信息
    has_strata = any("strata" in v for v in data.values())
    stratified_dca_rows = []
    if has_strata:
        # 按 stratum 分层做 DCA
        strata_names = set()
        for v in data.values():
            if "strata" in v:
                strata_names.update(v["strata"].keys())
        for stratum in sorted(strata_names):
            print(f"\n  分层: {stratum}")
            s_raw = []
            s_ben = []
            for v in data.values():
                if "strata" in v and stratum in v["strata"]:
                    sv = v["strata"][stratum]
                    s_raw.append(sv["raw_ece"])
                    s_ben.append(sv["delta_ece"] < SAFE_DELTA_ECE)
            s_raw = np.array(s_raw)
            s_ben = np.array(s_ben)
            n_s = len(s_raw)
            n_ben_s = int(s_ben.sum())
            print(f"    样本: {n_s}, 有益: {n_ben_s} ({n_ben_s/n_s*100:.1f}%)")
            print(f"    {'Threshold':>10} {'TP':>6} {'FP':>6} {'NB_pred':>10} {'NB_treat_all':>12}")
            for t in np.percentile(s_raw, [25, 50, 75]):
                pred = s_raw > t
                tp = int((pred & s_ben).sum())
                fp = int((pred & ~s_ben).sum())
                nb_pred = net_benefit(tp, fp, n_s, 0.3)
                nb_all = net_benefit(n_ben_s, n_s - n_ben_s, n_s, 0.3)
                print(f"    {t:>10.4f} {tp:>6} {fp:>6} {nb_pred:>10.4f} {nb_all:>12.4f}")
                stratified_dca_rows.append({"stratum": stratum, "threshold": float(t),
                                            "n": n_s, "n_beneficial": n_ben_s,
                                            "tp": tp, "fp": fp,
                                            "nb_pred": nb_pred, "nb_treat_all": nb_all})
    else:
        print("\n  ⚠ l2_shift_results.json 中未包含 NORM/STTC 分层信息（eval_l2_shift.py 未按 superclass 分层评估）")
        print("  → 退化为全样本 DCA（与表2 相同），分层结果见补充材料（需重跑 eval_l2_shift.py 加分层）")
        print()
        print(f"  全样本回退: n={n}, n_beneficial={n_ben}")
        print(f"  {'Threshold':>10} {'TP':>6} {'FP':>6} {'NB_pred':>10} {'NB_treat_all':>12}")
        for t in np.percentile(all_raw, [25, 50, 75]):
            pred = all_raw > t
            tp = int((pred & all_ben).sum())
            fp = int((pred & ~all_ben).sum())
            nb_pred = net_benefit(tp, fp, n, 0.3)
            nb_all = net_benefit(n_ben, n - n_ben, n, 0.3)
            print(f"  {t:>10.4f} {tp:>6} {fp:>6} {nb_pred:>10.4f} {nb_all:>12.4f}")
            stratified_dca_rows.append({"stratum": "ALL_FALLBACK", "threshold": float(t),
                                        "n": n, "n_beneficial": n_ben,
                                        "tp": tp, "fp": fp,
                                        "nb_pred": nb_pred, "nb_treat_all": nb_all})

    # ============================================================
    # 表6: 安全判据汇总（§9:182-183）
    # ============================================================
    print("\n" + "=" * 100)
    print("表6: 安全判据汇总（安全 = ΔECE < -0.01 且 校准后 ECE < 0.05）")
    print("=" * 100)
    print(f"判据: safe = (delta_ece < {SAFE_DELTA_ECE}) AND (cal_ece < {SAFE_CAL_ECE})")
    print()
    safe_rows = []
    print(f"{'Method':<12} {'n_total':>8} {'n_safe':>8} {'n_ben_only':>12} {'n_cal_only':>12} {'safe_rate':>10}")
    for m in METHODS:
        m_entries = [v for (p, s, sh, mm), v in data.items() if mm == m]
        n_total = len(m_entries)
        n_safe = sum(1 for v in m_entries
                     if v["delta_ece"] < SAFE_DELTA_ECE and v["cal_ece"] < SAFE_CAL_ECE)
        n_ben_only = sum(1 for v in m_entries if v["delta_ece"] < SAFE_DELTA_ECE)
        n_cal_only = sum(1 for v in m_entries if v["cal_ece"] < SAFE_CAL_ECE)
        safe_rate = n_safe / n_total if n_total > 0 else 0.0
        print(f"{m:<12} {n_total:>8} {n_safe:>8} {n_ben_only:>12} {n_cal_only:>12} {safe_rate:>10.4f}")
        safe_rows.append({"method": m, "n_total": n_total, "n_safe": n_safe,
                          "n_beneficial_only": n_ben_only,
                          "n_calibrated_only": n_cal_only,
                          "safe_rate": float(safe_rate)})
    # 按 shift 汇总安全率
    print()
    print(f"{'Shift':<10} {'n_total':>8} {'n_safe':>8} {'safe_rate':>10}")
    for shift in SHIFTS:
        s_entries = [v for (p, s, sh, mm), v in data.items() if sh == shift]
        n_total = len(s_entries)
        n_safe = sum(1 for v in s_entries
                     if v["delta_ece"] < SAFE_DELTA_ECE and v["cal_ece"] < SAFE_CAL_ECE)
        safe_rate = n_safe / n_total if n_total > 0 else 0.0
        print(f"{shift:<10} {n_total:>8} {n_safe:>8} {safe_rate:>10.4f}")
        safe_rows.append({"shift": shift, "n_total": n_total, "n_safe": n_safe,
                          "safe_rate": float(safe_rate)})

    # ============================================================
    # 表7: 平凡策略对照（§9:182-183）
    # ============================================================
    print("\n" + "=" * 100)
    print("表7: 平凡策略对照（always-TS / always-buy-n-labels vs 查找表策略）")
    print("=" * 100)
    # always-TS: 总是应用 TS 的净收益（用 ΔECE 度量，越负越好）
    ts_deltas = [v["delta_ece"] for (p, s, sh, mm), v in data.items() if mm == "ts"]
    # always-buy-n-labels: 假设购买标注后可重新训练，ECE 降至 0.02（理想值），净收益 = 0.02 - raw_ece
    buy_n_deltas = [0.02 - v["raw_ece"] for v in data.values()]
    # 查找表策略: 每 shift 选 best method 的 ΔECE
    lookup_deltas = []
    for (p, s, sh, mm), v in data.items():
        best_m = min(METHODS, key=lambda m: lookup.get((sh, m), (0, 0, 0))[0])
        if mm == best_m:
            lookup_deltas.append(v["delta_ece"])
    # 不校准策略: ΔECE = 0
    none_deltas = [0.0] * len(data)

    def _stats(vals):
        vals = np.array(vals)
        return float(np.mean(vals)), float(np.std(vals)), float(np.median(vals))

    strategies = {
        "always-none": none_deltas,
        "always-TS": ts_deltas,
        "always-buy-n-labels": buy_n_deltas,
        "lookup-table": lookup_deltas,
    }
    print(f"{'Strategy':<22} {'mean ΔECE':>12} {'std':>10} {'median':>10} {'n':>8}")
    baseline_rows = []
    for name, vals in strategies.items():
        mean, std, med = _stats(vals)
        print(f"{name:<22} {mean:>+12.4f} {std:>10.4f} {med:>+10.4f} {len(vals):>8}")
        baseline_rows.append({"strategy": name, "mean_delta_ece": mean,
                              "std": std, "median": med, "n": len(vals)})
    print("\n  注: always-buy-n-labels 假设购买标注后重训达 ECE=0.02（理想下界）")
    print("       always-none 为不校准基线（ΔECE≡0）")

    # ============================================================
    # 保存结果
    # ============================================================
    # 1. 查找表 JSON
    out_json = ROOT / "checkpoints" / "deployment_lookup.json"
    out_json.write_text(json.dumps(
        {f"{sh}_{m}": {"mean": c[0], "ci_lo": c[1], "ci_hi": c[2]}
         for (sh, m), c in lookup.items()}, indent=2), encoding="utf-8")
    print(f"\n查找表已保存到 {out_json}")

    # 2. 综合指标 CSV
    out_csv = ROOT / "results" / "deployment_metrics.csv"
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(out_csv, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["# ECG-Lab §9 部署指标汇总"])
        w.writerow(["# 安全判据: delta_ece < -0.01 AND cal_ece < 0.05"])
        w.writerow(["# 数据点数", len(data)])
        w.writerow([])

        # 表1 查找表
        w.writerow(["## 表1 部署查找表 (shift x method -> delta_ece mean [ci_lo, ci_hi])"])
        w.writerow(["shift", "method", "mean", "ci_lo", "ci_hi"])
        for (sh, m), (mean, lo, hi) in sorted(lookup.items()):
            w.writerow([sh, m, f"{mean:.6f}", f"{lo:.6f}", f"{hi:.6f}"])
        w.writerow([])

        # 表2 DCA
        w.writerow(["## 表2 DCA (全样本)"])
        w.writerow(["threshold", "tp", "fp", "nb_pred", "nb_treat_all"])
        for r in dca_rows:
            w.writerow([f"{r['threshold']:.6f}", r["tp"], r["fp"],
                        f"{r['nb_pred']:.6f}", f"{r['nb_treat_all']:.6f}"])
        w.writerow([])

        # 表3 留出集
        w.writerow(["## 表3 留出集验证"])
        w.writerow(["shift_type", "method", "train_mean", "holdout_mean", "gap"])
        for r in holdout_rows:
            w.writerow([r["shift_type"], r["method"],
                        f"{r['train_mean']:.6f}", f"{r['holdout_mean']:.6f}", f"{r['gap']:.6f}"])
        w.writerow([])

        # 表4 敏感度/特异度
        w.writerow(["## 表4 敏感度/特异度 (raw_ece > threshold -> predict beneficial)"])
        w.writerow(["threshold", "sensitivity", "specificity", "tp", "fp", "tn", "fn", "youden"])
        for r in sens_spec_rows:
            w.writerow([f"{r['threshold']:.6f}", f"{r['sensitivity']:.6f}",
                        f"{r['specificity']:.6f}", r["tp"], r["fp"], r["tn"], r["fn"],
                        f"{r['youden']:.6f}"])
        w.writerow(["# 最优阈值", f"{best_threshold:.6f}", "Youden", f"{best_youden:.6f}"])
        w.writerow([])

        # 表5 分层 DCA
        w.writerow(["## 表5 NORM/STTC 分层 DCA"])
        w.writerow(["stratum", "threshold", "n", "n_beneficial", "tp", "fp", "nb_pred", "nb_treat_all"])
        for r in stratified_dca_rows:
            w.writerow([r["stratum"], f"{r['threshold']:.6f}", r["n"], r["n_beneficial"],
                        r["tp"], r["fp"], f"{r['nb_pred']:.6f}", f"{r['nb_treat_all']:.6f}"])
        w.writerow([])

        # 表6 安全判据
        w.writerow(["## 表6 安全判据汇总"])
        w.writerow(["category", "name", "n_total", "n_safe", "n_beneficial_only", "n_calibrated_only", "safe_rate"])
        for r in safe_rows:
            if "method" in r:
                w.writerow(["method", r["method"], r["n_total"], r["n_safe"],
                            r.get("n_beneficial_only", ""), r.get("n_calibrated_only", ""),
                            f"{r['safe_rate']:.6f}"])
            elif "shift" in r:
                w.writerow(["shift", r["shift"], r["n_total"], r["n_safe"],
                            "", "", f"{r['safe_rate']:.6f}"])
        w.writerow([])

        # 表7 平凡策略
        w.writerow(["## 表7 平凡策略对照"])
        w.writerow(["strategy", "mean_delta_ece", "std", "median", "n"])
        for r in baseline_rows:
            w.writerow([r["strategy"], f"{r['mean_delta_ece']:.6f}",
                        f"{r['std']:.6f}", f"{r['median']:.6f}", r["n"]])

    print(f"综合指标已保存到 {out_csv}")


if __name__ == "__main__":
    main()
