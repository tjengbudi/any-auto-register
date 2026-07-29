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
        # "{name.upper}" triggers attribute access during str.format; a plain
        # str param has no such formattable attribute path that resolves the
        # way a dict/object field would, so this must degrade, not raise.
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
