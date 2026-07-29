"""main.py 启动守卫单元测试 — Unit tests for main.py's `_ensure_i18n_ready()` startup guard.

只测 helper 本身，不驱动完整的 `async with lifespan(app):` —
Only exercises the helper directly; never drives the full `lifespan()`
context manager (which would start the scheduler/task runtime/solver too).
`main` is imported lazily inside each test body per tests/conftest.py's
documented "hoisting the import bypasses the test-DB engine patch" hazard.
"""
from __future__ import annotations

import inspect
import json

import pytest


@pytest.fixture(autouse=True)
def _isolated_catalog_cache(monkeypatch):
    """Every test gets its own i18n catalog cache slot so tests never leak state."""
    import i18n

    monkeypatch.setattr(i18n, "_catalogs", None)
    yield


class TestEnsureI18nReady:
    def test_real_shipped_catalog_succeeds(self):
        import main

        # Must not raise; the real shipped i18n/zh.json is present and valid.
        main._ensure_i18n_ready()

    def test_missing_zh_json_aborts_with_bundle_hint(self, tmp_path, monkeypatch, capsys):
        import i18n
        import main

        resolved = tmp_path.resolve()
        monkeypatch.setattr(i18n, "__file__", str(resolved / "__init__.py"))
        (resolved / "en.json").write_text("{}", encoding="utf-8")

        with pytest.raises(i18n.CatalogError) as exc_info:
            main._ensure_i18n_ready()

        message = str(exc_info.value)
        assert str(resolved / "zh.json") in message
        assert "i18n/zh.json" in message
        assert "i18n/en.json" in message
        assert "i18n/vi.json" in message
        # exc's own text already carries an "i18n:" tag -- no doubled "[i18n] i18n:" prefix.
        assert "[i18n]" not in message

        # The console print() is a redundant channel alongside the raised exception --
        # assert it actually carries the same information, not just that it didn't crash.
        captured = capsys.readouterr()
        assert str(resolved / "zh.json") in captured.out
        assert "i18n/en.json" in captured.out

    def test_missing_target_locales_pass_through(self, tmp_path, monkeypatch):
        import i18n
        import main

        resolved = tmp_path.resolve()
        monkeypatch.setattr(i18n, "__file__", str(resolved / "__init__.py"))
        (resolved / "zh.json").write_text(
            json.dumps({"chatgpt": {"a3f21c8e": "你好"}}), encoding="utf-8"
        )
        # en.json and vi.json intentionally absent from tmp_path.

        # Must not raise; i18n.load() degrades both missing target catalogs to {}.
        main._ensure_i18n_ready()

        assert i18n._catalogs["en"] == {}
        assert i18n._catalogs["vi"] == {}
        assert i18n._catalogs["zh"] == {"chatgpt": {"a3f21c8e": "你好"}}

    def test_non_catalog_error_propagates_unwrapped(self, monkeypatch):
        """The guard must react only to CatalogError -- any other exception from
        load_i18n() passes through untouched, never caught or reinterpreted."""
        import main

        def _boom():
            raise ValueError("boom")

        monkeypatch.setattr(main, "load_i18n", _boom)

        with pytest.raises(ValueError, match="boom"):
            main._ensure_i18n_ready()

    def test_guard_runs_before_init_db_in_lifespan_source(self):
        """Static ordering check: `lifespan()` must call the guard strictly before
        `init_db()`, per this story's core "fail fast before any DB work" guarantee.
        Avoids driving the full async lifespan, which also starts the scheduler,
        task runtime, solver subprocess, and lifecycle manager."""
        import main

        source = inspect.getsource(main.lifespan)
        guard_pos = source.index("_ensure_i18n_ready()")
        init_db_pos = source.index("init_db()")
        assert guard_pos < init_db_pos
