"""Direct unit coverage for `core/desktop_apps.py`'s process-matching and
OS-dispatch logic.

`is_process_running` and `_list_process_entries` are the app's entire
process-matching and OS-dispatch logic, but nothing in the suite exercises
them directly -- the one existing reference, `tests/test_core_i18n_labels.py`,
patches `is_process_running` away entirely to test
`build_desktop_app_state`'s label rendering. This module drives both
functions directly: `is_process_running` via a stubbed
`_list_process_entries`, and `_list_process_entries` via patched
`platform.system` / `_run_command`.
"""
from __future__ import annotations

from unittest.mock import patch

from core.desktop_apps import _list_process_entries, is_process_running


# ---------------------------------------------------------------------------
# is_process_running -- matching / normalization branches
# ---------------------------------------------------------------------------


def test_is_process_running_exact_match():
    with patch("core.desktop_apps._list_process_entries", return_value=["foo"]):
        assert is_process_running(["foo"]) is True


def test_is_process_running_path_suffix_match():
    with patch("core.desktop_apps._list_process_entries", return_value=["/usr/bin/foo"]):
        assert is_process_running(["foo"]) is True


def test_is_process_running_exe_suffix_match():
    with patch("core.desktop_apps._list_process_entries", return_value=["/usr/bin/foo.exe"]):
        assert is_process_running(["foo"]) is True


def test_is_process_running_macos_bundle_match():
    entries = ["/Applications/Foo.app/Contents/MacOS/foo"]
    with patch("core.desktop_apps._list_process_entries", return_value=entries):
        assert is_process_running(["foo"]) is True


def test_is_process_running_macos_bundle_exe_match():
    # A macOS .app bundle containing a `.exe`-suffixed binary is not a real
    # combination -- this exercises the defensive branch as coded, not an
    # observed real-world path shape.
    entries = ["/Applications/Foo.app/Contents/MacOS/foo.exe"]
    with patch("core.desktop_apps._list_process_entries", return_value=entries):
        assert is_process_running(["foo"]) is True


def test_is_process_running_slash_pattern_exact_match():
    with patch("core.desktop_apps._list_process_entries", return_value=["usr/bin/foo"]):
        assert is_process_running(["usr/bin/foo"]) is True


def test_is_process_running_slash_pattern_rejects_suffix_only():
    # Slash-bearing patterns must match exactly -- suffix matches (which
    # would apply to slash-free patterns) are not accepted for them.
    with patch("core.desktop_apps._list_process_entries", return_value=["/opt/usr/bin/foo"]):
        assert is_process_running(["usr/bin/foo"]) is False


def test_is_process_running_empty_patterns_returns_false_without_listing():
    with patch("core.desktop_apps._list_process_entries") as mock_list:
        assert is_process_running(["", "   "]) is False
    mock_list.assert_not_called()


def test_is_process_running_no_match():
    with patch("core.desktop_apps._list_process_entries", return_value=["bar", "baz"]):
        assert is_process_running(["zzz-nonexistent"]) is False


def test_is_process_running_skips_entry_that_normalizes_to_empty():
    with patch("core.desktop_apps._list_process_entries", return_value=["", "   ", "foo"]):
        assert is_process_running(["foo"]) is True


def test_is_process_running_slash_pattern_with_exe_suffix_requires_exact_match():
    with patch("core.desktop_apps._list_process_entries", return_value=["usr/bin/foo.exe"]):
        assert is_process_running(["usr/bin/foo.exe"]) is True
    with patch("core.desktop_apps._list_process_entries", return_value=["/opt/usr/bin/foo.exe"]):
        assert is_process_running(["usr/bin/foo.exe"]) is False


def test_is_process_running_matches_case_insensitively():
    with patch("core.desktop_apps._list_process_entries", return_value=["Chrome"]):
        assert is_process_running(["CHROME"]) is True


def test_is_process_running_normalizes_quoted_pattern():
    with patch("core.desktop_apps._list_process_entries", return_value=["/usr/bin/foo"]):
        assert is_process_running(['"foo"']) is True


def test_is_process_running_normalizes_pattern_side_exe_suffix():
    with patch("core.desktop_apps._list_process_entries", return_value=["foo"]):
        assert is_process_running(["Foo.exe"]) is True


