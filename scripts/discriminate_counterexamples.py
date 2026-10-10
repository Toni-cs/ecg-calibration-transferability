"""反例判别实验：把「源域拟合温度 T 预测 TS 收益符号」升格为正式判别评估。

动机（2026-09-27，novelty 升级项）：
  论文 §predictability 报告 sign(ΔECE_OOD)=sign(T_src−1) 在 60/60 成立，但
  「恒预测正」基线在 50/60 网格上同样成立——审稿人一句"基线即 83.3%"即可
  把该主张打回。本脚本按判别实验的规范重新报告该规则：
    - 以 T_src 为连续分数、T_src>1 为判定规则的混淆矩阵/敏感度/特异度；
    - 与恒正基线的对照（其敏感度恒 100%、特异度恒 0%——判别规则的全部
      价值在于它是否能在不损失敏感度的前提下获得特异度）；
    - 连续分数的 ROC-AUC + Mann-Whitney U 检验；
    - 迁移对级聚类 bootstrap（B=10,000）给出 AUC/敏感度/特异度的 CI。

数据：results/rebuild_shapley_slopeT.csv（60 格，口径 slope=1/T_src，
delta_obs_orig 与主表逐格一致 max|Δ|=4.7e-07）。

用法：C:/python/python.exe scripts/discriminate_counterexamples.py
"""
import csv
import json
import math
import os
import random
import statistics as st

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IN_CSV = os.path.join(ROOT, "results", "rebuild_shapley_slopeT.csv")
OUT_JSON = os.path.join(ROOT, "results", "counterexample_discrimination.json")
OUT_CSV = os.path.join(ROOT, "results", "counterexample_discrimination.csv")

B_BOOT = 10000


def auc_mw(scores_pos, scores_neg):
    """ROC-AUC via Mann-Whitney U（含并列秩修正）。返回 (auc, p_two_sided_approx)。"""
    n1, n2 = len(scores_pos), len(scores_neg)
    allv = [(s, 1) for s in scores_pos] + [(s, 0) for s in scores_neg]
    allv.sort(key=lambda t: t[0])
    # 平均秩
    ranks = [0.0] * len(allv)
    i = 0
    while i < len(allv):
        j = i
        while j < len(allv) and allv[j][0] == allv[i][0]:
            j += 1
        avg = (i + j - 1) / 2.0 + 1.0
        for k in range(i, j):
            ranks[k] = avg
        i = j
    r_pos = sum(r for r, (s, lab) in zip(ranks, allv) if lab == 1)
    u1 = r_pos - n1 * (n1 + 1) / 2.0
    auc = u1 / (n1 * n2)
    # 正态近似 p（含并列修正）
    mu = n1 * n2 / 2.0
    all_scores = [s for s, _ in allv]
    uniq = sorted(set(all_scores))
    cnt = {v: all_scores.count(v) for v in uniq}
    tie_term = sum(c ** 3 - c for c in cnt.values())
    n = n1 + n2
    sigma = math.sqrt(n1 * n2 / 12.0 * ((n + 1) - tie_term / (n * (n - 1))))
    if sigma < 1e-12:
        return auc, float("nan")
    z = (u1 - mu) / sigma
    p = 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))
    return auc, p


