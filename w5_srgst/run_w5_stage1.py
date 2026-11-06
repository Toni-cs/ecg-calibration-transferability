"""W5 stage 1/2 — 600 main seeds, checkpointed.

Execution split ONLY because the sandbox kills ~5-min calls. Design, seeds,
strata, estimators and thresholds are byte-identical to PREREGISTRATION_W5.md.
"""
from __future__ import annotations
import json, pathlib, sys, time
import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from w5_srgst import run_w5_seed

SEED_A = list(range(7000, 7300))
SEED_B = list(range(7300, 7600))
T0 = time.time()

print('[MAIN-A] 300 Mamba seeds 7000-7299 (W3 DGP) ...', flush=True)
A = []
for i, s in enumerate(SEED_A):
    A.append(run_w5_seed(s, stratum='A'))
    if (i + 1) % 150 == 0:
        print(f'   A {i+1}/300 {time.time()-T0:.0f}s', flush=True)
(HERE / 'w5_stage1_A.json').write_text(json.dumps(A, ensure_ascii=False), encoding='utf-8')
print(f'   A checkpointed {time.time()-T0:.0f}s', flush=True)

print('[MAIN-B] 300 Mamba seeds 7300-7599 (long-tail small groups) ...', flush=True)
B = []
for i, s in enumerate(SEED_B):
    B.append(run_w5_seed(s, stratum='B'))
    if (i + 1) % 150 == 0:
        print(f'   B {i+1}/300 {time.time()-T0:.0f}s', flush=True)
(HERE / 'w5_stage1_B.json').write_text(json.dumps(B, ensure_ascii=False), encoding='utf-8')
print(f'   B checkpointed {time.time()-T0:.0f}s', flush=True)
print('STAGE 1 DONE', flush=True)
