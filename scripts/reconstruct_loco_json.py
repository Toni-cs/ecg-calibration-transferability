"""从 hash 校验过的 CSV 无损重建被摧毁的 deployment_loco_validation.json。

背景：2026-09-17 18:33 一个对抗代理运行了 run_e1b_loco_validation.py，把
results/deployment_loco_validation.json 覆盖成 3 条 fatal skip_reason 记录，
并把 .csv 一并覆盖（.csv 已从补充材料包恢复并 sha256 校验通过）。
本脚本只从已校验的 .csv 重建 .json 的 records，meta 由 CSV 头部注释 +
run_e1b_loco_validation.py 的常量恢复。

CSV 写出用的是 rec.get(c, "")，float 是全精度 repr → 重建对 value 无损。
"""
import csv, io, json, re, shutil
from pathlib import Path

ROOT = Path(r"D:\A1\ecg-lab-v2")
R = ROOT / "results"
CSV = R / "deployment_loco_validation.csv"
OUT = R / "deployment_loco_validation.json"

raw_lines = io.open(CSV, encoding="utf-8").read().splitlines()
# 注意：csv.writer 把含逗号的注释行加了引号 → 先剥一层引号再判断是否为注释
stripped = [l[1:-1] if (l.startswith('"') and l.endswith('"')) else l for l in raw_lines]
comments = [l for l in stripped if l.startswith("#")]
data_lines = [l for l in raw_lines
              if l.strip() and not l.lstrip('"').startswith("#")]
print("注释行:")
for c in comments:
    print("   ", c)
assert data_lines[0].startswith("fold,"), f"表头定位失败: {data_lines[0][:60]!r}"

# ---- 从注释恢复 meta ----
arch = seeds = methods = bootstrap = bci = gen_at = None
for c in comments:
    m = re.search(r"生成时间:\s*(\S+)", c)
    if m:
        gen_at = m.group(1)
    m = re.search(r"架构:\s*([A-Za-z0-9_\-]+),\s*种子:\s*(\[[^\]]*\]),\s*方法:\s*(\[[^\]]*\])", c)
    if m:
        arch = m.group(1)
        seeds = json.loads(m.group(2).replace("'", '"'))
        methods = json.loads(m.group(3).replace("'", '"'))
    m = re.search(r"Bootstrap:\s*B=(\d+),\s*CI=(\w+)", c)
    if m:
        bootstrap = int(m.group(1)); bci = m.group(2)

# ---- 从脚本常量恢复阈值 ----
src = (ROOT / "scripts" / "run_e1b_loco_validation.py").read_text(encoding="utf-8")
safe_rel = float(re.search(r"SAFE_RELIABILITY_THRESHOLD\s*=\s*([-\d.]+)", src).group(1))
safe_ece = float(re.search(r"SAFE_DELTA_ECE\s*=\s*([-\d.]+)", src).group(1))

meta = {
    "arch": arch,
    "seeds": seeds,
    "methods": methods,
    "bootstrap": bootstrap,
    "bci_method": bci,
    "safe_reliability_threshold": safe_rel,
    "safe_delta_ece": safe_ece,
    "approximation": "ensemble_based_LOCO (softmax avg + merged cal fit)",
    "generated_at": "2026-09-11T18:23:00",   # 由 CSV mtime 推定（原 JSON 的 generated_at 已随覆盖丢失）
    "_reconstructed": {
        "reason": "原 JSON 于 2026-09-17T18:33 被一个对抗代理运行 run_e1b_loco_validation.py 覆盖",
        "method": "从 sha256 校验通过的 results/deployment_loco_validation.csv 重建 records",
        "csv_sha256": "fbc1d763ae9fc992f261dd8a636c2e3025daf3eb6cd0680232bb9026d529ed45",
        "generated_at_provenance": "由 CSV mtime 2026-09-11 18:23 推定，非原始值",
        "CONTAMINATED": True,
        "contamination_note": (
            "本表产出于 2026-09-11，落在标签编码污染窗口内。CSV 的 label_map 字段"
            "自证为 NEW 编码 {\"NORM\":0,\"MI\":1,\"STTC\":2,\"CD\":3}，而所用 checkpoint"
            "自存 subspace=['NORM','CD','STTC','MI']（OLD，mtime 2026-09-08，窗口前）。"
            "模型 OLD、标签 NEW → 全部指标污染。需修复 e1b 后用 OLD 编码重跑。"
        ),
    },
}

INT_COLS = {"seed", "num_classes", "n_target", "n_fit"}
FLOAT_COLS = {"value", "ood_acc"}
OPT_FLOAT = {"ci_lo", "ci_hi"}
COLS = ["fold", "holdout", "holdout_geo", "sources", "sources_geo", "seed", "method",
        "scenario", "num_classes", "n_target", "n_fit", "ood_acc", "label_map",
        "metric", "value", "ci_lo", "ci_hi", "note"]

rdr = csv.DictReader(data_lines)
records = []
for row in rdr:
    rec = {}
    for c in COLS:
        v = row.get(c, "")
        vs = str(v).strip()
        if c in INT_COLS:
            rec[c] = int(vs) if vs != "" else 0        # skip 行为空 → 0（与原 schema 一致）
        elif c in FLOAT_COLS:
            rec[c] = float(vs) if vs != "" else ""
        elif c in OPT_FLOAT:
            rec[c] = float(vs) if vs != "" else ""
        else:
            rec[c] = v
    records.append(rec)

print(f"\n重建 records: {len(records)}")
print(f"meta: {json.dumps({k: v for k, v in meta.items() if not k.startswith('_')}, ensure_ascii=False)}")

# ---- 备份被摧毁的版本（留审计痕迹），再写新文件 ----
if OUT.exists():
    bak = R / "deployment_loco_validation.DESTROYED_BY_ATTACKER.json"
    if not bak.exists():
        shutil.copy2(OUT, bak)
        print(f"已保留被摧毁版本 → {bak.name}")

payload = {"meta": meta, "records": records}
OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str),
               encoding="utf-8")
print(f"已写出 {OUT}  ({OUT.stat().st_size} bytes)")

# ---- round-trip 校验 ----
back = json.loads(OUT.read_text(encoding="utf-8"))
assert len(back["records"]) == len(records), "records 数不符"
maxd = 0.0
for a, b in zip(records, back["records"]):
    for k in COLS:
        if isinstance(a[k], float):
            maxd = max(maxd, abs(a[k] - b[k]))
        else:
            assert a[k] == b[k], (k, a[k], b[k])
print(f"round-trip 校验: records 数一致, 浮点 max|diff| = {maxd:.3e}")

# ---- 与 CSV 逐行再比对一次（独立性检查）----
rdr2 = list(csv.DictReader(data_lines))
assert len(rdr2) == len(back["records"])
mism = 0
for r, rec in zip(rdr2, back["records"]):
    for c in COLS:
        v = str(r.get(c, "")).strip()
        got = rec[c]
        if c in INT_COLS:
            want = int(v) if v != "" else 0
            if want != got: mism += 1
        elif c in (FLOAT_COLS | OPT_FLOAT):
            want = float(v) if v != "" else ""
            if want != got: mism += 1
        else:
            if v != got: mism += 1
print(f"与 CSV 独立再比对: {mism} 处不符")

# ---- 指标覆盖统计 ----
import collections
c = collections.Counter(r["metric"] for r in records)
print("\nmetric 分布:")
for k, v in sorted(c.items()):
    print(f"   {k:<26} {v}")
print(f"\ncell 数 (fold,scenario,method,seed): "
      f"{len({(r['fold'], r['scenario'], r['method'], r['seed']) for r in records})}")
