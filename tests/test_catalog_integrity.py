"""Catalog integrity tests: zh.json is authoritative, en/vi orphans fail the
suite, translation gaps only ever show up in a structured coverage report,
and every zh key the code actually reads must carry a non-empty en value.

Story 1.4 (plus DW-29's reference-aware parity follow-up). Reads
i18n/zh.json, i18n/en.json, i18n/vi.json directly via `json.load` and never
imports the `i18n` package or uses the `client` fixture from conftest.py --
see test_does_not_use_i18n_module_or_client_fixture below for an automated
check of that constraint.

DW-29 note: `vi` is deliberately exempt from the reference-aware parity
check below -- ARCHITECTURE-SPINE.md:205 freezes it as structure-with-no-
values for this release, so a referenced key having no `vi` value is
expected, not a defect. See test_every_referenced_zh_key_has_a_non_empty_en_translation.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import pytest

# Mirrors i18n/__init__.py's own `base = Path(__file__).resolve().parent`
# convention, without importing i18n: this file lives in tests/, so the
# catalog package is one directory up and over.
_CATALOG_DIR = Path(__file__).resolve().parent.parent / "i18n"

_SOURCE_LOCALE = "zh"
_TARGET_LOCALES = ("en", "vi")


def _catalog_path(locale: str) -> Path:
    return _CATALOG_DIR / f"{locale}.json"


def _load_catalog(locale: str) -> dict:
    # utf-8-sig matches i18n/__init__.py's own decoding convention, so a
    # BOM-prefixed catalog that the production loader accepts doesn't
    # spuriously fail this integrity check.
    return json.loads(_catalog_path(locale).read_text(encoding="utf-8-sig"))


def _load_all_catalogs() -> dict[str, dict]:
    """Load zh/en/vi directly off disk. No i18n.load(), no cache."""
    return {locale: _load_catalog(locale) for locale in (_SOURCE_LOCALE, *_TARGET_LOCALES)}


def _flatten(catalog: dict) -> dict[str, str]:
    """Walk the shipped {owner: {subkey: value}} shape into {"owner.subkey": value}."""
    flat: dict[str, str] = {}
    for owner, subkeys in catalog.items():
        if not isinstance(subkeys, dict):
            continue
        for subkey, value in subkeys.items():
            flat[f"{owner}.{subkey}"] = value
    return flat


def _find_orphans(reference: dict[str, str], candidate: dict[str, str]) -> set[str]:
    """Keys present in `candidate` with no counterpart in `reference`."""
    return set(candidate) - set(reference)


def _collect_orphans(zh_flat: dict[str, str], target_flats: dict[str, dict[str, str]]) -> list[str]:
    """"locale:key" for every orphan, across every target locale, sorted for a stable message."""
    found: list[str] = []
    for locale in sorted(target_flats):
        found.extend(f"{locale}:{key}" for key in sorted(_find_orphans(zh_flat, target_flats[locale])))
    return found


def _build_coverage_report(
    zh_flat: dict[str, str], target_flats: dict[str, dict[str, str]]
) -> dict[str, dict[str, int]]:
    """Per-locale {"translated": N, "total": M}; total is len(zh_flat).

    A zh key counts as translated only if the target locale has it with a
    non-empty string value -- i18n.t() treats "" as untranslated and falls
    back to zh, so counting it here would misreport real coverage.
    """
    total = len(zh_flat)
    report: dict[str, dict[str, int]] = {}
    for locale, flat in target_flats.items():
        translated = sum(
            1 for key in zh_flat if isinstance(flat.get(key), str) and flat.get(key) != ""
        )
        report[locale] = {"translated": translated, "total": total}
    return report


# catalog-conventions.md's Python key shape: machine-minted `<owner>.<hash8>`,
# hash8 = lowercase hex, width 8. TypeScript keys are hand-authored camelCase
# in a disjoint namespace, so this pattern never matches a TS-owned key --
# it is scanned for anyway (per DW-29's decision) in case a TS/TSX call site
# ever forwards a Python-owned key through, e.g., a backend-rendered payload.
# Matches single-, double- and backtick-quoted literals; the (?P=quote)
# backreference requires the closing quote to match the opening one, so
# mismatched-quote prose (e.g. an apostrophe followed later by a stray
# double quote) can't be misread as a key literal. A key built via
# concatenation, an f-string, or a variable is out of reach for a textual
# scan and stays out of scope, same as the rest of this literal-based check.
_KEY_REFERENCE_PATTERN = re.compile(
    r"""(?P<quote>["'`])(?P<key>[A-Za-z][A-Za-z0-9_]*\.[0-9a-f]{8})(?P=quote)"""
)

_REFERENCE_SCAN_ROOT = _CATALOG_DIR.parent
_REFERENCE_SOURCE_EXTENSIONS = (".py", ".ts", ".tsx")
# Vendored deps, VCS internals, caches and build output hold no call sites of
# our own and are large enough (.venv, node_modules) to be worth pruning
# during the walk rather than filtering after listing every file.
_REFERENCE_EXCLUDED_DIR_NAMES = {
    "node_modules", ".git", "__pycache__", "tests", ".venv", ".pytest_cache", "dist", "build",
}


def _iter_reference_source_files(root: Path):
    """Yield non-test .py/.ts/.tsx files under root, pruning vendor/build/test dirs."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in _REFERENCE_EXCLUDED_DIR_NAMES)
        for filename in sorted(filenames):
            path = Path(dirpath) / filename
            if path.suffix not in _REFERENCE_SOURCE_EXTENSIONS:
                continue
            stem = path.stem
            if stem == "test" or stem.startswith("test_") or stem.endswith(("_test", ".test", ".spec")):
                continue
            yield path


def _collect_referenced_zh_keys(root: Path) -> set[str]:
    """`owner.hash8` keys referenced as string literals across source files."""
    referenced: set[str] = set()
    for path in _iter_reference_source_files(root):
        text = path.read_text(encoding="utf-8", errors="ignore")
        referenced.update(m.group("key") for m in _KEY_REFERENCE_PATTERN.finditer(text))
    return referenced


def _write_catalogs(base_dir: Path, *, zh=None, en=None, vi=None) -> None:
    for locale, data in (("zh", zh), ("en", en), ("vi", vi)):
        (base_dir / f"{locale}.json").write_text(
            json.dumps(data if data is not None else {}), encoding="utf-8"
        )


# ---------------------------------------------------------------------------
# Required acceptance tests: run against the real, shipped catalog files.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def _shipped_catalogs() -> dict[str, dict]:
    """Load the three real catalog files off disk exactly once for this module."""
    return _load_all_catalogs()


@pytest.fixture(scope="module")
def _shipped_flat(_shipped_catalogs) -> dict[str, dict[str, str]]:
    return {locale: _flatten(catalog) for locale, catalog in _shipped_catalogs.items()}


def test_no_orphaned_keys_in_target_locales(_shipped_flat):
    zh_flat = _shipped_flat[_SOURCE_LOCALE]
    target_flats = {locale: _shipped_flat[locale] for locale in _TARGET_LOCALES}

    orphans = _collect_orphans(zh_flat, target_flats)

    assert not orphans, f"orphaned keys (locale:key) with no zh.json counterpart: {orphans}"


def test_every_referenced_zh_key_has_a_non_empty_en_translation(_shipped_flat):
    """Reference-aware parity gate: every zh key referenced by an
    `<owner>.<hash8>`-shaped string literal in source must have a non-empty
    en.json value. This is a textual literal scan, not a `t()` call-site
    trace -- it cannot see a key built via concatenation, an f-string, or a
    variable, and (by design, see below) ignores a literal that doesn't
    match an existing zh key.

    Narrower than test_no_orphaned_keys_in_target_locales above, which only
    catches the opposite direction (a target-locale key with no zh
    counterpart), and orthogonal to test_translation_coverage_report below,
    which asserts range invariants rather than coverage -- neither one
    catches a referenced key shipping untranslated. This test scans non-test
    .py/.ts/.tsx sources for the `<owner>.<hash8>` key shape and asserts
    every referenced zh key survives translation into en, so a future story
    that wires one of today's currently-dead zh keys without translating it
    fails here instead of shipping silent untranslated text to English
    users.

    `vi` is deliberately exempt from this check: ARCHITECTURE-SPINE.md:205
    freezes it as structure-with-no-values for this release, so a referenced
    key having no `vi` value is expected, not a defect this test should
    catch.
    """
    zh_flat = _shipped_flat[_SOURCE_LOCALE]
    en_flat = _shipped_flat["en"]

    referenced = _collect_referenced_zh_keys(_REFERENCE_SCAN_ROOT)
    assert referenced, (
        f"no owner.hash8 key references found under {_REFERENCE_SCAN_ROOT} -- "
        "the scan root or extension/exclusion filters are likely misconfigured"
    )
    # A referenced literal with no zh.json counterpart at all (typo, stale
    # rename) is a different bug than an untranslated real key, and out of
    # this test's scope -- see test_no_orphaned_keys_in_target_locales for
    # the orphan-detection direction this doesn't cover.
    referenced_zh_keys = referenced & set(zh_flat)

    untranslated = sorted(
        key
        for key in referenced_zh_keys
        if not (isinstance(en_flat.get(key), str) and en_flat.get(key) != "")
    )

    assert not untranslated, f"referenced zh keys with no non-empty en.json translation: {untranslated}"


def test_translation_coverage_report(_shipped_flat):
    zh_flat = _shipped_flat[_SOURCE_LOCALE]
    target_flats = {locale: _shipped_flat[locale] for locale in _TARGET_LOCALES}

    report = _build_coverage_report(zh_flat, target_flats)

    # These structural/range invariants -- not a hardcoded exact value --
    # are what this test verifies: they hold both today, while the shipped
    # catalogs are still empty, and once Story 1.5's i18n_mint.py populates
    # them, with no update required either way.
    assert set(report) == set(_TARGET_LOCALES)
    for locale in _TARGET_LOCALES:
        assert report[locale]["total"] == len(zh_flat)
        assert 0 <= report[locale]["translated"] <= report[locale]["total"]


def test_does_not_use_i18n_module_or_client_fixture():
    """Automates this story's Always constraint: no i18n.load()/t(), no `client` fixture.

    Parsed via ast rather than substring search so this check does not trip
    over its own source text (e.g. the string "import i18n" appearing in a
    comment or in this very assertion).
    """
    import ast

    source = Path(__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            module_names = (
                [alias.name for alias in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
            )
            for name in module_names:
                assert name != "i18n" and not name.startswith("i18n."), ast.dump(node)
        if isinstance(node, ast.Attribute) and node.attr in ("load", "t"):
            if isinstance(node.value, ast.Name) and node.value.id == "i18n":
                pytest.fail(f"unexpected i18n.{node.attr} reference: {ast.dump(node)}")
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
            arg_names = {arg.arg for arg in node.args.args}
            assert "client" not in arg_names, node.name
            for decorator in node.decorator_list:
                if (
                    isinstance(decorator, ast.Call)
                    and isinstance(decorator.func, ast.Attribute)
                    and decorator.func.attr == "usefixtures"
                ):
                    fixture_names = {
                        a.value for a in decorator.args if isinstance(a, ast.Constant)
                    }
                    assert "client" not in fixture_names, node.name


class TestCatalogDirResolution:
    def test_catalog_dir_points_at_the_real_i18n_package(self):
        assert _CATALOG_DIR.name == "i18n"
        assert (_CATALOG_DIR / "zh.json").is_file()
        assert (_CATALOG_DIR / "en.json").is_file()
        assert (_CATALOG_DIR / "vi.json").is_file()


# ---------------------------------------------------------------------------
# Helper unit tests: in-memory dicts, no file I/O.
# ---------------------------------------------------------------------------


class TestFlatten:
    def test_flattens_two_level_shape(self):
        assert _flatten({"chatgpt": {"a": "hi", "b": "bye"}, "settings": {"c": "x"}}) == {
            "chatgpt.a": "hi",
            "chatgpt.b": "bye",
            "settings.c": "x",
        }

    def test_empty_catalog_flattens_to_empty_dict(self):
        assert _flatten({}) == {}


class TestBuildCoverageReport:
    def test_translated_excludes_empty_string_values(self):
        zh_flat = {"a.b": "你好", "a.c": "再见"}
        report = _build_coverage_report(zh_flat, {"en": {"a.b": "Hi", "a.c": ""}})
        assert report == {"en": {"translated": 1, "total": 2}}

    def test_zero_keys_yields_zero_total_and_zero_translated(self):
        report = _build_coverage_report({}, {"en": {}, "vi": {}})
        assert report == {
            "en": {"translated": 0, "total": 0},
            "vi": {"translated": 0, "total": 0},
        }


# ---------------------------------------------------------------------------
# DW-29 reference scan: synthetic source trees under tmp_path, exercising
# _collect_referenced_zh_keys's filtering rules in isolation from the real
# (large, mostly-vendored) repo tree the acceptance test above scans.
# ---------------------------------------------------------------------------


class TestCollectReferencedZhKeys:
    def test_collects_owner_hash8_literal_from_py_file(self, tmp_path):
        (tmp_path / "mod.py").write_text('t("chatgpt.a3f21c8e", lang)\n', encoding="utf-8")
        assert _collect_referenced_zh_keys(tmp_path) == {"chatgpt.a3f21c8e"}

    def test_matches_single_double_and_backtick_quotes(self, tmp_path):
        (tmp_path / "mod.ts").write_text(
            "const a = 'core.11112222'\nconst b = \"core.33334444\"\nconst c = `core.55556666`\n",
            encoding="utf-8",
        )
        assert _collect_referenced_zh_keys(tmp_path) == {
            "core.11112222", "core.33334444", "core.55556666",
        }

    def test_ignores_non_source_extensions(self, tmp_path):
        (tmp_path / "notes.md").write_text('"chatgpt.a3f21c8e"\n', encoding="utf-8")
        assert _collect_referenced_zh_keys(tmp_path) == set()

    def test_excludes_files_under_excluded_dir_names(self, tmp_path):
        vendored = tmp_path / "node_modules" / "pkg"
        vendored.mkdir(parents=True)
        (vendored / "mod.ts").write_text('"vendor.deadbeef"\n', encoding="utf-8")
        assert _collect_referenced_zh_keys(tmp_path) == set()

    def test_excludes_test_prefixed_and_bare_test_named_files(self, tmp_path):
        (tmp_path / "test_mod.py").write_text('"chatgpt.a3f21c8e"\n', encoding="utf-8")
        (tmp_path / "test.ts").write_text('"core.11112222"\n', encoding="utf-8")
        (tmp_path / "widget.test.tsx").write_text('"core.33334444"\n', encoding="utf-8")
        assert _collect_referenced_zh_keys(tmp_path) == set()

    def test_excludes_underscore_test_and_spec_suffixed_files(self, tmp_path):
        (tmp_path / "mod_test.py").write_text('"chatgpt.a3f21c8e"\n', encoding="utf-8")
        (tmp_path / "widget.spec.tsx").write_text('"core.11112222"\n', encoding="utf-8")
        assert _collect_referenced_zh_keys(tmp_path) == set()

    def test_ignores_uppercase_hex_suffix(self, tmp_path):
        (tmp_path / "mod.py").write_text('"chatgpt.A3F21C8E"\n', encoding="utf-8")
        assert _collect_referenced_zh_keys(tmp_path) == set()

    def test_ignores_mismatched_quote_flanks(self, tmp_path):
        (tmp_path / "mod.py").write_text(
            "# note about 'chatgpt.a3f21c8e\" mismatched quoting in prose\n", encoding="utf-8"
        )
        assert _collect_referenced_zh_keys(tmp_path) == set()


# ---------------------------------------------------------------------------
# I/O matrix: synthetic catalogs on disk, module's path resolution redirected
# via tmp_path + monkeypatch -- mirrors tests/test_i18n.py::TestLoad's style
# of redirecting `i18n.__file__` rather than the `i18n` module's own cache.
# ---------------------------------------------------------------------------


class TestOrphanDetectionAgainstDisk:
    def test_orphan_key_in_en_is_named(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys.modules[__name__], "_CATALOG_DIR", tmp_path)
        _write_catalogs(
            tmp_path,
            zh={"chatgpt": {"a": "你好"}},
            en={"chatgpt": {"a": "Hi", "orphan_key": "Orphan"}},
        )
        flat = {locale: _flatten(c) for locale, c in _load_all_catalogs().items()}

        orphans = _collect_orphans(flat["zh"], {"en": flat["en"], "vi": flat["vi"]})

        assert orphans == ["en:chatgpt.orphan_key"]

    def test_orphan_key_in_vi_is_named(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys.modules[__name__], "_CATALOG_DIR", tmp_path)
        _write_catalogs(
            tmp_path,
            zh={"chatgpt": {"a": "你好"}},
            vi={"chatgpt": {"a": "", "orphan_key": "Orphan"}},
        )
        flat = {locale: _flatten(c) for locale, c in _load_all_catalogs().items()}

        orphans = _collect_orphans(flat["zh"], {"en": flat["en"], "vi": flat["vi"]})

        assert orphans == ["vi:chatgpt.orphan_key"]

    def test_orphans_in_both_locales_are_all_named_in_one_pass(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys.modules[__name__], "_CATALOG_DIR", tmp_path)
        _write_catalogs(
            tmp_path,
            zh={"chatgpt": {"a": "你好"}},
            en={"chatgpt": {"a": "Hi", "orphan_en": "x"}},
            vi={"chatgpt": {"a": "", "orphan_vi": "y"}},
        )
        flat = {locale: _flatten(c) for locale, c in _load_all_catalogs().items()}

        orphans = _collect_orphans(flat["zh"], {"en": flat["en"], "vi": flat["vi"]})

        assert orphans == ["en:chatgpt.orphan_en", "vi:chatgpt.orphan_vi"]


class TestCoverageAgainstDisk:
    def test_zh_only_gap_passes_and_is_untranslated_in_report(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys.modules[__name__], "_CATALOG_DIR", tmp_path)
        _write_catalogs(
            tmp_path,
            zh={"chatgpt": {"a": "你好", "b": "再见"}},
            en={"chatgpt": {"a": "Hi"}},
            vi={},
        )
        flat = {locale: _flatten(c) for locale, c in _load_all_catalogs().items()}

        assert _collect_orphans(flat["zh"], {"en": flat["en"], "vi": flat["vi"]}) == []

        report = _build_coverage_report(flat["zh"], {"en": flat["en"], "vi": flat["vi"]})
        assert report == {
            "en": {"translated": 1, "total": 2},
            "vi": {"translated": 0, "total": 2},
        }

    def test_all_empty_catalogs_produce_zero_coverage_and_no_orphans(self, tmp_path, monkeypatch):
        # The real shipped state per Story 1.2/1.3.
        monkeypatch.setattr(sys.modules[__name__], "_CATALOG_DIR", tmp_path)
        _write_catalogs(tmp_path, zh={}, en={}, vi={})
        flat = {locale: _flatten(c) for locale, c in _load_all_catalogs().items()}

        assert _collect_orphans(flat["zh"], {"en": flat["en"], "vi": flat["vi"]}) == []

        report = _build_coverage_report(flat["zh"], {"en": flat["en"], "vi": flat["vi"]})
        assert report == {
            "en": {"translated": 0, "total": 0},
            "vi": {"translated": 0, "total": 0},
        }

    def test_empty_string_target_value_excluded_from_translated_but_not_orphaned(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(sys.modules[__name__], "_CATALOG_DIR", tmp_path)
        _write_catalogs(
            tmp_path,
            zh={"chatgpt": {"a": "你好"}},
            en={"chatgpt": {"a": ""}},
            vi={},
        )
        flat = {locale: _flatten(c) for locale, c in _load_all_catalogs().items()}

        assert _collect_orphans(flat["zh"], {"en": flat["en"], "vi": flat["vi"]}) == []

        report = _build_coverage_report(flat["zh"], {"en": flat["en"], "vi": flat["vi"]})
        assert report["en"] == {"translated": 0, "total": 1}
