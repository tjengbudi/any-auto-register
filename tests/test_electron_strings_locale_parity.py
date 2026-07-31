"""`electron/main.js` `STRINGS.zh` / `STRINGS.en` 键集一致性测试 —
Key-parity test for `electron/main.js`'s `STRINGS.zh` / `STRINGS.en` blocks.

本文件只读取 `electron/main.js` 的源文本，从 `STRINGS` 对象里结构化地提取
`zh: { ... }` 与 `en: { ... }`两个代码块各自的顶层键名集合（通过匹配已知的
块边界与花括号配对，而不是硬编码当前的 11 个键名），然后断言两个集合相等。
不执行、不 `require`、不解析整个 JS 文件为 AST —— 遵循
`tests/test_i18n_bundle_files.py` 的既有模式：用 Python 测试对非 Python
源文件做文本层面的断言。

刻意的范围边界（AD-18）：本测试只检查 `electron/main.js` 这一个文件内部
`zh`/`en` 两个 locale 块之间的键集合是否一致，绝不会去比较
`i18n/*.json` 或 `frontend/src/i18n/*.ts` 里的键/字符串 —— 根据本项目的
架构决策 AD-18，Electron 主进程无法 import 这两个目录下的任何一个目录
（它们分别属于后端 Python 进程和前端渲染进程/构建产物），所以
`STRINGS` 与那两个目录的键空间在架构上是彼此不相交的。把它们放在一起比较
不会发现任何有效的问题，反而会把架构上明确禁止的耦合关系错误地编码进
测试里。因此这里的窄范围是有意为之，不是遗漏。

This module reads `electron/main.js`'s source text only, structurally
extracts the top-level key sets of the `zh: { ... }` and `en: { ... }`
blocks inside the `STRINGS` object (by matching the known block boundaries
and brace pairing, not by hard-coding the current 11 key names), and
asserts the two key sets are equal. It does not execute, `require`, or
parse the whole file as a JS AST -- following `tests/test_i18n_bundle_files.py`'s
established pattern of a Python test making text-level assertions about a
non-Python source file.

Deliberate scope boundary (AD-18): this test only checks key-set parity
between the `zh` and `en` locale blocks *within this one file*. It never
compares against `i18n/*.json` or `frontend/src/i18n/*.ts`, because under
this project's architecture decision AD-18 the Electron main process
cannot import either catalog (one belongs to the backend Python process,
the other to the frontend renderer/build output) -- so `STRINGS`'s key
space is structurally disjoint from both of those catalogs' key spaces.
Comparing across that boundary would have nothing valid to compare and
would encode a coupling the architecture forbids. The narrow scope here
is intentional, not an oversight.
"""
from __future__ import annotations

import re
from pathlib import Path

MAIN_JS_PATH = Path(__file__).resolve().parent.parent / "electron" / "main.js"

# Matches the start of the STRINGS object literal itself, so locale blocks
# are located only within its span -- a `zh`/`en`-named property elsewhere
# in the file (there is none today, but nothing statically prevents one)
# cannot be misattributed to the wrong object.
_STRINGS_OBJECT_START_RE = re.compile(r"^const STRINGS = \{\s*$", re.MULTILINE)

# Matches the start of each named locale block inside the STRINGS object,
# e.g. "  zh: {" or "  en: {" -- capturing the locale name and the position
# right after its opening brace.
_LOCALE_BLOCK_START_RE = re.compile(r"^\s*(?P<locale>\w+):\s*\{\s*$", re.MULTILINE)

# Matches a top-level property-start line directly inside a locale block,
# e.g. "    splashMessage: '...'" or "    backendTimeout: (total) => ...".
# Anchored on the 4-space indentation used for properties directly inside
# a `zh`/`en` block (one level deeper than the block's own `zh: {` line),
# so it does not match array literal elements like the strings inside
# `updateAvailableButtons: [...]`, which are indented further and don't
# have a `<identifier>:` property-start shape at that position anyway.
_PROPERTY_KEY_RE = re.compile(r"^    (\w+):", re.MULTILINE)


def _extract_braced_block(source: str, pos: int) -> str:
    """Return the raw text between an already-matched opening `{` position
    and its matching closing `}` (matched by brace depth, not by a fixed
    line count), so extraction tracks the real file rather than a frozen
    line-range copy."""
    depth = 1
    block_start = pos
    while depth > 0:
        next_open = source.find("{", pos)
        next_close = source.find("}", pos)
        assert next_close != -1, "unbalanced braces while scanning a block in " + str(MAIN_JS_PATH)
        if next_open != -1 and next_open < next_close:
            depth += 1
            pos = next_open + 1
        else:
            depth -= 1
            pos = next_close + 1
    return source[block_start : pos - 1]


def _extract_strings_object(source: str) -> str:
    """Return the raw text of the `const STRINGS = { ... }` object literal."""
    start_match = _STRINGS_OBJECT_START_RE.search(source)
    assert start_match is not None, f"could not find `const STRINGS = {{` in {MAIN_JS_PATH}"
    return _extract_braced_block(source, start_match.end())


def _extract_locale_block(strings_object_text: str, locale: str) -> str:
    """Return the raw text between a `<locale>: {` line and its matching
    closing `}` (matched by brace depth, not by a fixed line count), so the
    extraction tracks the real file rather than a frozen line-range copy.
    Searches only within the already-scoped `STRINGS` object text, so a
    same-named property elsewhere in the file cannot be misattributed."""
    start_match = None
    for m in _LOCALE_BLOCK_START_RE.finditer(strings_object_text):
        if m.group("locale") == locale:
            start_match = m
            break
    assert start_match is not None, (
        f"could not find a `{locale}: {{` block start inside STRINGS in {MAIN_JS_PATH}"
    )
    return _extract_braced_block(strings_object_text, start_match.end())


def _extract_top_level_keys(block_text: str) -> set[str]:
    """Return the set of top-level property names in a locale block's text."""
    return set(_PROPERTY_KEY_RE.findall(block_text))


class TestElectronStringsLocaleParity:
    def test_zh_and_en_key_sets_match(self):
        """Guards against DW-11's drift mode: a key added to only one of
        `STRINGS.zh` / `STRINGS.en` in `electron/main.js` would otherwise
        silently diverge with no lint, script, or test catching it. Reads
        the real shipped file (not a hard-coded copy) so this tracks future
        edits to `electron/main.js` automatically."""
        source = MAIN_JS_PATH.read_text(encoding="utf-8")
        strings_object_text = _extract_strings_object(source)

        zh_block = _extract_locale_block(strings_object_text, "zh")
        en_block = _extract_locale_block(strings_object_text, "en")

        zh_keys = _extract_top_level_keys(zh_block)
        en_keys = _extract_top_level_keys(en_block)

        assert zh_keys, f"no top-level keys extracted from the `zh` block in {MAIN_JS_PATH}"
        assert en_keys, f"no top-level keys extracted from the `en` block in {MAIN_JS_PATH}"

        only_in_zh = zh_keys - en_keys
        only_in_en = en_keys - zh_keys
        assert zh_keys == en_keys, (
            "STRINGS.zh and STRINGS.en key sets diverged in electron/main.js: "
            f"only in zh={sorted(only_in_zh)!r}, only in en={sorted(only_in_en)!r}"
        )
