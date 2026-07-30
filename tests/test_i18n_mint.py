"""tools/i18n_mint.py unit tests -- covers every row of the I/O & Edge-Case
Matrix in _bmad-output/implementation-artifacts/spec-1-5-the-key-mint-tool.md.

Mirrors tests/test_i18n.py::TestLoad's pattern of redirecting `i18n.__file__`
into a tmp_path fixture: here `i18n_mint.__file__` is redirected the same
way, which makes `_project_root()` (and therefore `_zh_json_path()`)
resolve inside a synthetic `tmp_path` tree instead of the real repository.
"""
from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from tools import i18n_mint


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def _set_root(monkeypatch, tmp_path: Path) -> Path:
    """Redirect i18n_mint's project-root resolution into tmp_path."""
    monkeypatch.setattr(i18n_mint, "__file__", str(tmp_path / "tools" / "i18n_mint.py"))
    return tmp_path


def _write_source(tmp_path: Path, rel_path: str, code: str) -> Path:
    path = tmp_path / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(code), encoding="utf-8")
    return path


def _write_zh(tmp_path: Path, data: dict | None = None) -> Path:
    zh_dir = tmp_path / "i18n"
    zh_dir.mkdir(parents=True, exist_ok=True)
    zh_path = zh_dir / "zh.json"
    zh_path.write_text(json.dumps(data or {}, ensure_ascii=False), encoding="utf-8")
    return zh_path


def _read_zh(tmp_path: Path) -> dict:
    return json.loads((tmp_path / "i18n" / "zh.json").read_text(encoding="utf-8"))


def _guard_write_text(monkeypatch, message: str) -> None:
    """Scoped inside a `with monkeypatch.context() as m` block by the caller;
    fails the test loudly if anything calls Path.write_text while active.
    """

    def _boom(*args, **kwargs):
        raise AssertionError(message)

    monkeypatch.setattr(Path, "write_text", _boom)


# ---------------------------------------------------------------------------
# Owner derivation (Boundaries & Constraints, path-based rule)
# ---------------------------------------------------------------------------


class TestOwnerDerivation:
    def test_platforms_subdirectory_owner_is_the_platform_name(self, tmp_path):
        path = tmp_path / "platforms" / "chatgpt" / "mailbox.py"
        assert i18n_mint._owner_for(path, tmp_path) == "chatgpt"

    def test_snake_case_top_level_package_folds_to_camel_case(self, tmp_path):
        path = tmp_path / "customer_portal_api" / "app" / "routers" / "accounts.py"
        assert i18n_mint._owner_for(path, tmp_path) == "customerPortalApi"

    def test_root_level_file_uses_its_own_stem(self, tmp_path):
        path = tmp_path / "main.py"
        assert i18n_mint._owner_for(path, tmp_path) == "main"

    def test_plain_top_level_package_passes_through_unchanged(self, tmp_path):
        # core/api/providers/services/application/infrastructure/tools all
        # have no underscore, so folding is a no-op for them.
        path = tmp_path / "core" / "registration" / "errors.py"
        assert i18n_mint._owner_for(path, tmp_path) == "core"

    def test_platforms_file_directly_under_platforms_uses_its_own_stem(self, tmp_path):
        # No platform subdirectory: platforms/foo.py, not platforms/foo/bar.py.
        path = tmp_path / "platforms" / "foo.py"
        assert i18n_mint._owner_for(path, tmp_path) == "foo"

    def test_invalid_derived_owner_raises_mint_error_not_a_bare_assert(self, tmp_path):
        # A leading-underscore top-level segment folds to a name starting
        # with an uppercase letter, which _OWNER_RE rejects. This must raise
        # the tool's own operator-facing error, not a bare AssertionError
        # that -O/PYTHONOPTIMIZE would strip away entirely.
        path = tmp_path / "_private_pkg" / "mod.py"
        with pytest.raises(i18n_mint.MintError):
            i18n_mint._owner_for(path, tmp_path)


# ---------------------------------------------------------------------------
# Not-yet-migrated file: one new Chinese string literal
# ---------------------------------------------------------------------------


