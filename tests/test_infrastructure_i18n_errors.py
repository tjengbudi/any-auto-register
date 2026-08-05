"""story 4.13 -- the `infrastructure/` failure messages.

Regression tests for all 4 pre-existing Chinese-bearing `raise` sites across
`infrastructure/provider_definitions_repository.py` and
`infrastructure/provider_settings_repository.py`. Each site now carries
`.i18n_key`/`.i18n_params` (AD-17), attached directly onto the exception
instance before it is raised -- mirroring `application/config.py:27-28` --
with no shared `_raise_keyed` helper and no `from i18n import ...` inside
`infrastructure/` itself (asserted below by
`test_infrastructure_source_files_do_not_import_i18n`).

Also covers the story's `api/` round-trip: `PUT /api/provider-settings` with
an unknown `provider_key` renders the carried key in English via
`api/deps.py::render_detail`, with zero `api/` code change.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from i18n import t
from infrastructure.provider_definitions_repository import ProviderDefinitionsRepository
from infrastructure.provider_settings_repository import ProviderSettingsRepository

_ROOT = Path(__file__).resolve().parent.parent

_INFRASTRUCTURE_FILES = [
    Path("infrastructure/provider_definitions_repository.py"),
    Path("infrastructure/provider_settings_repository.py"),
]


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
# infrastructure/provider_definitions_repository.py -- 2 sites
# ---------------------------------------------------------------------------


def test_provider_definitions_save_with_unknown_id():
    repo = ProviderDefinitionsRepository()

    with pytest.raises(ValueError) as excinfo:
        repo.save(
            definition_id=999999,
            provider_type="mailbox",
            provider_key="does-not-matter",
            label="x",
            description="",
            driver_type="generic_http_mailbox",
            enabled=True,
        )

    _assert_keyed(excinfo.value, "infrastructure.f4a7f40a", {})


def test_provider_definitions_delete_blocked_by_existing_settings():
    defs_repo = ProviderDefinitionsRepository()
    definition = defs_repo.save(
        definition_id=None,
        provider_type="mailbox",
        provider_key="story_4_13_definition",
        label="Story 4.13 test definition",
        description="",
        driver_type="generic_http_mailbox",
        enabled=True,
    )

    settings_repo = ProviderSettingsRepository(definitions=defs_repo)
    settings_repo.save(
        setting_id=None,
        provider_type="mailbox",
        provider_key="story_4_13_definition",
        display_name="Story 4.13 test setting",
        auth_mode="",
        enabled=True,
        is_default=False,
        config={},
        auth={},
        metadata={},
    )

    with pytest.raises(ValueError) as excinfo:
        defs_repo.delete(definition.id)

    _assert_keyed(excinfo.value, "infrastructure.be12dfa8", {})


# ---------------------------------------------------------------------------
# infrastructure/provider_settings_repository.py -- 2 sites
# ---------------------------------------------------------------------------


def test_provider_settings_save_with_unknown_id():
    defs_repo = ProviderDefinitionsRepository()
    defs_repo.save(
        definition_id=None,
        provider_type="mailbox",
        provider_key="story_4_13_settings_definition",
        label="Story 4.13 test definition",
        description="",
        driver_type="generic_http_mailbox",
        enabled=True,
    )
    settings_repo = ProviderSettingsRepository(definitions=defs_repo)

    with pytest.raises(ValueError) as excinfo:
        settings_repo.save(
            setting_id=999999,
            provider_type="mailbox",
            provider_key="story_4_13_settings_definition",
            display_name="",
            auth_mode="",
            enabled=True,
            is_default=False,
            config={},
            auth={},
            metadata={},
        )

    _assert_keyed(excinfo.value, "infrastructure.0fa0f821", {})


def test_provider_settings_save_unknown_provider():
    settings_repo = ProviderSettingsRepository()

    with pytest.raises(ValueError) as excinfo:
        settings_repo.save(
            setting_id=None,
            provider_type="mailbox",
            provider_key="totally_unknown_provider_xyz",
            display_name="",
            auth_mode="",
            enabled=True,
            is_default=False,
            config={},
            auth={},
            metadata={},
        )

    _assert_keyed(
        excinfo.value,
        "infrastructure.93615891",
        {"provider_type": "mailbox", "provider_key": "totally_unknown_provider_xyz"},
    )


# ---------------------------------------------------------------------------
# api/ round-trip: PUT /api/provider-settings with an unknown provider_key --
# proves api/deps.py::render_detail already picks up this story's new key
# with zero api/ code change (I/O & Edge-Case Matrix row 3).
# ---------------------------------------------------------------------------


def test_api_provider_settings_put_unknown_provider_renders_english(client):
    client.put("/api/config", json={"data": {"ui_language": "en"}})

    resp = client.put(
        "/api/provider-settings",
        json={
            "provider_type": "mailbox",
            "provider_key": "totally_unknown_provider_xyz",
        },
    )

    assert resp.status_code == 400
    assert resp.json()["detail"] == "Unknown provider: mailbox/totally_unknown_provider_xyz"


def test_api_provider_settings_put_unknown_provider_renders_chinese_default(client):
    resp = client.put(
        "/api/provider-settings",
        json={
            "provider_type": "mailbox",
            "provider_key": "totally_unknown_provider_xyz",
        },
    )

    assert resp.status_code == 400
    assert resp.json()["detail"] == "未知 provider: mailbox/totally_unknown_provider_xyz"


# ---------------------------------------------------------------------------
# Namespace-boundary check
# ---------------------------------------------------------------------------


def test_all_infrastructure_i18n_keys_use_the_infrastructure_namespace():
    """Every `i18n_key = "..."` literal in the 2 infrastructure/ files
    migrated by this story must belong to the `infrastructure` owner -- no
    cross-namespace reuse of api/'s already-shipped api.f4a7f40a/api.0fa0f821
    keys (AD-2), and exactly 4 sites carry one (re-enumerated count)."""
    pattern = re.compile(r'i18n_key\s*=\s*"([^"]+)"')
    found: list[str] = []
    for rel in _INFRASTRUCTURE_FILES:
        text = (_ROOT / rel).read_text(encoding="utf-8")
        found.extend(pattern.findall(text))

    assert len(found) == 4, found
    assert len(set(found)) == 4, "expected 4 distinct keys, found duplicates"
    for key in found:
        assert key.startswith("infrastructure."), key
        assert key not in ("api.f4a7f40a", "api.0fa0f821"), key


def test_infrastructure_source_files_do_not_import_i18n():
    """Mirrors this story's Never-list constraint: no `from i18n import ...`
    or `import i18n` inside infrastructure/ -- every site attaches
    i18n_key/i18n_params directly onto the exception, with nothing to
    render there."""
    for rel in _INFRASTRUCTURE_FILES:
        text = (_ROOT / rel).read_text(encoding="utf-8")
        assert "from i18n" not in text, rel
        assert "import i18n" not in text, rel
