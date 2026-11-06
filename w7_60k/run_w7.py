"""W7 runner — time-boxed, incremental, resumable, 2-worker parallel.

Usage:
  python run_w7.py --box 160          # one time box (~160s), then exit
  python run_w7.py --all              # loop boxes until 60,000 (use nohup)
  python run_w7.py --bridge           # 600 W6-regime bridge seeds
Each box writes an immutable shard. A sandbox kill loses at most one box.
"""
from __future__ import annotations
import argparse, json, pathlib, sys, time
from multiprocessing import Pool
import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
SHARDS = HERE / 'shards'; SHARDS.mkdir(exist_ok=True)
sys.path.insert(0, str(HERE))
from w7_kernel import run_one, COLS, NCOLS, T_GRID, TAU_GRID

MAIN_START, MAIN_END = 21000, 81000        # 60,000 seeds, half-open
BRIDGE_START, BRIDGE_END = 19000, 19600    # 600, W6 confirmatory regime
STATE = HERE / 'progress.json'


def load_state():
    if STATE.exists():
        return json.loads(STATE.read_text(encoding='utf-8'))
    return {'next_seed': MAIN_START, 'done': 0, 'shards': [], 'boxes': 0}


def save_state(st):
    STATE.write_text(json.dumps(st, indent=2), encoding='utf-8')


FLUSH_EVERY = 400


def flush(st, rows, t0, tag=''):
    if not rows:
        return
    a = np.asarray(rows, dtype=np.float64)
    idx = len(st['shards'])
    path = SHARDS / f'shard_{idx:03d}.npz'
    np.savez_compressed(path, X=a)
    st['shards'].append(path.name)
    st['done'] += len(rows)
    st['next_seed'] = MAIN_START + st['done']
    save_state(st)
    print(f'  [flush{tag}] +{len(rows)}  total {st["done"]}/60000  '
          f'{time.time()-t0:.0f}s -> {path.name}', flush=True)


def run_box(st, box_seconds, chunk=24, workers=1):
    """Incremental checkpointing INSIDE the box: a sandbox kill loses at most
    FLUSH_EVERY rows instead of the whole box."""
    t0 = time.time()
    todo = list(range(st['next_seed'], MAIN_END))
    if not todo:
        print('ALL 60,000 DONE', flush=True)
        return True
    rows = []
    # The sandbox exposes nproc=2 but a ~1-CPU cgroup quota; multiprocessing
    # measured SLOWER (0.10s/seed) than serial (0.077s/seed). Serial by default.
    if workers == 1:
        for s in todo:
            rows.append(run_one(s))
            if len(rows) >= FLUSH_EVERY:
                flush(st, rows, t0); rows = []
            if time.time() - t0 > box_seconds:
                break
    else:
        with Pool(workers) as pool:
            for i in range(0, len(todo), chunk):
                if time.time() - t0 > box_seconds:
                    break
                batch = todo[i:i + chunk]
                for r in pool.imap(run_one, batch, chunksize=4):
                    rows.append(r)
                    if len(rows) >= FLUSH_EVERY:
                        flush(st, rows, t0); rows = []
    flush(st, rows, t0, tag='-end')
    st['boxes'] += 1
    save_state(st)
    print(f'[box {st["boxes"]}] total {st["done"]}/60000  {time.time()-t0:.0f}s', flush=True)
    return st['done'] >= 60000


def run_bridge():
    """600 seeds under the EXACT W6 confirmatory regime for P0 bridging."""
    sys.path.insert(0, str(HERE.parent / 'w6_tier1'))
    from tier1_kernel import run_tier1_seed
    out = HERE / 'bridge_w6_regime.json'
    if out.exists():
        print('bridge already done', flush=True)
        return
    rows = []
    for i, s in enumerate(range(BRIDGE_START, BRIDGE_END)):
        sp = 1.0 if i < 300 else 0.20
        r = run_tier1_seed(s, spread=sp, do_full_chain=True,
                           do_loco=False, do_block_boot=False)
        rows.append({'seed': s, 'spread': sp, 'harm_GST': r['harm']['GST'],
                     'harm_CERT': r['harm']['CERT-GATE'],
                     'harm_GSGST': r['harm']['GS-GST'],
                     'dU_CERT': r['delta_U_CERT'],
                     'cert': r['certificate']['certificate']})
        if (i + 1) % 100 == 0:
            print(f'  bridge {i+1}/600', flush=True)
    out.write_text(json.dumps(rows, ensure_ascii=False), encoding='utf-8')
    print('bridge done', flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--box', type=float, default=160.0)
    ap.add_argument('--all', action='store_true')
    ap.add_argument('--bridge', action='store_true')
    ap.add_argument('--workers', type=int, default=1)
    args = ap.parse_args()
    if args.bridge:
        run_bridge(); return
    st = load_state()
    print(f'[start] next_seed={st["next_seed"]} done={st["done"]} '
          f'shards={len(st["shards"])} workers={args.workers}', flush=True)
    if args.all:
        while True:
            if run_box(st, args.box, workers=args.workers):
                break
    else:
        run_box(st, args.box, workers=args.workers)


if __name__ == '__main__':
    main()