def test_is_process_running_backslash_path_pattern_requires_exact_normalized_match():
    # Once a pattern contains a directory separator (backslash converted to
    # forward slash), it keeps its full path rather than being reduced to a
    # bare basename, so it must match an entry exactly -- not by suffix.
    with patch("core.desktop_apps._list_process_entries", return_value=["C:\\Program Files\\Foo.exe"]):
        assert is_process_running(["C:\\Program Files\\Foo.exe"]) is True
    with patch("core.desktop_apps._list_process_entries", return_value=["D:\\Other\\Foo.exe"]):
        assert is_process_running(["C:\\Program Files\\Foo.exe"]) is False


def test_is_process_running_matches_on_later_pattern_after_earlier_miss():
    with patch("core.desktop_apps._list_process_entries", return_value=["foo"]):
        assert is_process_running(["nomatch", "foo"]) is True


def test_is_process_running_matches_on_later_entry_after_earlier_miss():
    with patch("core.desktop_apps._list_process_entries", return_value=["bar", "foo"]):
        assert is_process_running(["foo"]) is True


# ---------------------------------------------------------------------------
# _list_process_entries -- Windows (tasklist) vs POSIX (ps) dispatch
# ---------------------------------------------------------------------------


def test_list_process_entries_windows_dispatch():
    csv_output = (
        '"chrome.exe","1234","Console","1","50,000 K"\r\n'
        '"Slack.exe","5678","Console","1","80,000 K"\r\n'
    )
    with patch("core.desktop_apps.platform.system", return_value="Windows"), \
            patch("core.desktop_apps._run_command", return_value=(True, csv_output)) as mock_run:
        entries = _list_process_entries()

    assert entries == ["chrome.exe", "Slack.exe"]
    mock_run.assert_called_once_with(["tasklist", "/FO", "CSV", "/NH"])


def test_list_process_entries_windows_dispatch_skips_blank_rows():
    csv_output = '"chrome.exe","1234","Console","1","50,000 K"\r\n\r\n"","","","",""\r\n'
    with patch("core.desktop_apps.platform.system", return_value="Windows"), \
            patch("core.desktop_apps._run_command", return_value=(True, csv_output)):
        entries = _list_process_entries()

    assert entries == ["chrome.exe"]


def test_list_process_entries_windows_dispatch_handles_quoted_comma_field():
    csv_output = '"Some, App.exe","1234","Console","1","50,000 K"\r\n'
    with patch("core.desktop_apps.platform.system", return_value="Windows"), \
            patch("core.desktop_apps._run_command", return_value=(True, csv_output)):
        entries = _list_process_entries()

    assert entries == ["Some, App.exe"]


def test_list_process_entries_windows_dispatch_ok_with_empty_output():
    with patch("core.desktop_apps.platform.system", return_value="Windows"), \
            patch("core.desktop_apps._run_command", return_value=(True, "")):
        entries = _list_process_entries()

    assert entries == []


def test_list_process_entries_windows_dispatch_command_fails():
    with patch("core.desktop_apps.platform.system", return_value="Windows"), \
            patch("core.desktop_apps._run_command", return_value=(False, "")) as mock_run:
        entries = _list_process_entries()

    assert entries == []
    mock_run.assert_called_once_with(["tasklist", "/FO", "CSV", "/NH"])


def test_list_process_entries_posix_dispatch():
    ps_output = "  chrome  \n\nSlack\n   \nfinder\n"
    with patch("core.desktop_apps.platform.system", return_value="Darwin"), \
            patch("core.desktop_apps._run_command", return_value=(True, ps_output)) as mock_run:
        entries = _list_process_entries()

    assert entries == ["chrome", "Slack", "finder"]
    mock_run.assert_called_once_with(["ps", "-ax", "-o", "comm="])


def test_list_process_entries_posix_dispatch_ok_with_empty_output():
    with patch("core.desktop_apps.platform.system", return_value="Darwin"), \
            patch("core.desktop_apps._run_command", return_value=(True, "")):
        entries = _list_process_entries()

    assert entries == []


def test_list_process_entries_posix_dispatch_command_fails():
    with patch("core.desktop_apps.platform.system", return_value="Linux"), \
            patch("core.desktop_apps._run_command", return_value=(False, "")) as mock_run:
        entries = _list_process_entries()

    assert entries == []
    mock_run.assert_called_once_with(["ps", "-ax", "-o", "comm="])
