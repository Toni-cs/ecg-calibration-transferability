"""后台串行启动 seed43 的 4 对 CPSC 转移实验。"""
import subprocess, sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
common = [
    sys.executable, "scripts/eval_transfer.py",
    "--arch", "inceptiontime",
    "--methods", "ts", "platt", "isotonic", "vector", "matrix", "dirichlet",
    "em_prior", "bbse_prior",
    "--seeds", "43",
    "--epochs", "50",
    "--gpu-inference",
    "--bootstrap", "200",
    "--bci-method", "percentile",
    "--save-dir", "checkpoints/transfer",
]
jobs = [
    (common + ["--source", "cpsc", "--source-dir", "data/cpsc_processed",
               "--target", "ptbxl", "--target-dir", "data/ptbxl_processed",
               "--load-model"], "cpsc_ptbxl_seed43"),
    (common + ["--source", "cpsc", "--source-dir", "data/cpsc_processed",
               "--target", "chapman", "--target-dir", "data/chapman_processed_v2",
               "--load-model"], "cpsc_chapman_seed43"),
    (common + ["--source", "ptbxl", "--source-dir", "data/ptbxl_processed",
               "--target", "cpsc", "--target-dir", "data/cpsc_processed"], "ptbxl_cpsc_seed43"),
    (common + ["--source", "chapman", "--source-dir", "data/chapman_processed_v2",
               "--target", "cpsc", "--target-dir", "data/cpsc_processed"], "chapman_cpsc_seed43"),
]
for i, (cmd, name) in enumerate(jobs):
    log = open(root / f"transfer_{name}.log", "w", encoding="utf-8")
    print(f"[{i+1}/4] Starting {name}...")
    proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, cwd=str(root))
    proc.wait()
    log.close()
    print(f"[{i+1}/4] {name} exited with code {proc.returncode}")
print("All seed43 transfer experiments done.")