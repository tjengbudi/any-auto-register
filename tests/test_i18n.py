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
        # Chinese; the only way to diagnose that later is a log line.
        monkeypatch.setattr(i18n, "__file__", str(tmp_path / "__init__.py"))
        (tmp_path / "zh.json").write_text("{}", encoding="utf-8")
        (tmp_path / "en.json").write_text("not valid json", encoding="utf-8")

        with caplog.at_level("WARNING", logger="i18n"):
            i18n.load()

        assert any("en" in rec.getMessage() for rec in caplog.records)


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
        assert i18n.t("a.b", "en", n=3, flag=True) == "n=3 ok=True"

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
        import ast
        import pathlib

        source = pathlib.Path(i18n.__file__).read_text(encoding="utf-8")
        modules = []
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.ImportFrom):
                modules.append(node.module)
            elif isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)

        forbidden = {"core", "application", "api", "customer_portal_api"}
        assert not [m for m in modules if m and m.split(".")[0] in forbidden], modules