class TestNotYetMigratedFile:
    def test_new_chinese_string_literal_is_minted(self, monkeypatch, tmp_path):
        _set_root(monkeypatch, tmp_path)
        _write_zh(tmp_path, {})
        _write_source(tmp_path, "main.py", '''\
            x = "你好世界"
        ''')

        exit_code = i18n_mint.main(["main.py"])

        assert exit_code == 0
        catalog = _read_zh(tmp_path)
        assert set(catalog.keys()) == {"main"}
        [(hash8, text)] = list(catalog["main"].items())
        assert text == "你好世界"
        assert hash8 == i18n_mint._hash8("你好世界")

    def test_two_files_in_different_owners_each_mint_their_own_entry(self, monkeypatch, tmp_path):
        _set_root(monkeypatch, tmp_path)
        _write_zh(tmp_path, {})
        _write_source(tmp_path, "platforms/chatgpt/mailbox.py", '''\
            msg = "邮箱验证码获取成功"
        ''')
        _write_source(tmp_path, "customer_portal_api/app/routers/accounts.py", '''\
            msg = "账号已锁定"
        ''')

        exit_code = i18n_mint.main(
            ["platforms/chatgpt/mailbox.py", "customer_portal_api/app/routers/accounts.py"]
        )

        assert exit_code == 0
        catalog = _read_zh(tmp_path)
        assert catalog == {
            "chatgpt": {i18n_mint._hash8("邮箱验证码获取成功"): "邮箱验证码获取成功"},
            "customerPortalApi": {i18n_mint._hash8("账号已锁定"): "账号已锁定"},
        }


# ---------------------------------------------------------------------------
# Idempotent re-run, value hand-edited since the first mint
# ---------------------------------------------------------------------------


class TestIdempotentHandEditedValue:
    def test_existing_entry_left_untouched_and_zero_writes(self, monkeypatch, tmp_path):
        _set_root(monkeypatch, tmp_path)
        _write_source(tmp_path, "main.py", '''\
            x = "你好世界"
        ''')
        hash8 = i18n_mint._hash8("你好世界")
        # "Hand edited" since the first mint: deliberately not what a fresh
        # hash of the current source text would produce.
        _write_zh(tmp_path, {"main": {hash8: "手动编辑过的翻译"}})
        before = (tmp_path / "i18n" / "zh.json").read_text(encoding="utf-8")

        with monkeypatch.context() as m:
            _guard_write_text(m, "zh.json must not be written on an idempotent re-run")
            exit_code = i18n_mint.main(["main.py"])

        assert exit_code == 0
        after = (tmp_path / "i18n" / "zh.json").read_text(encoding="utf-8")
        assert after == before
        assert _read_zh(tmp_path)["main"][hash8] == "手动编辑过的翻译"


# ---------------------------------------------------------------------------
# Hash collision, forced via a monkeypatched hash function
# ---------------------------------------------------------------------------


class TestHashCollision:
    def test_two_distinct_texts_forced_onto_same_hash_abort_before_write(
        self, monkeypatch, tmp_path, capsys
    ):
        _set_root(monkeypatch, tmp_path)
        _write_zh(tmp_path, {})
        _write_source(tmp_path, "main.py", '''\
            a = "第一个字符串"
            b = "第二个字符串"
        ''')
        before = (tmp_path / "i18n" / "zh.json").read_text(encoding="utf-8")

        # A real sha256 collision cannot be constructed for a test fixture;
        # force one by monkeypatching the tool's own hash function instead.
        monkeypatch.setattr(i18n_mint, "_hash8", lambda text: "00000000")

        with monkeypatch.context() as m:
            _guard_write_text(m, "zh.json must not be written when a collision is detected")
            exit_code = i18n_mint.main(["main.py"])

        assert exit_code == 1
        after = (tmp_path / "i18n" / "zh.json").read_text(encoding="utf-8")
        assert after == before

        err = capsys.readouterr().err
        assert "main.00000000" in err
        assert "main.py:1" in err
        assert "main.py:2" in err

    def test_collision_across_two_files_sharing_one_owner_is_detected(
        self, monkeypatch, tmp_path, capsys
    ):
        _set_root(monkeypatch, tmp_path)
        _write_zh(tmp_path, {})
        _write_source(tmp_path, "platforms/chatgpt/a.py", '''\
            a = "第一个字符串"
        ''')
        _write_source(tmp_path, "platforms/chatgpt/b.py", '''\
            b = "第二个字符串"
        ''')
        before = (tmp_path / "i18n" / "zh.json").read_text(encoding="utf-8")

        monkeypatch.setattr(i18n_mint, "_hash8", lambda text: "00000000")

        with monkeypatch.context() as m:
            _guard_write_text(m, "zh.json must not be written when a collision is detected")
            exit_code = i18n_mint.main(
                ["platforms/chatgpt/a.py", "platforms/chatgpt/b.py"]
            )

        assert exit_code == 1
        after = (tmp_path / "i18n" / "zh.json").read_text(encoding="utf-8")
        assert after == before

        err = capsys.readouterr().err
        assert "chatgpt.00000000" in err
        assert "platforms/chatgpt/a.py:1" in err
        assert "platforms/chatgpt/b.py:1" in err


