"""Re-run the full grid with BCa B=10,000 (ts primary endpoint): 6 pairs x 2 architectures x 5 seeds = 60 runs.

Per the preregistered protocol, B=10,000 + BCa (with the jackknife acceleration term); of the historical 60 experiments,
31 used percentile/B=10000, 21 used percentile/B=200, and 3 used BCa (only with mixed ts provenance).
This script upgrades all ts runs to the formal BCa version and relies on the
methods.ts.meta.n_bootstrap/bci_method fields written by eval_transfer.py as the resume-skip criterion.

- Each cell is invoked independently (one cell crashing does not affect the others), and [ret=] is logged per cell.
- Already-completed cells (meta.n_bootstrap>=10000 and bci_method=bca) are skipped automatically.
- Only the ts key is rewritten (--methods ts); the other 7 methods' historical percentile results are preserved;
  a full-method BCa version can be produced by changing METHODS to the full method list after ts completes.

Requires a free GPU. Estimated 5-15 min per cell (B=10000+jackknife), 6-12 hours total.
Usage: python scripts/rerun_bca10000.py [--archs inceptiontime resnet1d] [--dry-run]
"""
import os
import sys
import json
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
os.environ.pop("PYTHONUTF8", None)
os.environ["PYTHONUNBUFFERED"] = "1"

PAIRS = [
    ("chapman", "cpsc", "data/chapman_processed_v2", "data/cpsc_processed"),
    ("chapman", "ptbxl", "data/chapman_processed_v2", "data/ptbxl_processed"),
    ("cpsc", "chapman", "data/cpsc_processed", "data/chapman_processed_v2"),
    ("cpsc", "ptbxl", "data/cpsc_processed", "data/ptbxl_processed"),
    ("ptbxl", "chapman", "data/ptbxl_processed", "data/chapman_processed_v2"),
    ("ptbxl", "cpsc", "data/ptbxl_processed", "data/cpsc_processed"),
]
ARCHS = ["inceptiontime", "resnet1d"]
SEEDS = [42, 43, 44, 45, 46]
METHODS = "ts"
LOG = "logs/bca10000_full.log"


def done(rj: Path) -> bool:
    if not rj.exists():
        return False
    try:
        d = json.loads(rj.read_text(encoding="utf-8"))
        ts = d.get("methods", {}).get("ts", {})
        meta = ts.get("meta", {})
        return int(meta.get("n_bootstrap", 0)) >= 10000 and meta.get("bci_method") == "bca"
    except Exception:
        return False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--archs", nargs="+", default=ARCHS)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    # `logs/` is intentionally git-ignored (see .gitignore), so a fresh clone has
    # no such directory: opening the log would raise FileNotFoundError before a
    # single experiment ran. Create it on demand instead.
    Path(LOG).parent.mkdir(parents=True, exist_ok=True)
    open(LOG, "w").close()
    todo, skip_n = [], 0
    for src, tgt, sd, td in PAIRS:
        pair_key = f"{src}_{tgt}"
        for arch in args.archs:
            for seed in SEEDS:
                rj = ROOT / f"checkpoints/transfer/{pair_key}/{arch}/seed{seed}/transfer_result.json"
                if done(rj):
                    skip_n += 1
                    continue
                todo.append((src, tgt, sd, td, pair_key, arch, seed, rj))
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"[plan] {len(todo)} runs to do, {skip_n} already BCa-complete\n")
    print(f"[plan] {len(todo)} runs to do, {skip_n} already BCa-complete")

    if args.dry_run:
        for t in todo:
            print("  would run:", t[4], t[5], "seed", t[6])
        return

    rets = []
    for src, tgt, sd, td, pair_key, arch, seed, _rj in todo:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"\n{'='*60}\nBCa B=10000: {src} -> {tgt} [{arch}] seed{seed}\n{'='*60}\n")
        cmd = (
            f'python scripts/eval_transfer.py '
            f'--source {src} --source-dir {sd} --target {tgt} --target-dir {td} '
            f'--arch {arch} --seeds {seed} --load-model '
            f'--methods {METHODS} --bootstrap 10000 --bci-method bca '
            f'--gpu-inference --n-jobs 8 '
            f'>> {LOG} 2>&1'
        )
        ret = os.system(cmd)
        rets.append((pair_key, arch, seed, ret))
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"\n[ret={ret}] {src}->{tgt} {arch} seed{seed} done\n")

    n_fail = sum(1 for r in rets if r[3] != 0)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"\nBCa B=10000 full grid complete: {len(rets)} runs, {n_fail} failed.\n")
    print(f"[done] {len(rets)} runs, {n_fail} failed")


if __name__ == "__main__":
    main()
