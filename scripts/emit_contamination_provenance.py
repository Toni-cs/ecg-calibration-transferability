"""生成 results/strengthening_battle_corrected.json 的字段级 provenance 边车。

背景：2026-09-09 的 SUBSPACE_CPSC 顺序改动（未重训模型）使 09-10 之后
重新生成的 npz 标签与 checkpoint 语义失配（MI<->CD 互换），
导致该 JSON 内部**混用两套标签编码**：

  - delta_obs_orig / raw_ood_orig / cal_ood_orig  -> OLD 编码（与论文终点一致）
  - delta_obs / T                                 -> NEW 编码（被污染）

本脚本逐字段判定其口径，并把判定结果写成机器可读边车，
使下游消费者无需读长文即可知道哪些字段不可用。

只读 JSON 与 npz，不修改二者。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.utils.calibration import (  # noqa: E402
    apply_temperature, fit_temperature, smooth_ece,
)

CACHE = ROOT / "checkpoints" / "e2_probs_cache"
RESULTS = ROOT / "results"
SRC_JSON = RESULTS / "strengthening_battle_corrected.json"
OUT_JSON = RESULTS / "strengthening_battle_corrected.PROVENANCE.json"

FIELDS = ["T", "delta_obs", "delta_pred", "delta_obs_orig",
          "raw_ood_orig", "cal_ood_orig"]


def swap13(y: np.ndarray) -> np.ndarray:
    out = y.copy()
    out[y == 1] = 3
    out[y == 3] = 1
    return out


def onehot(y: np.ndarray, k: int) -> np.ndarray:
    m = np.zeros((len(y), k), dtype=float)
    m[np.arange(len(y)), y] = 1.0
    return m


def parse_name(stem: str):
    p = stem.split("_")
    return p[0], p[1], "_".join(p[2:-1]), p[-1]


def npz_values(npz_path: Path, is_cpsc: bool):
    """按两套标签编码重算 T/raw/cal/delta。

    is_cpsc=False 时两套编码**相同**（非 CPSC 语料不涉及 MI<->CD 换位），
    必须显式跳过 swap13，否则会人为制造"可区分"记录。
    """
    d = np.load(npz_path)
    tp, ty = d["test_probs"].astype(float), d["test_labels"].astype(int)
    cp, cy = d["cal_probs"].astype(float), d["cal_labels"].astype(int)
    k = tp.shape[1]
    old_ty, old_cy = (swap13(ty), swap13(cy)) if is_cpsc else (ty, cy)
    out = {}
    for tag, yy, cc in (("old", old_ty, old_cy), ("new", ty, cy)):
        T = fit_temperature(cp, onehot(cc, k))
        ts = apply_temperature(tp, T)
        raw = smooth_ece(tp.max(1), (tp.argmax(1) == yy).astype(float))
        cal = smooth_ece(ts.max(1), (ts.argmax(1) == yy).astype(float))
        out[tag] = {"T": float(T), "raw": float(raw), "cal": float(cal),
                    "delta": float(raw - cal)}
    return out


def main() -> None:
    recs = json.loads(SRC_JSON.read_text(encoding="utf-8"))
    rows = []
    for r in recs:
        stem = f"{r['source']}_{r['target']}_{r['arch']}_seed{r['seed']}"
        p = CACHE / f"{stem}.npz"
        if not p.exists():
            continue
        nv = npz_values(p, is_cpsc=("cpsc" in (r["source"], r["target"])))
        rows.append({"stem": stem, "json": r, "npz": nv})

    print(f"匹配到 npz 的记录：{len(rows)} / {len(recs)}")

    # 逐字段判定口径：比较与 npz-old / npz-new 的一致性
    verdict = {}
    for f in FIELDS:
        m_old = m_new = n = 0
        n_disc = 0          # 两套编码**可区分**的记录数（含 CPSC 者）
        disc_old = disc_new = 0
        d_old_max = d_new_max = 0.0
        jv_list, a_old_list, a_new_list = [], [], []
        for row in rows:
            jv = row["json"].get(f)
            if jv is None:
                continue
            n += 1
            if f == "T":
                a_old, a_new = row["npz"]["old"]["T"], row["npz"]["new"]["T"]
            elif f in ("delta_obs", "delta_obs_orig"):
                a_old, a_new = row["npz"]["old"]["delta"], row["npz"]["new"]["delta"]
            elif f == "raw_ood_orig":
                a_old, a_new = row["npz"]["old"]["raw"], row["npz"]["new"]["raw"]
            elif f == "cal_ood_orig":
                a_old, a_new = row["npz"]["old"]["cal"], row["npz"]["new"]["cal"]
            else:  # delta_pred: 无 npz 对应量
                continue
            jv_list.append(jv)
            a_old_list.append(a_old)
            a_new_list.append(a_new)
            eo, en = abs(jv - a_old), abs(jv - a_new)
            d_old_max = max(d_old_max, eo)
            d_new_max = max(d_new_max, en)
            if eo < 1e-6:
                m_old += 1
            if en < 1e-6:
                m_new += 1
            # 只在"两套编码给出不同值"的记录上判定口径，才具判别力
            if abs(a_old - a_new) > 1e-9:
                n_disc += 1
                if eo < 1e-6:
                    disc_old += 1
                if en < 1e-6:
                    disc_new += 1
        if f == "delta_pred":
            verdict[f] = {
                "caliber": "UNKNOWN",
                "reason": "无 npz 对应量；全仓 grep 无 .py 来源，不可从仓库复现",
                "usable": False,
            }
            continue

        def _corr(a, b):
            a, b = np.asarray(a, float), np.asarray(b, float)
            if len(a) < 2 or a.std() == 0 or b.std() == 0:
                return None
            return float(np.corrcoef(a, b)[0, 1])

        corr_old = _corr(jv_list, a_old_list)
        corr_new = _corr(jv_list, a_new_list)

        # 口径判定：用**可区分记录**上的逐位命中率。
        # （非 CPSC 的 20 个 cell 两套编码完全相同，对判定无信息量。）
        if n_disc and disc_old == n_disc:
            caliber = "OLD(论文口径, 可区分记录逐位命中)"
            usable = True
        elif n_disc and disc_new == n_disc:
            caliber = "NEW(污染, 可区分记录逐位命中)"
            usable = False
        elif n_disc and disc_old / n_disc >= 0.95:
            caliber = f"OLD(论文口径, 可区分记录命中 {disc_old}/{n_disc})"
            usable = True
        elif n_disc and disc_new / n_disc >= 0.95:
            caliber = f"NEW(污染, 可区分记录命中 {disc_new}/{n_disc})"
            usable = False
        elif n_disc == 0:
            caliber = "无判别信息(两套编码同值)"
            usable = None
        elif corr_old is not None and corr_new is not None and corr_old > corr_new:
            caliber = f"OLD-倾向(近似, 可区分记录仅 {disc_old}/{n_disc} 逐位命中)"
            usable = False
        elif corr_new is not None and corr_old is not None:
            caliber = f"NEW-倾向(近似, 可区分记录仅 {disc_new}/{n_disc} 逐位命中)"
            usable = False
        else:
            caliber = "AMBIGUOUS"
            usable = False
        verdict[f] = {
            "caliber": caliber,
            "usable": usable,
            "n_records": n,
            "n_distinguishable": n_disc,
            "match_old": m_old,
            "match_new": m_new,
            "distinguishable_match_old": disc_old,
            "distinguishable_match_new": disc_new,
            "max_abs_diff_vs_old": d_old_max,
            "max_abs_diff_vs_new": d_new_max,
            "corr_vs_old": corr_old,
            "corr_vs_new": corr_new,
            "json_mean": float(np.mean(jv_list)) if jv_list else None,
            "npz_old_mean": float(np.mean(a_old_list)) if a_old_list else None,
            "npz_new_mean": float(np.mean(a_new_list)) if a_new_list else None,
        }

    # 汇总统计
    def stats(vals):
        vals = [v for v in vals if v == v]
        return {"n": len(vals), "mean": float(np.mean(vals)),
                "median": float(np.median(vals))} if vals else {}

    T_old = [r["npz"]["old"]["T"] for r in rows]
    T_new = [r["npz"]["new"]["T"] for r in rows]

    out = {
        "_what": "字段级 provenance 判定：results/strengthening_battle_corrected.json",
        "_why": ("2026-09-09 SUBSPACE_CPSC 顺序改动未重训模型 -> npz(09-10) 标签与 "
                 "checkpoint 语义失配(MI<->CD 互换) -> 该 JSON 混用两套标签编码"),
        "_authority": "docs/PROTOCOL_AMENDMENT_A3_CORPUS_IDENTITY.md §A3.6; "
                      "reports/CPSC_OFFICIAL_DEFINITION_VERDICT_2026-09-16.md",
        "_verified_by": "scripts/reproduce_main_endpoint_both_encodings.py",
        "generated_for": "污染标记（Task #23）",
        "n_records_total": len(recs),
        "n_records_matched_to_npz": len(rows),
        "field_verdicts": verdict,
        "temperature_caliber": {
            "T_in_json_field": stats([r["json"].get("T") for r in rows]),
            "T_recomputed_OLD_encoding": stats(T_old),
            "T_recomputed_NEW_encoding": stats(T_new),
            "note": ("JSON 的 T 字段 == NEW 编码拟合值（被污染，中位约 1.84）；"
                     "论文若要披露 T 统计量，必须用 OLD 编码（中位约 1.08，全部 <1.5）。"),
        },
        "safe_fields": [f for f, v in verdict.items() if v.get("usable") is True],
        "contaminated_fields": [f for f, v in verdict.items() if v.get("usable") is False],
        "undetermined_fields": [f for f, v in verdict.items() if v.get("usable") is None],
        "paper_endpoint_field": "delta_obs_orig",
        "paper_endpoint_reproduced": True,
        "paper_endpoint_max_abs_diff": 1.110e-16,
    }

    OUT_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    print(f"\n写出：{OUT_JSON}")
    print("\n字段判定：")
    for f, v in verdict.items():
        print(f"  {f:16s} -> {v['caliber']:14s} usable={v.get('usable')}")
    def _med(d):
        v = d.get("median")
        return f"{v:.4f}" if v is not None else "n/a"

    print("\nT 口径：")
    print(f"  JSON.T  median = {_med(out['temperature_caliber']['T_in_json_field'])}")
    print(f"  T_OLD   median = {_med(out['temperature_caliber']['T_recomputed_OLD_encoding'])}")
    print(f"  T_NEW   median = {_med(out['temperature_caliber']['T_recomputed_NEW_encoding'])}")


if __name__ == "__main__":
    main()
