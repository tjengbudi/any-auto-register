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
import tokenize
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
# Cross-run collision: fresh candidate collides with a provably-unedited
# pre-existing catalog entry (DW-6)
# ---------------------------------------------------------------------------


class TestCrossRunCollision:
    def test_unedited_stored_value_colliding_fresh_text_aborts_before_write(
        self, monkeypatch, tmp_path, capsys
    ):
        _set_root(monkeypatch, tmp_path)
        # A real sha256 collision cannot be constructed for a test fixture;
        # force one by monkeypatching the tool's own hash function instead,
        # exactly as TestHashCollision does for the same-run case.
        monkeypatch.setattr(i18n_mint, "_hash8", lambda text: "00000000")
        _write_zh(tmp_path, {"main": {"00000000": "已存储的文本"}})
        _write_source(tmp_path, "main.py", '''\
            x = "新的候选文本"
        ''')
        before = (tmp_path / "i18n" / "zh.json").read_text(encoding="utf-8")

        with monkeypatch.context() as m:
            _guard_write_text(m, "zh.json must not be written on a cross-run collision")
            exit_code = i18n_mint.main(["main.py"])

        assert exit_code == 1
        after = (tmp_path / "i18n" / "zh.json").read_text(encoding="utf-8")
        assert after == before

        err = capsys.readouterr().err
        assert "main.00000000" in err
        assert "已存储的文本" in err
        assert "新的候选文本" in err
        assert "main.py:1" in err

    def test_hand_edited_stored_value_stays_silent_zero_writes_exit_zero(
        self, monkeypatch, tmp_path, capsys
    ):
        # Same shape as TestIdempotentHandEditedValue, restated here to make
        # explicit that it is this class's outcome-3 boundary: the stored
        # value's hash does NOT match its own key, so nothing can be
        # concluded and the tool must stay silent (unchanged from today).
        _set_root(monkeypatch, tmp_path)
        _write_source(tmp_path, "main.py", '''\
            x = "你好世界"
        ''')
        hash8 = i18n_mint._hash8("你好世界")
        _write_zh(tmp_path, {"main": {hash8: "手动编辑过的翻译"}})
        before = (tmp_path / "i18n" / "zh.json").read_text(encoding="utf-8")

        with monkeypatch.context() as m:
            _guard_write_text(m, "zh.json must not be written when provenance can't be verified")
            exit_code = i18n_mint.main(["main.py"])

        assert exit_code == 0
        after = (tmp_path / "i18n" / "zh.json").read_text(encoding="utf-8")
        assert after == before
        assert capsys.readouterr().err == ""

    def test_unedited_stored_value_identical_fresh_text_is_already_present(
        self, monkeypatch, tmp_path, capsys
    ):
        # Same shape as TestFullyAlreadyMigratedFile, restated here to make
        # explicit that it is this class's outcome-1 boundary: fresh text
        # equals stored text, so the hash gate is never even consulted.
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

    def test_non_string_stored_value_does_not_crash_and_stays_silent(
        self, monkeypatch, tmp_path, capsys
    ):
        # A corrupt catalog entry (stored value is a JSON int, not a string)
        # can be neither hashed nor have its provenance verified. It must be
        # treated the same as a hand-edited value -- silent, exit 0 -- not
        # crash with a raw AttributeError out of _hash8(stored_text).
        _set_root(monkeypatch, tmp_path)
        _write_source(tmp_path, "main.py", '''\
            x = "你好世界"
        ''')
        hash8 = i18n_mint._hash8("你好世界")
        _write_zh(tmp_path, {"main": {hash8: 123}})
        before = (tmp_path / "i18n" / "zh.json").read_text(encoding="utf-8")

        with monkeypatch.context() as m:
            _guard_write_text(m, "zh.json must not be written when the stored value is corrupt")
            exit_code = i18n_mint.main(["main.py"])

        assert exit_code == 0
        after = (tmp_path / "i18n" / "zh.json").read_text(encoding="utf-8")
        assert after == before
        assert capsys.readouterr().err == ""

    def test_two_independent_cross_run_collisions_are_both_reported_in_one_pass(
        self, monkeypatch, tmp_path, capsys
    ):
        # Mirrors TestHashCollision's same-run batching: the same-run check
        # collects every collision before aborting, so the cross-run check
        # must too -- an operator hitting two unrelated cross-run collisions
        # in one invocation must see both, not just the first, and must not
        # have to fix-and-rerun to discover the second. A third, genuinely
        # new owner with no existing entry proves the abort still happens
        # before ANY write, even though that owner's entry would otherwise
        # have minted cleanly on its own.
        _set_root(monkeypatch, tmp_path)
        monkeypatch.setattr(i18n_mint, "_hash8", lambda text: "00000000")
        _write_zh(
            tmp_path,
            {
                "b": {"00000000": "乙文本旧"},
                "c": {"00000000": "丙文本旧"},
            },
        )
        _write_source(tmp_path, "a.py", '''\
            x = "甲文本全新"
        ''')
        _write_source(tmp_path, "b.py", '''\
            x = "乙文本新"
        ''')
        _write_source(tmp_path, "c.py", '''\
            x = "丙文本新"
        ''')
        before = (tmp_path / "i18n" / "zh.json").read_text(encoding="utf-8")

        with monkeypatch.context() as m:
            _guard_write_text(m, "zh.json must not be written when any cross-run collision is found")
            exit_code = i18n_mint.main(["a.py", "b.py", "c.py"])

        assert exit_code == 1
        after = (tmp_path / "i18n" / "zh.json").read_text(encoding="utf-8")
        assert after == before

        err = capsys.readouterr().err
        assert "b.00000000" in err
        assert "乙文本旧" in err
        assert "乙文本新" in err
        assert "c.00000000" in err
        assert "丙文本旧" in err
        assert "丙文本新" in err
        assert capsys.readouterr().err == ""


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
# Adjacent-concatenated plain literal + f-string (DW-7): warn, don't mint
# ---------------------------------------------------------------------------


