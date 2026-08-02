"""i18n catalog module unit tests."""
from __future__ import annotations

import json

import pytest

import i18n


@pytest.fixture(autouse=True)
def _isolated_catalog_cache(monkeypatch):
    """Every test gets its own catalog cache slot so tests never leak state."""
    monkeypatch.setattr(i18n, "_catalogs", None)
    yield


def _set_catalogs(monkeypatch, zh=None, en=None, vi=None):
    monkeypatch.setattr(
        i18n,
        "_catalogs",
        {"zh": zh or {}, "en": en or {}, "vi": vi or {}},
    )


class TestKeyPresent:
    def test_key_present_in_requested_locale(self, monkeypatch):
        _set_catalogs(
            monkeypatch,
            zh={"chatgpt": {"a3f21c8e": "验证码：{code}"}},
            en={"chatgpt": {"a3f21c8e": "Code: {code}"}},
        )
        assert i18n.t("chatgpt.a3f21c8e", "en", code="123") == "Code: 123"


class TestFallbackToZh:
    def test_key_present_in_zh_absent_from_en(self, monkeypatch):
        _set_catalogs(monkeypatch, zh={"settings": {"deadbeef": "标签：{name}"}})
        assert i18n.t("settings.deadbeef", "en", name="X") == "标签：X"

    def test_vi_structure_present_but_no_values(self, monkeypatch):
        _set_catalogs(
            monkeypatch,
            zh={"chatgpt": {"a3f21c8e": "邮箱验证码获取成功"}},
            vi={},
        )
        assert i18n.t("chatgpt.a3f21c8e", "vi") == "邮箱验证码获取成功"


class TestRenderFailureDegrades:
    def test_malformed_placeholder_falls_back_to_zh(self, monkeypatch):
        _set_catalogs(
            monkeypatch,
            zh={"chatgpt": {"a3f21c8e": "验证码 {code}"}},
            en={"chatgpt": {"a3f21c8e": "Hello {name"}},
        )
        assert i18n.t("chatgpt.a3f21c8e", "en", code="123") == "验证码 123"

    def test_missing_named_param_falls_back_to_zh(self, monkeypatch):
        _set_catalogs(
            monkeypatch,
            zh={"chatgpt": {"a3f21c8e": "你好"}},
            en={"chatgpt": {"a3f21c8e": "Hi {name}"}},
        )
        assert i18n.t("chatgpt.a3f21c8e", "en") == "你好"

    def test_both_locale_and_zh_fail_returns_raw_key(self, monkeypatch):
        _set_catalogs(
            monkeypatch,
            zh={"chatgpt": {"a3f21c8e": "你好 {name}"}},
            en={"chatgpt": {"a3f21c8e": "Hi {name}"}},
        )
        # neither the en value nor the zh fallback can render without `name`
        assert i18n.t("chatgpt.a3f21c8e", "en") == "chatgpt.a3f21c8e"

    def test_render_failure_leaves_a_debug_trail(self, monkeypatch, caplog):
        # A raw key on screen with no log line anywhere gives an operator no
        # route back to the call site.
        _set_catalogs(monkeypatch, en={"chatgpt": {"a3f21c8e": "Hi {name}"}})

        with caplog.at_level("DEBUG", logger="i18n"):
            assert i18n.t("chatgpt.a3f21c8e", "en") == "chatgpt.a3f21c8e"

        assert any(
            "chatgpt.a3f21c8e" in rec.getMessage() for rec in caplog.records
        ), [rec.getMessage() for rec in caplog.records]


class TestExtraAndLiteralInterpolation:
    def test_extra_params_are_ignored(self, monkeypatch):
        _set_catalogs(monkeypatch, en={"greet": {"h1": "Hi {name}"}})
        assert i18n.t("greet.h1", "en", name="A", unused="B") == "Hi A"

    def test_literal_brace_escape_not_re_expanded(self, monkeypatch):
        _set_catalogs(monkeypatch, en={"promo": {"h1": "{{discount}}%"}})
        assert i18n.t("promo.h1", "en") == "{discount}%"

    def test_param_value_containing_braces_not_rescanned(self, monkeypatch):
        _set_catalogs(monkeypatch, en={"greet": {"h1": "Hi {name}"}})
        assert i18n.t("greet.h1", "en", name="a{b}c") == "Hi a{b}c"


