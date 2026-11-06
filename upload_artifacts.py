#!/usr/bin/env python3
"""Upload the W1-W12 artifact archive to GitHub WITHOUT touching main.

DESIGN CONSTRAINTS (deliberate):
  * --dry-run is the DEFAULT. Nothing is sent unless --execute is passed.
  * The token is read ONLY from the GITHUB_TOKEN environment variable.
    It is never printed, never written to disk, never embedded in a file.
  * main is never modified. We create a NEW branch (Git Data API) or a
    NEW Release asset, both from the current main HEAD.
  * --tier public (default) excludes unpublished strategy/roadmap docs.

Usage:
  python upload_artifacts.py                          # dry-run plan, no network
  python upload_artifacts.py --mode release --dry-run
  GITHUB_TOKEN=... python upload_artifacts.py --execute --mode branch
  GITHUB_TOKEN=... python upload_artifacts.py --execute --mode release

Requires: Python 3.8+, stdlib only (urllib). No requests / gh CLI needed.
"""
from __future__ import annotations
import argparse, base64, hashlib, json, os, pathlib, sys, urllib.error, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent
OWNER = 'Toni-cs'
REPO = 'ecg-calibration-transferability'
BRANCH = 'artifacts/w1-w12'
TAG = 'artifacts-w12-v1'
API = 'https://api.github.com'
UPLOADS = 'https://uploads.github.com'

# Unpublished strategy / journal-targeting / roadmap docs: NOT uploaded by default.
PRIVATE_TOPLEVEL = {
    '升二区执行计划.md',
    '创新点与工作量补强方案.md',
    '百万级数据与原创方法方案.md',
    '一区构想与实施蓝图.md',
    '直到一区执行计划.md',
    '上传前核查与归档清单.md',
    'UPLOAD_MANIFEST.sha256',   # full local manifest references private files
}
# Aggregate snapshot zips and the offline-only manifest are convenience copies
# for the user's local disk. All of their contents are shipped as loose files,
# and including a zip of the archive inside the archive creates a self-referential
# hash that can never be consistent. Excluded from ALL tiers.
SNAPSHOT_ONLY = {
    'W1_W12_全量产物_上传候选.zip',
    'W12_数据准入方案_交付.zip',
    'UPLOAD_MANIFEST.sha256',
}
SKIP_DIRS = {'.git', '__pycache__', 'repo_audit', 'dr:20261106020004', 'recheck'}
SKIP_FILES = {'audit.log', 'audit_github.py', 'audit_github2.py',
              'UPLOAD_DRYRUN.log', 'UPLOAD_EXECUTE.log', '.upload_blobs.json',
              '.gh_token'}  # logs / transient progress / credential: never shipped
SKIP_SUFFIX = {'.pyc'}

# Files that exist locally but are generated/verification-only for the branch.
BRANCH_ONLY = {'PUBLIC_MANIFEST.sha256'}


def collect(tier: str) -> list[pathlib.Path]:
    out: list[pathlib.Path] = []
    for p in sorted(ROOT.iterdir()):
        if p.is_dir():
            if p.name in SKIP_DIRS:
                continue
            for f in sorted(p.rglob('*')):
                if not f.is_file():
                    continue
                if any(s in f.parts for s in ('.git', '__pycache__')):
                    continue
                if f.suffix in SKIP_SUFFIX:
                    continue
                out.append(f)
        else:
            if p.name in SKIP_DIRS or p.name in SKIP_FILES:
                continue
            if p.name in SNAPSHOT_ONLY:
                continue
            if p.suffix in SKIP_SUFFIX:
                continue
            if tier == 'public' and p.name in PRIVATE_TOPLEVEL:
                continue
            out.append(p)
    # README / LICENSE / GPU note / uploader / public manifest always included
    for must in ('README.md', 'LICENSE', 'W12_GPU算力需求与三层口径.md',
                 'W12_数据准入与替代方案.md', '成功论文架构漏洞与补洞报告.md',
                 'upload_artifacts.py', 'PUBLIC_MANIFEST.sha256'):
        p = ROOT / must
        if p.is_file() and p not in out:
            out.append(p)
    return sorted(set(out))


MANIFEST_NAMES = {'PUBLIC_MANIFEST.sha256', 'FULL_MANIFEST.sha256'}


def write_manifest(files: list[pathlib.Path], dest: pathlib.Path) -> None:
    """Standard `sha256sum -c` format: '<hash>  <relative path>'.

    Both checksum files are mutually exclusive from their own listings:
    otherwise each would hash the other, creating a cycle that can never
    verify (writing one invalidates the other's recorded hash).
    """
    lines = []
    for f in sorted(set(files)):
        if f.name in MANIFEST_NAMES:
            continue
        h = hashlib.sha256(read_bytes(f)).hexdigest()
        lines.append(f'{h}  {f.relative_to(ROOT).as_posix()}')
    dest.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def read_bytes(f: pathlib.Path) -> bytes:
    """virtio-backed sandbox occasionally throws a transient EIO on read."""
    import time
    for i in range(4):
        try:
            return f.read_bytes()
        except OSError:
            if i == 3:
                raise
            time.sleep(0.4 * (i + 1))
    raise RuntimeError('unreachable')