# ---------------------------------------------------------------------------
# Fully already-migrated file
# ---------------------------------------------------------------------------


class TestFullyAlreadyMigratedFile:
    def test_zero_new_entries_when_every_candidate_already_minted(self, monkeypatch, tmp_path):
        _set_root(monkeypatch, tmp_path)
        _write_source(tmp_path, "main.py", '''\
            x = "你好世界"
        ''')
        hash8 = i18n_mint._hash8("你好世界")
        _write_zh(tmp_path, {"main": {hash8: "你好世界"}})
        before = (tmp_path / "i18n" / "zh.json").read_text(encoding="utf-8")

        with monkeypatch.context() as m:
            _guard_write_text(m, "zh.json must not be written when nothing is new")
            exit_code = i18n_mint.main(["main.py"])

        assert exit_code == 0
        after = (tmp_path / "i18n" / "zh.json").read_text(encoding="utf-8")
        assert after == before

    def test_file_with_no_remaining_chinese_literals_makes_no_changes(self, monkeypatch, tmp_path):
        # A file actually migrated to call sites: the raw Chinese literal is
        # gone, replaced by a call carrying the already-minted key. There is
        # no candidate left for the scanner to find at all.
        _set_root(monkeypatch, tmp_path)
        hash8 = i18n_mint._hash8("你好世界")
        _write_zh(tmp_path, {"main": {hash8: "你好世界"}})
        _write_source(tmp_path, "main.py", f'''\
            from i18n import t

            x = t("main.{hash8}", "zh")
        ''')
        before = (tmp_path / "i18n" / "zh.json").read_text(encoding="utf-8")

        with monkeypatch.context() as m:
            _guard_write_text(m, "zh.json must not be written for an already-migrated file")
            exit_code = i18n_mint.main(["main.py"])

        assert exit_code == 0
        after = (tmp_path / "i18n" / "zh.json").read_text(encoding="utf-8")
        assert after == before


# ---------------------------------------------------------------------------
# Same string twice in one owner
# ---------------------------------------------------------------------------


class TestSameStringTwiceInOneOwner:
    def test_identical_text_at_two_call_sites_mints_once(self, monkeypatch, tmp_path):
        _set_root(monkeypatch, tmp_path)
        _write_zh(tmp_path, {})
        _write_source(tmp_path, "main.py", '''\
            a = "重复的字符串"
            b = "重复的字符串"
        ''')

        exit_code = i18n_mint.main(["main.py"])

        assert exit_code == 0
        catalog = _read_zh(tmp_path)
        assert catalog == {"main": {i18n_mint._hash8("重复的字符串"): "重复的字符串"}}


# ---------------------------------------------------------------------------
# Docstring holding Chinese
# ---------------------------------------------------------------------------


class TestDocstringNotScanned:
    def test_module_docstring_is_not_scanned(self, monkeypatch, tmp_path):
        _set_root(monkeypatch, tmp_path)
        _write_zh(tmp_path, {})
        _write_source(tmp_path, "main.py", '''\
            """模块级中文文档字符串"""
            x = 1
        ''')

        exit_code = i18n_mint.main(["main.py"])

        assert exit_code == 0
        assert _read_zh(tmp_path) == {}

    def test_class_and_function_docstrings_are_not_scanned(self, monkeypatch, tmp_path):
        _set_root(monkeypatch, tmp_path)
        _write_zh(tmp_path, {})
        _write_source(tmp_path, "main.py", '''\
            class Foo:
                """类文档字符串，含有中文"""

                def bar(self):
                    """函数文档字符串，含有中文"""
                    return 1
        ''')

        exit_code = i18n_mint.main(["main.py"])

        assert exit_code == 0
        assert _read_zh(tmp_path) == {}

    def test_docstring_is_skipped_but_a_later_real_literal_in_the_same_file_is_still_found(
        self, monkeypatch, tmp_path
    ):
        _set_root(monkeypatch, tmp_path)
        _write_zh(tmp_path, {})
        _write_source(tmp_path, "main.py", '''\
            """模块文档字符串，含有中文，不应被扫描"""
            x = "真正应该被铸造的字符串"
        ''')

        exit_code = i18n_mint.main(["main.py"])

        assert exit_code == 0
        catalog = _read_zh(tmp_path)
        assert catalog == {
            "main": {i18n_mint._hash8("真正应该被铸造的字符串"): "真正应该被铸造的字符串"}
        }


