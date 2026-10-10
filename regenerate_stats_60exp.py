"""
基于60个实验重新生成统计补齐结果：
1. meta_analytic_pooled.csv - meta-analytic合并检验
2. bh_fdr_correction.csv - BH-FDR校正
"""
import json
import csv
import math
import os
from pathlib import Path
from collections import defaultdict

WORK_DIR = Path(r"D:\A1\ecg-lab-v2")
RESULTS_DIR = WORK_DIR / "results"

ALL_PAIRS = ["chapman_cpsc", "chapman_ptbxl", "cpsc_chapman", "cpsc_ptbxl",
             "ptbxl_chapman", "ptbxl_cpsc"]
ARCHS = ["inceptiontime", "resnet1d"]
ALL_SEEDS = [42, 43, 44, 45, 46]


def load_all_results():
    """加载所有60个实验的TS方法结果"""
    results = []
    for pair in ALL_PAIRS:
        for arch in ARCHS:
            for seed in ALL_SEEDS:
                json_path = (WORK_DIR / "checkpoints" / "transfer" / pair / arch /
                             f"seed{seed}" / "transfer_result.json")
                if json_path.exists():
                    with open(json_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if "ts" in data["methods"]:
                        ts = data["methods"]["ts"]
                        if "ood" in ts:
                            results.append({
                                "pair": pair,
                                "arch": arch,
                                "seed": seed,
                                "ood_delta": ts["ood"]["deltaECE"],
                                "ood_ci_lo": ts["ood"]["ci"][0],
                                "ood_ci_hi": ts["ood"]["ci"][1],
                            })
    return results


def compute_meta_analytic(results):
    """计算meta-analytic合并效应（固定效应模型，逆方差加权）"""
    # 按架构分层
    strata_results = {
        "InceptionTime": [r for r in results if r["arch"] == "inceptiontime"],
        "ResNet1D": [r for r in results if r["arch"] == "resnet1d"],
        "CrossArchitecture": results,
    }

    rows = []
    for strata, items in strata_results.items():
        n = len(items)
        if n == 0:
            continue
        # 每个实验的效应量 y_i = ΔECE_OOD
        # 方差 v_i = ((CI_hi - CI_lo) / (2 * 1.96))^2
        # 权重 w_i = 1 / v_i
        # 合并效应 pooled = sum(w_i * y_i) / sum(w_i)
        # 合并SE = sqrt(1 / sum(w_i))
        y_list = []
        w_list = []
        for r in items:
            y = r["ood_delta"]
            ci_width = r["ood_ci_hi"] - r["ood_ci_lo"]
            se_i = ci_width / (2 * 1.96) if ci_width > 0 else 0.001
            v_i = se_i ** 2
            w_i = 1.0 / v_i if v_i > 0 else 0.0
            y_list.append(y)
            w_list.append(w_i)
        sum_w = sum(w_list)
        sum_wy = sum(w_list[i] * y_list[i] for i in range(n))
        pooled_effect = sum_wy / sum_w
        pooled_se = math.sqrt(1.0 / sum_w)
        ci_lo = pooled_effect - 1.96 * pooled_se
        ci_hi = pooled_effect + 1.96 * pooled_se
        z_stat = pooled_effect / pooled_se if pooled_se > 0 else 0
        # 双侧p值
        p_value = math.erfc(abs(z_stat) / math.sqrt(2))
        rows.append({
            "strata": strata,
            "n_experiments": n,
            "pooled_effect": pooled_effect,
            "pooled_se": pooled_se,
            "ci_lo": ci_lo,
            "ci_hi": ci_hi,
            "z_statistic": z_stat,
            "p_value": p_value,
        })
    return rows


def compute_bh_fdr(results):
    """计算BH-FDR校正后的支持率"""
    n = len(results)
    # 单侧p值：H0: ΔECE <= 0 vs H1: ΔECE > 0
    # p_one_sided = P(Z > z) where z = ΔECE / SE
    p_values = []
    for r in results:
        y = r["ood_delta"]
        ci_width = r["ood_ci_hi"] - r["ood_ci_lo"]
        se = ci_width / (2 * 1.96) if ci_width > 0 else 0.001
        z = y / se if se > 0 else 0
        # 单侧p值
        p = 0.5 * math.erfc(z / math.sqrt(2))
        p_values.append(p)

    # 未校正
    n_sig_uncorrected = sum(1 for p in p_values if p < 0.05)

    # BH-FDR (q=0.05)
    sorted_idx = sorted(range(n), key=lambda i: p_values[i])
    sorted_p = [p_values[i] for i in sorted_idx]
    # 找最大i使得 p_(i) <= (i/n) * q
    max_i = 0
    for i in range(1, n + 1):
        threshold = (i / n) * 0.05
        if sorted_p[i - 1] <= threshold:
            max_i = i
    n_sig_bh = max_i

    # Bonferroni
    bonferroni_alpha = 0.05 / n
    n_sig_bonferroni = sum(1 for p in p_values if p < bonferroni_alpha)

    rows = [
        {
            "correction_method": "None (uncorrected)",
            "n_total": n,
            "n_significant": n_sig_uncorrected,
            "support_rate": f"{n_sig_uncorrected}/{n}",
            "threshold_description": "p_one_sided < 0.05",
            "p_value_type": "one-sided (ΔECE>0)",
        },
        {
            "correction_method": "BH-FDR (q=0.05)",
            "n_total": n,
            "n_significant": n_sig_bh,
            "support_rate": f"{n_sig_bh}/{n}",
            "threshold_description": "p_i <= (i/n) * q, find max i",
            "p_value_type": "one-sided (ΔECE>0)",
        },
        {
            "correction_method": "Bonferroni",
            "n_total": n,
            "n_significant": n_sig_bonferroni,
            "support_rate": f"{n_sig_bonferroni}/{n}",
            "threshold_description": f"p_one_sided < {bonferroni_alpha:.6e}",
            "p_value_type": "one-sided (ΔECE>0)",
        },
    ]
    return rows


def main():
    print("=" * 70)
    print("基于60个实验重新生成统计补齐结果")
    print("=" * 70)

    results = load_all_results()
    print(f"\n[1] 加载 {len(results)} 个实验")
    by_arch = defaultdict(int)
    for r in results:
        by_arch[r["arch"]] += 1
    for arch, cnt in by_arch.items():
        print(f"    {arch}: {cnt}")

    # Meta-analytic
    meta_rows = compute_meta_analytic(results)
    meta_path = RESULTS_DIR / "meta_analytic_pooled.csv"
    with open(meta_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "strata", "n_experiments", "pooled_effect", "pooled_se",
            "ci_lo", "ci_hi", "z_statistic", "p_value"
        ])
        writer.writeheader()
        for row in meta_rows:
            writer.writerow({
                "strata": row["strata"],
                "n_experiments": row["n_experiments"],
                "pooled_effect": f"{row['pooled_effect']:.6f}",
                "pooled_se": f"{row['pooled_se']:.6f}",
                "ci_lo": f"{row['ci_lo']:.6f}",
                "ci_hi": f"{row['ci_hi']:.6f}",
                "z_statistic": f"{row['z_statistic']:.4f}",
                "p_value": f"{row['p_value']:.6e}",
            })
    print(f"\n[2] Meta-analytic结果保存到: {meta_path}")
    for row in meta_rows:
        print(f"    {row['strata']}: n={row['n_experiments']}, "
              f"effect={row['pooled_effect']:.6f}, "
              f"CI=[{row['ci_lo']:.6f}, {row['ci_hi']:.6f}], "
              f"z={row['z_statistic']:.2f}, p={row['p_value']:.2e}")

    # BH-FDR
    bh_rows = compute_bh_fdr(results)
    bh_path = RESULTS_DIR / "bh_fdr_correction.csv"
    with open(bh_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "correction_method", "n_total", "n_significant",
            "support_rate", "threshold_description", "p_value_type"
        ])
        writer.writeheader()
        for row in bh_rows:
            writer.writerow(row)
    print(f"\n[3] BH-FDR校正结果保存到: {bh_path}")
    for row in bh_rows:
        print(f"    {row['correction_method']}: {row['support_rate']}")

    print(f"\n[4] 完成！")


if __name__ == "__main__":
    main()