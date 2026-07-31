"""Catalog TS integrity tests: cross-locale `{token}` interpolation parity
and within-namespace duplicate-value detection, read directly off
`frontend/src/i18n/{zh,en,vi}.ts` -- no compiled JSON, no `i18n` package.

DW-10. `test_catalog_integrity.py` only ever checks the compiled
`i18n/*.json` catalogs; nothing reads the shipped `.ts` sources, so a
translator dropping a `{token}` from one locale, or a new key colliding
byte-for-byte with an existing value in the same namespace (the real
`accounts.filterEligibleOption` / `accounts.statTrialEligible` incident from
story 2.4b's review), would go unnoticed. This module parses the three `.ts`
files with a line-based regex matching their exact shipped shape -- a
two-level-deep `const catalogX = { namespace: { key: 'value', ... }, ... }`
object literal, single- or double-quoted leaf lines, no backticks, no
escaped quotes, no third nesting level -- and flattens each to
`{"namespace.key": value}` just like `test_catalog_integrity.py::_flatten`
does for the JSON catalogs, for naming consistency with that file. Any
value equal to the empty string `''`/`""` is treated as "not a real
translation yet" (matches `LanguageContext.tsx`'s `withZhFallback` and
`test_catalog_integrity.py`'s own convention) and is skipped by both checks
below -- this matters because every one of `vi.ts`'s 483 values is
currently `''`. The duplicate-value check is a report gated by a
hand-authored, per-locale allowlist rather than a hard assertion across all
groups: today's 20 pre-existing groups (7 in `zh.ts`, 13 in `en.ts`) are
mostly legitimate coincidental word reuse (e.g. "Mailbox" as a tab label, a
metric label, and a page title), so only a *new*, un-allowlisted duplicate
should fail the suite.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

# This file lives in tests/, so frontend/src/i18n is one directory up and over.
_I18N_TS_DIR = Path(__file__).resolve().parent.parent / "frontend" / "src" / "i18n"

_LOCALES = ("zh", "en", "vi")

# Namespace header: 2-space indent, e.g. `  settings: {`.
_NAMESPACE_RE = re.compile(r"^  (\w+): \{$")
# Namespace close: 2-space indent `},` or `}` -- resets which namespace a
# subsequent leaf line would be attributed to, so a stray leaf-shaped line
# between two namespaces can never be folded into the wrong one.
_NAMESPACE_CLOSE_RE = re.compile(r"^  \},?$")
# Leaf line: 4-space indent, single- or double-quoted value, optional
# trailing comma. Both quote styles are shipped today (en.ts:296 uses double
# quotes because its value contains an apostrophe); no line uses a
# backtick, an escaped quote, or a third nesting level.
_LEAF_SINGLE_RE = re.compile(r"^    (\w+): '((?:[^'\\]|\\.)*)',?$")
_LEAF_DOUBLE_RE = re.compile(r'^    (\w+): "((?:[^"\\]|\\.)*)",?$')

_TOKEN_RE = re.compile(r"\{(\w+)\}")


def _catalog_ts_path(locale: str) -> Path:
    return _I18N_TS_DIR / f"{locale}.ts"


def _parse_catalog_ts(path: Path) -> dict[str, str]:
    """Line-based parse of a shipped `const catalogX = {...}` file into a flat dict.

    Mirrors `test_catalog_integrity.py::_flatten`'s "namespace.key" naming,
    but parses TS source lines directly rather than walking a loaded JSON
    object, since no `.ts` parser exists in this repo to reuse. Any line
    inside an open namespace body that matches neither the leaf regex nor
    the close-brace regex raises immediately -- a silently-dropped key would
    make both integrity checks vacuously pass for exactly the value most
    likely to need checking (a newly-edited one), so an unrecognized shape
    (a template literal, a third nesting level, a trailing inline comment)
    must fail loud instead of just vanishing from the flattened dict.
    """
    flat: dict[str, str] = {}
    namespace: str | None = None
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if _NAMESPACE_CLOSE_RE.match(line):
            namespace = None
            continue
        ns_match = _NAMESPACE_RE.match(line)
        if ns_match:
            namespace = ns_match.group(1)
            continue
        if namespace is None:
            continue
        leaf_match = _LEAF_SINGLE_RE.match(line) or _LEAF_DOUBLE_RE.match(line)
        if leaf_match is None:
            raise AssertionError(
                f"{path}:{lineno}: line inside namespace {namespace!r} matches neither "
                f"the leaf-line regex nor a namespace close -- catalog parser is out of "
                f"date with the shipped .ts format: {line!r}"
            )
        key, value = leaf_match.group(1), leaf_match.group(2)
        flat[f"{namespace}.{key}"] = value
    return flat


def _load_all_catalogs_ts() -> dict[str, dict[str, str]]:
    """Parse and flatten zh/en/vi.ts directly off disk. No caching."""
    return {locale: _parse_catalog_ts(_catalog_ts_path(locale)) for locale in _LOCALES}


def _tokens(value: str) -> set[str]:
    """The set of `{token}` placeholder names appearing in a catalog value."""
    return set(_TOKEN_RE.findall(value))


def _find_token_mismatches(flats: dict[str, dict[str, str]]) -> list[str]:
    """"key: zh={...} <locale>={...}" for every non-empty-valued key whose
    `{token}` set differs between `zh` and a target locale that also has a
    non-empty value for that key."""
    mismatches: list[str] = []
    zh_flat = flats["zh"]
    for key, zh_value in sorted(zh_flat.items()):
        if zh_value == "":
            continue
        zh_tokens = _tokens(zh_value)
        for locale in ("en", "vi"):
            other_value = flats[locale].get(key)
            if not other_value:
                continue
            other_tokens = _tokens(other_value)
            if other_tokens != zh_tokens:
                mismatches.append(
                    f"{key}: zh={sorted(zh_tokens)} {locale}={sorted(other_tokens)}"
                )
    return mismatches


def _find_duplicate_groups(flat: dict[str, str]) -> dict[tuple[str, str], frozenset[str]]:
    """Group non-empty values by (namespace, value); keep only groups with >1 key.

    Keys in the returned mapping's values are the bare leaf name (not
    "namespace.leaf"), matching how `_ALLOWED_DUPLICATE_GROUPS` below
    records them.
    """
    groups: dict[tuple[str, str], list[str]] = {}
    for full_key, value in flat.items():
        if value == "":
            continue
        namespace, _, leaf = full_key.partition(".")
        groups.setdefault((namespace, value), []).append(leaf)
    return {
        group_key: frozenset(leaves)
        for group_key, leaves in groups.items()
        if len(leaves) > 1
    }


# ---------------------------------------------------------------------------
# Hard-coded, hand-authored allowlist of pre-existing duplicate-value groups,
# measured 2026-07-31 against the real shipped catalogs. This is a record of
# groups already reviewed and accepted -- not derived from the current file
# contents -- so a *new* duplicate introduced later has nothing to match
# against and fails, while these 20 stay green. Keyed by locale, then
# namespace, then the shared value, to a frozenset of the colliding leaf keys.
# ---------------------------------------------------------------------------
_ALLOWED_DUPLICATE_GROUPS: dict[str, dict[tuple[str, str], frozenset[str]]] = {
    "zh": {
        # "注册策略" (Register strategy): a settings tab label and its page title.
        ("settings", "注册策略"): frozenset({"registerTabButtonLabel", "pageTitleRegister"}),
        # "邮箱服务" (Mailbox service): tab label, dashboard metric label, page title.
        ("settings", "邮箱服务"): frozenset(
            {"mailboxTabLabel", "mailboxMetricLabel", "pageTitleMailbox"}
        ),
        # "验证服务" (Captcha service): tab label and page title.
        ("settings", "验证服务"): frozenset({"captchaTabLabel", "pageTitleCaptcha"}),
        # "接码服务" (SMS service): tab label, metric label, page title.
        ("settings", "接码服务"): frozenset(
            {"smsTabLabel", "smsMetricLabel", "pageTitleSms"}
        ),
        # "启用" (Enable/Enabled): a status metric and an action button share the verb.
        ("proxies", "启用"): frozenset({"metricEnabled", "actionEnable"}),
        # "成功" (Succeeded): a summary metric and a filter option share the word.
        ("taskHistory", "成功"): frozenset({"metricSucceeded", "statusSucceededOption"}),
        # "失败" (Failed): a summary metric and a filter option share the word.
        ("taskHistory", "失败"): frozenset({"metricFailed", "statusFailedOption"}),
    },
    "en": {
        # "Register strategy": a settings tab label and its page title.
        ("settings", "Register strategy"): frozenset(
            {"registerTabButtonLabel", "pageTitleRegister"}
        ),
        # "Mailbox": tab label, dashboard metric label, page title.
        ("settings", "Mailbox"): frozenset(
            {"mailboxTabLabel", "mailboxMetricLabel", "pageTitleMailbox"}
        ),
        # "Captcha": tab label, metric label, page title.
        ("settings", "Captcha"): frozenset(
            {"captchaTabLabel", "captchaMetricLabel", "pageTitleCaptcha"}
        ),
        # "SMS": tab label, metric label, page title, and a service-type option.
        ("settings", "SMS"): frozenset(
            {"smsTabLabel", "smsMetricLabel", "pageTitleSms", "serviceTypeSms"}
        ),
        # "Subscribed": a status label and a dashboard stat share the word.
        ("dashboard", "Subscribed"): frozenset({"statusSubscribed", "statSubscribed"}),
        # "Ready": a status label and its badge variant share the word.
        ("dashboard", "Ready"): frozenset({"ready", "readyBadge"}),
        # "Proxies": a summary metric label and the page header title.
        ("proxies", "Proxies"): frozenset({"metricProxyCount", "headerTitle"}),
        # "Succeeded": a summary metric and a filter option share the word.
        ("taskHistory", "Succeeded"): frozenset(
            {"metricSucceeded", "statusSucceededOption"}
        ),
        # "Failed": a summary metric and a filter option share the word.
        ("taskHistory", "Failed"): frozenset({"metricFailed", "statusFailedOption"}),
        # "Running": a summary metric and a filter option share the word.
        ("taskHistory", "Running"): frozenset({"metricRunning", "statusRunningOption"}),
        # "Email": a form field label and a table header share the word.
        ("accounts", "Email"): frozenset({"fieldEmail", "tableHeaderEmail"}),
        # "Details": a default section title and a button label share the word.
        ("accounts", "Details"): frozenset({"defaultSectionTitle", "detailButton"}),
        # "Validity": a full-width label and its compact variant share the word.
        ("accounts", "Validity"): frozenset({"validityBoxLabel", "compactValidityLabel"}),
    },
    # vi.ts: every value is currently the empty-string placeholder, so no
    # duplicate groups exist there today. Not special-cased in the parser --
    # this is simply an empty allowlist, same shape as the others.
    "vi": {},
}


# ---------------------------------------------------------------------------
# Required acceptance tests: run against the real, shipped .ts catalogs.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def _shipped_flat_ts() -> dict[str, dict[str, str]]:
    """Parse the three real .ts catalog files off disk exactly once for this module."""
    return _load_all_catalogs_ts()


def test_token_parity_across_locales(_shipped_flat_ts):
    mismatches = _find_token_mismatches(_shipped_flat_ts)

    assert not mismatches, (
        "cross-locale {token} interpolation mismatches (key: zh=[...] locale=[...]): "
        f"{mismatches}"
    )


def test_duplicate_values_are_all_allowlisted(_shipped_flat_ts):
    for locale, flat in _shipped_flat_ts.items():
        discovered = _find_duplicate_groups(flat)
        allowed = _ALLOWED_DUPLICATE_GROUPS[locale]
        unallowlisted = {
            group_key: leaves
            for group_key, leaves in discovered.items()
            if allowed.get(group_key) != leaves
        }
        assert not unallowlisted, (
            f"un-allowlisted duplicate value group(s) in {locale}.ts "
            "(namespace, shared value) -> colliding keys: "
            f"{ {k: sorted(v) for k, v in unallowlisted.items()} }"
        )


class TestI18nTsDirResolution:
    def test_dir_points_at_the_real_i18n_ts_sources(self):
        assert _I18N_TS_DIR.name == "i18n"
        assert (_I18N_TS_DIR / "zh.ts").is_file()
        assert (_I18N_TS_DIR / "en.ts").is_file()
        assert (_I18N_TS_DIR / "vi.ts").is_file()


# ---------------------------------------------------------------------------
# Helper unit tests: in-memory dicts, no file I/O.
# ---------------------------------------------------------------------------


class TestParseCatalogTs:
    def test_parses_single_and_double_quoted_leaf_lines(self, tmp_path):
        source = (
            "const catalogX = {\n"
            "  settings: {\n"
            "    label: 'Hello {name}',\n"
            "    quip: \"Doesn't break\",\n"
            "  },\n"
            "}\n"
            "\n"
            "export default catalogX\n"
        )
        path = tmp_path / "x.ts"
        path.write_text(source, encoding="utf-8")

        assert _parse_catalog_ts(path) == {
            "settings.label": "Hello {name}",
            "settings.quip": "Doesn't break",
        }

    def test_empty_catalog_parses_to_empty_dict(self, tmp_path):
        path = tmp_path / "empty.ts"
        path.write_text("const catalogX = {\n}\n", encoding="utf-8")

        assert _parse_catalog_ts(path) == {}

    def test_unrecognized_line_shape_inside_a_namespace_raises(self, tmp_path):
        source = (
            "const catalogX = {\n"
            "  settings: {\n"
            "    label: 'Hello',\n"
            "    quip: `templates not supported`,\n"
            "  },\n"
            "}\n"
        )
        path = tmp_path / "x.ts"
        path.write_text(source, encoding="utf-8")

        with pytest.raises(AssertionError):
            _parse_catalog_ts(path)

    def test_namespace_closes_before_the_next_namespace_opens(self, tmp_path):
        # A leaf-shaped line sitting between one namespace's `},` and the
        # next namespace's header must not be silently folded into either.
        source = (
            "const catalogX = {\n"
            "  settings: {\n"
            "    a: 'A',\n"
            "  },\n"
            "  accounts: {\n"
            "    b: 'A',\n"
            "  },\n"
            "}\n"
        )
        path = tmp_path / "x.ts"
        path.write_text(source, encoding="utf-8")

        assert _parse_catalog_ts(path) == {"settings.a": "A", "accounts.b": "A"}


class TestFindTokenMismatches:
    def test_no_mismatch_when_all_locales_share_tokens(self):
        flats = {
            "zh": {"a.b": "你好 {name}"},
            "en": {"a.b": "Hi {name}"},
            "vi": {"a.b": ""},
        }
        assert _find_token_mismatches(flats) == []

    def test_mismatch_is_named_with_both_token_sets(self):
        flats = {
            "zh": {"a.b": "你好 {name} {count}"},
            "en": {"a.b": "Hi {name}"},
            "vi": {"a.b": ""},
        }
        mismatches = _find_token_mismatches(flats)
        assert len(mismatches) == 1
        assert "a.b" in mismatches[0]
        assert "'count'" in mismatches[0] or "count" in mismatches[0]

    def test_empty_value_in_zh_or_target_locale_is_skipped(self):
        flats = {
            "zh": {"a.b": "", "a.c": "Hi {x}"},
            "en": {"a.b": "Anything {y}", "a.c": ""},
            "vi": {"a.b": "", "a.c": ""},
        }
        assert _find_token_mismatches(flats) == []


class TestFindDuplicateGroups:
    def test_groups_non_empty_values_within_a_namespace(self):
        flat = {
            "settings.a": "Mailbox",
            "settings.b": "Mailbox",
            "settings.c": "Other",
            "accounts.d": "Mailbox",  # different namespace: not grouped with settings.*
        }
        assert _find_duplicate_groups(flat) == {
            ("settings", "Mailbox"): frozenset({"a", "b"}),
        }

    def test_empty_values_are_never_grouped(self):
        flat = {"settings.a": "", "settings.b": ""}
        assert _find_duplicate_groups(flat) == {}

    def test_singleton_values_are_not_a_group(self):
        flat = {"settings.a": "Unique"}
        assert _find_duplicate_groups(flat) == {}


# ---------------------------------------------------------------------------
# Regression tests: prove the two detectors actually fire on synthetic,
# in-memory data (not the real files) -- otherwise a vacuously-passing check
# against today's clean catalogs would be indistinguishable from a broken one.
# ---------------------------------------------------------------------------


class TestDetectorsAreLoadBearing:
    def test_token_parity_check_fires_on_synthetic_mismatch(self, _shipped_flat_ts):
        tampered = dict(_shipped_flat_ts)
        tampered["en"] = dict(tampered["en"])
        # Pick a real zh key with a non-empty en counterpart and a token,
        # then drop the token from the en side only, in memory.
        zh_flat = _shipped_flat_ts["zh"]
        target_key = next(
            key
            for key, value in zh_flat.items()
            if value and _tokens(value) and tampered["en"].get(key)
        )
        tampered["en"][target_key] = "no tokens here at all"

        mismatches = _find_token_mismatches(tampered)

        assert any(target_key in m for m in mismatches)

    def test_duplicate_value_check_fires_on_synthetic_unallowlisted_duplicate(
        self, _shipped_flat_ts
    ):
        tampered_en = dict(_shipped_flat_ts["en"])
        # Introduce a brand-new key/value pair inside an existing namespace
        # that collides with an existing, unrelated value -- not a member of
        # any allowlisted group.
        some_namespace_key = next(iter(tampered_en))
        namespace = some_namespace_key.partition(".")[0]
        tampered_en[f"{namespace}.syntheticDuplicateKey"] = "__synthetic sentinel value__"
        tampered_en[f"{namespace}.syntheticDuplicateKeyTwo"] = "__synthetic sentinel value__"

        discovered = _find_duplicate_groups(tampered_en)
        allowed = _ALLOWED_DUPLICATE_GROUPS["en"]
        unallowlisted = {
            group_key: leaves
            for group_key, leaves in discovered.items()
            if allowed.get(group_key) != leaves
        }

        assert (namespace, "__synthetic sentinel value__") in unallowlisted
        assert unallowlisted[(namespace, "__synthetic sentinel value__")] == frozenset(
            {"syntheticDuplicateKey", "syntheticDuplicateKeyTwo"}
        )
