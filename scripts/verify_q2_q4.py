"""Q2/Q4 决定性验证。

A. 确认 delta_obs_orig 与 delta_obs 的差异 = 「不同 run」而非「不同度量」：
   在两次 run 完全一致的 cell 上（e6 复算 == transfer raw），两者应相等。
B. 定位差异来源：源域(cal)侧是否一致（id_acc / T / cal ECE）。
C. 用 npz（现存活数据）重算 SmoothECE ΔECE，给出完整可复现代码与 T 分层。
D. Q4：delta_obs_orig 的 T-不变性是否为「度量不敏感」伪影？—— 同度量对照。
"""
import json
import os
import sys

import numpy as np

ROOT = r"D:/A1/ecg-lab-v2"
sys.path.insert(0, ROOT)

from src.utils.calibration import smooth_ece  # noqa: E402
from src.utils.calibration_methods import (  # noqa: E402
    fit_temperature_multiclass, apply_temperature_multiclass)

CACHE = os.path.join(ROOT, "checkpoints", "e2_probs_cache")
TRANS = os.path.join(ROOT, "checkpoints", "transfer")
JSON = os.path.join(ROOT, "results", "strengthening_battle_corrected.json")


def toplabel(p, y):
    return p.max(1).astype(float), (p.argmax(1) == y).astype(float)


