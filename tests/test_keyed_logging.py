"""Unit tests for the keyed logging seam (story 4.1):
`BasePlatform.log_key`, `RegistrationContext.log_key`, `TaskLogger.log_key`,
and the `_build_platform_instance` wiring, including the real cross-layer
`register()` -> `RegistrationContext.log_key_fn` -> `platform._log_key_fn`
path a prior review pass caught broken.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlmodel import Session, select

import application.tasks as tasks_module
import core.base_platform as base_platform_module
from application.tasks import TaskLogger, _build_platform_instance
from core.base_platform import BasePlatform, RegisterConfig
from core.db import TaskEventModel, engine
from core.registration.models import RegistrationContext
from i18n import t


class _NonScalar:
    """An arbitrary object -- not a JSON scalar, not JSON-serializable either."""


class _ConcretePlatform(BasePlatform):
    name = "test_platform"
    display_name = "Test Platform"
    supported_executors = ["protocol"]

    def check_valid(self, account):
        return True


# --- BasePlatform.log_key ----------------------------------------------------


def test_base_platform_log_key_no_sink_falls_back_to_log(monkeypatch):
    platform = object.__new__(_ConcretePlatform)
    platform._log_key_fn = None
    calls = []
    platform._log_fn = lambda message: calls.append(message)

    platform.log_key("does.not.exist", name="x")

    assert calls == [t("does.not.exist", "zh", name="x")]


def test_base_platform_log_key_with_sink_calls_it_with_positional_dict():
    platform = object.__new__(_ConcretePlatform)
    calls = []
    platform._log_key_fn = lambda key, params: calls.append((key, params))
    platform._log_fn = lambda message: (_ for _ in ()).throw(AssertionError("should not fall back"))

    platform.log_key("owner.hash8", name="x", count=3)

    assert calls == [("owner.hash8", {"name": "x", "count": 3})]


def test_base_platform_log_key_non_scalar_param_no_sink_does_not_raise():
    platform = object.__new__(_ConcretePlatform)
    platform._log_key_fn = None
    calls = []
    platform._log_fn = lambda message: calls.append(message)

    platform.log_key("does.not.exist", n=_NonScalar())

    # t() degrades silently (AD-10); no exception, no structured persistence.
    assert calls == [t("does.not.exist", "zh", n=_NonScalar())]


# --- RegistrationContext.log_key ---------------------------------------------


def _make_ctx(log_key_fn=None, log_fn=None) -> RegistrationContext:
    return RegistrationContext(
        platform_name="test_platform",
        platform_display_name="Test Platform",
        platform=None,
        identity=None,
        config=None,
        email=None,
        password=None,
        log_fn=log_fn or (lambda message: None),
        log_key_fn=log_key_fn,
    )


def test_registration_context_log_key_no_sink_falls_back_to_log_fn():
    calls = []
    ctx = _make_ctx(log_fn=lambda message: calls.append(message))

    ctx.log_key("does.not.exist", name="x")

    assert calls == [t("does.not.exist", "zh", name="x")]


def test_registration_context_log_key_with_sink_calls_it_with_positional_dict():
    calls = []
    ctx = _make_ctx(log_key_fn=lambda key, params: calls.append((key, params)))

    ctx.log_key("owner.hash8", name="x")

    assert calls == [("owner.hash8", {"name": "x"})]


def test_registration_context_log_key_non_scalar_param_no_sink_does_not_raise():
    calls = []
    ctx = _make_ctx(log_fn=lambda message: calls.append(message))

    ctx.log_key("does.not.exist", n=_NonScalar())

    assert calls == [t("does.not.exist", "zh", n=_NonScalar())]


# --- TaskLogger.log_key -------------------------------------------------------


def _events_for(task_id: str) -> list[TaskEventModel]:
    with Session(engine) as session:
        return list(session.exec(select(TaskEventModel).where(TaskEventModel.task_id == task_id)))


def test_task_logger_log_key_writes_detail_json_and_renders_zh_message():
    logger = TaskLogger("task-log-key-1")

    logger.log_key("does.not.exist", params={"name": "x"})

    events = _events_for("task-log-key-1")
    assert len(events) == 1
    event = events[0]
    assert event.message == t("does.not.exist", "zh", name="x")
    detail = event.get_detail()
    assert detail == {"i18n_key": "does.not.exist", "i18n_params": {"name": "x"}}


def test_task_logger_log_key_no_params_defaults_to_empty_dict():
    logger = TaskLogger("task-log-key-2")

    logger.log_key("does.not.exist")

    events = _events_for("task-log-key-2")
    assert len(events) == 1
    detail = events[0].get_detail()
    assert detail == {"i18n_key": "does.not.exist", "i18n_params": {}}


def test_task_logger_log_key_rejects_non_scalar_object_param_and_persists_nothing():
    logger = TaskLogger("task-log-key-non-scalar-object")

    with pytest.raises(ValueError, match=r"i18n_params\['n'\]"):
        logger.log_key("does.not.exist", params={"n": _NonScalar()})

    assert _events_for("task-log-key-non-scalar-object") == []


def test_task_logger_log_key_rejects_dict_param_and_persists_nothing():
    logger = TaskLogger("task-log-key-dict-param")

    with pytest.raises(ValueError, match=r"i18n_params\['n'\]"):
        logger.log_key("does.not.exist", params={"n": {"nested": "dict"}})

    assert _events_for("task-log-key-dict-param") == []


def test_task_logger_log_key_rejects_list_param_and_persists_nothing():
    logger = TaskLogger("task-log-key-list-param")

    with pytest.raises(ValueError, match=r"i18n_params\['n'\]"):
        logger.log_key("does.not.exist", params={"n": [1, 2, 3]})

    assert _events_for("task-log-key-list-param") == []


def test_task_logger_log_key_scalar_types_all_accepted():
    logger = TaskLogger("task-log-key-scalars")

    logger.log_key(
        "does.not.exist",
        params={"a": "str", "b": 1, "c": 1.5, "d": True, "e": None},
    )

    events = _events_for("task-log-key-scalars")
    assert len(events) == 1


# --- _build_platform_instance wiring ------------------------------------------


class _FakePlatformWithSetLogger:
    def __init__(self, config=None, mailbox=None):
        self.config = config
        self.mailbox = mailbox
        self.set_logger_called_with = None

    def set_logger(self, logger):
        self.set_logger_called_with = logger


class _FakePlatformWithoutSetLogger:
    def __init__(self, config=None, mailbox=None):
        self.config = config
        self.mailbox = mailbox
        self._log_fn = None


def _build_fake_platform(monkeypatch, fake_cls):
    monkeypatch.setattr(tasks_module, "get", lambda name: fake_cls)
    logger = TaskLogger("task-build-platform")
    return _build_platform_instance(
        "fake_platform",
        {"extra": {}},
        logger,
        resolved_proxy=None,
        shared_mailbox=object(),
    ), logger


def test_build_platform_instance_wires_log_key_fn_with_set_logger_branch(monkeypatch):
    platform, logger = _build_fake_platform(monkeypatch, _FakePlatformWithSetLogger)

    assert platform.set_logger_called_with == logger.log
    assert platform._log_key_fn == logger.log_key


def test_build_platform_instance_wires_log_key_fn_without_set_logger_branch(monkeypatch):
    platform, logger = _build_fake_platform(monkeypatch, _FakePlatformWithoutSetLogger)

    assert platform._log_fn == logger.log
    assert platform._log_key_fn == logger.log_key


# --- Critical end-to-end cross-layer test -------------------------------------


def test_register_wires_registration_context_log_key_to_raw_log_key_fn(monkeypatch):
    """This is the exact cross-layer path a previous review pass caught broken:
    RegistrationContext.log_key_fn must be wired to BasePlatform._log_key_fn
    (the raw attribute, (key, params)-shaped), NOT to the bound BasePlatform.log_key
    method (**params-shaped) -- wiring the latter crashes with a TypeError on
    every real call under the standard register() wiring.
    """
    # Bypass BasePlatform.__init__ (which looks the platform up in the DB-backed
    # registry), mirroring tests/test_chatgpt_oauth_requirements.py:63's
    # object.__new__ pattern -- this is a real BasePlatform subclass instance,
    # not a mock, exercising the real register()/log_key()/log() bound methods.
    platform = object.__new__(_ConcretePlatform)
    platform.config = RegisterConfig(executor_type="protocol")
    platform._log_fn = print

    # Simulate _build_platform_instance's wiring: platform._log_key_fn is set to
    # a (key, params)-positional-dict-shaped stub, exactly like TaskLogger.log_key.
    recorded = []

    def _recording_log_key(key, params):
        recorded.append((key, params))

    platform._log_key_fn = _recording_log_key

    # Give the platform a trivially-resolvable identity so register() reaches
    # the RegistrationContext construction without needing a real mailbox.
    monkeypatch.setattr(
        platform,
        "_resolve_identity",
        lambda email=None, *, require_email=True: SimpleNamespace(
            email=email or "user@example.com", identity_provider="mailbox", metadata={}
        ),
    )

    captured = {}
    real_ctor = RegistrationContext

    def _capturing_ctor(**kwargs):
        ctx = real_ctor(**kwargs)
        captured["ctx"] = ctx
        return ctx

    monkeypatch.setattr(base_platform_module, "RegistrationContext", _capturing_ctor)

    # build_protocol_mailbox_adapter defaults to None -> register() raises
    # NotImplementedError right after constructing the RegistrationContext;
    # that's fine, the ctx we need is already captured by then.
    with pytest.raises(NotImplementedError):
        platform.register(email="user@example.com")

    ctx = captured["ctx"]
    assert ctx.log_key_fn is platform._log_key_fn

    # register() itself already emits a core.1a4231de ("邮箱: {email}", story
    # 4.4) log_key call through this same sink before raising above. Assert the
    # whole sequence rather than just the tail, so a spurious or duplicated
    # emission from register() still fails this test.
    ctx.log_key("owner.hash8", name="x", count=3)

    assert recorded == [
        ("core.1a4231de", {"email": "user@example.com"}),
        ("owner.hash8", {"name": "x", "count": 3}),
    ]