class TestKeyAbsentEverywhere:
    def test_key_absent_from_every_locale_returns_raw_key(self, monkeypatch):
        _set_catalogs(monkeypatch)
        assert i18n.t("nope.deadbeef", "en") == "nope.deadbeef"


class TestKeyAndLangShapeEdgeCases:
    def test_key_without_dot_separator_degrades_to_raw_key(self, monkeypatch):
        _set_catalogs(monkeypatch)
        assert i18n.t("nope", "en") == "nope"

    def test_unknown_lang_code_falls_back_to_zh(self, monkeypatch):
        _set_catalogs(monkeypatch, zh={"chatgpt": {"a3f21c8e": "你好"}})
        assert i18n.t("chatgpt.a3f21c8e", "fr") == "你好"

    def test_attribute_access_placeholder_never_raises(self, monkeypatch):
        # Attribute access is outside the frozen "{param}" convention, so the
        # strict formatter rejects it and the value degrades to zh.
        _set_catalogs(
            monkeypatch,
            zh={"chatgpt": {"a3f21c8e": "你好"}},
            en={"chatgpt": {"a3f21c8e": "Hi {name.missing_attr}"}},
        )
        assert i18n.t("chatgpt.a3f21c8e", "en", name="plain") == "你好"


class TestLoad:
    def test_missing_zh_json_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr(i18n, "__file__", str(tmp_path / "__init__.py"))
        (tmp_path / "en.json").write_text("{}", encoding="utf-8")

        with pytest.raises(RuntimeError) as exc_info:
            i18n.load()

        assert str(tmp_path / "zh.json") in str(exc_info.value)

    def test_invalid_zh_json_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr(i18n, "__file__", str(tmp_path / "__init__.py"))
        (tmp_path / "zh.json").write_text("not valid json", encoding="utf-8")

        with pytest.raises(RuntimeError):
            i18n.load()

    def test_missing_en_and_vi_treated_as_empty_catalog(self, tmp_path, monkeypatch):
        monkeypatch.setattr(i18n, "__file__", str(tmp_path / "__init__.py"))
        (tmp_path / "zh.json").write_text(
            json.dumps({"chatgpt": {"a3f21c8e": "你好"}}), encoding="utf-8"
        )

        catalogs = i18n.load()

        assert catalogs["zh"] == {"chatgpt": {"a3f21c8e": "你好"}}
        assert catalogs["en"] == {}
        assert catalogs["vi"] == {}

    def test_invalid_en_json_treated_as_empty_catalog(self, tmp_path, monkeypatch):
        monkeypatch.setattr(i18n, "__file__", str(tmp_path / "__init__.py"))
        (tmp_path / "zh.json").write_text("{}", encoding="utf-8")
        (tmp_path / "en.json").write_text("not valid json", encoding="utf-8")

        catalogs = i18n.load()

        assert catalogs["en"] == {}

    def test_non_dict_zh_json_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr(i18n, "__file__", str(tmp_path / "__init__.py"))
        (tmp_path / "zh.json").write_text("[]", encoding="utf-8")

        with pytest.raises(RuntimeError):
            i18n.load()

    def test_non_dict_en_json_treated_as_empty_catalog(self, tmp_path, monkeypatch):
        monkeypatch.setattr(i18n, "__file__", str(tmp_path / "__init__.py"))
        (tmp_path / "zh.json").write_text("{}", encoding="utf-8")
        (tmp_path / "en.json").write_text('"not an object"', encoding="utf-8")

        catalogs = i18n.load()

        assert catalogs["en"] == {}

    def test_load_caches_after_first_call(self, tmp_path, monkeypatch):
        monkeypatch.setattr(i18n, "__file__", str(tmp_path / "__init__.py"))
        (tmp_path / "zh.json").write_text("{}", encoding="utf-8")

        first = i18n.load()
        # Remove the file on disk; a cached second call must not re-read it.
        (tmp_path / "zh.json").unlink()
        second = i18n.load()

        assert first is second

    def test_utf8_bom_catalog_still_parses(self, tmp_path, monkeypatch):
        # A Windows/GUI editor writing a BOM must not turn a valid catalog into
        # a fatal "not valid JSON" abort.
        monkeypatch.setattr(i18n, "__file__", str(tmp_path / "__init__.py"))
        (tmp_path / "zh.json").write_text(
            json.dumps({"chatgpt": {"a3f21c8e": "你好"}}), encoding="utf-8-sig"
        )

        assert i18n.load()["zh"] == {"chatgpt": {"a3f21c8e": "你好"}}

    def test_catalog_error_is_a_runtime_error(self, tmp_path, monkeypatch):
        # Story 1.3 catches this; `except RuntimeError` must keep working.
        monkeypatch.setattr(i18n, "__file__", str(tmp_path / "__init__.py"))

        with pytest.raises(i18n.CatalogError):
            i18n.load()
        assert issubclass(i18n.CatalogError, RuntimeError)

    def test_degraded_target_catalog_is_logged(self, tmp_path, monkeypatch, caplog):
        # An en.json that silently becomes {} makes every English user see
        # Chinese; the only way to diagnose that later is a log line. Assert the
        # level and the offending path too — a substring match on "en" alone
        # passes on almost any message, at any level.
        monkeypatch.setattr(i18n, "__file__", str(tmp_path / "__init__.py"))
        (tmp_path / "zh.json").write_text("{}", encoding="utf-8")
        (tmp_path / "en.json").write_text("not valid json", encoding="utf-8")

        with caplog.at_level("WARNING", logger="i18n"):
            i18n.load()

        warnings = [
            rec for rec in caplog.records
            if rec.levelname == "WARNING" and str(tmp_path / "en.json") in rec.getMessage()
        ]
        assert len(warnings) == 1, [rec.getMessage() for rec in caplog.records]
        assert "JSON" in warnings[0].getMessage()

    def test_invalid_utf8_zh_reports_encoding_not_json(self, tmp_path, monkeypatch):
        # UnicodeDecodeError subclasses ValueError, so without its own branch a
        # mis-encoded save aborts startup pointing at a JSON syntax error that
        # does not exist.
        monkeypatch.setattr(i18n, "__file__", str(tmp_path / "__init__.py"))
        (tmp_path / "zh.json").write_bytes(b'{"a": {"b": "\xff\xfe"}}')

        with pytest.raises(i18n.CatalogError) as exc_info:
            i18n.load()

        assert "UTF-8" in str(exc_info.value)

    def test_invalid_utf8_en_treated_as_empty_catalog(self, tmp_path, monkeypatch):
        monkeypatch.setattr(i18n, "__file__", str(tmp_path / "__init__.py"))
        (tmp_path / "zh.json").write_text("{}", encoding="utf-8")
        (tmp_path / "en.json").write_bytes(b'{"a": {"b": "\xff\xfe"}}')

        assert i18n.load()["en"] == {}