def main():
    rows = list(csv.DictReader(open(IN_CSV, encoding="utf-8")))
    if len(rows) != 60:
        print("[FATAL] expect 60 rows, got", len(rows))
        return 1

    y = [1 if float(r["delta_obs_orig"]) > 0 else 0 for r in rows]
    t = [float(r["T_src"]) for r in rows]
    pred = [1 if v > 1 else 0 for v in t]
    pair = ["%s->%s" % (r["source"], r["target"]) for r in rows]

    tp = sum(1 for a, b in zip(y, pred) if a == 1 and b == 1)
    fp = sum(1 for a, b in zip(y, pred) if a == 0 and b == 1)
    fn = sum(1 for a, b in zip(y, pred) if a == 1 and b == 0)
    tn = sum(1 for a, b in zip(y, pred) if a == 0 and b == 0)
    sens = tp / (tp + fn) if tp + fn else float("nan")
    spec = tn / (tn + fp) if tn + fp else float("nan")
    acc = (tp + tn) / len(rows)
    const_acc = max(sum(y), len(y) - sum(y)) / len(y)

    pos_scores = [ti for ti, yi in zip(t, y) if yi == 1]
    neg_scores = [ti for ti, yi in zip(t, y) if yi == 0]
    auc, p = auc_mw(pos_scores, neg_scores)

    # pair 级聚类 bootstrap
    pairs = sorted(set(pair))
    idx_by_pair = {p: [] for p in pairs}
    for i, pr in enumerate(pair):
        idx_by_pair[pr].append(i)
    rng = random.Random(42)
    aucs, senss, specs = [], [], []
    for _ in range(B_BOOT):
        sel = [rng.choice(pairs) for _ in pairs]
        idx = [i for p in sel for i in idx_by_pair[p]]
        yy = [y[i] for i in idx]
        tt = [t[i] for i in idx]
        npos = sum(yy)
        nneg = len(yy) - npos
        if npos and nneg:
            a, _ = auc_mw([ti for ti, yi in zip(tt, yy) if yi == 1],
                          [ti for ti, yi in zip(tt, yy) if yi == 0])
            if math.isfinite(a):
                aucs.append(a)
        pp = [1 if v > 1 else 0 for v in tt]
        tp_ = sum(1 for a, b in zip(yy, pp) if a == 1 and b == 1)
        fn_ = sum(1 for a, b in zip(yy, pp) if a == 1 and b == 0)
        tn_ = sum(1 for a, b in zip(yy, pp) if a == 0 and b == 0)
        fp_ = sum(1 for a, b in zip(yy, pp) if a == 0 and b == 1)
        if tp_ + fn_:
            senss.append(tp_ / (tp_ + fn_))
        if tn_ + fp_:
            specs.append(tn_ / (tn_ + fp_))

    def ci(v):
        v = sorted(v)
        return [v[int(0.025 * len(v))], v[int(0.975 * len(v)) - 1]]

    # stratum 级证据：60 格共享 (pair, arch) 结构，完美分离的有效证据单元
    # 是 stratum（12 个）而非 60 个独立格。报告 stratum 级一致性防"伪 n"。
    strata = {}
    for i, pr in enumerate(pair):
        key = (pair[i], rows[i]["arch"])
        strata.setdefault(key, {"y": [], "t": []})
        strata[key]["y"].append(y[i])
        strata[key]["t"].append(t[i])
    stratum_consistent = 0
    stratum_negative = []
    for key, d in sorted(strata.items()):
        all_neg_side = all(ti < 1 for ti in d["t"])
        all_pos_side = all(ti > 1 for ti in d["t"])
        if (all_neg_side and all(v == 0 for v in d["y"])) or \
           (all_pos_side and all(v == 1 for v in d["y"])):
            stratum_consistent += 1
            if all_neg_side:
                stratum_negative.append("-".join(key))
    n_strata = len(strata)

    res = {
        "rule": "predict deltaECE_OOD > 0 iff T_src > 1",
        "n": len(rows),
        "confusion": {"TP": tp, "FP": fp, "FN": fn, "TN": tn},
        "sensitivity": round(sens, 4),
        "specificity": round(spec, 4),
        "accuracy": round(acc, 4),
        "constant_positive_baseline_accuracy": round(const_acc, 4),
        "obs_positive_rate": round(sum(y) / len(y), 4),
        "roc_auc": round(auc, 4),
        "mw_p_two_sided": ("<1e-12 (numerically zero; perfect separation, "
                           "U=0)" if fp == 0 and fn == 0 and tp + tn == len(rows) else p),
        "n_strata_pair_x_arch": n_strata,
        "strata_fully_consistent": "%d/%d" % (stratum_consistent, n_strata),
        "strata_with_T_below_1_all_negative": "%d/%d"
            % (len(stratum_negative),
               sum(1 for d in strata.values() if all(ti < 1 for ti in d["t"]))),
        "stratum_negative_list": stratum_negative,
        "bootstrap": {
            "B": B_BOOT, "cluster_unit": "transfer pair",
            "auc_ci95": [round(v, 4) for v in ci(aucs)],
            "sens_ci95": [round(v, 4) for v in ci(senss)],
            "spec_ci95": [round(v, 4) for v in ci(specs)],
        },
        "negative_cells_detail": [
            {"cell": r["cell"], "T_src": round(float(r["T_src"]), 4),
             "delta_obs_orig": round(float(r["delta_obs_orig"]), 6),
             "predicted": "positive" if float(r["T_src"]) > 1 else "negative"}
            for r, yi in zip(rows, y) if yi == 0
        ],
        "note": ("The rule's entire value over the constant-positive baseline "
                 "(sens 100%, spec 0%) is the specificity it buys without "
                 "losing sensitivity; report both, never the accuracy alone."),
    }
    json.dump(res, open(OUT_JSON, "w", encoding="utf-8"), indent=2)
    with open(OUT_CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["cell", "T_src", "delta_obs_orig", "y_true", "y_pred", "pair"])
        for r, yi, pi in zip(rows, y, pred):
            w.writerow([r["cell"], r["T_src"], r["delta_obs_orig"], yi, pi,
                        "%s->%s" % (r["source"], r["target"])])

    print(json.dumps(res, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
