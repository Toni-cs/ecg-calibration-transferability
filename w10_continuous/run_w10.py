"""W10 runner — time-boxed, incremental, resumable.

Tags:
  main     130000..149999  (20,000 confirmatory seeds)
  loco     150000..150599  (600 seeds x 3 fold-type rows)
  falsify  151000..151599  (600 seeds, 5 conditions x 120)

`done` counts SEEDS (not rows); a sandbox kill loses <= FLUSH_EVERY seeds.
"""
from __future__ import annotations
import argparse, json, pathlib, sys, time
import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
SHARDS = HERE / 'shards'; SHARDS.mkdir(exist_ok=True)
sys.path.insert(0, str(HERE))
from w10_kernel import run_one, run_loco

RANGES = {'main': (130000, 150000), 'loco': (150000, 150600),
          'falsify': (151000, 151600)}
FLUSH_EVERY = 400


def load(tag):
    p = HERE / f'progress_{tag}.json'
    if p.exists():
        return json.loads(p.read_text(encoding='utf-8'))
    return {'done': 0, 'shards': [], 'boxes': 0}


def save(tag, st):
    (HERE / f'progress_{tag}.json').write_text(
        json.dumps(st, indent=2), encoding='utf-8')


def next_seed(tag, st):
    return RANGES[tag][0] + st['done']


def flush(tag, st, rows, pending, t0, suffix=''):
    """Commit `pending` seeds worth of rows and advance the seed counter."""
    if pending == 0:
        return
    a = np.asarray(rows, dtype=np.float64)
    idx = len(st['shards'])
    folder = SHARDS / tag; folder.mkdir(exist_ok=True)
    path = folder / f'shard_{idx:03d}.npz'
    np.savez_compressed(path, X=a)
    st['shards'].append(f'{tag}/shard_{idx:03d}.npz')
    st['done'] += pending
    save(tag, st)
    print(f'  [flush{suffix}] +{pending} seeds ({len(rows)} rows)  '
          f'total {st["done"]}  {time.time()-t0:.0f}s -> {path.name}',
          flush=True)


def run_box(tag, st, box_seconds):
    t0 = time.time()
    start, end = RANGES[tag]
    todo = list(range(next_seed(tag, st), end))
    if not todo:
        print(f'{tag} DONE ({st["done"]})', flush=True)
        return True
    rows, pending = [], 0
    for s in todo:
        if tag == 'main':
            rows.append(run_one(s))
        elif tag == 'loco':
            rows.extend(list(run_loco(s)))
        else:
            j = (s - start) % 5
            kw = ({0: dict(deff_override=1.0), 1: dict(rel_override=1.0),
                   2: dict(rel_override=0.0), 3: dict(strat_random=True),
                   4: dict(homogeneous=True)})[j]
            rows.append(run_one(s, **kw))
        pending += 1
        if pending >= FLUSH_EVERY:
            flush(tag, st, rows, pending, t0); rows, pending = [], 0
        if time.time() - t0 > box_seconds:
            break
    flush(tag, st, rows, pending, t0, '-end')
    st['boxes'] += 1
    save(tag, st)
    print(f'[{tag} box {st["boxes"]}] next={next_seed(tag, st)} '
          f'done={st["done"]}  {time.time()-t0:.0f}s', flush=True)
    return next_seed(tag, st) >= end


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tag', default='main', choices=['main', 'loco', 'falsify'])
    ap.add_argument('--box', type=float, default=170.0)
    ap.add_argument('--all', action='store_true')
    args = ap.parse_args()
    tag = args.tag
    st = load(tag)
    print(f'[start {tag}] next={next_seed(tag, st)} done={st["done"]} '
          f'shards={len(st["shards"])} all={args.all}', flush=True)
    if args.all:
        while True:
            if run_box(tag, st, args.box):
                break
    else:
        run_box(tag, st, args.box)


if __name__ == '__main__':
    main()
