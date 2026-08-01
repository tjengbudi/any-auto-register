from __future__ import annotations

import logging

from sqlmodel import Session, select

from core.db import ProviderDefinitionModel, engine
from infrastructure.provider_definitions_repository import ProviderDefinitionsRepository


def test_ensure_seeded_warns_and_reverts_edited_builtin_label(caplog):
    # 纯单元测试不经过 lifespan，_reset_db 只建表不 seed，
    # 因此要先播种 provider 定义。
    repository = ProviderDefinitionsRepository()
    repository.ensure_seeded()

    original = repository.get_by_key("mailbox", "cfworker_admin_api")
    original_label = original.label

    with Session(engine) as session:
        row = session.exec(
            select(ProviderDefinitionModel)
            .where(ProviderDefinitionModel.provider_type == "mailbox")
            .where(ProviderDefinitionModel.provider_key == "cfworker_admin_api")
        ).one()
        row.label = "Operator Edited Label"
        session.add(row)
        session.commit()

    with caplog.at_level(logging.WARNING, logger="infrastructure.provider_definitions_repository"):
        repository.ensure_seeded()

    reverted = repository.get_by_key("mailbox", "cfworker_admin_api")
    assert reverted.label == original_label

    matching = [
        record for record in caplog.records
        if "mailbox" in record.getMessage()
        and "cfworker_admin_api" in record.getMessage()
        and "label" in record.getMessage()
    ]
    assert matching, f"expected a warning naming mailbox/cfworker_admin_api/label, got: {[r.getMessage() for r in caplog.records]}"


def test_ensure_seeded_does_not_warn_when_row_matches_seed(caplog):
    repository = ProviderDefinitionsRepository()
    repository.ensure_seeded()

    with caplog.at_level(logging.WARNING, logger="infrastructure.provider_definitions_repository"):
        repository.ensure_seeded()

    ours = [r for r in caplog.records if r.name == "infrastructure.provider_definitions_repository"]
    assert ours == []


def test_ensure_seeded_warns_with_multiple_differing_fields(caplog):
    repository = ProviderDefinitionsRepository()
    repository.ensure_seeded()

    with Session(engine) as session:
        row = session.exec(
            select(ProviderDefinitionModel)
            .where(ProviderDefinitionModel.provider_type == "mailbox")
            .where(ProviderDefinitionModel.provider_key == "cfworker_admin_api")
        ).one()
        row.label = "Operator Edited Label"
        row.enabled = False
        session.add(row)
        session.commit()

    with caplog.at_level(logging.WARNING, logger="infrastructure.provider_definitions_repository"):
        repository.ensure_seeded()

    reverted = repository.get_by_key("mailbox", "cfworker_admin_api")
    assert reverted.label != "Operator Edited Label"
    assert reverted.enabled is True

    matching = [
        record for record in caplog.records
        if "mailbox" in record.getMessage()
        and "cfworker_admin_api" in record.getMessage()
        and "label" in record.getMessage()
        and "enabled" in record.getMessage()
    ]
    assert matching, f"expected one warning naming both label and enabled, got: {[r.getMessage() for r in caplog.records]}"


def test_ensure_seeded_warns_on_fields_and_auth_modes_diff(caplog):
    repository = ProviderDefinitionsRepository()
    repository.ensure_seeded()

    with Session(engine) as session:
        row = session.exec(
            select(ProviderDefinitionModel)
            .where(ProviderDefinitionModel.provider_type == "mailbox")
            .where(ProviderDefinitionModel.provider_key == "cfworker_admin_api")
        ).one()
        original_fields = row.get_fields()
        row.set_auth_modes([{"value": "operator_added", "label": "Operator Added"}])
        session.add(row)
        session.commit()

    with caplog.at_level(logging.WARNING, logger="infrastructure.provider_definitions_repository"):
        repository.ensure_seeded()

    reverted = repository.get_by_key("mailbox", "cfworker_admin_api")
    assert reverted.get_fields() == original_fields
    assert reverted.get_auth_modes() != [{"value": "operator_added", "label": "Operator Added"}]

    matching = [
        record for record in caplog.records
        if "mailbox" in record.getMessage()
        and "cfworker_admin_api" in record.getMessage()
        and "auth_modes" in record.getMessage()
    ]
    assert matching, f"expected a warning naming auth_modes, got: {[r.getMessage() for r in caplog.records]}"


def test_ensure_seeded_new_row_never_warns(caplog):
    with caplog.at_level(logging.INFO, logger="infrastructure.provider_definitions_repository"):
        ProviderDefinitionsRepository().ensure_seeded()

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    infos = [r for r in caplog.records if r.levelno == logging.INFO]
    assert warnings == []
    assert any("新增" in r.getMessage() for r in infos)
