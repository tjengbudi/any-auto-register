"""story 4.13 -- the `providers/` failure messages.

Regression tests for all 18 pre-existing Chinese-bearing `raise` sites
across `providers/captcha/local_solver.py`, `providers/captcha/twocaptcha.py`,
`providers/captcha/yescaptcha.py`, `providers/registry.py`,
`providers/proxy/rotating_gateway.py` and `providers/proxy/api_extract.py`.

Each site now carries `.i18n_key`/`.i18n_params` (AD-17), attached directly
onto the exception instance before it is raised -- mirroring
`application/config.py:27-28` -- with no shared `_raise_keyed` helper and no
`from i18n import ...` inside `providers/` itself (asserted below by
`test_providers_source_files_do_not_import_i18n`).

No live captcha-solve or proxy-fetch runs here: every HTTP call is mocked.
"""
from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from i18n import t
from providers.captcha.local_solver import LocalSolverCaptcha
from providers.captcha.twocaptcha import TwoCaptcha
from providers.captcha.yescaptcha import YesCaptcha
from providers.proxy.api_extract import ApiExtractProvider
from providers.proxy.rotating_gateway import RotatingProxyProvider
from providers.registry import _registry, create_provider, register_provider

_ROOT = Path(__file__).resolve().parent.parent

_PROVIDERS_FILES = [
    Path("providers/captcha/local_solver.py"),
    Path("providers/captcha/twocaptcha.py"),
    Path("providers/captcha/yescaptcha.py"),
    Path("providers/registry.py"),
    Path("providers/proxy/rotating_gateway.py"),
    Path("providers/proxy/api_extract.py"),
]