class TestAdjacentFstringWarning:
    def test_han_literal_adjacent_concatenated_into_fstring_warns_and_is_not_minted(
        self, monkeypatch, tmp_path, capsys
    ):
        # "你好" f"{name}" parses to the same ast.JoinedStr as f"你好{name}"
        # (verified: the AST cannot tell them apart), so the plain fragment
        # is genuinely lost to _iter_candidates. tokenize can still tell
        # them apart -- this is the diagnostic that replaces silent loss.
        _set_root(monkeypatch, tmp_path)
        _write_zh(tmp_path, {})
        _write_source(tmp_path, "main.py", '''\
            name = "value"
            x = "你好" f"{name}"
        ''')

        exit_code = i18n_mint.main(["main.py"])

        assert exit_code == 0
        assert _read_zh(tmp_path) == {}
        err = capsys.readouterr().err
        assert "main.py:2" in err
        assert "你好" in err

    def test_pure_fstring_with_chinese_static_segment_stays_silent(self, monkeypatch, tmp_path, capsys):
        # f"你好{name}" -- no adjacent-concatenated plain literal exists here,
        # so this stays the deliberately-silent case spec 1.5's Never clause
        # requires: no mint, and now also no warning.
        _set_root(monkeypatch, tmp_path)
        _write_zh(tmp_path, {})
        _write_source(tmp_path, "main.py", '''\
            name = "value"
            x = f"你好{name}"
        ''')

        exit_code = i18n_mint.main(["main.py"])

        assert exit_code == 0
        assert _read_zh(tmp_path) == {}
        assert capsys.readouterr().err == ""

    def test_no_han_text_in_adjacent_literal_stays_silent(self, monkeypatch, tmp_path, capsys):
        # "hello" f"{name}" -- adjacent-concatenated with an f-string, but
        # the plain fragment has no CJK text, so it was never a mint
        # candidate in the first place (I/O matrix row 3).
        _set_root(monkeypatch, tmp_path)
        _write_zh(tmp_path, {})
        _write_source(tmp_path, "main.py", '''\
            name = "value"
            x = "hello" f"{name}"
        ''')

        exit_code = i18n_mint.main(["main.py"])

        assert exit_code == 0
        assert _read_zh(tmp_path) == {}
        assert capsys.readouterr().err == ""

    def test_explicit_plus_concatenation_is_not_implicit_and_stays_silent(self, monkeypatch, tmp_path, capsys):
        # "你好" + f"{name}" is a BinOp, not implicit concatenation -- Python
        # never merges it into one ast.JoinedStr, so the plain literal is
        # already its own ordinary mint candidate and no warning applies.
        _set_root(monkeypatch, tmp_path)
        _write_zh(tmp_path, {})
        _write_source(tmp_path, "main.py", '''\
            name = "value"
            x = "你好" + f"{name}"
        ''')

        exit_code = i18n_mint.main(["main.py"])

        assert exit_code == 0
        assert _read_zh(tmp_path) == {"main": {i18n_mint._hash8("你好"): "你好"}}
        assert capsys.readouterr().err == ""

    def test_warns_once_per_han_bearing_plain_atom_in_one_run(self, monkeypatch, tmp_path, capsys):
        # "你好" "再见" f"{name}" -- two Han-bearing plain atoms fall into the
        # same implicit-concatenation run; each is swallowed by the merged
        # JoinedStr and each must get its own warning.
        _set_root(monkeypatch, tmp_path)
        _write_zh(tmp_path, {})
        _write_source(tmp_path, "main.py", '''\
            name = "value"
            x = "你好" "再见" f"{name}"
        ''')

        exit_code = i18n_mint.main(["main.py"])

        assert exit_code == 0
        assert _read_zh(tmp_path) == {}
        err = capsys.readouterr().err
        assert "你好" in err
        assert "再见" in err

    def test_warning_fires_when_fstring_precedes_the_plain_literal(self, monkeypatch, tmp_path, capsys):
        # f"{name}" "你好" -- the f-string comes first in the run; detection
        # must not depend on which side of the run the f-string is on.
        _set_root(monkeypatch, tmp_path)
        _write_zh(tmp_path, {})
        _write_source(tmp_path, "main.py", '''\
            name = "value"
            x = f"{name}" "你好"
        ''')

        exit_code = i18n_mint.main(["main.py"])

        assert exit_code == 0
        assert _read_zh(tmp_path) == {}
        assert "你好" in capsys.readouterr().err

    def test_warning_fires_across_a_parenthesized_multiline_run_with_a_comment(
        self, monkeypatch, tmp_path, capsys
    ):
        # A parenthesized multi-line implicit concatenation with a comment
        # between the atoms is still one concatenation run in Python's own
        # grammar -- the NL/COMMENT tokens between them must not break it.
        _set_root(monkeypatch, tmp_path)
        _write_zh(tmp_path, {})
        _write_source(tmp_path, "main.py", '''\
            name = "value"
            x = (
                "你好"
                # a comment between the atoms
                f"{name}"
            )
        ''')

        exit_code = i18n_mint.main(["main.py"])

        assert exit_code == 0
        assert _read_zh(tmp_path) == {}
        assert "你好" in capsys.readouterr().err

    def test_standalone_literal_still_mints_alongside_a_warned_adjacent_fragment(
        self, monkeypatch, tmp_path, capsys
    ):
        # A genuine standalone candidate elsewhere in the same file must
        # still mint normally in the same run as a warned fragment.
        _set_root(monkeypatch, tmp_path)
        _write_zh(tmp_path, {})
        _write_source(tmp_path, "main.py", '''\
            name = "value"
            warned = "你好" f"{name}"
            standalone = "普通字符串"
        ''')

        exit_code = i18n_mint.main(["main.py"])

        assert exit_code == 0
        assert _read_zh(tmp_path) == {"main": {i18n_mint._hash8("普通字符串"): "普通字符串"}}
        assert "你好" in capsys.readouterr().err

    def test_tokenize_failure_falls_back_to_no_warnings_without_crashing(self, monkeypatch, tmp_path, capsys):
        # If tokenize ever raises on source ast.parse already accepted, the
        # diagnostic must degrade gracefully instead of crashing the whole
        # run -- guards against the except-tuple naming the wrong exception
        # class (tokenize.TokenizeError is not real; tokenize.TokenError is).
        _set_root(monkeypatch, tmp_path)
        _write_zh(tmp_path, {})
        _write_source(tmp_path, "main.py", '''\
            x = "普通字符串"
        ''')

        def _raise(*args, **kwargs):
            raise tokenize.TokenError("boom")

        monkeypatch.setattr(i18n_mint.tokenize, "generate_tokens", _raise)

        exit_code = i18n_mint.main(["main.py"])

        assert exit_code == 0
        assert capsys.readouterr().err == ""
        assert _read_zh(tmp_path) == {"main": {i18n_mint._hash8("普通字符串"): "普通字符串"}}

    def test_fieldless_fstring_adjacent_concatenated_with_a_real_fstring_warns(
        self, monkeypatch, tmp_path, capsys
    ):
        # f"你好" f"{name}" -- the first atom carries a redundant f-prefix but
        # has no {expr} field at all, so it is functionally a plain literal.
        # It parses to the same ast.JoinedStr as "你好" f"{name}" (verified),
        # so it must be caught the same way -- classifying it as an f-string
        # purely by its prefix would silently lose the Han text again.
        _set_root(monkeypatch, tmp_path)
        _write_zh(tmp_path, {})
        _write_source(tmp_path, "main.py", '''\
            name = "value"
            x = f"你好" f"{name}"
        ''')

        exit_code = i18n_mint.main(["main.py"])

        assert exit_code == 0
        assert _read_zh(tmp_path) == {}
        err = capsys.readouterr().err
        assert "main.py:2" in err
        assert "你好" in err

    def test_fieldless_fstring_with_escaped_braces_alone_stays_silent(self, monkeypatch, tmp_path, capsys):
        # f"你好{{}}再见" alone (no adjacent f-string) -- the doubled braces are
        # an escaped literal `{`/`}`, not a field, so this atom has no real
        # interpolation either. Standing alone it is not part of a run
        # containing a genuine f-string, so it must stay silent -- same as
        # any other pure f-string per spec 1.5's Never clause.
        _set_root(monkeypatch, tmp_path)
        _write_zh(tmp_path, {})
        _write_source(tmp_path, "main.py", '''\
            x = f"你好{{}}再见"
        ''')

        exit_code = i18n_mint.main(["main.py"])

        assert exit_code == 0
        assert _read_zh(tmp_path) == {}
        assert capsys.readouterr().err == ""

    def test_literal_eval_failure_falls_back_to_no_warnings_without_crashing(self, monkeypatch, tmp_path, capsys):
        # ast.literal_eval on a plain STRING token's raw text is documented
        # to be able to raise ValueError/TypeError; the fallback around the
        # diagnostic call must also catch those, not just the tokenizer's
        # own exceptions, or a rare divergence crashes the whole run instead
        # of degrading gracefully.
        _set_root(monkeypatch, tmp_path)
        _write_zh(tmp_path, {})
        _write_source(tmp_path, "main.py", '''\
            x = "普通字符串"
        ''')

        real_literal_eval = i18n_mint.ast.literal_eval

        def _raise(*args, **kwargs):
            raise ValueError("boom")

        monkeypatch.setattr(i18n_mint.ast, "literal_eval", _raise)

        exit_code = i18n_mint.main(["main.py"])

        monkeypatch.setattr(i18n_mint.ast, "literal_eval", real_literal_eval)

        assert exit_code == 0
        assert capsys.readouterr().err == ""
        assert _read_zh(tmp_path) == {"main": {i18n_mint._hash8("普通字符串"): "普通字符串"}}


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
