"""Integrity + lang-rendering coverage for story 3.3's `core/` catalog keys.

`tests/test_api_actions_i18n.py` only exercises the capability labels that
happen to be reachable through `chatgpt`/`windsurf`'s action lists -- 2 of
the 9 `STANDARD_CAPABILITIES` entries. This module asserts every minted
label directly against `core/capability_registry.py`, and covers
`core/desktop_apps.py::build_desktop_app_state`'s lang-dependent output,
which no existing test touches.
"""
from __future__ import annotations

import os
from unittest.mock import patch

from i18n import t
from core.capability_registry import STANDARD_CAPABILITIES
from core.desktop_apps import build_desktop_app_state

EXISTING_DIR = os.getcwd()  # any real path -- `existing_paths()` checks os.path.exists


def test_every_capability_label_and_param_label_translates_to_english():
    for cap_id, definition in STANDARD_CAPABILITIES.items():
        assert t(definition.label, "en") != definition.label, f"{cap_id}.label has no English translation"
        assert t(definition.label, "en") != t(definition.label, "zh"), f"{cap_id}.label renders identically in en/zh"
        for param in definition.param_schema:
            key = param["label"]
            if not key.startswith("core."):
                continue  # already a plain English literal, not a minted key
            assert t(key, "en") != key, f"{cap_id} param {param['key']}.label has no English translation"


def test_build_desktop_app_state_renders_status_and_ready_labels_by_lang():
    ready_en = build_desktop_app_state(
        app_id="x", app_name="X", process_patterns=["nonexistent-process-xyz"],
        install_paths=[EXISTING_DIR], current_account_present=True, lang="en",
    )
    assert ready_en["status_label"] == "Not running"
    assert ready_en["ready_label"] == "Ready"

    ready_zh = build_desktop_app_state(
        app_id="x", app_name="X", process_patterns=["nonexistent-process-xyz"],
        install_paths=[EXISTING_DIR], current_account_present=True, lang="zh",
    )
    assert ready_zh["status_label"] == "未打开"
    assert ready_zh["ready_label"] == "已就绪"

    not_installed_en = build_desktop_app_state(
        app_id="x", app_name="X", process_patterns=["nonexistent-process-xyz"], lang="en",
    )
    assert not_installed_en["ready_label"] == "Not installed"

    installed_not_configured_en = build_desktop_app_state(
        app_id="x", app_name="X", process_patterns=["nonexistent-process-xyz"],
        install_paths=[EXISTING_DIR], lang="en",
    )
    assert installed_not_configured_en["ready_label"] == "Not configured"


def test_build_desktop_app_state_renders_running_status_label_by_lang():
    with patch("core.desktop_apps.is_process_running", return_value=True) as mock_running:
        running_en = build_desktop_app_state(
            app_id="x", app_name="X", process_patterns=["anything"], lang="en",
        )
        running_zh = build_desktop_app_state(
            app_id="x", app_name="X", process_patterns=["anything"], lang="zh",
        )
    assert running_en["status_label"] == "Running"
    assert running_zh["status_label"] == "已打开"
    mock_running.assert_called_with(["anything"])
