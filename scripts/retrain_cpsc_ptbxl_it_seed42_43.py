#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""重训 cpsc->ptbxl / inceptiontime / seed{42,43}，恢复 60 格的模型独立性。

背景
====
2026-09-17 的检查点独立性审计发现：`cpsc_chapman/inceptiontime/seed{42,43}` 与
`cpsc_ptbxl/inceptiontime/seed{42,43}` 的 `best_model.pt` 是**逐字节相同的拷贝**
（md5 6ee3b3995d5b / 2cbada61a0ce，mtime 精确到纳秒也相同 —— 两次训练不可能同纳秒完成）。

为什么只有 cpsc 源会这样
========================
`eval_transfer.py:139-142` 在复用检查点时会校验 `num_classes`，不匹配直接 raise。
K = min(源库类别数, 目标库类别数)：
  - 源=cpsc  → 两个目标(chapman/ptbxl)都是 K=4 ⇒ 检查点**可以**复用
  - 源=chapman→ cpsc 是 K=4，但 ptbxl 是 K=5 ⇒ **不能**复用
  - 源=ptbxl → 同理不能复用
所以只有 cpsc 源存在「共享」的可能，而实际只在 seed42/43 共享了、seed44-46 没有 ——
网格构造口径不自洽。本脚本把 seed42/43 也训练成独立模型，使 60 格 = 60 个独立源模型。

口径复刻（取自被替换的 `transfer_result.json`）
==============================================
  n_bootstrap=10000, bci_method=bca, ts_fit=source_cal,
  metric=smooth_ece_0.45*(n/2000)^-0.2, label_map={'NORM':0,'CD':1,'STTC':2,'MI':3}(OLD)

用法::
    /c/python/python.exe scripts/retrain_cpsc_ptbxl_it_seed42_43.py
"""
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]

cmd = [
    sys.executable, "scripts/eval_transfer.py",
    "--arch", "inceptiontime",
    "--source", "cpsc", "--source-dir", "data/cpsc_processed",
    "--target", "ptbxl", "--target-dir", "data/ptbxl_processed",
    "--seeds", "42", "43",
    "--methods", "ts", "platt", "isotonic", "vector", "matrix", "dirichlet",
    "em_prior", "bbse_prior",
    "--epochs", "50",
    "--gpu-inference",
    "--bootstrap", "10000",
    "--bci-method", "bca",
    "--n-jobs", "8",
    "--save-dir", "checkpoints/transfer",
]

log_path = root / "logs" / "retrain_cpsc_ptbxl_it_seed42_43.log"
log_path.parent.mkdir(parents=True, exist_ok=True)
print(" ".join(str(c) for c in cmd), flush=True)
with log_path.open("w", encoding="utf-8") as fh:
    proc = subprocess.Popen([str(c) for c in cmd], stdout=fh,
                            stderr=subprocess.STDOUT, cwd=str(root))
    rc = proc.wait()
print(f"exit={rc}  log={log_path}", flush=True)
sys.exit(rc)
