"""W6 stage 1/2 — 300 main seeds per layer, checkpointed.

Execution split ONLY because the sandbox kills long calls. Design, seeds,
strata, estimators and thresholds are byte-identical to PREREGISTRATION_W6.md.
Usage: python run_w6_stage1.py A   /   python run_w6_stage1.py B
"""
from __future__ import annotations
import json, pathlib, sys, time
import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from tier1_kernel import run_tier1_seed

LAYERS = {
    'A': {'seeds': list(range(10000, 10300)), 'spread': 1.00,
          'label': 'high heterogeneity / should split'},
    'B': {'seeds': list(range(10300, 10600)), 'spread': 0.20,
          'label': 'low heterogeneity / should NOT split'},
}
tag = sys.argv[1].upper() if len(sys.argv) > 1 else 'A'
cfg = LAYERS[tag]
BATCH = 100                     # incremental checkpoint; survives sandbox kills
CKPT = HERE / f'w6_stage1_{tag}.json'
T0 = time.time()

if CKPT.exists():
    payload = json.loads(CKPT.read_text(encoding='utf-8'))
    rows = payload['rows']
else:
    rows = []
start = len(rows)
todo = cfg['seeds'][start:start + BATCH]
print(f'[MAIN-{tag}] {start}/300 already checkpointed; running '
      f'{len(todo)} more (seeds {todo[0] if todo else "-"}-'
      f'{todo[-1] if todo else "-"}), spread={cfg["spread"]} ...', flush=True)
for j, s in enumerate(todo):
    rows.append(run_tier1_seed(s, spread=cfg['spread'],
                               do_full_chain=True, do_loco=True,
                               do_block_boot=False))
    if (j + 1) % 50 == 0:
        print(f'   {tag} {start+j+1}/300  {time.time()-T0:.0f}s', flush=True)
CKPT.write_text(json.dumps({'layer': tag, 'spread': cfg['spread'],
                            'rows': rows}, ensure_ascii=False), encoding='utf-8')
print(f'   {tag} checkpointed {len(rows)}/300, {time.time()-T0:.0f}s', flush=True)
print(f'STAGE 1 {tag} {"DONE" if len(rows) == 300 else "PARTIAL"}', flush=True)