def token_headers(token: str, extra: dict | None = None) -> dict:
    h = {
        'Authorization': f'Bearer {token}',
        'Accept': 'application/vnd.github+json',
        'User-Agent': 'w12-artifact-uploader/1.0',
        'X-GitHub-Api-Version': '2022-11-28',
    }
    if extra:
        h.update(extra)
    return h


def req(method: str, url: str, token: str, body=None, raw: bytes | None = None,
        content_type: str = 'application/json', tries: int = 6):
    """With retry/backoff for secondary rate limits and transient 5xx."""
    import time
    data = raw if raw is not None else (json.dumps(body).encode('utf-8')
                                        if body is not None else None)
    headers = token_headers(token, {'Content-Type': content_type} if data else None)
    last = None
    for attempt in range(tries):
        r = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(r, timeout=90) as resp:
                payload = resp.read()
                return resp.status, (json.loads(payload) if payload else {})
        except urllib.error.HTTPError as e:
            msg = e.read().decode('utf-8', 'replace')[:220]
            last = f'HTTP {e.code}: {msg}'
            if e.code in (403, 429, 500, 502, 503, 504):
                wait = float(e.headers.get('Retry-After') or 0)
                if not wait:
                    reset = e.headers.get('X-RateLimit-Reset')
                    if reset and e.code == 403:
                        wait = max(1.0, float(reset) - time.time() + 2)
                if not wait:
                    wait = min(30.0, 2.0 * (2 ** attempt))
                print(f'  retry {attempt+1}/{tries} after {wait:.1f}s ({e.code})')
                time.sleep(wait)
                continue
            raise RuntimeError(f'HTTP {e.code} on {method} {url}: {msg}') from None
        except Exception as e:
            last = f'{type(e).__name__}: {e}'
            if attempt < tries - 1:
                time.sleep(min(20.0, 1.5 * (2 ** attempt)))
                continue
    raise RuntimeError(f'failed after {tries} tries: {last}')


def plan_print(files: list[pathlib.Path], mode: str, tier: str, execute: bool):
    total = sum(f.stat().st_size for f in files)
    print('=' * 68)
    print('W1-W12 ARTIFACT UPLOAD PLAN')
    print('=' * 68)
    print(f'  mode        : {mode}')
    print(f'  tier        : {tier}')
    print(f'  execute     : {execute}  (False = DRY RUN, no network calls)')
    print(f'  target      : {OWNER}/{REPO}')
    print(f'  main        : UNTOUCHED')
    print(f'  branch      : {BRANCH}' if mode == 'branch' else f'  release tag : {TAG}')
    print(f'  files       : {len(files)}')
    print(f'  raw bytes   : {total}  ({total/1024/1024:.2f} MiB)')
    if mode == 'release':
        z = ROOT / 'W1_W12_全量产物_上传候选.zip'
        print(f'  asset       : {z.name} ({z.stat().st_size/1024/1024:.2f} MiB)'
              if z.exists() else '  asset       : MISSING local zip')
    print(f'  excluded    : {len(PRIVATE_TOPLEVEL)} private/roadmap docs'
          if tier == 'public' else '  excluded    : none (FULL tier)')
    print('  token       : read from GITHUB_TOKEN env only; never printed/stored')
    print('-' * 68)
    for f in files[:12]:
        print('   +', f.relative_to(ROOT).as_posix())
    print(f'   ... and {max(0, len(files) - 12)} more')
    print('-' * 68)
    if not execute:
        print('DRY RUN COMPLETE. No request was sent, main is unchanged.')
        print('To actually upload: set GITHUB_TOKEN and add --execute')
    return total


PROGRESS = ROOT / '.upload_blobs.json'


def load_cache():
    if PROGRESS.exists():
        try:
            return json.loads(PROGRESS.read_text(encoding='utf-8'))
        except Exception:
            return {}
    return {}


def blob_entries(files, cache):
    entries, missing = [], []
    for f in files:
        rel = f.relative_to(ROOT).as_posix()
        digest = hashlib.sha256(read_bytes(f)).hexdigest()
        hit = cache.get(rel)
        if hit and hit.get('digest') == digest:
            entries.append({'path': rel, 'mode': '100644', 'type': 'blob',
                            'sha': hit['sha']})
        else:
            missing.append((f, rel, digest))
    return entries, missing


def prepare_blobs(token, files, max_new=0):
    """Create up to `max_new` missing blobs; resume-safe, no branch writes."""
    import time
    cache = load_cache()
    entries, missing = blob_entries(files, cache)
    print(f'  blobs cached {len(entries)}/{len(files)}, missing {len(missing)}',
          flush=True)
    created = 0
    for f, rel, digest in missing:
        if max_new and created >= max_new:
            break
        b = read_bytes(f)
        _, blob = req('POST', f'{API}/repos/{OWNER}/{REPO}/git/blobs', token,
                      body={'content': base64.b64encode(b).decode('ascii'),
                            'encoding': 'base64'})
        cache[rel] = {'sha': blob['sha'], 'digest': digest}
        PROGRESS.write_text(json.dumps(cache, indent=0), encoding='utf-8')
        created += 1
        time.sleep(0.18)
        if created % 25 == 0:
            print(f'  created {created} new blobs', flush=True)
    left = len(blob_entries(files, cache)[1])
    print(f'  phase blobs: created {created}, remaining {left}', flush=True)
    return left == 0


