"""main.py `_i18n_bundle_files()` 单元测试 — Unit tests for main.py's
`_i18n_bundle_files()` PyInstaller bundle-file hint helper.

只测 helper 本身；`main` 和 `i18n` 在每个测试体内延迟导入，遵循
tests/conftest.py 记录的“提前 import 会绕过测试用 DB engine 补丁”的坑，
与 test_main_startup_guard.py / test_main_selfcheck_i18n.py 的既有模式一致 —
Only exercises the helper directly; `main` and `i18n` are imported lazily
inside each test body per tests/conftest.py's documented "hoisting the
import bypasses the test-DB engine patch" hazard, following
test_main_startup_guard.py / test_main_selfcheck_i18n.py's established
pattern.
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolated_catalog_cache(monkeypatch):
    """Every test gets its own i18n catalog cache slot so tests never leak state."""
    import i18n

    monkeypatch.setattr(i18n, "_catalogs", None)
    yield


class TestI18nBundleFiles:
    def test_matches_locales_derived_independently(self):
        import i18n
        import main

        expected = "、".join(f"i18n/{loc}.json" for loc in i18n.LOCALES)

        assert main._i18n_bundle_files() == expected

    def test_reflects_locale_change_immediately_no_reload(self, monkeypatch):
        """The regression test for DW-8 itself: a hard-coded string would never
        react to this monkeypatch, since it would have been frozen at import
        time. The helper must read `i18n.LOCALES` fresh on every call."""
        import i18n
        import main

        monkeypatch.setattr(i18n, "LOCALES", (*i18n.LOCALES, "ja"))

        result = main._i18n_bundle_files()

        assert result == "、".join(f"i18n/{loc}.json" for loc in i18n.LOCALES)
        assert result.count("i18n/ja.json") == 1