# ---------------------------------------------------------------------------
# Chinese inside an f-string
# ---------------------------------------------------------------------------


class TestFStringNotScanned:
    def test_chinese_static_segment_of_fstring_is_not_scanned(self, monkeypatch, tmp_path):
        _set_root(monkeypatch, tmp_path)
        _write_zh(tmp_path, {})
        _write_source(tmp_path, "main.py", '''\
            name = "value"
            x = f"你好 {name}"
        ''')

        exit_code = i18n_mint.main(["main.py"])

        assert exit_code == 0
        assert _read_zh(tmp_path) == {}

    def test_chinese_literal_nested_inside_an_fstring_expression_is_also_not_scanned(
        self, monkeypatch, tmp_path
    ):
        # Everything inside a JoinedStr subtree -- including a literal
        # argument passed to a call inside {expr} -- counts as "inside the
        # f-string" and is out of this tool's scope, per the spec's Never
        # section ("do not mine f-string interpolation fragments").
        _set_root(monkeypatch, tmp_path)
        _write_zh(tmp_path, {})
        _write_source(tmp_path, "main.py", '''\
            def t(key, default):
                return default

            x = f"{t('k', '嵌套的中文')}"
        ''')

        exit_code = i18n_mint.main(["main.py"])

        assert exit_code == 0
        assert _read_zh(tmp_path) == {}


# ---------------------------------------------------------------------------
# Operator-facing errors: bad input instead of a raw traceback
# ---------------------------------------------------------------------------


class TestOperatorFacingErrors:
    def test_missing_source_file_exits_1_with_a_clean_message(self, monkeypatch, tmp_path, capsys):
        _set_root(monkeypatch, tmp_path)
        _write_zh(tmp_path, {})

        exit_code = i18n_mint.main(["does_not_exist.py"])

        assert exit_code == 1
        assert "does_not_exist.py" in capsys.readouterr().err

    def test_syntax_error_source_file_exits_1_with_a_clean_message(self, monkeypatch, tmp_path, capsys):
        _set_root(monkeypatch, tmp_path)
        _write_zh(tmp_path, {})
        _write_source(tmp_path, "main.py", '''\
            def broken(:
        ''')

        exit_code = i18n_mint.main(["main.py"])

        assert exit_code == 1
        assert "main.py" in capsys.readouterr().err

    def test_corrupt_zh_json_exits_1_with_a_clean_message(self, monkeypatch, tmp_path, capsys):
        _set_root(monkeypatch, tmp_path)
        _write_source(tmp_path, "main.py", '''\
            x = "你好世界"
        ''')
        zh_path = tmp_path / "i18n" / "zh.json"
        zh_path.parent.mkdir(parents=True, exist_ok=True)
        zh_path.write_text("{not valid json", encoding="utf-8")

        exit_code = i18n_mint.main(["main.py"])

        assert exit_code == 1
        assert "zh.json" in capsys.readouterr().err

    def test_missing_i18n_directory_is_created_before_first_write(self, monkeypatch, tmp_path):
        _set_root(monkeypatch, tmp_path)
        _write_source(tmp_path, "main.py", '''\
            x = "你好世界"
        ''')
        assert not (tmp_path / "i18n").exists()

        exit_code = i18n_mint.main(["main.py"])

        assert exit_code == 0
        assert _read_zh(tmp_path) == {
            "main": {i18n_mint._hash8("你好世界"): "你好世界"}
        }


# ---------------------------------------------------------------------------
# CLI plumbing
# ---------------------------------------------------------------------------


class TestCli:
    def test_help_exits_zero(self, capsys):
        try:
            i18n_mint.main(["--help"])
        except SystemExit as exc:
            assert exc.code == 0
        else:
            raise AssertionError("--help should raise SystemExit(0)")
        out = capsys.readouterr().out
        assert "usage" in out.lower()