class TestSourceLocaleLookup:
    def test_source_locale_key_present(self, monkeypatch):
        _set_catalogs(monkeypatch, zh={"chatgpt": {"a3f21c8e": "验证码：{code}"}})
        assert i18n.t("chatgpt.a3f21c8e", "zh", code="123") == "验证码：123"

    def test_source_locale_render_failure_returns_raw_key(self, monkeypatch):
        # zh is both the requested locale and the fallback, so there is nothing
        # left to degrade to but the key itself.
        _set_catalogs(monkeypatch, zh={"chatgpt": {"a3f21c8e": "你好 {name}"}})
        assert i18n.t("chatgpt.a3f21c8e", "zh") == "chatgpt.a3f21c8e"

    def test_source_locale_render_failure_looks_up_once(self, monkeypatch):
        calls = []
        original = i18n._lookup

        def spy(catalog, owner, subkey):
            calls.append((owner, subkey))
            return original(catalog, owner, subkey)

        monkeypatch.setattr(i18n, "_lookup", spy)
        _set_catalogs(monkeypatch, zh={"chatgpt": {"a3f21c8e": "你好 {name}"}})

        assert i18n.t("chatgpt.a3f21c8e", "zh") == "chatgpt.a3f21c8e"
        assert len(calls) == 1