def _resp(json_data=None, text: str = "", status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    resp.json.return_value = json_data if json_data is not None else {}
    resp.raise_for_status = lambda: None
    return resp


def _assert_keyed(exc: Exception, expected_key: str, expected_params: dict) -> None:
    assert exc.i18n_key == expected_key
    assert exc.i18n_params == expected_params
    assert t(exc.i18n_key, "zh", **exc.i18n_params) == str(exc)
    # A missing/empty/copy-pasted-Chinese en.json entry would pass every
    # other assertion here (the zh round-trip only proves the source
    # literal matches its own key) -- catch it explicitly, since English
    # rendering is this story's whole point (CAP-4's stated scenario).
    en_rendered = t(exc.i18n_key, "en", **exc.i18n_params)
    assert en_rendered, f"{exc.i18n_key} has no English translation"
    assert en_rendered != str(exc), f"{exc.i18n_key} English translation was not localized"


# ---------------------------------------------------------------------------
# providers/captcha/local_solver.py -- 5 sites
# ---------------------------------------------------------------------------


@patch("requests.get")
def test_local_solver_missing_task_id(mock_get):
    mock_get.return_value = _resp(json_data={}, text="no task id here")
    solver = LocalSolverCaptcha(solver_url="http://localhost:8889")

    with pytest.raises(RuntimeError) as excinfo:
        solver.solve_turnstile("http://page", "site-key")

    _assert_keyed(excinfo.value, "providers.4ea7683b", {"text": "no task id here"})


@patch("time.sleep", lambda *a, **k: None)
@patch("requests.get")
def test_local_solver_turnstile_failed_with_message(mock_get):
    mock_get.side_effect = [
        _resp(json_data={"taskId": "abc"}),
        _resp(json_data={"errorId": 1, "errorDescription": "bad site key"}),
    ]
    solver = LocalSolverCaptcha(solver_url="http://localhost:8889")

    with pytest.raises(RuntimeError) as excinfo:
        solver.solve_turnstile("http://page", "site-key")

    _assert_keyed(excinfo.value, "providers.78d5466d", {"message": "bad site key"})


@patch("time.sleep", lambda *a, **k: None)
@patch("requests.get")
def test_local_solver_captcha_fail_status(mock_get):
    mock_get.side_effect = [
        _resp(json_data={"taskId": "abc"}),
        _resp(json_data={"errorId": 0, "status": "CAPTCHA_FAIL"}),
    ]
    solver = LocalSolverCaptcha(solver_url="http://localhost:8889")

    with pytest.raises(RuntimeError) as excinfo:
        solver.solve_turnstile("http://page", "site-key")

    _assert_keyed(excinfo.value, "providers.17194286", {})


@patch("time.sleep", lambda *a, **k: None)
@patch("requests.get")
def test_local_solver_turnstile_timeout(mock_get):
    submit = _resp(json_data={"taskId": "abc"})
    pending = _resp(status_code=404)
    mock_get.side_effect = [submit] + [pending] * 60
    solver = LocalSolverCaptcha(solver_url="http://localhost:8889")

    with pytest.raises(TimeoutError) as excinfo:
        solver.solve_turnstile("http://page", "site-key")

    _assert_keyed(excinfo.value, "providers.4ccd485e", {})


@patch("time.sleep", lambda *a, **k: None)
@patch("subprocess.Popen")
@patch("requests.get", side_effect=Exception("connection refused"))
def test_local_solver_start_solver_timeout(mock_get, mock_popen):
    with pytest.raises(RuntimeError) as excinfo:
        LocalSolverCaptcha.start_solver(headless=True, browser_type="camoufox", port=18889)

    _assert_keyed(excinfo.value, "providers.850c56bd", {})


# ---------------------------------------------------------------------------
# providers/captcha/twocaptcha.py -- 5 sites
# ---------------------------------------------------------------------------


def test_twocaptcha_missing_api_key():
    with pytest.raises(RuntimeError) as excinfo:
        TwoCaptcha.from_config({})

    _assert_keyed(excinfo.value, "providers.1146b4a0", {})


@patch("requests.post")
def test_twocaptcha_create_task_failed(mock_post):
    payload = {"status": 0, "request": "ERROR_KEY_DOES_NOT_EXIST"}
    mock_post.return_value = _resp(json_data=payload)
    solver = TwoCaptcha(api_key="key")

    with pytest.raises(RuntimeError) as excinfo:
        solver.solve_turnstile("http://page", "site-key")

    _assert_keyed(excinfo.value, "providers.bc8aa395", {"payload": str(payload)})


@patch("requests.post")
def test_twocaptcha_no_task_id_returned(mock_post):
    payload = {"status": 1}
    mock_post.return_value = _resp(json_data=payload)
    solver = TwoCaptcha(api_key="key")

    with pytest.raises(RuntimeError) as excinfo:
        solver.solve_turnstile("http://page", "site-key")

    _assert_keyed(excinfo.value, "providers.b0f1f4ea", {"payload": str(payload)})


@patch("time.sleep", lambda *a, **k: None)
@patch("requests.post")
@patch("requests.get")
def test_twocaptcha_poll_error(mock_get, mock_post):
    mock_post.return_value = _resp(json_data={"status": 1, "request": "task123"})
    data = {"status": 0, "request": "ERROR_CAPTCHA_UNSOLVABLE"}
    mock_get.return_value = _resp(json_data=data)
    solver = TwoCaptcha(api_key="key")

    with pytest.raises(RuntimeError) as excinfo:
        solver.solve_turnstile("http://page", "site-key")

    _assert_keyed(excinfo.value, "providers.04161146", {"data": str(data)})


@patch("time.sleep", lambda *a, **k: None)
@patch("requests.post")
@patch("requests.get")
def test_twocaptcha_turnstile_timeout(mock_get, mock_post):
    mock_post.return_value = _resp(json_data={"status": 1, "request": "task123"})
    mock_get.return_value = _resp(json_data={"status": 0, "request": "CAPCHA_NOT_READY"})
    solver = TwoCaptcha(api_key="key")

    with pytest.raises(TimeoutError) as excinfo:
        solver.solve_turnstile("http://page", "site-key")

    _assert_keyed(excinfo.value, "providers.482309b7", {})


# ---------------------------------------------------------------------------
# providers/captcha/yescaptcha.py -- 4 sites (CAP-4's stated acceptance
# scenario lives at the from_config site below)
# ---------------------------------------------------------------------------


def test_yescaptcha_missing_client_key():
    with pytest.raises(RuntimeError) as excinfo:
        YesCaptcha.from_config({})

    _assert_keyed(excinfo.value, "providers.9bfc5153", {})


@patch("requests.post")
def test_yescaptcha_create_task_failed(mock_post):
    mock_post.return_value = _resp(json_data={}, text="createTask failed")
    solver = YesCaptcha(client_key="key")

    with pytest.raises(RuntimeError) as excinfo:
        solver.solve_turnstile("http://page", "site-key")

    _assert_keyed(excinfo.value, "providers.1b3c747c", {"text": "createTask failed"})


@patch("time.sleep", lambda *a, **k: None)
@patch("requests.post")
def test_yescaptcha_poll_error(mock_post):
    error_body = {"errorId": 5, "errorDescription": "bad site key"}
    mock_post.side_effect = [
        _resp(json_data={"taskId": "abc"}),
        _resp(json_data=error_body),
    ]
    solver = YesCaptcha(client_key="key")

    with pytest.raises(RuntimeError) as excinfo:
        solver.solve_turnstile("http://page", "site-key")

    _assert_keyed(excinfo.value, "providers.4ec76fbc", {"d": str(error_body)})


@patch("time.sleep", lambda *a, **k: None)
@patch("requests.post")
def test_yescaptcha_turnstile_timeout(mock_post):
    mock_post.side_effect = [_resp(json_data={"taskId": "abc"})] + [
        _resp(json_data={"status": "processing", "errorId": 0})
    ] * 60
    solver = YesCaptcha(client_key="key")

    with pytest.raises(TimeoutError) as excinfo:
        solver.solve_turnstile("http://page", "site-key")

    _assert_keyed(excinfo.value, "providers.ee9cda95", {})


# ---------------------------------------------------------------------------
# providers/registry.py -- 2 sites
# ---------------------------------------------------------------------------


def test_registry_unregistered_provider():
    with pytest.raises(ValueError) as excinfo:
        create_provider("captcha", "does_not_exist_driver", {})

    _assert_keyed(
        excinfo.value,
        "providers.0d361083",
        {"provider_type": "captcha", "driver_type": "does_not_exist_driver"},
    )


def test_registry_missing_from_config_classmethod():
    class _NoFactory:
        pass

    register_provider("captcha", "_test_no_factory")(_NoFactory)
    try:
        with pytest.raises(TypeError) as excinfo:
            create_provider("captcha", "_test_no_factory", {})
        _assert_keyed(excinfo.value, "providers.446112fc", {"cls_name": "_NoFactory"})
    finally:
        _registry["captcha"].pop("_test_no_factory", None)


# ---------------------------------------------------------------------------
# providers/proxy/rotating_gateway.py -- 1 site
# ---------------------------------------------------------------------------


def test_rotating_gateway_missing_url():
    with pytest.raises(RuntimeError) as excinfo:
        RotatingProxyProvider.from_config({})

    _assert_keyed(excinfo.value, "providers.76b19954", {})


# ---------------------------------------------------------------------------
# providers/proxy/api_extract.py -- 1 site
# ---------------------------------------------------------------------------


def test_api_extract_provider_missing_url():
    with pytest.raises(RuntimeError) as excinfo:
        ApiExtractProvider.from_config({})

    _assert_keyed(excinfo.value, "providers.14a57e71", {})


# ---------------------------------------------------------------------------
# Namespace-boundary check
# ---------------------------------------------------------------------------


def test_all_providers_i18n_keys_use_the_providers_namespace():
    """Every `i18n_key = "..."` literal in the 6 providers/ files migrated by
    this story must belong to the `providers` owner -- no cross-namespace
    reuse (AD-2), and exactly 18 sites carry one (re-enumerated count)."""
    pattern = re.compile(r'i18n_key\s*=\s*"([^"]+)"')
    found: list[str] = []
    for rel in _PROVIDERS_FILES:
        text = (_ROOT / rel).read_text(encoding="utf-8")
        found.extend(pattern.findall(text))

    assert len(found) == 18, found
    assert len(set(found)) == 18, "expected 18 distinct keys, found duplicates"
    for key in found:
        assert key.startswith("providers."), key


def test_providers_source_files_do_not_import_i18n():
    """Mirrors this story's Never-list constraint: no `from i18n import ...`
    or `import i18n` inside providers/ -- every site attaches i18n_key/
    i18n_params directly onto the exception, with nothing to render there."""
    for rel in _PROVIDERS_FILES:
        text = (_ROOT / rel).read_text(encoding="utf-8")
        assert "from i18n" not in text, rel
        assert "import i18n" not in text, rel
