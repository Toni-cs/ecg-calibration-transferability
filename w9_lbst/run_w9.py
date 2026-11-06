"""W9 runner — time-boxed, incremental, resumable (W7-proven design).

Default: 110000..119999 (10,000 confirmatory seeds).
Falsification: 120000..120599 (600 seeds) via --falsify.
Each flush writes an immutable npz shard; a sandbox kill loses <= 400 rows.
"""
from __future__ import annotations
import argparse, json, pathlib, sys, time
import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
SHARDS = HERE / 'shards'; SHARDS.mkdir(exist_ok=True)
sys.path.insert(0, str(HERE))
from w9_kernel import run_one, COLS, NCOLS

MAIN_START, MAIN_END = 110000, 120000
FAL_START, FAL_END = 120000, 120600
FLUSH_EVERY = 400
STATE = HERE / 'progress.json'


def state_path(tag):
    return HERE / f'progress_{tag}.json'


def load(tag):
    p = state_path(tag)
    if p.exists():
        return json.loads(p.read_text(encoding='utf-8'))
    return {'next_seed': MAIN_START if tag == 'main' else FAL_START,
            'done': 0, 'shards': [], 'boxes': 0}


def save(tag, st):
    state_path(tag).write_text(json.dumps(st, indent=2), encoding='utf-8')


def flush(tag, st, rows, t0, suffix=''):
    if not rows:
        return
    a = np.asarray(rows, dtype=np.float64)
    idx = len(st['shards'])
    folder = SHARDS / tag; folder.mkdir(exist_ok=True)
    path = folder / f'shard_{idx:03d}.npz'
    np.savez_compressed(path, X=a)
    st['shards'].append(f'{tag}/shard_{idx:03d}.npz')
    st['done'] += len(rows)
    st['next_seed'] = (MAIN_START if tag == 'main' else FAL_START) + st['done']
    save(tag, st)
    print(f'  [flush{suffix}] +{len(rows)} total {st["done"]} '
          f'{time.time()-t0:.0f}s -> {path.name}', flush=True)


def run_box(tag, st, box_seconds):
    t0 = time.time()
    END = MAIN_END if tag == 'main' else FAL_END
    todo = list(range(st['next_seed'], END))
    if not todo:
        print(f'{tag} DONE ({st["done"]})', flush=True)
        return True
    rows = []
    for s in todo:
        if tag == 'falsify':
            j = (s - FAL_START) % 5
            kw = ({0: dict(se_zero=True), 1: dict(lb_zero=True),
                   2: dict(random_lb=True), 3: dict(homogeneous=True),
                   4: dict(lb_upper=True)})[j]
            rows.append(run_one(s, **kw))
            # paired baseline is recomputed deterministically in analyze_w9.py
        else:
            rows.append(run_one(s))
        if len(rows) >= FLUSH_EVERY:
            flush(tag, st, rows, t0); rows = []
        if time.time() - t0 > box_seconds:
            break
    flush(tag, st, rows, t0, '-end')
    st['boxes'] += 1
    save(tag, st)
    print(f'[{tag} box {st["boxes"]}] total {st["done"]} '
          f'{time.time()-t0:.0f}s', flush=True)
    return st['done'] >= (END - (MAIN_START if tag == 'main' else FAL_START))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--box', type=float, default=170.0)
    ap.add_argument('--falsify', action='store_true')
    args = ap.parse_args()
    tag = 'falsify' if args.falsify else 'main'
    st = load(tag)
    print(f'[start {tag}] next={st["next_seed"]} done={st["done"]} '
          f'shards={len(st["shards"])}', flush=True)
    run_box(tag, st, args.box)


if __name__ == '__main__':
    main()