class TestPlaceholderRestrictions:
    """catalog-conventions.md fixes interpolation at bare named `{param}` only."""

    def test_attribute_placeholder_cannot_reach_into_a_param(self, monkeypatch):
        class Config:
            token = "SECRET-123"

        _set_catalogs(
            monkeypatch,
            zh={"a": {"b": "中文"}},
            en={"a": {"b": "leak {cfg.token}"}},
        )
        assert i18n.t("a.b", "en", cfg=Config()) == "中文"

    def test_index_placeholder_is_rejected(self, monkeypatch):
        _set_catalogs(
            monkeypatch,
            zh={"a": {"b": "中文"}},
            en={"a": {"b": "{items[0]}"}},
        )
        assert i18n.t("a.b", "en", items=["x"]) == "中文"

    def test_conversion_placeholder_is_rejected(self, monkeypatch):
        _set_catalogs(
            monkeypatch,
            zh={"a": {"b": "中文"}},
            en={"a": {"b": "{name!r}"}},
        )
        assert i18n.t("a.b", "en", name="x") == "中文"

    def test_format_spec_is_rejected(self, monkeypatch):
        # "{x:>2000000}" renders a 2 MB string from a two-character param.
        _set_catalogs(
            monkeypatch,
            zh={"a": {"b": "中文"}},
            en={"a": {"b": "{x:>2000000}"}},
        )
        assert i18n.t("a.b", "en", x="hi") == "中文"

    def test_nested_format_spec_is_rejected(self, monkeypatch):
        # "{x:{y}}" resolves its spec before format_field ever sees it, so a
        # spec that resolves to empty slipped past the format_field guard.
        _set_catalogs(
            monkeypatch,
            zh={"a": {"b": "中文"}},
            en={"a": {"b": "{x:{y}}"}},
        )
        assert i18n.t("a.b", "en", x="hi", y="") == "中文"

    def test_positional_placeholder_is_rejected(self, monkeypatch):
        _set_catalogs(
            monkeypatch,
            zh={"a": {"b": "中文"}},
            en={"a": {"b": "{0}"}},
        )
        assert i18n.t("a.b", "en", name="x") == "中文"

    def test_param_whose_format_raises_never_escapes(self, monkeypatch):
        class Boom:
            def __str__(self):
                raise RuntimeError("boom")

        _set_catalogs(
            monkeypatch,
            zh={"a": {"b": "中文"}},
            en={"a": {"b": "Hi {x}"}},
        )
        # RuntimeError is outside any enumerable str.format exception tuple.
        assert i18n.t("a.b", "en", x=Boom()) == "中文"

    def test_json_scalar_params_are_rendered(self, monkeypatch):
        _set_catalogs(monkeypatch, en={"a": {"b": "n={n} ok={flag}"}})
        assert i18n.t("a.b", "en", n=3, flag=True) == "n=3 ok=true"

    def test_none_param_renders_as_json_null(self, monkeypatch):
        _set_catalogs(monkeypatch, en={"a": {"b": "x={x}"}})
        assert i18n.t("a.b", "en", x=None) == "x=null"

    def test_bool_params_render_as_json_lowercase(self, monkeypatch):
        _set_catalogs(monkeypatch, en={"a": {"b": "x={x}"}})
        assert i18n.t("a.b", "en", x=True) == "x=true"
        assert i18n.t("a.b", "en", x=False) == "x=false"

    def test_integral_float_param_renders_without_trailing_zero(self, monkeypatch):
        _set_catalogs(monkeypatch, en={"a": {"b": "x={x}"}})
        assert i18n.t("a.b", "en", x=1.0) == "x=1"

    def test_non_integral_float_param_renders_unchanged(self, monkeypatch):
        _set_catalogs(monkeypatch, en={"a": {"b": "x={x}"}})
        assert i18n.t("a.b", "en", x=2.5) == "x=2.5"

    def test_non_scalar_param_degrades_instead_of_leaking_a_repr(self, monkeypatch):
        # AD-7 restricts params to JSON scalars; str(obj) would otherwise print
        # "<tests.test_i18n.Opaque object at 0x...>" into user-facing text.
        class Opaque:
            pass

        _set_catalogs(
            monkeypatch,
            zh={"a": {"b": "中文"}},
            en={"a": {"b": "Hi {x}"}},
        )
        assert i18n.t("a.b", "en", x=Opaque()) == "中文"