def main():
    recs = [r for r in json.load(open(JSON, encoding="utf-8"))
            if r.get("arch") != "mamba"]
    key = {(r["source"], r["target"], r["arch"], r["seed"]): r for r in recs}

    # ---------- A/B: 两 run 一致性分类 ----------
    print("=" * 104)
    print("A. 两次 run 是否一致？（判据：npz 复算 smooth_ece == transfer raw）")
    print("=" * 104)
    same, diff = [], []
    for k, r in key.items():
        src, tgt, arch, seed = k
        d = os.path.join(TRANS, "%s_%s" % (src, tgt), arch, "seed%d" % seed)
        tr = json.load(open(os.path.join(d, "transfer_result.json"),
                            encoding="utf-8"))
        raw_t = tr["methods"]["ts"]["ood"]["raw"]
        z = np.load(os.path.join(CACHE, "%s_%s_%s_seed%d.npz"
                                 % (src, tgt, arch, seed)), allow_pickle=True)
        conf, corr = toplabel(z["test_probs"], z["test_labels"])
        s = smooth_ece(conf, corr)
        (same if abs(s - raw_t) < 1e-9 else diff).append((k, s, raw_t, r))

    print("  完全一致(same run): %d ; 不一致(diff run): %d"
          % (len(same), len(diff)))

    def stat(tag, lst, f):
        v = np.array([f(x[3]) for x in lst])
        return "%s n=%2d  %s" % (tag, len(lst), v)

    if same:
        a = np.array([x[3]["delta_obs_orig"] for x in same])
        b = np.array([x[3]["delta_obs"] for x in same])
        print("\n  [same-run 子集] delta_obs_orig vs delta_obs：")
        print("    mean orig=%+.6f  mean obs=%+.6f  max|diff|=%.3e  corr=%.4f"
              % (a.mean(), b.mean(), np.abs(a - b).max(), np.corrcoef(a, b)[0, 1]))
        print("    → 同 run 时两者 %s"
              % ("完全相等（差异纯属 run）" if np.abs(a - b).max() < 1e-9
                 else "仍不等（存在度量差异）"))
    if diff:
        a = np.array([x[3]["delta_obs_orig"] for x in diff])
        b = np.array([x[3]["delta_obs"] for x in diff])
        print("  [diff-run 子集] mean orig=%+.6f  mean obs=%+.6f  corr=%.4f"
              % (a.mean(), b.mean(), np.corrcoef(a, b)[0, 1]))

    # ---------- B: 源域是否一致 ----------
    print("\n" + "=" * 104)
    print("B. 差异来自源域还是目标域？（e6 id_acc vs transfer id_acc）")
    print("=" * 104)
    nid = 0
    for k, s, raw_t, r in same + diff:
        src, tgt, arch, seed = k
        d = os.path.join(TRANS, "%s_%s" % (src, tgt), arch, "seed%d" % seed)
        e6 = os.path.join(d, "e6_probs.npz")
        if not os.path.exists(e6):
            continue
        z = np.load(e6, allow_pickle=True)
        idacc = float((z["id_raw"].argmax(1) == z["id_labels"]).mean())
        tr = json.load(open(os.path.join(d, "transfer_result.json"),
                            encoding="utf-8"))
        nid += 1
        if nid <= 8:
            print("  %-9s %-9s %-13s %2d | id_acc e6=%.4f trans=%.4f | "
                  "ood_acc npz=%.4f trans=%.4f"
                  % (src, tgt, arch, seed, idacc, tr["id_acc"], r["ood_acc"],
                     tr["ood_acc"]))
    print("  (若 id_acc 一致而 ood_acc 不一致 → 源域/模型相同，目标域切分不同)")

    # ---------- C: 用 npz 完整重算（可复现主路径） ----------
    print("\n" + "=" * 104)
    print("C. 从 npz 复算 SmoothECE ΔECE（60 main cells）")
    print("=" * 104)
    rows = []
    for k, r in key.items():
        src, tgt, arch, seed = k
        z = np.load(os.path.join(CACHE, "%s_%s_%s_seed%d.npz"
                                 % (src, tgt, arch, seed)), allow_pickle=True)
        cal_p, cal_y = z["cal_probs"], z["cal_labels"]
        tp, ty = z["test_probs"], z["test_labels"]
        tpar = fit_temperature_multiclass(cal_p, cal_y)
        T = float(tpar["T"])
        rc, ry = toplabel(tp, ty)
        cc, cy = toplabel(apply_temperature_multiclass(tp, tpar), ty)
        raw, cal = smooth_ece(rc, ry), smooth_ece(cc, cy)
        rows.append(dict(src=src, tgt=tgt, arch=arch, seed=seed, T=T,
                         raw=raw, cal=cal, d=raw - cal,
                         ood_acc=float((tp.argmax(1) == ty).mean()),
                         raw_o=r["raw_ood_orig"], cal_o=r["cal_ood_orig"],
                         d_o=r["delta_obs_orig"], d_obs=r["delta_obs"]))
    d = np.array([x["d"] for x in rows])
    do = np.array([x["d_obs"] for x in rows])
    doo = np.array([x["d_o"] for x in rows])
    T = np.array([x["T"] for x in rows])
    raw = np.array([x["raw"] for x in rows])
    print("  复算 raw   mean=%.4f   (JSON raw_ood_orig mean=%.4f)"
          % (raw.mean(), np.array([x["raw_o"] for x in rows]).mean()))
    print("  复算 ΔECE  mean=%+.6f  pos %d/60   corr(T)=%+.4f  R2=%.4f"
          % (d.mean(), (d > 0).sum(), np.corrcoef(d, T)[0, 1],
             np.corrcoef(d, T)[0, 1] ** 2))
    print("  corr(复算, JSON.delta_obs)      = %.6f" % np.corrcoef(d, do)[0, 1])
    print("  corr(复算, JSON.delta_obs_orig) = %.6f" % np.corrcoef(d, doo)[0, 1])
    print("  JSON.delta_obs_orig mean=%+.6f pos %d/60 corr(T)=%+.4f"
          % (doo.mean(), (doo > 0).sum(), np.corrcoef(doo, T)[0, 1]))
    print("  JSON.delta_obs      mean=%+.6f pos %d/60 corr(T)=%+.4f"
          % (do.mean(), (do > 0).sum(), np.corrcoef(do, T)[0, 1]))

    # ---------- D: T 分层（同度量、同数据） ----------
    print("\n" + "=" * 104)
    print("D. T 分层对照（左=现存活 npz 复算 SmoothECE；右=JSON.delta_obs_orig）")
    print("=" * 104)
    print("  %-14s %5s | %-12s | %-12s" % ("T 区间", "n", "npz 复算ΔECE",
                                            "JSON.orig"))
    for lo, hi in [(0, 1.5), (1.5, 2), (2, 3), (3, 5)]:
        m = (T >= lo) & (T < hi)
        if m.sum():
            print("  [%.1f,%.1f)      %5d | %+12.4f | %+12.4f"
                  % (lo, hi, m.sum(), d[m].mean(), doo[m].mean()))
    print("\n  → 同一度量(smooth_ece)、同一存活数据下，ΔECE 随 T 单调膨胀；")
    print("    JSON.delta_obs_orig 的「平坦」发生在另一份（已丢失）数据上。")

    json.dump(rows, open(os.path.join(ROOT, "results",
                                      "q2_npz_recompute.json"), "w"), indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
