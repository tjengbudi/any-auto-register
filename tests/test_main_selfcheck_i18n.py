"""main.py --selfcheck-i18n 单元测试 — Unit tests for main.py's `_run_selfcheck_i18n()`.

只测 helper 本身，不驱动 `if __name__ == "__main__":` 的 sys.exit 分支 —
Only exercises the helper directly; never drives the `sys.exit(...)` dispatch
in `if __name__ == "__main__":`.
`main` is imported lazily inside each test body per tests/conftest.py's
documented "hoisting the import bypasses the test-DB engine patch" hazard,
following test_main_startup_guard.py's established pattern.
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


class TestRunSelfcheckI18n:
    def test_real_shipped_catalogs_succeed(self, capsys):
        import main

        result = main._run_selfcheck_i18n()

        assert result == 0
        captured = capsys.readouterr()
        assert "[selfcheck] OK" in captured.out

    def test_missing_zh_json_fails_with_bundle_hint(self, tmp_path, monkeypatch, capsys):
        import i18n
        import main

        resolved = tmp_path.resolve()
        monkeypatch.setattr(i18n, "__file__", str(resolved / "__init__.py"))
        (resolved / "en.json").write_text("{}", encoding="utf-8")

        result = main._run_selfcheck_i18n()

        assert result == 1
        captured = capsys.readouterr()
        assert "[selfcheck] FAIL: " in captured.out
        assert str(resolved / "zh.json") in captured.out
        assert "i18n/zh.json" in captured.out
        assert "i18n/en.json" in captured.out
        assert "i18n/vi.json" in captured.out

    def test_missing_target_locales_alone_still_succeeds(self, tmp_path, monkeypatch, capsys):
        import i18n
        import main

        resolved = tmp_path.resolve()
        monkeypatch.setattr(i18n, "__file__", str(resolved / "__init__.py"))
        (resolved / "zh.json").write_text(
            json.dumps({"chatgpt": {"a3f21c8e": "你好"}}), encoding="utf-8"
        )
        # en.json and vi.json intentionally absent from tmp_path.

        result = main._run_selfcheck_i18n()

        assert result == 0
        captured = capsys.readouterr()
        assert "[selfcheck] OK" in captured.out
        assert i18n._catalogs["en"] == {}
        assert i18n._catalogs["vi"] == {}
        assert i18n._catalogs["zh"] == {"chatgpt": {"a3f21c8e": "你好"}}

    def test_non_catalog_error_propagates_unwrapped(self, monkeypatch):
        """The self-check must react only to CatalogError -- any other exception
        from selfcheck_i18n() passes through untouched, never swallowed into a
        `[selfcheck] FAIL` exit code."""
        import main

        def _boom():
            raise ValueError("boom")

        monkeypatch.setattr(main, "selfcheck_i18n", _boom)

        with pytest.raises(ValueError, match="boom"):
            main._run_selfcheck_i18n()

    def test_selfcheck_dispatch_runs_before_uvicorn_in_main_block_source(self):
        """Static ordering check: the `--selfcheck-i18n` CLI branch must appear
        strictly before `uvicorn.run(...)` in the `if __name__ == "__main__":`
        block, so the self-check can never fall through into the FastAPI
        lifespan (which would start solver_manager.start_async() and download
        a browser). Avoids actually driving the `__main__` block, which only
        executes when the module is run as a script."""
        import main

        source = inspect.getsource(main)
        main_block = source[source.index('if __name__ == "__main__":'):]
        selfcheck_pos = main_block.index("--selfcheck-i18n")
        uvicorn_pos = main_block.index("uvicorn.run(")
        assert selfcheck_pos < uvicorn_pos