class TestMalformedCatalogShapes:
    def test_non_dict_owner_namespace_degrades(self, monkeypatch):
        _set_catalogs(monkeypatch, zh={"a": "not a namespace"})
        assert i18n.t("a.b", "en") == "a.b"

    def test_non_string_leaf_value_degrades(self, monkeypatch):
        _set_catalogs(monkeypatch, zh={"a": {"b": 123}})
        assert i18n.t("a.b", "en") == "a.b"


class TestShippedPackage:
    def test_shipped_catalogs_exist_and_parse(self):
        # The tests above all monkeypatch in-memory catalogs, so nothing else in
        # the suite ever opens the three files this story ships. A malformed
        # zh.json would otherwise leave pytest green and kill startup.
        catalogs = i18n.load()

        assert set(catalogs) == {"zh", "en", "vi"}
        for locale, catalog in catalogs.items():
            assert isinstance(catalog, dict), locale

    def test_imports_no_application_packages(self):
        # NFR9/AD-3: the portal must be able to import this without pulling in
        # the desktop backend. Enforced here rather than by a manual command.
        # Every .py in the package, not just __init__.py — Story 1.6 plans to
        # add selfcheck() here, and a forbidden import in a new module must fail
        # this test too.
        import ast
        import pathlib

        package_dir = pathlib.Path(i18n.__file__).parent
        sources = sorted(package_dir.glob("*.py"))
        assert sources, "expected at least i18n/__init__.py"

        forbidden = {"core", "application", "api", "customer_portal_api"}
        for source_path in sources:
            modules = []
            for node in ast.walk(ast.parse(source_path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.ImportFrom):
                    modules.append(node.module)
                elif isinstance(node, ast.Import):
                    modules.extend(alias.name for alias in node.names)

            offenders = [m for m in modules if m and m.split(".")[0] in forbidden]
            assert not offenders, (source_path.name, offenders)


class TestUntranslatedEmptyValue:
    """catalog-conventions.md:11 — vi ships "structure only, values not populated"."""

    def test_empty_value_falls_back_to_zh(self, monkeypatch):
        # The TypeScript half of the same convention types the catalog as
        # `Record<Lang, Catalog>`, so every key must be *present* in vi. The
        # natural representation of "present but untranslated" is "", and it
        # must render zh rather than a blank screen.
        _set_catalogs(
            monkeypatch,
            zh={"chatgpt": {"a3f21c8e": "邮箱验证码获取成功"}},
            vi={"chatgpt": {"a3f21c8e": ""}},
        )
        assert i18n.t("chatgpt.a3f21c8e", "vi") == "邮箱验证码获取成功"

    def test_empty_value_in_zh_degrades_to_raw_key(self, monkeypatch):
        _set_catalogs(monkeypatch, zh={"chatgpt": {"a3f21c8e": ""}})
        assert i18n.t("chatgpt.a3f21c8e", "zh") == "chatgpt.a3f21c8e"


class TestRenderMarker:
    """story 3.6 — render_marker(value, lang): the worker-thread marker convention."""

    def test_parses_marker_and_renders(self, monkeypatch):
        _set_catalogs(
            monkeypatch,
            zh={"cursor": {"a1b2c3d4": "账号缺少 token"}},
            en={"cursor": {"a1b2c3d4": "The account is missing a token"}},
        )
        marker = json.dumps({"i18n_key": "cursor.a1b2c3d4", "i18n_params": {}}, ensure_ascii=False)
        assert i18n.render_marker(marker, "en") == "The account is missing a token"

    def test_marker_with_scalar_params_renders(self, monkeypatch):
        _set_catalogs(
            monkeypatch,
            zh={"kiro": {"deadbeef": "刷新失败: {code}"}},
            en={"kiro": {"deadbeef": "Refresh failed: {code}"}},
        )
        marker = json.dumps({"i18n_key": "kiro.deadbeef", "i18n_params": {"code": 500}}, ensure_ascii=False)
        assert i18n.render_marker(marker, "en") == "Refresh failed: 500"

    def test_nested_marker_param_resolves_bottom_up(self, monkeypatch):
        # Mirrors the cursor switch+restart composition example in the spec's
        # Design Notes: a param value is itself another marker string.
        _set_catalogs(
            monkeypatch,
            zh={
                "cursor": {
                    "switchkey": "切换成功",
                    "restartkey": "已重启",
                    "composekey": "{switch_msg}。{restart_msg}",
                }
            },
            en={
                "cursor": {
                    "switchkey": "Switched",
                    "restartkey": "Restarted",
                    "composekey": "{switch_msg} {restart_msg}",
                }
            },
        )
        switch_marker = json.dumps({"i18n_key": "cursor.switchkey", "i18n_params": {}}, ensure_ascii=False)
        restart_marker = json.dumps({"i18n_key": "cursor.restartkey", "i18n_params": {}}, ensure_ascii=False)
        composed = json.dumps(
            {
                "i18n_key": "cursor.composekey",
                "i18n_params": {"switch_msg": switch_marker, "restart_msg": restart_marker},
            },
            ensure_ascii=False,
        )
        assert i18n.render_marker(composed, "en") == "Switched Restarted"
        # Never leaves an unresolved marker's raw JSON inside the rendered text.
        assert "i18n_key" not in i18n.render_marker(composed, "en")

    def test_coincidentally_marker_shaped_payload_renders_as_marker(self, monkeypatch):
        # Contract pin: exact-key-set matching is deliberate, not accidental.
        # Any string that decodes to exactly {"i18n_key": str,
        # "i18n_params": dict} is rendered as a marker even if it was never
        # produced by a marker-writing call site -- this is by design.
        _set_catalogs(
            monkeypatch,
            zh={"cursor": {"coincidence": "巧合"}},
            en={"cursor": {"coincidence": "Coincidence"}},
        )
        payload = json.dumps(
            {"i18n_key": "cursor.coincidence", "i18n_params": {}},
            ensure_ascii=False,
        )
        assert i18n.render_marker(payload, "en") == "Coincidence"

    def test_non_scalar_param_with_nested_marker_string_degrades_to_bare_key(
        self, monkeypatch
    ):
        # A dict/list-valued i18n_params entry cannot be resolved by the
        # str-only branch in render_marker's params loop, even when it
        # contains a marker-shaped string inside it. It reaches t() unchanged
        # and _StrictFormatter.format_field's scalar guard (AD-7) degrades
        # the whole render to the bare i18n_key -- no raw marker JSON and no
        # Python repr of the list leaks into the rendered text.
        _set_catalogs(
            monkeypatch,
            zh={"kiro": {"deadbeef": "刷新失败: {code}"}},
            en={"kiro": {"deadbeef": "Refresh failed: {code}"}},
        )
        inner_marker = json.dumps(
            {"i18n_key": "kiro.deadbeef", "i18n_params": {}}, ensure_ascii=False
        )
        marker = json.dumps(
            {"i18n_key": "kiro.deadbeef", "i18n_params": {"code": [inner_marker]}},
            ensure_ascii=False,
        )
        result = i18n.render_marker(marker, "en")
        assert result == "kiro.deadbeef"
        assert "i18n_key" not in result
        assert "[" not in result and "{" not in result

    def test_plain_text_passes_through_unchanged(self):
        assert i18n.render_marker("账号缺少 token", "en") == "账号缺少 token"

    def test_malformed_json_passes_through_unchanged(self):
        assert i18n.render_marker("{not valid json", "en") == "{not valid json"

    def test_unrelated_json_shape_passes_through_unchanged(self):
        value = json.dumps({"foo": "bar"})
        assert i18n.render_marker(value, "en") == value

    def test_wrong_field_types_pass_through_unchanged(self):
        # i18n_key not a string, i18n_params not a dict -- shape mismatch.
        value = json.dumps({"i18n_key": 123, "i18n_params": {}})
        assert i18n.render_marker(value, "en") == value
        value = json.dumps({"i18n_key": "cursor.x", "i18n_params": "nope"})
        assert i18n.render_marker(value, "en") == value

    def test_non_string_value_passes_through_unchanged(self):
        assert i18n.render_marker(None, "en") is None
        assert i18n.render_marker(42, "en") == 42

    def test_excess_nesting_depth_returns_raw_marker_without_crashing(self, monkeypatch):
        # A pathological chain of nested markers deeper than the depth cap
        # must degrade instead of recursing without bound.
        zh_catalog: dict = {"deep": {"base": "leaf value"}}
        current = json.dumps({"i18n_key": "deep.base", "i18n_params": {}}, ensure_ascii=False)
        for depth in range(8):
            subkey = f"lvl{depth}"
            zh_catalog["deep"][subkey] = "{inner}"
            current = json.dumps(
                {"i18n_key": f"deep.{subkey}", "i18n_params": {"inner": current}},
                ensure_ascii=False,
            )
        _set_catalogs(monkeypatch, zh=zh_catalog)
        # Must not raise (RecursionError or otherwise); degrades to text
        # instead of resolving the whole unbounded chain.
        result = i18n.render_marker(current, "zh")
        assert isinstance(result, str)


class TestRenderResult:
    """story 3.6 — render_result(value, lang): recursive dict/list walk."""

    def test_renders_every_string_in_nested_structure(self, monkeypatch):
        _set_catalogs(
            monkeypatch,
            zh={"blink": {"aaaaaaaa": "未获取到 workspace_id"}},
            en={"blink": {"aaaaaaaa": "workspace_id not found"}},
        )
        marker = json.dumps({"i18n_key": "blink.aaaaaaaa", "i18n_params": {}}, ensure_ascii=False)
        value = {
            "ok": False,
            "data": {"nested": [marker, "plain text", {"deeper": marker}]},
            "count": 3,
            "flag": None,
        }
        rendered = i18n.render_result(value, "en")
        assert rendered["data"]["nested"][0] == "workspace_id not found"
        assert rendered["data"]["nested"][1] == "plain text"
        assert rendered["data"]["nested"][2]["deeper"] == "workspace_id not found"
        assert rendered["count"] == 3
        assert rendered["flag"] is None

    def test_non_dict_non_list_non_string_passes_through(self):
        assert i18n.render_result(42, "en") == 42
        assert i18n.render_result(None, "en") is None
        assert i18n.render_result(True, "en") is True

    def test_empty_containers_pass_through(self):
        assert i18n.render_result({}, "en") == {}
        assert i18n.render_result([], "en") == []
