"""
i18n 铸键工具 —— 扫描给定的 .py 文件，为其中的中文字符串字面量铸造
`owner.hash8` 键并写入 i18n/zh.json —
i18n key mint tool — AST-scan the given .py files for Chinese string
literals, mint their `owner.hash8` keys and write them into i18n/zh.json.

用法:
    python3 tools/i18n_mint.py platforms/chatgpt/mailbox.py
    python3 tools/i18n_mint.py customer_portal_api/app/routers/accounts.py core/registration/errors.py

规则（详见 _bmad-output/specs/spec-i18n/catalog-conventions.md）:
    - hash8 = sha256(text.encode()).hexdigest()[:8]；key = f"{owner}.{hash8}"。
    - owner 由文件路径推导：platforms/<x>/... 取 <x>；否则取路径第一段
      （下划线折叠为驼峰，如 customer_portal_api -> customerPortalApi）；
      根目录文件取自身文件名（不含扩展名）。
    - 只扫描命令行给出的文件，不做目录遍历；f-string 片段与文档字符串不算候选。
    - 一次运行内两个不同文本撞在同一个 owner.hash8 上会中止整次运行、不写入
      任何内容；已存在的键永远保持不变，即使它当前的值已经不再匹配新的哈希。

Rules (see _bmad-output/specs/spec-i18n/catalog-conventions.md for the full
authoring convention this tool implements):
    - hash8 = sha256(text.encode()).hexdigest()[:8]; key = f"{owner}.{hash8}".
    - `owner` is derived from the file path: platforms/<x>/... takes <x>;
      otherwise the path's first segment (snake_case folded to camelCase,
      e.g. customer_portal_api -> customerPortalApi); a root-level file uses
      its own stem.
    - Only the files given on the command line are scanned -- no directory
      walk. f-string fragments and docstrings are never candidates.
    - Two distinct texts colliding on the same owner.hash8 within one run
      aborts the whole run before any write; an already-existing key is
      always left untouched, even if its stored value no longer matches a
      fresh hash of the current source text.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import io
import json
import re
import sys
import tokenize
from pathlib import Path
from typing import Iterator

__all__ = ["main"]


class MintError(Exception):
    """一个可预期的、面向操作者的错误 —— 由 main() 打印到 stderr 并以退出码 1 结束，
    而不是暴露一条裸的 traceback ——
    An expected, operator-facing error -- caught by main(), printed to
    stderr, and turned into exit code 1 instead of a raw traceback.
    """

# U+4E00-U+9FFF：中日韩统一表意文字基本区，本工具的"候选"判定标准 —
# The CJK Unified Ideographs basic block; this is the candidate test.
_HAN_RE = re.compile("[一-鿿]")

# 把 snake_case 的一段折叠为 camelCase；纯字母数字（core/api/tools/...）原样通过 —
# Folds one snake_case segment into camelCase; a plain alnum segment
# (core/api/tools/...) passes through unchanged since it has no underscore.
_SNAKE_SEGMENT_RE = re.compile(r"_([a-zA-Z0-9])")

_OWNER_RE = re.compile(r"[a-z][a-zA-Z0-9]*")

# 字符串字面量前缀（r/b/f 及其组合），位于引号之前 —
# A string literal's prefix (r/b/f and combinations), before the quote.
_STRING_PREFIX_RE = re.compile(r"^[a-zA-Z]*")

_DOCSTRING_HOLDER_TYPES = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)


def _project_root() -> Path:
    """项目根目录 —— tools/ 的上一级 —— Project root: one level above tools/."""
    return Path(__file__).resolve().parent.parent


def _zh_json_path(root: Path) -> Path:
    """zh.json 的路径 —— i18n/zh.json under the project root."""
    return root / "i18n" / "zh.json"


def _resolve_source_path(file_arg: str, root: Path) -> Path:
    """把命令行给出的文件参数相对项目根目录解析为绝对路径 —
    Resolve a CLI file argument to an absolute path, relative to the project root.
    """
    path = Path(file_arg)
    if not path.is_absolute():
        path = root / path
    return path.resolve()


def _fold_snake_to_camel(segment: str) -> str:
    """snake_case 折叠为 camelCase；无下划线的名字原样返回 —
    Fold snake_case to camelCase; a name with no underscore passes through unchanged.
    """
    return _SNAKE_SEGMENT_RE.sub(lambda m: m.group(1).upper(), segment)


def _owner_for(path: Path, root: Path) -> str:
    """按路径推导 owner —— Derive `owner` from `path`, relative to `root`.

    platforms/<x>/... 取第二段 <x>；否则取第一段（下划线折叠为驼峰）；
    根目录文件（只有一段）取自身文件名（不含扩展名）——
    Under platforms/<x>/... the owner is <x>; otherwise it is the path's
    first segment (snake_case folded to camelCase); a root-level file (a
    single path segment) uses its own stem.
    """
    rel = path.resolve().relative_to(root.resolve())
    parts = rel.parts
    if len(parts) == 1:
        segment = Path(parts[0]).stem
    elif parts[0] == "platforms":
        segment = parts[1]
        if len(parts) == 2:
            # platforms/foo.py 直接放在 platforms/ 下，没有平台子目录 ——
            # a file directly under platforms/ with no platform subdirectory;
            # fall back to its own stem rather than keeping ".py" in the name.
            segment = Path(segment).stem
    else:
        segment = parts[0]

    owner = _fold_snake_to_camel(segment)
    if not _OWNER_RE.fullmatch(owner):
        raise MintError(f"派生的 owner 不合法 (invalid derived owner): {owner!r}")
    return owner


def _docstring_constant_ids(tree: ast.AST) -> set[int]:
    """收集所有文档字符串常量节点的 id —— Module/ClassDef/FunctionDef/
    AsyncFunctionDef body 的第一条语句，如果是字符串字面量表达式 ——
    Collect the id() of every docstring Constant node: the first statement
    of a Module/ClassDef/FunctionDef/AsyncFunctionDef body, when it is a
    bare string-literal expression.
    """
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, _DOCSTRING_HOLDER_TYPES):
            body = node.body
            if body and isinstance(body[0], ast.Expr):
                value = body[0].value
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    ids.add(id(value))
    return ids


def _walk_skip_fstring_fragments(node: ast.AST) -> Iterator[ast.AST]:
    """类似 ast.walk，但完全不深入 ast.JoinedStr（f-string）子树 ——
    静态文本片段和 {expr} 内部的表达式都算"在 f-string 内部"，一律跳过 ——
    Like ast.walk, but never descends into an ast.JoinedStr (f-string)
    subtree at all -- both its static text fragments and whatever sits
    inside a {expr} count as "inside" the f-string and are skipped.
    """
    yield node
    if isinstance(node, ast.JoinedStr):
        return
    for child in ast.iter_child_nodes(node):
        yield from _walk_skip_fstring_fragments(child)


def _iter_candidates(tree: ast.AST) -> Iterator[tuple[int, str]]:
    """扫描 AST，产出含至少一个汉字的字符串字面量候选 (行号, 文本)；跳过
    f-string 片段与文档字符串 ——
    Walk the AST and yield (lineno, text) for every Han-bearing string
    literal candidate, skipping f-string fragments and docstrings.
    """
    docstring_ids = _docstring_constant_ids(tree)
    for node in _walk_skip_fstring_fragments(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        if id(node) in docstring_ids:
            continue
        if _HAN_RE.search(node.value):
            yield node.lineno, node.value


def _is_fstring_token(tok_string: str) -> bool:
    """判断一个 STRING 记号是否带 f/F 前缀 —— 3.12 以前，f-string 整体只产出
    一个 STRING 记号，前缀是唯一能看出它是 f-string 的地方 ——
    Whether a STRING token carries an f/F prefix. Before 3.12, an f-string
    tokenizes as a single STRING token, and the prefix is the only way to
    tell it apart from a plain string.
    """
    return "f" in _STRING_PREFIX_RE.match(tok_string).group(0).lower()


def _iter_adjacent_fstring_warnings(source: str) -> Iterator[tuple[int, str]]:
    """用 tokenize 找出隐式与 f-string 相邻拼接、且含汉字的普通字符串字面量 ——
    Python 的语法把 `"你好" f"{x}"` 和 `f"你好{x}"` 解析成字节相同的
    ast.JoinedStr，AST 层面无法区分；但 tokenize 层面能看出前者是两个独立
    的记号（一个 STRING，一个 f-string），后者是一个 —— 产出 (行号, 文本)。
    Portable across the pre-3.12 single-STRING-token and 3.12+
    FSTRING_START/MIDDLE/END tokenizations of an f-string. Python's grammar
    parses `"你好" f"{x}"` and `f"你好{x}"` into byte-identical ast.JoinedStr
    nodes -- the AST cannot tell them apart -- but tokenize can, since the
    former is two separate tokens (a STRING, then an f-string) and the
    latter is one. Yields (lineno, text) for each Han-bearing plain literal
    caught in an implicit concatenation run that also contains an f-string.
    """
    fstring_start = getattr(tokenize, "FSTRING_START", None)
    fstring_end = getattr(tokenize, "FSTRING_END", None)

    tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))

    run: list[tuple[str, int, str | None]] = []

    def flush() -> Iterator[tuple[int, str]]:
        if any(kind == "fstring" for kind, _, _ in run):
            for kind, lineno, text in run:
                if kind == "plain" and _HAN_RE.search(text):
                    yield lineno, text

    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.type == tokenize.STRING:
            if _is_fstring_token(tok.string):
                run.append(("fstring", tok.start[0], None))
            else:
                run.append(("plain", tok.start[0], ast.literal_eval(tok.string)))
            i += 1
        elif fstring_start is not None and tok.type == fstring_start:
            lineno = tok.start[0]
            depth = 1
            i += 1
            while i < len(tokens) and depth:
                if tokens[i].type == fstring_start:
                    depth += 1
                elif tokens[i].type == fstring_end:
                    depth -= 1
                i += 1
            run.append(("fstring", lineno, None))
        elif tok.type in (tokenize.NL, tokenize.COMMENT):
            i += 1  # 不打断隐式拼接串 —— does not break a concatenation run
        else:
            yield from flush()
            run = []
            i += 1
    yield from flush()


def _load_existing_zh(path: Path) -> dict:
    """读取已有的 zh.json；文件不存在时视为空目录 ——
    Load the existing zh.json; a missing file is treated as an empty catalog.
    """
    try:
        text = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise MintError(f"{path} 不是合法的 JSON (not valid JSON): {exc}") from exc
    if not isinstance(data, dict):
        raise MintError(f"{path} 的顶层结构不是一个对象 (top level is not an object): {type(data).__name__}")
    return data


def _hash8(text: str) -> str:
    """冻结的哈希规则 —— catalog-conventions.md:64 的 sha256(...)[:8] ——
    The frozen hash rule: sha256(text)[:8], per catalog-conventions.md:64.
    """
    return hashlib.sha256(text.encode()).hexdigest()[:8]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="i18n_mint.py",
        description=(
            "扫描给定的 .py 文件，为其中的中文字符串铸造 owner.hash8 键并写入 "
            "i18n/zh.json —— Scan the given .py files, mint owner.hash8 keys "
            "for their Chinese strings, and write them into i18n/zh.json."
        ),
    )
    parser.add_argument(
        "files",
        nargs="+",
        help=(
            "要扫描的 .py 文件路径（相对项目根目录或绝对路径）—— "
            ".py file paths to scan (relative to the project root, or absolute)"
        ),
    )
    args = parser.parse_args(argv)

    root = _project_root()
    zh_path = _zh_json_path(root)

    # 按 (owner, hash8) 分组，组内再按 text 分组，用来侦测同一次运行内的碰撞 ——
    # Group by (owner, hash8); sub-group by text to detect same-run collisions.
    groups: dict[tuple[str, str], dict[str, list[str]]] = {}

    for file_arg in args.files:
        resolved = _resolve_source_path(file_arg, root)
        try:
            rel_display = resolved.relative_to(root).as_posix()
        except ValueError:
            rel_display = str(resolved)

        try:
            source = resolved.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=rel_display)
            owner = _owner_for(resolved, root)
        except (OSError, UnicodeDecodeError, SyntaxError, MintError) as exc:
            print(f"错误：无法处理 {rel_display} (failed to process {rel_display}): {exc}", file=sys.stderr)
            return 1

        try:
            adjacent_warnings = list(_iter_adjacent_fstring_warnings(source))
        except (tokenize.TokenError, IndentationError, SyntaxError):
            adjacent_warnings = []
        for lineno, text in adjacent_warnings:
            print(
                f"警告：{rel_display}:{lineno} 处的中文字面量与相邻 f-string 隐式拼接为一体，"
                f"铸键工具无法安全提取，需要人工处理：{text!r} —— "
                f"warning: Chinese literal at {rel_display}:{lineno} is implicitly "
                f"concatenated with an adjacent f-string and must be extracted manually: {text!r}",
                file=sys.stderr,
            )

        for lineno, text in _iter_candidates(tree):
            hash8 = _hash8(text)
            by_text = groups.setdefault((owner, hash8), {})
            by_text.setdefault(text, []).append(f"{rel_display}:{lineno}")

    collisions = {key: by_text for key, by_text in groups.items() if len(by_text) > 1}
    if collisions:
        print(
            "错误：同一次运行内出现哈希冲突，未写入任何内容 —— "
            "Hash collision within this run; nothing was written:",
            file=sys.stderr,
        )
        for owner, hash8 in sorted(collisions):
            by_text = collisions[(owner, hash8)]
            print(f"  {owner}.{hash8}:", file=sys.stderr)
            for text in sorted(by_text):
                locations = ", ".join(sorted(by_text[text]))
                print(f"    {text!r} @ {locations}", file=sys.stderr)
        return 1

    try:
        existing = _load_existing_zh(zh_path)

        minted = 0
        already_present = 0
        for (owner, hash8), by_text in groups.items():
            # 碰撞已经在上面排除，这里 by_text 必然只有一个 text ——
            # Collisions were already excluded above, so by_text has exactly one text.
            (text,) = by_text.keys()
            owner_map = existing.setdefault(owner, {})
            if not isinstance(owner_map, dict):
                raise MintError(
                    f"{zh_path} 中 owner {owner!r} 对应的值不是一个对象 "
                    f"(the value for owner {owner!r} is not an object): {type(owner_map).__name__}"
                )
            if hash8 in owner_map:
                already_present += 1
                continue
            owner_map[hash8] = text
            minted += 1
    except MintError as exc:
        print(f"错误 (error): {exc}", file=sys.stderr)
        return 1

    if minted:
        zh_path.parent.mkdir(parents=True, exist_ok=True)
        zh_path.write_text(
            json.dumps(existing, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    print(
        f"新增 {minted} 个键，{already_present} 个已存在（未作改动）—— "
        f"minted {minted} new key(s), {already_present} already present (left untouched)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