def finish_branch(token, files):
    """Tree + root commit + ref. Requires all blobs already cached."""
    cache = load_cache()
    entries, missing = blob_entries(files, cache)
    if missing:
        raise RuntimeError(f'{len(missing)} blobs missing; run --phase blobs first')
    # Never overwrite an existing branch.
    try:
        req('GET', f'{API}/repos/{OWNER}/{REPO}/git/ref/heads/{BRANCH}', token)
        raise RuntimeError(f'branch {BRANCH} already exists; refusing to overwrite')
    except RuntimeError as e:
        if 'already exists' in str(e):
            raise
    _, ref = req('GET', f'{API}/repos/{OWNER}/{REPO}/git/ref/heads/main', token)
    print(f'  main HEAD {ref["object"]["sha"][:10]} (read-only; never modified)',
          flush=True)
    # Orphan tree: contains ONLY our artifacts, so our README.md cannot
    # overwrite upstream's README on the new branch.
    _, tree = req('POST', f'{API}/repos/{OWNER}/{REPO}/git/trees', token,
                  body={'tree': entries})
    _, newc = req('POST', f'{API}/repos/{OWNER}/{REPO}/git/commits', token,
                  body={'message': 'Add W1-W14 artifact archive (orphan branch; main untouched)',
                        'tree': tree['sha'], 'parents': []})
    req('POST', f'{API}/repos/{OWNER}/{REPO}/git/refs', token,
        body={'ref': f'refs/heads/{BRANCH}', 'sha': newc['sha']})
    print(f'  DONE: {BRANCH} @ {newc["sha"][:10]}  ({len(files)} files)',
          flush=True)
    PROGRESS.unlink(missing_ok=True)


def do_branch(token, files):
    prepare_blobs(token, files)
    finish_branch(token, files)


def do_release(token: str) -> None:
    z = ROOT / 'W1_W12_全量产物_上传候选.zip'
    if not z.exists():
        raise RuntimeError('local zip missing')
    _, rel = req('POST', f'{API}/repos/{OWNER}/{REPO}/releases', token,
                 body={'tag_name': TAG, 'name': 'W1–W12 合成层实验归档',
                       'body': 'Unpublished synthetic-layer internal experiments. '
                               'No real patient data. CPU-only, no GPU training. '
                               'See README.md in the artifact branch.',
                       'draft': False, 'prerelease': True})
    print(f'  release created: {rel.get("html_url", "")}')
    url = f'{UPLOADS}/repos/{OWNER}/{REPO}/releases/{rel["id"]}/assets?name={z.name}'
    raw = read_bytes(z)
    _, asset = req('POST', url, token, raw=raw,
                   content_type='application/zip')
    print(f'  asset uploaded: {asset.get("name")} '
          f'({asset.get("size", len(raw))} bytes)')


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--mode', choices=['branch', 'release'], default='branch')
    ap.add_argument('--tier', choices=['public', 'full'], default='full')
    ap.add_argument('--dry-run', action='store_true', default=False)
    ap.add_argument('--execute', action='store_true', default=False)
    ap.add_argument('--phase', choices=['blobs', 'finish', 'all'], default='all')
    ap.add_argument('--max-blobs', type=int, default=0,
                    help='cap new blobs per invocation (0 = no cap)')
    a = ap.parse_args()
    execute = a.execute and not a.dry_run

    # Both checksum files are always generated and shipped, so a reader of
    # either tier can verify exactly what that tier contains.
    PUB = ROOT / 'PUBLIC_MANIFEST.sha256'
    FULL = ROOT / 'FULL_MANIFEST.sha256'
    pub_files = collect('public')
    full_files = collect('full')
    write_manifest(pub_files, PUB)
    write_manifest(full_files, FULL)
    files = collect(a.tier)
    for m in (PUB, FULL):
        if m not in files:
            files.append(m)
    files = sorted(set(files))
    # Re-write the chosen tier's manifest now that both are on disk.
    write_manifest(files, PUB if a.tier == 'public' else FULL)
    plan_print(files, a.mode, a.tier, execute)
    if not execute:
        return 0

    token = os.environ.get('GITHUB_TOKEN', '').strip()
    if not token:
        print('ABORT: GITHUB_TOKEN not set. Nothing was sent.', file=sys.stderr)
        return 2
    print('  executing with token from environment (value never shown)')
    try:
        if a.mode == 'release':
            do_release(token)
        elif a.phase == 'blobs':
            prepare_blobs(token, files, a.max_blobs)
        elif a.phase == 'finish':
            finish_branch(token, files)
        else:
            do_branch(token, files)
    except RuntimeError as e:
        print(f'ABORT: {e}', file=sys.stderr)
        return 3
    return 0


if __name__ == '__main__':
    sys.exit(main())
