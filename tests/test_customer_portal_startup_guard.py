"""customer_portal_api/main.py startup guard unit tests.

Mirrors tests/test_main_startup_guard.py's technique: only exercises
`_ensure_i18n_ready()` directly, never drives the full `async with
lifespan(app):` context manager (which would also call
`initialize_runtime()`). `customer_portal_api.main` is imported lazily
inside each test body, matching tests/conftest.py's documented
"hoisting the import bypasses the test-DB engine patch" hazard.
"""
from __future__ import annotations

import inspect

import pytest


@pytest.fixture(autouse=True)
def _isolated_catalog_cache(monkeypatch):
    """Every test gets its own i18n catalog cache slot so tests never leak state."""
    import i18n

    monkeypatch.setattr(i18n, "_catalogs", None)
    yield


class TestEnsureI18nReady:
    def test_real_shipped_catalog_succeeds(self):
        import customer_portal_api.main as main

        # Must not raise; the real shipped i18n/zh.json is present and valid.
        main._ensure_i18n_ready()

    def test_missing_zh_json_aborts_naming_the_path(self, tmp_path, monkeypatch, capsys):
        import i18n
        import customer_portal_api.main as main

        resolved = tmp_path.resolve()
        monkeypatch.setattr(i18n, "__file__", str(resolved / "__init__.py"))
        (resolved / "en.json").write_text("{}", encoding="utf-8")

        with pytest.raises(i18n.CatalogError) as exc_info:
            main._ensure_i18n_ready()

        message = str(exc_info.value)
        assert str(resolved / "zh.json") in message

        # The console print() is a redundant channel alongside the raised
        # exception -- assert it actually carries the same information.
        captured = capsys.readouterr()
        assert str(resolved / "zh.json") in captured.out

    def test_non_catalog_error_propagates_unwrapped(self, monkeypatch):
        """The guard must react only to CatalogError -- any other exception from
        load_i18n() passes through untouched, never caught or reinterpreted."""
        import customer_portal_api.main as main

        def _boom():
            raise ValueError("boom")

        monkeypatch.setattr(main, "load_i18n", _boom)

        with pytest.raises(ValueError, match="boom"):
            main._ensure_i18n_ready()

    def test_guard_runs_before_initialize_runtime_in_lifespan_source(self):
        """Static ordering check: `lifespan()` must call the guard strictly
        before `initialize_runtime()`. Avoids driving the full async lifespan."""
        import customer_portal_api.main as main

        source = inspect.getsource(main.lifespan)
        guard_pos = source.index("_ensure_i18n_ready()")
        init_pos = source.index("initialize_runtime()")
        assert guard_pos < init_pos
