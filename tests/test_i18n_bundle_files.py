"""main.py `_i18n_bundle_files()` 单元测试 — Unit tests for main.py's
`_i18n_bundle_files()` PyInstaller bundle-file hint helper.

只测 helper 本身；`main` 和 `i18n` 在每个测试体内延迟导入，遵循
tests/conftest.py 记录的“提前 import 会绕过测试用 DB engine 补丁”的坑，
与 test_main_startup_guard.py / test_main_selfcheck_i18n.py 的既有模式一致。
这里不需要 test_main_startup_guard.py 那样的 `_isolated_catalog_cache` 自动
fixture 来重置 `i18n._catalogs`：本文件的测试都不调用 load()/selfcheck()，
只读 `i18n.LOCALES`，没有目录缓存要隔离 —
Only exercises the helper directly; `main` and `i18n` are imported lazily
inside each test body per tests/conftest.py's documented "hoisting the
import bypasses the test-DB engine patch" hazard, following
test_main_startup_guard.py / test_main_selfcheck_i18n.py's established
pattern. Unlike those two files, no autouse fixture resets
`i18n._catalogs` here: none of these tests call `load()`/`selfcheck()`,
only read `i18n.LOCALES`, so there is no catalog cache to isolate.
"""
from __future__ import annotations


class TestI18nBundleFiles:
    def test_matches_real_shipped_locales_in_declared_order(self):
        """Pins the exact rendered format against a hard-coded literal, not just
        against the same join expression the production code itself uses --
        a typo'd separator or missing `i18n/` prefix in `_i18n_bundle_files()`
        would still be caught here even though it would also match a
        self-referential `"、".join(...)` comparison."""
        import i18n
        import main

        assert i18n.LOCALES == ("zh", "en", "vi")
        assert main._i18n_bundle_files() == "i18n/zh.json、i18n/en.json、i18n/vi.json"

    def test_reflects_locale_change_immediately_no_reload(self, monkeypatch):
        """The regression test for DW-8 itself: a hard-coded string would never
        react to this monkeypatch, since it would have been frozen at import
        time. The helper must read `i18n.LOCALES` fresh on every call."""
        import i18n
        import main

        monkeypatch.setattr(i18n, "LOCALES", ("zh", "en", "vi", "ja"))

        assert main._i18n_bundle_files() == "i18n/zh.json、i18n/en.json、i18n/vi.json、i18n/ja.json"
