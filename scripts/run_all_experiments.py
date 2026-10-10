"""Run all experiments in batch (sequentially, to avoid GPU OOM).

Execution order:
1. E3  - Brier Reliability + DCR + NCV (core experiment, ~1h)
2. E2  - ablation + discrimination metrics (~1h)
3. E1a - L2 shift matrix completion (~2h)
4. E1b - LOCO cross-corpus validation (~30min)
5. E4  - temperature distribution analysis (~1h)
6. E6  - reliability diagram generation (~1h)
7. E5  - InceptionTime-Lite training (~30-45h)
"""
import subprocess
import sys
import time
import os

os.environ["PYTHONIOENCODING"] = "utf-8"

# Working directory for the child experiment processes. Defaults to the
# repository root (two levels above this script); override with --work-dir.
WORK_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for _i, _a in enumerate(sys.argv):
    if _a == "--work-dir" and _i + 1 < len(sys.argv):
        WORK_DIR = os.path.abspath(sys.argv[_i + 1])

EXPERIMENTS = [
    {
        "name": "E3",
        "cmd": [sys.executable, "scripts/run_e3_brier_dcr_ncv.py", "--batch-size", "16"],
        "log": "results/e3_full.log",
        "timeout": 7200,  # 2 hours
    },
    {
        "name": "E2",
        "cmd": [sys.executable, "scripts/run_e2_ablation_discrimination.py"],
        "log": "results/e2_full.log",
        "timeout": 7200,
    },
    {
        "name": "E1a",
        "cmd": [sys.executable, "scripts/run_e1a_l2_shift_full.py"],
        "log": "results/e1a_full.log",
        "timeout": 14400,  # 4 hours
    },
    {
        "name": "E1b",
        "cmd": [sys.executable, "scripts/run_e1b_loco_validation.py"],
        "log": "results/e1b_full.log",
        "timeout": 3600,
    },
    {
        "name": "E4",
        "cmd": [sys.executable, "scripts/run_e4_temperature_analysis.py"],
        "log": "results/e4_full.log",
        "timeout": 7200,
    },
    {
        "name": "E6",
        "cmd": [sys.executable, "scripts/run_e6_reliability_diagrams.py"],
        "log": "results/e6_full.log",
        "timeout": 7200,
    },
    # E5 is last (30-45 hours)
    {
        "name": "E5",
        "cmd": [sys.executable, "scripts/run_e5_inception_lite.py"],
        "log": "results/e5_full.log",
        "timeout": 180000,  # 50 hours
    },
]


def run_experiment(exp):
    name = exp["name"]
    cmd = exp["cmd"]
    log_path = exp["log"]
    timeout = exp["timeout"]

    print(f"\n{'='*80}")
    print(f"Starting {name}: {' '.join(cmd)}")
    print(f"Log: {log_path}")
    print(f"Timeout: {timeout}s")
    print(f"{'='*80}")

    start = time.time()
    try:
        with open(log_path, "w", encoding="utf-8") as logf:
            proc = subprocess.Popen(
                cmd,
                stdout=logf,
                stderr=subprocess.STDOUT,
                cwd=WORK_DIR,
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            )
            proc.wait(timeout=timeout)
            elapsed = time.time() - start
            rc = proc.returncode
            print(f"\n{name} done: returncode={rc}, elapsed={elapsed:.0f}s ({elapsed/3600:.1f}h)")
            return rc == 0
    except subprocess.TimeoutExpired:
        proc.kill()
        elapsed = time.time() - start
        print(f"\n{name} timed out! elapsed={elapsed:.0f}s")
        return False
    except Exception as e:
        elapsed = time.time() - start
        print(f"\n{name} error: {e}, elapsed={elapsed:.0f}s")
        return False


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip", nargs="*", default=[], help="experiments to skip")
    ap.add_argument("--only", nargs="*", default=None, help="only run the specified experiments")
    args = ap.parse_args()

    exps = EXPERIMENTS
    if args.only:
        exps = [e for e in EXPERIMENTS if e["name"] in args.only]
    else:
        exps = [e for e in EXPERIMENTS if e["name"] not in args.skip]

    results = {}
    for exp in exps:
        # Defensive guard: skip an entry point whose script file is missing
        # instead of aborting the whole batch with a bare traceback, which is
        # what a partial checkout used to do at the first missing script.
        # All seven scripts are present in this checkout, so the guard only
        # fires in a stripped-down tree.
        script = next((a for a in exp["cmd"] if a.endswith(".py")), None)
        if script and not os.path.exists(os.path.join(WORK_DIR, script)):
            print(f"\nSkipping {exp['name']}: {script} is not present in this "
                  f"checkout (expected at {os.path.join(WORK_DIR, script)}).")
            results[exp["name"]] = None
            continue
        ok = run_experiment(exp)
        results[exp["name"]] = ok
        if not ok and exp["name"] != "E5":
            print(f"\nWarning: {exp['name']} failed, continuing to next experiment")

    print(f"\n{'='*80}")
    print("All experiments complete")
    print(f"{'='*80}")
    for name, ok in results.items():
        status = "✓ success" if ok else ("· skipped (script not in this checkout)" if ok is None else "✗ failed")
        print(f"  {name}: {status}")


if __name__ == "__main__":
    main()
