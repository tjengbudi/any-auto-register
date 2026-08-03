"""
i18n 校验工具 —— 扫描固定的源码根目录，找出所有携带汉字的 `X.log(...)` 调用站点，
和已冻结的基线文件比对，只对"新出现"的站点报错 ——
i18n lint tool — AST-scans the fixed source roots for any `X.log(...)` call
site carrying Han (Chinese) characters in a string/f-string literal argument,
compares them against a frozen baseline file, and fails only on a genuinely
*new* site.

用法 (usage):
    python3 tools/i18n_lint.py                  # 检查 (check mode); exit 0 = 无新增站点
    python3 tools/i18n_lint.py --update-baseline # 用当前代码树重新生成基线文件

规则 (rules):
    - 只扫描 platforms/、core/、application/、providers/、infrastructure/、api/
      这六个固定根目录下的 .py 文件，排除任意路径分量为 "tests" 的文件——
      Only .py files under the six fixed roots above are scanned, excluding
      any path with a "tests" path component.
    - 站点判定：任意形如 `X.log(...)` 的调用（`ast.Call`，其 `func` 是
      `ast.Attribute(attr="log")`），其某个字面量参数（`ast.Constant` 字符串，
      或 f-string `ast.JoinedStr` 内的 `ast.Constant` 片段）包含至少一个汉字
      （`_HAN_RE`，与 tools/i18n_mint.py 的 `_HAN_RE` 完全一致）——
      A site is any `X.log(...)` call whose func is `Attribute(attr="log")`
      and which carries a Han character in a string-literal or f-string
      literal-segment argument.
    - 每个站点由 (相对文件路径, sha256(literal_text).hexdigest()) 唯一标识——
      内容寻址而非行号寻址，避免同文件内无关的上方编辑造成假的"新增站点" ——
      Each site is identified by (relative_file_path, sha256(text).hexdigest())
      -- content-addressed, not line-addressed, so an unrelated edit above a
      call site never produces a false "new site" the next time this runs.
    - 本工具只和检查入基线文件比较，不做任何 git diff / git history 的判断——
      This tool only ever compares against the checked-in baseline file; it
      never inspects git diff/history.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
from pathlib import Path

__all__ = ["scan", "load_baseline", "find_unbaselined", "main"]

# U+4E00-U+9FFF：中日韩统一表意文字基本区 —— 与 tools/i18n_mint.py 的 _HAN_RE 一致 —
# The CJK Unified Ideographs basic block, matching tools/i18n_mint.py's _HAN_RE.
_HAN_RE = re.compile("[一-鿿]")

# 固定扫描的源码根目录 —— Fixed source roots to scan.
_SCAN_ROOTS = ("platforms", "core", "application", "providers", "infrastructure", "api")

_BASELINE_REL_PATH = "tests/fixtures/chinese_log_baseline.json"


def _project_root() -> Path:
    """项目根目录 —— tools/ 的上一级 —— Project root: one level above tools/."""
    return Path(__file__).resolve().parent.parent


def _baseline_path(root: Path) -> Path:
    return root / _BASELINE_REL_PATH


def _iter_source_files(root: Path):
    """产出所有待扫描的 .py 文件的绝对路径 —— Yield every .py file to scan.

    只遍历固定的六个根目录，排除任何路径分量为 "tests" 的文件 ——
    Only walks the six fixed roots, excluding any file with a "tests" path
    component.
    """
    for root_name in _SCAN_ROOTS:
        base = root / root_name
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            rel_parts = path.relative_to(root).parts
            if "tests" in rel_parts:
                continue
            yield path


def _han_text_from_arg(node: ast.expr) -> str | None:
    """如果这个参数节点携带汉字文本，返回该文本；否则返回 None ——
    Return the Han-bearing text carried by this argument node, or None.

    处理 ast.Constant 字符串字面量，以及 f-string (ast.JoinedStr) 内部的
    ast.Constant 片段（拼接后再判定/取用整体文本）——
    Handles plain ast.Constant string literals, and f-string (ast.JoinedStr)
    Constant segments (joined together before testing/using the whole text).
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value if _HAN_RE.search(node.value) else None
    if isinstance(node, ast.JoinedStr):
        parts = [
            value.value
            for value in node.values
            if isinstance(value, ast.Constant) and isinstance(value.value, str)
        ]
        text = "".join(parts)
        return text if _HAN_RE.search(text) else None
    return None


