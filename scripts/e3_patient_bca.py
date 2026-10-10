"""E3 registered-unit deliverable: patient-level cluster BCa (B=10,000)
for NCV / DCR, reproducing the main endpoint's protocol semantics
(§4.12/§9: patient-level paired cluster bootstrap, BCa operating CI).

Per cell (pair, arch, seed):
  - load e3_probs.npz (encoding-guard stamped, same discipline as run_e3)
  - rebuild the SOURCE and TARGET test split via the exact same builder path
    as eval_transfer._build so clusters_test aligns 1:1 with probs order
  - aggregate paired decision variables per patient
      NCV_p  = (tp_improved + tn_improved - fp_worsened - fn_worsened)_p
      size_p = n_records_p x K           (N_total = N_samples x N_classes)
      DCR_p  = dwrong_p + abstain_cost * dabs_p ;  n_p = n_records_p
  - bootstrap: patient-level multinomial counts (G picks, replace=True), B=10,000
      benefit_b = sum_p c_bp * net_p / sum_p c_bp * size_p
  - BCa per cell via src.utils.calibration._bca_interval with
    leave-one-patient-out jackknife acceleration
  - integrity gate: per-cell recomputed NCV/DCR point estimators (ID and OOD)
    must equal the shipped E3 table (c1_dcr_ncv_multiclass.csv) to 1e-9.

Pooled units: 12 pair x arch strata (equal weight over its 5 cells) and
all-60 equal-weight pooled; per-b aligned cell draws are averaged
cell-wise (the cluster-bootstrap analog of the equal-cell-weight mean).

Outputs:
  results/e3_patient_bca_cells.csv    (60 rows, per cell, ID + OOD)
  results/e3_patient_bca_summary.json (strata + pooled + provenance)
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(PROJECT / "scripts"))

from src.utils.calibration import _bca_interval, apply_temperature  # noqa: E402
from src.utils.encoding_guard import assert_cache_encoding  # noqa: E402
from src.data.mapping import SUBSPACE_CPSC  # noqa: E402
from eval_transfer import _build  # noqa: E402

TAU = 0.5
ABSTAIN_COST = 0.5
B = 10_000
CONF = 0.95
RNG_SEED = 20261010

PAIRS = ["ptbxl_chapman", "ptbxl_cpsc", "chapman_ptbxl",
         "chapman_cpsc", "cpsc_ptbxl", "cpsc_chapman"]
ARCHS = ["inceptiontime", "resnet1d"]
SEEDS = [42, 43, 44, 45, 46]
DATA_DIRS = {
    "ptbxl": PROJECT / "data" / "ptbxl_processed",
    "chapman": PROJECT / "data" / "chapman_processed_v2",
    "cpsc": PROJECT / "data" / "cpsc_processed",
}
NCLASSES = {"ptbxl": 5, "chapman": 5, "cpsc": 4}


def paired_rowvars(probs_raw, probs_cal, labels):
    N, K = probs_raw.shape
    raw_pos = probs_raw > TAU
    cal_pos = probs_cal > TAU
    onehot = np.zeros((N, K), dtype=bool)
    onehot[np.arange(N), labels] = True
    tp = ((~raw_pos) & cal_pos & onehot).sum(axis=1)
    tn = (raw_pos & (~cal_pos) & (~onehot)).sum(axis=1)
    fp = ((~raw_pos) & cal_pos & (~onehot)).sum(axis=1)
    fn = (raw_pos & (~cal_pos) & onehot).sum(axis=1)
    net = (tp + tn - fp - fn).astype(np.float64)
    raw_dec = probs_raw.max(axis=1) > TAU
    cal_dec = probs_cal.max(axis=1) > TAU
    dwrong = ((probs_raw.argmax(axis=1) != labels) & raw_dec).astype(np.float64) \
        - ((probs_cal.argmax(axis=1) != labels) & cal_dec).astype(np.float64)
    dabs = (~raw_dec).astype(np.float64) - (~cal_dec).astype(np.float64)
    return net, dwrong, dabs, K, N


def aggregate_patients(net, dwrong, dabs, K, clusters):
    cl = np.asarray(clusters)
    uniq, inv = np.unique(cl, return_inverse=True)
    G = len(uniq)
    net_p, dwrong_p, dabs_p, n_p = (np.zeros(G) for _ in range(4))
    np.add.at(net_p, inv, net)
    np.add.at(dwrong_p, inv, dwrong)
    np.add.at(dabs_p, inv, dabs)
    np.add.at(n_p, inv, 1)
    return net_p, dwrong_p + ABSTAIN_COST * dabs_p, n_p * K, n_p, G


def cell_draws(num_p, denom_p, rng):
    """(B,) 患者级 multinomial 计数重采样（分块防大 G 内存尖峰）。"""
    G = len(num_p)
    per = 2500 if G > 4000 else B
    out = np.empty(B)
    done = 0
    while done < B:
        n = min(per, B - done)
        counts = rng.multinomial(G, np.full(G, 1.0 / G), size=n)  # (n, G)
        out[done:done + n] = (counts @ num_p) / (counts @ denom_p)
        done += n
    return out


def jackknife(num_p, denom_p):
    with np.errstate(invalid="ignore", divide="ignore"):
        return (num_p.sum() - num_p) / (denom_p.sum() - denom_p)


def two_sided(draws, zero=0.0):
    """bootstrap p for H0: theta = 0（两倍较小侧比例）；比例已归一化。"""
    pl = float(np.mean(draws <= zero))
    pg = float(np.mean(draws >= zero))
    return float(np.clip(2.0 * min(pl, pg), 0.0, 1.0))


def main():
    ap = argparse.ArgumentParser(
        description="E3 registered-unit deliverable: patient-level cluster BCa (B=10000)")
    ap.add_argument("--archs", nargs="+", default=ARCHS)
    ap.add_argument("--pairs", nargs="+", default=PAIRS)
    ap.add_argument("--seeds", type=int, nargs="+", default=SEEDS)
    ap.add_argument("--out-tag", default="", help="文件名后缀（冒烟测试用）")
    args = ap.parse_args()

    ref = {}
    header = None
    build_memo = {}                        # (role, dataset, seed) -> (ds, clusters)
    p_ref = PROJECT / "results/c1_dcr_ncv_multiclass.csv"
    with open(p_ref, encoding="utf-8-sig") as f:
        for row in csv.reader(f):
            if not row or row[0].strip().startswith("#"):
                continue
            if row[0] == "pair":
                header = row
                continue
            d = dict(zip(header, row))
            ref[(d["pair"], d["arch"], int(d["seed"]))] = {
                "ncv_ood": float(d["ncv_ood"]), "dcr_ood": float(d["dcr_ood"]),
                "ncv_id": float(d["ncv_id"]), "dcr_id": float(d["dcr_id"])}
    print(f"E3 reference table rows: {len(ref)}", flush=True)

    cells_out = []
    cell_draws_all = []                    # loop order；元素 (ood_ncv, ood_dcr, id_ncv, id_dcr)
    strata = {}                            # (pair, arch) -> list of (这 5 个 seed 的 draws tuple)

    total = len(args.pairs) * len(args.archs) * len(args.seeds)
    n_done = 0
    for pair in args.pairs:
        src_name, tgt_name = pair.split("_")
        for arch in args.archs:
            for seed in args.seeds:
                n_done += 1
                print(f"[{n_done}/{total}] {pair}/{arch}/seed{seed} ...", flush=True)

                ckpt_dir = PROJECT / "checkpoints" / "transfer" / pair / arch / f"seed{seed}"
                npz_path = ckpt_dir / "e3_probs.npz"
                data = np.load(npz_path, allow_pickle=False)
                K = int(np.asarray(data["num_classes"]).ravel()[0])
                subspace = SUBSPACE_CPSC if K == 4 else None
                assert_cache_encoding(npz_path, data, K, subspace, allow_unstamped=False)
                T = float(np.asarray(data["T"]).ravel()[0])
                assert K == min(NCLASSES[src_name], NCLASSES[tgt_name])

                sk_src = (src_name, seed, subspace)
                sk_tgt = (tgt_name, seed, subspace)
                if sk_src not in build_memo:
                    build_memo[sk_src] = _build(src_name, str(DATA_DIRS[src_name]), seed,
                                                None, subspace=subspace)
                if sk_tgt not in build_memo:
                    build_memo[sk_tgt] = _build(tgt_name, str(DATA_DIRS[tgt_name]), seed,
                                                None, subspace=subspace)
                id_clusters = np.asarray(build_memo[sk_src][1])
                ood_clusters = np.asarray(build_memo[sk_tgt][1])
                id_clusters = np.asarray(id_clusters)
                ood_clusters = np.asarray(ood_clusters)

                row = ref[(pair, arch, seed)]
                cell = {"pair": pair, "arch": arch, "seed": seed, "T": T}
                draws_pack = []
                for split in ("ood", "id"):
                    if split == "ood":
                        clusters = ood_clusters
                        probs_raw = np.asarray(data["ood_probs"], dtype=float)
                        labels = np.asarray(data["ood_labels"]).astype(int)
                    else:
                        clusters = id_clusters
                        probs_raw = np.asarray(data["id_probs"], dtype=float)
                        labels = np.asarray(data["id_labels"]).astype(int)
                    if len(clusters) != len(probs_raw):
                        raise RuntimeError(
                            f"{pair}/{arch}/seed{seed} {split}: cluster n={len(clusters)} "
                            f"!= probs n={len(probs_raw)} — builder/cache 顺序错位，停止")
                    probs_cal = apply_temperature(probs_raw, T)
                    net, dwrong, dabs, Kr, Nrec = paired_rowvars(probs_raw, probs_cal, labels)
                    net_p, dcr_num_p, size_p, n_p, G = aggregate_patients(
                        net, dwrong, dabs, K, clusters)
                    point_ncv = float(net_p.sum() / size_p.sum())
                    point_dcr = float(dcr_num_p.sum() / n_p.sum())
                    exp_ncv = row[f"ncv_{split}"]
                    exp_dcr = row[f"dcr_{split}"]
                    if abs(point_ncv - exp_ncv) > 1e-9 or abs(point_dcr - exp_dcr) > 1e-9:
                        raise RuntimeError(
                            f"{pair}/{arch}/seed{seed} {split}: 重算与已交付 E3 表不匹配 "
                            f"(ncv {point_ncv:+.9f} vs {exp_ncv:+.9f}, "
                            f"dcr {point_dcr:+.9f} vs {exp_dcr:+.9f})")
                    rng = np.random.default_rng(np.random.SeedSequence(
                        [RNG_SEED, PAIRS.index(pair), ARCHS.index(arch), seed,
                         0 if split == "ood" else 1]))
                    ncv_draws = cell_draws(net_p, size_p, rng)
                    dcr_draws = cell_draws(dcr_num_p, n_p, rng)
                    ncv_lo, ncv_hi = _bca_interval(point_ncv, ncv_draws,
                                                   jackknife(net_p, size_p), CONF)
                    dcr_lo, dcr_hi = _bca_interval(point_dcr, dcr_draws,
                                                   jackknife(dcr_num_p, n_p), CONF)
                    cell.update({
                        f"n_patients_{split}": int(G),
                        f"n_{split}": int(Nrec),
                        f"ncv_{split}": point_ncv,
                        f"ncv_{split}_lo": float(ncv_lo),
                        f"ncv_{split}_hi": float(ncv_hi),
                        f"p_bca_ncv_{split}": two_sided(ncv_draws),
                        f"dcr_{split}": point_dcr,
                        f"dcr_{split}_lo": float(dcr_lo),
                        f"dcr_{split}_hi": float(dcr_hi),
                        f"p_bca_dcr_{split}": two_sided(dcr_draws),
                    })
                    draws_pack.append((ncv_draws, dcr_draws))
                cells_out.append(cell)
                cell_draws_all.append(tuple(draws_pack))          # (ood_ncv, ood_dcr), (id_ncv, id_dcr)
                strata.setdefault((pair, arch), []).append(tuple(draws_pack))
                print(f"    ood ncv {cell['ncv_ood']:+.6f} "
                      f"[{cell['ncv_ood_lo']:+.6f}, {cell['ncv_ood_hi']:+.6f}]  "
                      f"p={cell['p_bca_ncv_ood']:.4f} | "
                      f"dcr {cell['dcr_ood']:+.6f} "
                      f"[{cell['dcr_ood_lo']:+.6f}, {cell['dcr_ood_hi']:+.6f}]", flush=True)

    tag = args.out_tag or ""
    cells_csv = PROJECT / "results" / f"e3_patient_bca_cells{tag}.csv"
    fields = ["pair", "arch", "seed", "T", "n_ood", "n_patients_ood",
              "ncv_ood", "ncv_ood_lo", "ncv_ood_hi", "p_bca_ncv_ood",
              "dcr_ood", "dcr_ood_lo", "dcr_ood_hi", "p_bca_dcr_ood",
              "n_id", "n_patients_id",
              "ncv_id", "ncv_id_lo", "ncv_id_hi", "p_bca_ncv_id",
              "dcr_id", "dcr_id_lo", "dcr_id_hi", "p_bca_dcr_id"]
    with open(cells_csv, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for c in cells_out:
            w.writerow({k: (f"{c[k]:.9f}" if isinstance(c[k], float) else c[k])
                        for k in fields if k in c})
    print(f"wrote {cells_csv}")

    vector_cache = {}

    def pool_stats(points_list, draws_list, key=None):
        stack = np.vstack(draws_list)
        pooled = stack.mean(axis=0)
        if key:
            vector_cache[key] = pooled.astype(np.float64)
        point = float(np.mean(points_list))
        lo, hi = np.percentile(pooled, [(1 - CONF) / 2 * 100, (1 + CONF) / 2 * 100])
        return {"point": point, "bca_lo": float(lo), "bca_hi": float(hi),
                "p_bootstrap": two_sided(pooled), "n_units": len(points_list),
                "pooled_draw_mean": float(pooled.mean())}

    summary = {
        "meta": {"B": B, "confidence": CONF, "rng_seed": RNG_SEED,
                 "tau": TAU, "abstain_cost": ABSTAIN_COST,
                 "cells": len(cells_out), "date": "2026-10-10",
                 "unit": "patient-level cluster bootstrap; BCa per cell; "
                         "pooled = equal-cell-weight mean of aligned per-cell draws",
                 "integrity_gate": "per-cell recomputed NCV/DCR (ID & OOD) exact-match "
                                   "results/c1_dcr_ncv_multiclass.csv at 1e-9"},
        "pooled": {"ncv_ood": None, "dcr_ood": None, "ncv_id": None, "dcr_id": None},
        "strata": {},
    }
    for split, idx in (("ood", 0), ("id", 1)):
        for metric, pos in (("ncv", 0), ("dcr", 1)):
            pts = [c[f"{metric}_{split}"] for c in cells_out]
            dws = [t[idx][pos] for t in cell_draws_all]
            summary["pooled"][f"{metric}_{split}"] = pool_stats(pts, dws, key=f"{metric}_{split}")

    for (pair, arch), packs in strata.items():
        sk = f"{pair}|{arch}"
        summary["strata"][sk] = {}
        for split, idx in (("ood", 0), ("id", 1)):
            for metric, pos in (("ncv", 0), ("dcr", 1)):
                pts = [p[idx][pos] for p in packs]
                dws = [p[idx][pos] for p in packs]
                summary["strata"][sk][f"{metric}_{split}"] = pool_stats(pts, dws)

    ncv_support = sum(1 for c in cells_out if c["ncv_ood_lo"] > 0)
    dcr_support = sum(1 for c in cells_out if c["dcr_ood_lo"] > 0)
    summary["percell_support_counts"] = {
        "ncv_ood_lo_gt0": ncv_support, "dcr_ood_lo_gt0": dcr_support, "out_of": len(cells_out)}

    out_json = PROJECT / "results" / f"e3_patient_bca_summary{tag}.json"
    out_json.write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(f"wrote {out_json}")
    # 池化 draws 存档（provenance：p_bootstrap 可随时从 draws 重算）
    if not tag:
        pooled_npz = PROJECT / "results" / "e3_patient_bca_pooled_draws.npz"
        np.savez_compressed(
            pooled_npz,
            ncv_ood=vector_cache.get("ncv_ood"),
            dcr_ood=vector_cache.get("dcr_ood"),
            ncv_id=vector_cache.get("ncv_id"),
            dcr_id=vector_cache.get("dcr_id"),
        )
        print(f"wrote {pooled_npz}")
    print("---- pooled ----")
    print(json.dumps(summary["pooled"], indent=1))
    print("---- support counts ----")
    print(json.dumps(summary["percell_support_counts"], indent=1))


if __name__ == "__main__":
    main()
