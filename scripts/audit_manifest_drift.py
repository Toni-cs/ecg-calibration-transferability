"""对比 docs/osf_archive_manifest.json 的哈希与仓库当前状态。

用途：清单是"某时刻的快照"，改动后不应静默重写，而应记录"清单之后哪些文件变了"。
本脚本只读，输出变更清单（供人工写入 post-corrections 记录）。
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs" / "osf_archive_manifest.json"


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    print(f"清单时间戳: {m.get('timestamp_utc')}")
    print(f"清单 target_venue: {m.get('target_venue')!r}  <- 现已过期（改投 CMPB）")
    print(f"清单文件数: {len(m.get('files', {}))}")
    print()

    unchanged, changed, missing = [], [], []
    for rel, meta in sorted(m["files"].items()):
        p = ROOT / rel
        if not p.exists():
            missing.append(rel)
            continue
        cur = sha256(p)
        if cur == meta["sha256"]:
            unchanged.append(rel)
        else:
            changed.append((rel, meta["sha256"], cur,
                            meta.get("size_bytes"), p.stat().st_size))

    print("=" * 78)
    print(f"未变 ({len(unchanged)})")
    print("=" * 78)
    for r in unchanged:
        print(f"  = {r}")

    print()
    print("=" * 78)
    print(f"已变 ({len(changed)})  <-- 需要记录为 post-manifest correction")
    print("=" * 78)
    for rel, old, new, old_sz, new_sz in changed:
        print(f"  M {rel}")
        print(f"      old sha256 = {old}")
        print(f"      new sha256 = {new}")
        print(f"      size {old_sz} -> {new_sz}")

    if missing:
        print()
        print("=" * 78)
        print(f"清单中有但仓库已不存在 ({len(missing)})")
        print("=" * 78)
        for r in missing:
            print(f"  ! {r}")

    # 同时列出"清单未收录但属分析关键路径"的新文件
    print()
    print("=" * 78)
    print("清单之后新增的关键文件（未在清单中）")
    print("=" * 78)
    for rel in [
        "docs/PROTOCOL_AMENDMENT_A3_CORPUS_IDENTITY.md",
        "docs/PROTOCOL_AMENDMENT_A2_FAMILY_REDUCTION.md",
        "reports/CPSC_OFFICIAL_DEFINITION_VERDICT_2026-09-16.md",
        "tests/test_data.py",
        "scripts/verify_cpsc_corpus_identity.py",
        "scripts/reproduce_main_endpoint_both_encodings.py",
        "scripts/verify_main_from_transfer.py",
        "scripts/audit_temperature_csv_caliber.py",
        "results/strengthening_battle_corrected.PROVENANCE.json",
        "checkpoints/e2_probs_cache/_CONTAMINATION_NOTICE.md",
    ]:
        p = ROOT / rel
        tag = "存在" if p.exists() else "缺失"
        print(f"  + {rel}  [{tag}]")

    sys.exit(0)


if __name__ == "__main__":
    main()