def _iter_log_call_sites(tree: ast.AST):
    """产出 (行号, 文本) —— 每个携带汉字的 X.log(...) 调用站点 ——
    Yield (lineno, text) for every Han-bearing X.log(...) call site.
    """
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "log"):
            continue
        for arg in (*node.args, *(kw.value for kw in node.keywords)):
            text = _han_text_from_arg(arg)
            if text is not None:
                yield node.lineno, text


def _hash_text(text: str) -> str:
    """站点标识用的哈希 —— sha256(text).hexdigest()（全量，非 mint 工具的截断
    8 位）—— The site-identity hash: full sha256(text).hexdigest() (not the
    8-char truncation tools/i18n_mint.py uses).
    """
    return hashlib.sha256(text.encode()).hexdigest()


def scan(root: Path | None = None) -> dict[str, list[tuple[int, str, str]]]:
    """扫描所有源码根目录，返回 {相对路径: [(行号, 文本, hash), ...]} ——
    Scan every source root; return {relative_path: [(lineno, text, hash), ...]}.

    不可解析/不可读的文件被静默跳过 —— 这是一个手动运行的开发工具，不是 CI 强制
    关口，见 spec 的 Design Notes ——
    Unparseable/unreadable files are silently skipped -- this is a manually
    run dev tool, not a CI-enforced gate.
    """
    if root is None:
        root = _project_root()

    results: dict[str, list[tuple[int, str, str]]] = {}
    for path in _iter_source_files(root):
        rel = path.relative_to(root).as_posix()
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=rel)
        except (OSError, UnicodeDecodeError, SyntaxError):
            continue

        sites = [
            (lineno, text, _hash_text(text))
            for lineno, text in _iter_log_call_sites(tree)
        ]
        if sites:
            results[rel] = sites
    return results


def load_baseline(root: Path | None = None) -> dict[str, list[str]]:
    """读取基线文件；文件不存在时视为空基线 ——
    Load the baseline file; a missing file is treated as an empty baseline.
    """
    if root is None:
        root = _project_root()
    path = _baseline_path(root)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    return json.loads(text)


def find_unbaselined(
    scanned: dict[str, list[tuple[int, str, str]]],
    baseline: dict[str, list[str]],
) -> list[tuple[str, int, str, str]]:
    """比对扫描结果与基线，返回未在基线中出现的站点列表
    [(相对路径, 行号, 文本, hash), ...] ——
    Diff the scan against the baseline; return unbaselined sites as
    [(relative_path, lineno, text, hash), ...].
    """
    unbaselined: list[tuple[str, int, str, str]] = []
    for rel, sites in scanned.items():
        known_hashes = set(baseline.get(rel, []))
        for lineno, text, text_hash in sites:
            if text_hash not in known_hashes:
                unbaselined.append((rel, lineno, text, text_hash))
    return unbaselined


def _write_baseline(root: Path, scanned: dict[str, list[tuple[int, str, str]]]) -> dict[str, list[str]]:
    """写入基线文件，并返回实际写入的（去重后的）基线内容 ——
    Write the baseline file and return the (deduplicated) content actually written,
    so callers report a count that matches what is on disk, not the raw pre-dedup scan.
    """
    baseline = {
        rel: sorted({text_hash for _, _, text_hash in sites})
        for rel, sites in scanned.items()
    }
    path = _baseline_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(baseline, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return baseline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="i18n_lint.py",
        description=(
            "扫描固定源码根目录下携带汉字的 X.log(...) 调用站点，和基线文件比对 —— "
            "Scan the fixed source roots for Han-bearing X.log(...) call sites "
            "and compare them against the baseline file."
        ),
    )
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help=(
            "用当前代码树重新生成基线文件，而不是检查 —— "
            "Regenerate the baseline file from the current tree instead of checking."
        ),
    )
    args = parser.parse_args(argv)

    root = _project_root()
    scanned = scan(root)

    if args.update_baseline:
        written = _write_baseline(root, scanned)
        site_count = sum(len(hashes) for hashes in written.values())
        print(
            f"已重新生成基线 (baseline regenerated)：{len(written)} 个文件，"
            f"{site_count} 个站点 ({len(written)} files, {site_count} sites)"
        )
        return 0

    baseline = load_baseline(root)
    unbaselined = find_unbaselined(scanned, baseline)
    if not unbaselined:
        print("OK：未发现新的中文 .log(...) 调用站点 (no new Han-bearing .log(...) sites found)")
        return 0

    print(
        "错误：发现未在基线中登记的中文 .log(...) 调用站点 (unbaselined Han-bearing "
        ".log(...) call sites found):",
        file=sys.stderr,
    )
    for rel, lineno, text, _ in sorted(unbaselined):
        print(f"  {rel}:{lineno}: {text!r}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
