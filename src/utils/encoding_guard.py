"""标签编码护栏（encoding guard）。

为什么需要它
------------
`label_map = {c: i for i, c in enumerate(SUBSPACE_CPSC)}` —— 元组的**顺序就是**
整数标签编码。仓库里有 10 处（7 个脚本）都写着同一句

    subspace = SUBSPACE_CPSC if num_classes == 4 else None

然后**用它重建数据集标签**。只要其中任何一处在「checkpoint 是旧编码训练、
常量已改成新编码」时被调用，标签就会与模型输出的索引语义错位
（MI↔CD 互换，占 CPSC 测试集 38.3% 样本），而所有指标仍然正常输出、
不报错、不警告。

2026-09-09~09-16 真实发生过一次，波及：
  * `checkpoints/e2_probs_cache/*.npz` —— 全部 62 份，mtime 09-10 12:30~12:40
  * 60 份 `l2_shift_results.json` 与两张 `l2_shift_full_*` 表（09-10~09-12）
  * 派生 `predictability_3arch.csv`
  * `results/deployment_loco_validation.*`（E1b，09-11，见
    `_LOCO_CONTAMINATION_NOTICE.md`）
参见 `results/_L2_SHIFT_CONTAMINATION_NOTICE.md`、
`results/_ABLATION_TS_COMPONENTS_CONTAMINATION_NOTICE.md` 与
`reports/NUMBER_PROVENANCE_SWEEP_2026-09-17.md`。

三条规则
--------
1. **以 checkpoint 自存的 `transfer_result.json:subspace` 为唯一权威编码。**
   全 60 格主分析该文件的 mtime = 2026-09-08，**早于污染窗口**，因此可信。
2. 运行时编码必须与之逐元素相等，否则 `raise`（绝不静默继续）。
3. 任何 probs/labels 缓存必须携带编码戳；无戳即拒绝（除非显式放行）。

`strict` 逃生舱
--------------
某些脚本加载的是**自己的** checkpoint 目录，那里**本来就没有**
`transfer_result.json`（例如 `run_e5_inception_lite.py` 的
`checkpoints/e5_inception_lite/`）。对这些调用点，用
`checkpoint_subspace(..., strict=False)`：**缺 provenance 时**退回运行时编码
并发出显式 `warnings.warn`；但**编码不一致时仍然 raise**（不一致永远不可接受）。

⚠️ `strict=False` 只能用于「该目录确实从不写 provenance」的调用点。
不要用它来绕过真实的不一致。
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path
from typing import Optional, Sequence, Tuple

from src.data.mapping import SUBSPACE_CPSC, SUPERCLASSES

__all__ = [
    "CACHE_STAMP_KEY",
    "checkpoint_subspace",
    "load_checkpoint_subspace",
    "encoding_stamp",
    "expected_stamp",
    "assert_cache_encoding",
    "assert_encoding_record",
    "stamp_into",
]

#: 缓存 npz 中记录编码的键名
CACHE_STAMP_KEY = "label_encoding"

#: `transfer_result.json` / `l2_shift_results.json` 中记录编码的键名
RECORD_STAMP_KEY = "label_encoding"


def encoding_stamp(num_classes: int, subspace: Optional[Sequence[str]]) -> str:
    """把一套标签编码规范化成可直接比较的字符串戳。

    * ``num_classes == len(SUPERCLASSES)``（5 类）→ 规范超类顺序 ``SUPERCLASSES``
      （builder 在 5 类时正是用它）。
    * 否则若给了 ``subspace`` → 子空间顺序本身（如 ``"NORM|CD|STTC|MI"``）。
    * 否则 → `RuntimeError`（**不能**退回某个默认戳，否则会误判为"已校验"）。
    """
    if num_classes == len(SUPERCLASSES):
        return "|".join(str(c) for c in SUPERCLASSES)
    if subspace is not None:
        return "|".join(str(c) for c in subspace)
    raise RuntimeError(
        f"[编码护栏] 无法生成编码戳：num_classes={num_classes} 且 subspace=None。\n"
        f"  只有 {len(SUPERCLASSES)} 类可以省略 subspace（走 SUPERCLASSES）。\n"
        f"  其余类别数必须显式给出 subspace，否则无法证明标签编码。")


def expected_stamp(num_classes: int, runtime_subspace: Optional[Sequence[str]]) -> str:
    """按运行时编码算出「应该」的戳。"""
    return encoding_stamp(num_classes, runtime_subspace)


def load_checkpoint_subspace(run_dir: Path) -> Optional[Tuple[str, ...]]:
    """只读取 checkpoint 自存的 `subspace`，**不做任何断言**。

    返回 `None` 表示该目录没有 `transfer_result.json`、或文件里没有
    `subspace` 字段（例如 5 类 checkpoint、或 toy/临时 run）。
    """
    tr = Path(run_dir) / "transfer_result.json"
    if not tr.exists():
        return None
    try:
        stored = json.loads(tr.read_text(encoding="utf-8")).get("subspace")
    except (json.JSONDecodeError, OSError):
        return None
    return tuple(stored) if stored else None


def checkpoint_subspace(
    run_dir: Path,
    num_classes: int,
    runtime_subspace: Optional[Sequence[str]],
    *,
    strict: bool = True,
) -> Optional[Tuple[str, ...]]:
    """取 checkpoint 自存的标签编码，并断言与运行时常量一致（编码护栏）。

    参数
    ----
    run_dir : 该 checkpoint 所在目录（须含 `transfer_result.json`）。
    num_classes : 本次评估要用的类别数。
    runtime_subspace : 运行时 `SUBSPACE_CPSC`（`num_classes == 4` 时），否则 None。
    strict : 见模块 docstring 的「`strict` 逃生舱」。默认 True = 缺 provenance
        即中断。仅在「该目录从不写 provenance」的调用点传 False。

    返回
    ----
    `num_classes == 4` 时返回 checkpoint 自存的子空间元组；否则返回 None
    （5 类走 `SUPERCLASSES`，不存在该错位风险）。

    异常
    ----
    `RuntimeError` ——
      * `strict=True` 且缺 `transfer_result.json`；
      * `strict=True` 且文件里没有 `subspace` 字段；
      * **无论 strict 取值**，自存编码 ≠ 运行时编码（不一致永远不可接受）。
    """
    if num_classes != 4:
        return None

    tr = Path(run_dir) / "transfer_result.json"

    if not tr.exists():
        if strict:
            raise RuntimeError(
                f"[编码护栏] 缺少 {tr}，无法确认该 checkpoint 的标签编码。\n"
                f"  拒绝在无 provenance 的情况下重算。\n"
                f"  参见 results/_L2_SHIFT_CONTAMINATION_NOTICE.md")
        warnings.warn(
            f"[编码护栏·宽松模式] {tr} 不存在，退回运行时编码 "
            f"{tuple(runtime_subspace)}。\n"
            f"  该目录从不写 provenance，因此无法用文件自证；"
            f"若这批 checkpoint 实际是另一套编码训练，结果仍会错位。",
            RuntimeWarning, stacklevel=2)
        return tuple(runtime_subspace) if runtime_subspace else None

    stored = json.loads(tr.read_text(encoding="utf-8")).get("subspace")

    if not stored:
        if strict:
            raise RuntimeError(
                f"[编码护栏] {tr} 未记录 `subspace`，无法判定编码。")
        warnings.warn(
            f"[编码护栏·宽松模式] {tr} 存在但未记录 `subspace`，"
            f"退回运行时编码 {tuple(runtime_subspace)}。",
            RuntimeWarning, stacklevel=2)
        return tuple(runtime_subspace) if runtime_subspace else None

    if tuple(stored) != tuple(runtime_subspace):
        raise RuntimeError(
            f"[编码护栏] 编码不一致，拒绝继续：\n"
            f"  checkpoint 自存 subspace = {tuple(stored)}\n"
            f"  运行时 SUBSPACE_CPSC     = {tuple(runtime_subspace)}\n"
            f"  两者不同意味着标签与 probs 会错位（MI↔CD 互换），"
            f"结果将是污染值。请先统一 src/data/mapping.py 的编码，"
            f"或改用与 checkpoint 一致的编码重建数据集。")

    return tuple(stored)


def assert_cache_encoding(
    cache_file: Path,
    data,
    num_classes: int,
    subspace: Optional[Sequence[str]],
    allow_unstamped: bool = False,
) -> None:
    """校验 probs/labels 缓存携带的编码戳。

    `data` 可以是 `np.load(...)` 返回的 NpzFile，也可以是普通 dict。
    无戳的旧缓存一律拒绝（它们正是 09-10 那一批），除非显式
    `allow_unstamped=True`（调用方必须已人工确认其编码）。
    """
    want = expected_stamp(num_classes, subspace)

    try:
        have = data[CACHE_STAMP_KEY]
    except (KeyError, IndexError, TypeError):
        have = None

    if have is None:
        if allow_unstamped:
            return
        raise RuntimeError(
            f"[编码护栏] {cache_file} 未携带编码戳 `{CACHE_STAMP_KEY}`。\n"
            f"  这类缓存写于护栏上线之前（已知 09-10 那一批为污染值），\n"
            f"  无法从文件本身判定其标签编码。请用 `--no-cache` 重建，\n"
            f"  或显式传 `--allow-unstamped-cache` 表示已人工确认。")

    have = str(have)
    if have != want:
        raise RuntimeError(
            f"[编码护栏] {cache_file} 的编码戳与当前口径不符：\n"
            f"  缓存 = {have}\n"
            f"  期望 = {want}\n"
            f"  继续使用会得到标签错位的结果。请用 `--no-cache` 重建。")


def assert_encoding_record(
    record: dict,
    num_classes: int,
    subspace: Optional[Sequence[str]],
    where: str,
) -> None:
    """校验 JSON 结果记录（如 `l2_shift_results.json`）携带的编码戳。

    用途：下游消费者（如 `step2_predictability.py`）在读入别处产出的 JSON 时，
    必须能证明该 JSON 是在哪套编码下算出来的。缺戳即拒绝。
    """
    want = expected_stamp(num_classes, subspace)
    have = record.get(RECORD_STAMP_KEY)
    if have is None:
        raise RuntimeError(
            f"[编码护栏] {where} 未记录 `{RECORD_STAMP_KEY}`，无法证明其标签编码。\n"
            f"  该文件可能产出于护栏上线之前（09-10~09-12 那一批为污染值）。\n"
            f"  参见 results/_L2_SHIFT_CONTAMINATION_NOTICE.md")
    if str(have) != want:
        raise RuntimeError(
            f"[编码护栏] {where} 的编码戳与当前口径不符：\n"
            f"  文件 = {have}\n"
            f"  期望 = {want}")


def stamp_into(payload: dict, num_classes: int,
               subspace: Optional[Sequence[str]]) -> dict:
    """把编码戳写进待落盘的 dict（原地修改并返回）。"""
    payload[RECORD_STAMP_KEY] = expected_stamp(num_classes, subspace)
    return payload
