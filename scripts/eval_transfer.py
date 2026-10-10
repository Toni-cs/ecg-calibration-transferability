"""Cross-library calibration transfer S1 evaluation: source model -> OOD target primary endpoint (protocol §7 + §13).

Purpose: run the paper's primary test of "calibration-benefit ID->OOD decay" on real
cross-library pairs.
Scenario S1 (zero-shot transfer, primary analysis): the calibration method is fit on the
source cal split and applied directly to the target test split (no target labels). Compare
against the ID baseline (same method on source test) to obtain the ΔECE decay.

Pipeline:
1. Train the source model (train/val/cal/test four-way split, patient-level leakage-free).
2. The source model emits raw probs for source-test and target-test.
3. Each calibration method is fit on source-cal (S1) and the same parameters are applied to
   source-test (ΔECE_ID, the ID baseline) and target-test (ΔECE_OOD, the primary analysis).
4. benefit_inference (BCa, patient-level cluster, B=10,000) yields the paired CI for ΔECE.
5. Primary test: H0 that (ΔECE_ID - ΔECE_OOD) = 0, with its CI.

Invocation:
    python scripts/eval_transfer.py \
        --source ptbxl --source-dir data/ptbxl_processed \
        --target chapman --target-dir data/chapman_processed_v2 \
        --arch mamba --seeds 42 43
    # smoke test: add --limit 240 --epochs 2

Consistency requirement: both libraries use the fixed label order
SUPERCLASSES = (NORM, MI, STTC, CD, HYP), so their probability spaces are aligned
(a precondition for cross-library calibration transfer, guaranteed by preprocessing).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.models.ecg_classifier import ECGClassifier  # noqa: E402
from src.utils.calibration import benefit_inference, smooth_ece, smooth_ece_gpu  # noqa: E402
from src.utils.calibration_methods import CALIBRATION_METHODS  # noqa: E402
from train import (  # noqa: E402
    set_seed, evaluate, train_model, create_dataloader,
    build_ptbxl_datasets, build_chapman_datasets, build_cpsc_datasets,
)
from src.data.mapping import SUBSPACE_CPSC, SUPERCLASSES  # noqa: E402

DATASET_BUILDERS = {
    "ptbxl": build_ptbxl_datasets,
    "chapman": build_chapman_datasets,
    "cpsc": build_cpsc_datasets,
}

DATASET_NUM_CLASSES = {
    "ptbxl": 5,
    "chapman": 5,
    "cpsc": 4,
}


def _build(dataset: str, data_dir: str, seed: int, limit: int | None,
           subspace: tuple | None = None):
    """Build the four-way split; returns (datasets, clusters_test)

    subspace: if provided (e.g. SUBSPACE_CPSC), ptbxl/chapman are filtered/reduced to the subspace (preregistered protocol §2 symmetric recomputation);
    cpsc always uses SUBSPACE_CPSC (built-in 4 classes); the subspace argument is ignored.
    """
    builder = DATASET_BUILDERS[dataset]
    if dataset == "cpsc":
        ds, clusters = builder(data_dir, seed, limit=limit)
    elif subspace is not None:
        ds, clusters = builder(data_dir, seed, limit=limit, subspace=subspace)
    else:
        ds, clusters = builder(data_dir, seed, limit=limit)
    return ds, clusters


def fit_apply_method(method_name, fit_probs, fit_labels, test_probs):
    """Fit the calibration method on the fit distribution and apply it to the test distribution -> (calibrated probabilities, params)"""
    if method_name == "none":
        return test_probs, {}
    fit_fn, apply_fn, _ = CALIBRATION_METHODS[method_name]
    # fit_fn needs 2D full-class probabilities + class labels (one-hot or integer index, method-dependent)
    params = fit_fn(fit_probs, fit_labels)
    if params is None:  # small-sample / over-parameterized preregistered failure -> return original probabilities (no benefit)
        return test_probs, {}
    return apply_fn(test_probs, params), params


def run_pair(args, source_name, source_dir, target_name, target_dir,
             seed: int) -> dict:
    """Train the source model and run the S1 cross-library evaluation; return the primary-endpoint result for this (pair, arch, seed)."""
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    set_seed(seed)

    # ---------- num_classes / subspace inference (preregistered protocol §2: CPSC -> 4-class symmetric reduction) ----------
    num_classes = min(DATASET_NUM_CLASSES[source_name],
                      DATASET_NUM_CLASSES[target_name])
    subspace = SUBSPACE_CPSC if num_classes == 4 else None

    # ---------- source model training (train/val/cal/test) ----------
    src_ds, src_clusters = _build(source_name, source_dir, seed, args.limit,
                                  subspace=subspace)
    loaders = {k: create_dataloader(src_ds[k], args.batch_size,
                                    shuffle=(k == "train"),
                                    drop_last=(k == "train"),
                                    num_workers=args.num_workers)
                for k in ("train", "val", "cal", "test")}
    model = ECGClassifier(in_channels=12, d_model=args.d_model,
                          n_layers=args.n_layers, num_classes=num_classes,
                          dropout=0.1, backbone_type=args.arch).to(device)
    run_dir = Path(args.save_dir) / f"{source_name}_{target_name}" / \
        args.arch / f"seed{seed}"
    run_dir.mkdir(parents=True, exist_ok=True)
    cfg = {"epochs": args.epochs, "lr": args.lr, "lr_min": 1e-6,
           "weight_decay": 1e-4, "patience": 10, "save_dir": str(run_dir)}
    ckpt_path = run_dir / "best_model.pt"
    if args.load_model and ckpt_path.exists():
        ckpt = torch.load(ckpt_path, weights_only=False, map_location=device)
        ckpt_nc = ckpt.get("num_classes")
        if ckpt_nc is not None and ckpt_nc != num_classes:
            raise RuntimeError(
                f"Checkpoint num_classes={ckpt_nc} != current num_classes={num_classes}."
                f"This checkpoint cannot be reused for this pair (label dimension mismatch).")
        sd = ckpt["model_state_dict"]
        if args.arch == "mamba":
            inferred_d_model = sd["backbone.stem.0.weight"].shape[0]
            import re
            layer_ids = {re.match(r"backbone\.layers\.(\d+)\.", k).group(1)
                         for k in sd if re.match(r"backbone\.layers\.(\d+)\.", k)}
            inferred_n_layers = len(layer_ids)
        elif "backbone.proj.weight" in sd:
            inferred_d_model = sd["backbone.proj.weight"].shape[0]
            inferred_n_layers = args.n_layers
        else:
            inferred_d_model = args.d_model
            inferred_n_layers = args.n_layers
        if inferred_d_model != args.d_model or inferred_n_layers != args.n_layers:
            model = ECGClassifier(in_channels=12, d_model=inferred_d_model,
                                  n_layers=inferred_n_layers, num_classes=num_classes,
                                  dropout=0.1, backbone_type=args.arch).to(device)
        try:
            model.load_state_dict(sd)
        except RuntimeError as e:
            raise RuntimeError(
                f"load_state_dict failed (likely num_classes mismatch): {e}") from e
        print(f"Loaded checkpoint {ckpt_path} (epoch {ckpt.get('epoch','?')}, "
              f"val_ece={ckpt.get('val_ece','?'):.4f}, d_model={inferred_d_model}, n_layers={inferred_n_layers})")
    else:
        model = train_model(model, loaders["train"], loaders["val"], cfg, device)

    # ---------- source ID evaluation: source-cal fit -> source-test apply ----------
    cal_eval = evaluate(model, loaders["cal"], device, compute_calibration=False)
    test_eval = evaluate(model, loaders["test"], device, compute_calibration=False)
    id_probs = test_eval["probs"]          # (N_ID, 5) source test raw
    id_labels = test_eval["labels"]
    cal_probs = cal_eval["probs"]          # (N_cal, 5) source cal raw
    cal_labels = cal_eval["labels"]

    # ---------- OOD target: source model forward pass on target test ----------
    tgt_ds, tgt_clusters = _build(target_name, target_dir, seed, args.limit,
                                  subspace=subspace)
    tgt_loaders = create_dataloader(tgt_ds["test"], args.batch_size,
                                    shuffle=False, num_workers=args.num_workers)
    tgt_eval = evaluate(model, tgt_loaders, device, compute_calibration=False)
    ood_probs = tgt_eval["probs"]          # (N_OOD, 5) target raw
    ood_labels = tgt_eval["labels"]
    # target patient IDs used as clusters (patient-level bootstrap)
    ood_clusters = tgt_clusters

    # ---------- per-method: S1 fit (source-cal) -> apply to both domains ----------
    results = {
        "source": source_name, "target": target_name, "arch": args.arch,
        "seed": seed,
        "num_classes": num_classes,
        "subspace": list(subspace) if subspace else None,
        "label_map": {c: i for i, c in enumerate(subspace)} if subspace
                     else {c: i for i, c in enumerate(SUPERCLASSES)},
        "n_id": int(len(id_probs)), "n_ood": int(len(ood_probs)),
        "id_acc": float((id_probs.argmax(1) == id_labels).mean()),
        "ood_acc": float((ood_probs.argmax(1) == ood_labels).mean()),
        "methods": {},
    }

    rng = np.random.default_rng(seed)
    for mname in args.methods:
        # Per-method fit parameters. This MUST be reset on every iteration:
        # `fit_params` is read unconditionally below (the meta "T" column) but
        # was historically only assigned in the non-prior branch. As a result a
        # prior method (em_prior / bbse_prior, which fit no temperature)
        # inherited the *previous* method's parameters -- so `--methods ts
        # em_prior` recorded ts's T under em_prior's entry -- and crashed with
        # UnboundLocalError if a prior method ran first.
        fit_params = {}
        if mname in ("em_prior", "bbse_prior"):
            # S1 (target-domain unsupervised prior adaptation; Saerens 2002 / BBSE, Lipton 2018):
            # estimate the target prior pi_hat from source-cal (labeled) + target-test (unlabeled) -> rescale probabilities.
            # Note: applying the same pi_hat to the ID domain deliberately introduces a prior mismatch (ID true prior = source prior),
            # and its ID degradation is part of the method's paradigm; for prior methods the decay is interpreted as
            # "target-specific benefit"; the paper must state this explicitly (to preempt reviewer challenges on pairing fairness).
            from src.utils.prior_shift import fit_em, fit_bbse
            fit_fn = fit_em if mname == "em_prior" else fit_bbse
            res = fit_fn(cal_probs, cal_labels, ood_probs)
            if res is None:
                results["methods"][mname] = {
                    "status": "skipped", "reason": "prior not identifiable",
                    "id": None, "ood": None, "decay": None}
                print(f"[{mname:9s}] SKIPPED: prior not identifiable")
                continue
            pi_hat, pi_train = res["pi_hat"], res["pi_train"]

            def _apply_prior(probs, _r=(pi_hat / np.maximum(pi_train, 1e-12))):
                adj = probs * _r[None, :]
                return adj / adj.sum(axis=1, keepdims=True)

            ood_cal = _apply_prior(ood_probs)
            id_cal = _apply_prior(id_probs)
            w = pi_hat / np.maximum(pi_train, 1e-12)
            print(f"  [{mname}] π̂_target={np.round(pi_hat, 3)} "
                  f"(π_train={np.round(pi_train, 3)})")
            print(f"  [{mname}] w=π̂/π_train={np.round(w, 2)}")
            if "confusion_cond" in res:
                print(f"  [{mname}] cond(C)={res['confusion_cond']:.1f} "
                      f"rank={res['rank']}/{len(pi_train)}")
            res_id = fit_fn(cal_probs, cal_labels, id_probs)
            pi_id = w_id = None
            sanity_flag = None
            if res_id is not None:
                pi_id = res_id["pi_hat"]
                w_id = pi_id / np.maximum(pi_train, 1e-12)
                print(f"  [{mname}] [sanity] π̂_ID={np.round(pi_id, 3)} "
                      f"w_ID={np.round(w_id, 2)} (~1 if no shift)")
                # ID sanity drift alarm (identifiability proxy)
                max_drift = float(np.nanmax(np.abs(w_id - 1.0)))
                cond_id = res_id.get("confusion_cond")
                if max_drift > 10.0:
                    sanity_flag = f"w_ID drift max|w-1|={max_drift:.1f} > 10; estimator likely ill-conditioned/unnamed-shift"
                    print(f"  [{mname}] [sanity][WARN] {sanity_flag}")
                elif cond_id is not None and float(cond_id) > 1e4:
                    sanity_flag = f"cond(C)={float(cond_id):.1f} > 1e4; prior recovery unreliable"
                    print(f"  [{mname}] [sanity][warn] {sanity_flag}")
            results["methods"][mname + "_pi"] = {
                "pi_hat": pi_hat.tolist(), "pi_train": pi_train.tolist(),
                "estimator": res["method"], "w": w.tolist(),
                "cond_C": res.get("confusion_cond"),
                "pi_hat_ID": pi_id.tolist() if pi_id is not None else None,
                "w_ID": w_id.tolist() if w_id is not None else None,
                "sanity_flag": sanity_flag}
        elif mname == "saerens":
            # saerens needs target-domain unsupervised prior estimation, incompatible with the S1 source-cal fitting paradigm (category error:
            # saerens's "parameter" is the target prior and can only be estimated in the target domain). Mark as skipped rather than fabricating output.
            # For the S1 scenario use em_prior / bbse_prior (equivalent methods, correct paradigm).
            results["methods"][mname] = {
                "status": "skipped",
                "reason": "saerens needs target-domain unsupervised fit; incompatible with the S1 source-cal fitting paradigm; use em_prior/bbse_prior",
                "id": None, "ood": None, "decay": None,
            }
            print(f"[{mname:9s}] SKIPPED: needs target-domain unsupervised fit; incompatible with S1 source-cal fitting")
            continue
        else:
            ood_cal, fit_params = fit_apply_method(mname, cal_probs, cal_labels, ood_probs)
            id_cal, _ = fit_apply_method(mname, cal_probs, cal_labels, id_probs)

        # Paired cluster bootstrap needs (probs_raw, probs_cal) in the same order + labels
        metric_fn = smooth_ece_gpu if args.gpu_inference else smooth_ece
        print(f"  [{mname}] OOD bootstrap inference in progress... (B={args.bootstrap}, "
              f"method={args.bci_method}, metric={'gpu' if args.gpu_inference else 'cpu'})")
        ood_ben = benefit_inference(
            _maxprob(ood_probs), _maxprob(ood_cal), _bin(ood_cal, ood_labels),
            metric=metric_fn, n_bootstrap=args.bootstrap, rng=rng,
            clusters=ood_clusters, bci_method=args.bci_method)
        print(f"  [{mname}] ID bootstrap inference in progress...")
        id_ben = benefit_inference(
            _maxprob(id_probs), _maxprob(id_cal), _bin(id_cal, id_labels),
            metric=metric_fn, n_bootstrap=args.bootstrap, rng=rng,
            clusters=src_clusters, bci_method=args.bci_method)

        results["methods"][mname] = {
            "id": {"deltaECE": id_ben["benefit"], "ci": list(id_ben["benefit_ci"]),
                   "raw": id_ben["raw"], "cal": id_ben["cal"]},
            "ood": {"deltaECE": ood_ben["benefit"], "ci": list(ood_ben["benefit_ci"]),
                    "raw": ood_ben["raw"], "cal": ood_ben["cal"]},
            "decay": float(ood_ben["benefit"] - id_ben["benefit"]),
            "meta": {"n_bootstrap": int(args.bootstrap), "bci_method": args.bci_method,
                     "ts_fit": "source_cal" if mname == "ts" else "source_cal_or_target_unlabeled",
                     "metric": "smooth_ece_0.45*(n/2000)^-0.2",
                     "T": float(fit_params.get('T', float('nan'))) if fit_params else float('nan')},
        }
        print(f"[{mname:9s}] ID ΔECE={id_ben['benefit']:+.4f} "
              f"[{id_ben['benefit_ci'][0]:+.4f},{id_ben['benefit_ci'][1]:+.4f}] | "
              f"OOD ΔECE={ood_ben['benefit']:+.4f} "
              f"[{ood_ben['benefit_ci'][0]:+.4f},{ood_ben['benefit_ci'][1]:+.4f}] | "
              f"decay={ood_ben['benefit']-id_ben['benefit']:+.4f}")

    out = run_dir / "transfer_result.json"
    if out.exists():
        try:
            existing = json.loads(out.read_text(encoding="utf-8"))
            if "methods" in existing and isinstance(existing["methods"], dict):
                existing["methods"].update(results.get("methods", {}))
                results = existing
        except Exception:
            pass
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nSaved to {out}")
    return results


def _maxprob(p): return np.asarray(p).max(axis=1)
def _bin(p, labels): return (np.asarray(p).argmax(1) == np.asarray(labels)).astype(float)


def main():
    ap = argparse.ArgumentParser(description="Cross-library S1 calibration transfer eval")
    ap.add_argument("--source", choices=list(DATASET_BUILDERS), required=True)
    ap.add_argument("--source-dir", required=True)
    ap.add_argument("--target", choices=list(DATASET_BUILDERS), required=True)
    ap.add_argument("--target-dir", required=True)
    ap.add_argument("--arch", default="mamba",
                    choices=["mamba", "resnet1d", "inceptiontime"])
    ap.add_argument("--methods", nargs="+",
                    default=["ts", "platt", "em_prior", "bbse_prior"],
                    help="S1 primary method subset: ts/platt/isotonic/vector/matrix/dirichlet/"
                         "em_prior/bbse_prior (S1 target-domain unsupervised prior adaptation)")
    ap.add_argument("--seeds", nargs="+", type=int, default=[42])
    ap.add_argument("--epochs", type=int, default=50)
    ap.add_argument("--batch-size", type=int, default=16)
    ap.add_argument("--d-model", "--d_model", dest="d_model",
                    type=int, default=64, help="Hidden dimension(--d-model/--d_model both accepted)")
    ap.add_argument("--n-layers", type=int, default=2)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--bootstrap", type=int, default=10000,
                    help="Preregistered B=10,000 (default); use --bootstrap 200 for a smoke test")
    ap.add_argument("--n-jobs", type=int, default=1,
                    help="leave-one-cluster-out jackknife parallel worker count (default 1, serial;"
                         "formal pilot set >=8 to speed up BCa acceleration term, bit-identical output)")
    ap.add_argument("--save-dir", default="checkpoints/transfer")
    ap.add_argument("--limit", type=int, default=None, help="smoke-test truncation")
    ap.add_argument("--num-workers", type=int, default=0,
                    help="DataLoader multi-threaded data loading (0=single thread, 4-8 speeds up I/O significantly)")
    ap.add_argument("--bci-method", default="bca", choices=["bca", "percentile"],
                    help="CI method: bca (default, includes jackknife acceleration, slow) or percentile (fast, skips jackknife)")
    ap.add_argument("--gpu-inference", action="store_true",
                    help="Use GPU implementation of smooth_ece (numerically identical to CPU, max diff <1e-15, jackknife 92x faster)")
    ap.add_argument("--load-model", action="store_true",
                    help="Reuse a trained best_model.pt to skip retraining (use only when inferring new methods)")
    args = ap.parse_args()

    all_runs = []
    for seed in args.seeds:
        r = run_pair(args, args.source, args.source_dir,
                     args.target, args.target_dir, seed)
        all_runs.append(r)

    # aggregate decay (primary test statistic: OOD ΔECE - ID ΔECE)
    print("\n" + "=" * 60)
    print("S1 cross-library primary-endpoint summary (ID->OOD ΔECE decay)")
    print("=" * 60)
    for mname in args.methods:
        decays = [r["methods"][mname]["decay"] for r in all_runs]
        print(f"  {mname:9s} mean decay={np.mean(decays):+.4f} "
              f"sd={np.std(decays):.4f} (n={len(decays)} seed)")

    agg_path = Path(args.save_dir) / f"{args.source}_{args.target}" / \
        args.arch / "aggregate.json"
    agg_path.parent.mkdir(parents=True, exist_ok=True)
    agg_path.write_text(json.dumps(
        {"pairs": [{k: v for k, v in r.items() if k != "methods"} for r in all_runs],
         "method_decay": {m: [r["methods"][m]["decay"] for r in all_runs]
                          for m in args.methods}},
        indent=2), encoding="utf-8")
    print(f"Aggregate -> {agg_path}")


if __name__ == "__main__":
    main()
