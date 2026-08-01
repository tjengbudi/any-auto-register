from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlmodel import Session, select

from core.db import ProviderDefinitionModel, ProviderSettingModel, engine

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _diff_seed_fields(item: ProviderDefinitionModel, seed: dict) -> list[str]:
    """比较已存在的行与种子数据的字段差异。
    Compare an existing row's fields against the seed data.

    返回字段名列表（按检查顺序），列出当前值与种子值不同的字段；
    仅用于日志展示，不影响 ensure_seeded() 随后的赋值。
    Returns the field names (in check order) whose current value differs
    from the seed; used only to build the warning log, it has no effect on
    the assignment that ensure_seeded() performs afterwards.
    """
    diffs: list[str] = []
    if item.label != seed.get("label", seed["provider_key"]):
        diffs.append("label")
    if item.description != seed.get("description", ""):
        diffs.append("description")
    if item.driver_type != seed.get("driver_type", seed["provider_key"]):
        diffs.append("driver_type")
    if item.default_auth_mode != seed.get("default_auth_mode", ""):
        diffs.append("default_auth_mode")
    if item.enabled != seed.get("enabled", True):
        diffs.append("enabled")
    if item.category != seed.get("category", ""):
        diffs.append("category")
    if item.get_auth_modes() != list(seed.get("auth_modes") or []):
        diffs.append("auth_modes")
    if item.get_fields() != list(seed.get("fields") or []):
        diffs.append("fields")
    if item.is_builtin is not True:
        diffs.append("is_builtin")
    return diffs


_BUILTIN_DEFINITIONS: list[dict] = [
    # ── mailbox ──────────────────────────────────────────────────────
    {
        "provider_type": "mailbox",
        "provider_key": "cfworker_admin_api",
        "label": "infrastructure.1dd984a0",
        "description": "infrastructure.8fe53b2d",
        "driver_type": "cfworker_admin_api",
        "default_auth_mode": "token",
        "enabled": True,
        "category": "selfhost",
        "auth_modes": [{"value": "token", "label": "infrastructure.51b3d0ff"}],
        "fields": [
            {"key": "cfworker_api_url", "label": "infrastructure.d94c3fb8", "placeholder": "https://your-worker.example.com", "category": "connection"},
            {"key": "cfworker_admin_token", "label": "Admin Token", "secret": True, "category": "auth"},
            {"key": "cfworker_domain", "label": "infrastructure.cb3fceba", "placeholder": "example.com", "category": "connection"},
            {"key": "cfworker_fingerprint", "label": "infrastructure.a4d87632", "placeholder": "", "category": "connection"},
        ],
    },
    {
        "provider_type": "mailbox",
        "provider_key": "moemail_api",
        "label": "MoeMail（sall.cc）",
        "description": "infrastructure.b31c768d",
        "driver_type": "moemail_api",
        "default_auth_mode": "password",
        "enabled": True,
        "category": "selfhost",
        "auth_modes": [
            {"value": "password", "label": "infrastructure.164c7afc"},
            {"value": "token", "label": "Session Token"},
        ],
        "fields": [
            {"key": "moemail_api_url", "label": "infrastructure.d94c3fb8", "placeholder": "https://moemail.example.com", "category": "connection"},
            {"key": "moemail_username", "label": "infrastructure.e67fea90", "category": "auth"},
            {"key": "moemail_password", "label": "infrastructure.44733c95", "secret": True, "category": "auth"},
            {"key": "moemail_session_token", "label": "infrastructure.e80eef08", "secret": True, "category": "auth"},
        ],
    },
    {
        "provider_type": "mailbox",
        "provider_key": "tempmail_lol_api",
        "label": "TempMail.lol",
        "description": "infrastructure.ac04434a",
        "driver_type": "tempmail_lol_api",
        "default_auth_mode": "",
        "enabled": True,
        "category": "free",
        "auth_modes": [],
        "fields": [],
    },
    {
        "provider_type": "mailbox",
        "provider_key": "tempmail_web_api",
        "label": "Temp-Mail.org",
        "description": "infrastructure.f701f554",
        "driver_type": "tempmail_web_api",
        "default_auth_mode": "",
        "enabled": True,
        "category": "free",
        "auth_modes": [],
        "fields": [
            {"key": "tempmail_web_base_url", "label": "infrastructure.3c46ee7a", "placeholder": "https://web2.temp-mail.org", "category": "connection"},
        ],
    },
    {
        "provider_type": "mailbox",
        "provider_key": "duckmail_api",
        "label": "infrastructure.de7316b4",
        "description": "infrastructure.9f8a74d2",
        "driver_type": "duckmail_api",
        "default_auth_mode": "bearer",
        "enabled": True,
        "category": "selfhost",
        "auth_modes": [{"value": "bearer", "label": "Bearer Token"}],
        "fields": [
            {"key": "duckmail_api_url", "label": "infrastructure.d94c3fb8", "placeholder": "https://duckmail.example.com", "category": "connection"},
            {"key": "duckmail_provider_url", "label": "infrastructure.12acb629", "placeholder": "", "category": "connection"},
            {"key": "duckmail_bearer", "label": "Bearer Token", "secret": True, "category": "auth"},
        ],
    },
    {
        "provider_type": "mailbox",
        "provider_key": "freemail_api",
        "label": "infrastructure.06bfac32",
        "description": "infrastructure.7837a490",
        "driver_type": "freemail_api",
        "default_auth_mode": "password",
        "enabled": True,
        "category": "selfhost",
        "auth_modes": [{"value": "password", "label": "infrastructure.164c7afc"}, {"value": "token", "label": "Admin Token"}],
        "fields": [
            {"key": "freemail_api_url", "label": "infrastructure.d94c3fb8", "placeholder": "https://freemail.example.com", "category": "connection"},
            {"key": "freemail_admin_token", "label": "Admin Token", "secret": True, "category": "auth"},
            {"key": "freemail_username", "label": "infrastructure.1a3f0617", "category": "auth"},
            {"key": "freemail_password", "label": "infrastructure.a621ab60", "secret": True, "category": "auth"},
        ],
    },
    {
        "provider_type": "mailbox",
        "provider_key": "testmail_api",
        "label": "infrastructure.5853ee81",
        "description": "infrastructure.9c43da0a",
        "driver_type": "testmail_api",
        "default_auth_mode": "apikey",
        "enabled": True,
        "category": "thirdparty",
        "auth_modes": [{"value": "apikey", "label": "API Key"}],
        "fields": [
            {"key": "testmail_api_url", "label": "infrastructure.3c46ee7a", "placeholder": "https://api.testmail.app", "category": "connection"},
            {"key": "testmail_api_key", "label": "API Key", "secret": True, "category": "auth"},
            {"key": "testmail_namespace", "label": "Namespace", "category": "identity"},
            {"key": "testmail_tag_prefix", "label": "infrastructure.b69e5706", "placeholder": "", "category": "identity"},
        ],
    },
    {
        "provider_type": "mailbox",
        "provider_key": "laoudo_api",
        "label": "infrastructure.a9c93732",
        "description": "infrastructure.9f544ddf",
        "driver_type": "laoudo_api",
        "default_auth_mode": "token",
        "enabled": True,
        "category": "thirdparty",
        "auth_modes": [{"value": "token", "label": "JWT Token"}],
        "fields": [
            {"key": "laoudo_auth", "label": "Auth Token", "secret": True, "category": "auth"},
            {"key": "laoudo_email", "label": "infrastructure.2e412e03", "placeholder": "your@email.com", "category": "identity"},
            {"key": "laoudo_account_id", "label": "Account ID", "category": "identity"},
        ],
    },
    {
        "provider_type": "mailbox",
        "provider_key": "aitre_api",
        "label": "infrastructure.48df429c",
        "description": "infrastructure.745c157d",
        "driver_type": "aitre_api",
        "default_auth_mode": "",
        "enabled": True,
        "category": "free",
        "auth_modes": [],
        "fields": [
            {"key": "aitre_email", "label": "infrastructure.2e412e03", "placeholder": "your@email.com", "category": "identity"},
            {"key": "aitre_api_url", "label": "infrastructure.3c46ee7a", "placeholder": "https://mail.aitre.cc/api/tempmail", "category": "connection"},
        ],
    },
    {
        "provider_type": "mailbox",
        "provider_key": "ddg_email",
        "label": "DuckDuckGo Email",
        "description": "infrastructure.f01eb4d4",
        "driver_type": "ddg_email",
        "default_auth_mode": "bearer",
        "enabled": True,
        "category": "thirdparty",
        "auth_modes": [{"value": "bearer", "label": "Bearer Token"}],
        "fields": [
            {"key": "ddg_bearer", "label": "DDG Bearer Token", "secret": True, "category": "auth"},
            {"key": "ddg_imap_host", "label": "infrastructure.c814cd6a", "placeholder": "infrastructure.9a7ffc4f", "category": "connection"},
            {"key": "ddg_imap_user", "label": "infrastructure.76f27a44", "placeholder": "your@gmail.com", "category": "auth"},
            {"key": "ddg_imap_pass", "label": "infrastructure.9c5c1a3f", "secret": True, "category": "auth"},
        ],
    },
    {
        "provider_type": "mailbox",
        "provider_key": "local_ms_pool",
        "label": "infrastructure.e0f9f6ae",
        "description": "infrastructure.2bd66787",
        "driver_type": "local_ms_pool",
        "default_auth_mode": "pool",
        "enabled": True,
        "category": "custom",
        "auth_modes": [{"value": "pool", "label": "infrastructure.b3e8b15d"}],
        "fields": [
            {
                "key": "local_ms_pool_file",
                "label": "infrastructure.d74d2887",
                "placeholder": "/Users/you/ms-mail-pool.txt",
                "category": "connection",
                "hint": "infrastructure.ca89740c",
            },
            {
                "key": "local_ms_pool_text",
                "label": "infrastructure.c4378e00",
                "type": "textarea",
                "category": "auth",
                "hint": "infrastructure.634df486",
            },
            {
                "key": "local_ms_graph_scope",
                "label": "Graph Scope",
                "placeholder": "https://graph.microsoft.com/Mail.Read offline_access",
                "category": "connection",
            },
            {
                "key": "local_ms_pool_state_file",
                "label": "infrastructure.6d4ce12f",
                "placeholder": "infrastructure.48f12aad",
                "category": "connection",
                "hint": "infrastructure.c3b7b9cc",
            },
            {
                "key": "local_ms_pool_allow_reuse",
                "label": "infrastructure.7052bb6d",
                "type": "toggle",
                "category": "connection",
                "hint": "infrastructure.1263dfa6",
            },
        ],
    },
    {
        "provider_type": "mailbox",
        "provider_key": "generic_http_mailbox",
        "label": "infrastructure.deaa111d",
        "description": "infrastructure.9c9a36fa",
        "driver_type": "generic_http_mailbox",
        "default_auth_mode": "",
        "enabled": True,
        "category": "custom",
        "auth_modes": [],
        "fields": [],
    },
    # ── captcha ──────────────────────────────────────────────────────
    {
        "provider_type": "captcha",
        "provider_key": "yescaptcha_api",
        "label": "YesCaptcha",
        "description": "infrastructure.c5610494",
        "driver_type": "yescaptcha_api",
        "default_auth_mode": "apikey",
        "enabled": True,
        "category": "thirdparty",
        "auth_modes": [{"value": "apikey", "label": "API Key"}],
        "fields": [
            {"key": "yescaptcha_key", "label": "Client Key", "secret": True},
        ],
    },
    {
        "provider_type": "captcha",
        "provider_key": "twocaptcha_api",
        "label": "2Captcha",
        "description": "infrastructure.87884820",
        "driver_type": "twocaptcha_api",
        "default_auth_mode": "apikey",
        "enabled": True,
        "category": "thirdparty",
        "auth_modes": [{"value": "apikey", "label": "API Key"}],
        "fields": [
            {"key": "twocaptcha_key", "label": "API Key", "secret": True},
        ],
    },
    {
        "provider_type": "captcha",
        "provider_key": "local_solver",
        "label": "infrastructure.0bbf838b",
        "description": "infrastructure.f3dff31c",
        "driver_type": "local_solver",
        "default_auth_mode": "",
        "enabled": True,
        "category": "thirdparty",
        "auth_modes": [],
        "fields": [
            {"key": "solver_url", "label": "infrastructure.27144ac9", "placeholder": "http://localhost:8889"},
        ],
    },
    {
        "provider_type": "captcha",
        "provider_key": "manual",
        "label": "infrastructure.20d319bf",
        "description": "infrastructure.dafbc4bd",
        "driver_type": "manual",
        "default_auth_mode": "",
        "enabled": True,
        "category": "thirdparty",
        "auth_modes": [],
        "fields": [],
    },
    # ── sms ──────────────────────────────────────────────────────────
    {
        "provider_type": "sms",
        "provider_key": "herosms_api",
        "label": "HeroSMS",
        "description": "infrastructure.efde1a99",
        "driver_type": "herosms_api",
        "default_auth_mode": "apikey",
        "enabled": True,
        "category": "thirdparty",
        "auth_modes": [{"value": "apikey", "label": "API Key"}],
        "fields": [
            {"key": "herosms_api_key", "label": "API Key", "secret": True, "category": "auth"},
            {"key": "herosms_default_country", "label": "infrastructure.2dd115e2", "type": "async-select", "asyncUrl": "/sms/herosms/countries", "asyncValueKey": "id", "asyncLabelKey": "chn", "placeholder": "infrastructure.ffdcce0a"},
            {"key": "herosms_default_service", "label": "infrastructure.2bb40855", "type": "async-select", "asyncUrl": "/sms/herosms/services", "asyncValueKey": "code", "asyncLabelKey": "name", "placeholder": "infrastructure.788bdadf"},
            {"key": "herosms_max_price", "label": "infrastructure.3b3bbf62", "placeholder": "-1"},
            {"key": "herosms_auto_country", "label": "infrastructure.235f0e93", "type": "toggle", "hint": "infrastructure.f55d5470"},
            {"key": "herosms_auto_country_min_stock", "label": "infrastructure.0ddddccb", "placeholder": "20"},
            {"key": "herosms_auto_country_max_price", "label": "infrastructure.44eba305", "placeholder": "infrastructure.73381c3a"},
            {"key": "register_phone_extra_max", "label": "infrastructure.ca983e45", "placeholder": "3"},
            {"key": "register_reuse_phone_to_max", "label": "infrastructure.77ba1789", "type": "toggle"},
        ],
    },
    {
        "provider_type": "sms",
        "provider_key": "sms_activate_api",
        "label": "SMS-Activate",
        "description": "infrastructure.86a89f8e",
        "driver_type": "sms_activate_api",
        "default_auth_mode": "apikey",
        "enabled": True,
        "category": "thirdparty",
        "auth_modes": [{"value": "apikey", "label": "API Key"}],
        "fields": [
            {"key": "sms_activate_api_key", "label": "API Key", "secret": True},
            {"key": "sms_activate_default_country", "label": "infrastructure.2cc664e7", "placeholder": "ru"},
        ],
    },
    {
        "provider_type": "sms",
        "provider_key": "smsbower_api",
        "label": "SMSBower",
        "description": "infrastructure.fb981701",
        "driver_type": "smsbower_api",
        "default_auth_mode": "apikey",
        "enabled": True,
        "category": "thirdparty",
        "auth_modes": [{"value": "apikey", "label": "API Key"}],
        "fields": [
            {"key": "smsbower_api_key", "label": "API Key", "secret": True, "category": "auth"},
            {"key": "smsbower_default_country", "label": "infrastructure.2dd115e2", "type": "async-select", "asyncUrl": "/sms/smsbower/countries", "asyncValueKey": "id", "asyncLabelKey": "chn", "placeholder": "infrastructure.ffdcce0a"},
            {"key": "smsbower_default_service", "label": "infrastructure.2bb40855", "type": "async-select", "asyncUrl": "/sms/smsbower/services", "asyncValueKey": "code", "asyncLabelKey": "name", "placeholder": "infrastructure.788bdadf"},
            {"key": "smsbower_max_price", "label": "infrastructure.3b3bbf62", "placeholder": "-1"},
            {"key": "smsbower_auto_country", "label": "infrastructure.235f0e93", "type": "toggle", "hint": "infrastructure.f55d5470"},
            {"key": "register_phone_extra_max", "label": "infrastructure.ca983e45", "placeholder": "3"},
            {"key": "register_reuse_phone_to_max", "label": "infrastructure.77ba1789", "type": "toggle"},
        ],
    },
    # ── proxy ────────────────────────────────────────────────────────
    {
        "provider_type": "proxy",
        "provider_key": "api_extract",
        "label": "infrastructure.10721d25",
        "description": "infrastructure.6f3c803f",
        "driver_type": "api_extract",
        "default_auth_mode": "",
        "enabled": False,
        "category": "thirdparty",
        "auth_modes": [],
        "fields": [
            {"key": "proxy_api_url", "label": "infrastructure.d94c3fb8", "placeholder": "https://provider.com/api/get_proxy?key=xxx"},
            {"key": "proxy_protocol", "label": "infrastructure.ab2f31f3", "placeholder": "http / socks5"},
            {"key": "proxy_username", "label": "infrastructure.66d0d116"},
            {"key": "proxy_password", "label": "infrastructure.b6a06e42", "secret": True},
        ],
    },
    {
        "provider_type": "proxy",
        "provider_key": "rotating_gateway",
        "label": "infrastructure.96c97413",
        "description": "infrastructure.a87111b9",
        "driver_type": "rotating_gateway",
        "default_auth_mode": "",
        "enabled": False,
        "category": "thirdparty",
        "auth_modes": [],
        "fields": [
            {"key": "proxy_gateway_url", "label": "infrastructure.0fbc24ee", "placeholder": "http://user:pass@gate.example.com:7777"},
        ],
    },
]


class ProviderDefinitionsRepository:

    def ensure_seeded(self) -> None:
        """将内置 provider definition 种子数据写入数据库。

        新增的插入，已存在的更新字段定义（label、description、fields 等），
        确保代码升级后内置 provider 的元数据能同步到数据库。
        """
        with Session(engine) as session:
            existing: dict[str, ProviderDefinitionModel] = {}
            for row in session.exec(select(ProviderDefinitionModel)).all():
                key = f"{row.provider_type}::{row.provider_key}"
                existing[key] = row

            changed = False
            for seed in _BUILTIN_DEFINITIONS:
                key = f"{seed['provider_type']}::{seed['provider_key']}"
                item = existing.get(key)

                if item is None:
                    # 新增
                    item = ProviderDefinitionModel(
                        provider_type=seed["provider_type"],
                        provider_key=seed["provider_key"],
                        created_at=_utcnow(),
                    )
                    logger.info("种子数据: 新增 %s/%s", seed["provider_type"], seed["provider_key"])
                else:
                    # 检测将被种子覆盖的字段 — detect the fields about to be overwritten
                    overwritten = _diff_seed_fields(item, seed)
                    if overwritten:
                        logger.warning(
                            "种子数据: %s/%s 的字段 %s 与种子不同，已被种子值覆盖",
                            seed["provider_type"],
                            seed["provider_key"],
                            ", ".join(overwritten),
                        )

                # 更新元数据（每次启动都同步，确保代码变更生效）
                item.label = seed.get("label", seed["provider_key"])
                item.description = seed.get("description", "")
                item.driver_type = seed.get("driver_type", seed["provider_key"])
                item.default_auth_mode = seed.get("default_auth_mode", "")
                item.enabled = seed.get("enabled", True)
                item.is_builtin = True
                item.category = seed.get("category", "")
                item.set_auth_modes(list(seed.get("auth_modes") or []))
                item.set_fields(list(seed.get("fields") or []))
                if not item.get_metadata():
                    # 只在 metadata 为空时写入种子值，避免覆盖用户自定义的 pipeline
                    item.set_metadata(dict(seed.get("metadata") or {}))
                item.updated_at = _utcnow()
                session.add(item)
                changed = True

            if changed:
                session.commit()

    # ── 查询（全部从 DB） ────────────────────────────────────────────

    def list_by_type(self, provider_type: str, *, enabled_only: bool = False) -> list[ProviderDefinitionModel]:
        with Session(engine) as session:
            query = select(ProviderDefinitionModel).where(ProviderDefinitionModel.provider_type == provider_type)
            if enabled_only:
                query = query.where(ProviderDefinitionModel.enabled == True)  # noqa: E712
            return session.exec(query.order_by(ProviderDefinitionModel.id)).all()

    def get_by_key(self, provider_type: str, provider_key: str) -> ProviderDefinitionModel | None:
        with Session(engine) as session:
            return session.exec(
                select(ProviderDefinitionModel)
                .where(ProviderDefinitionModel.provider_type == provider_type)
                .where(ProviderDefinitionModel.provider_key == provider_key)
            ).first()

    def list_driver_templates(self, provider_type: str) -> list[dict]:
        """从 DB 读取：按 driver_type 去重，返回可用驱动模板列表。"""
        with Session(engine) as session:
            definitions = session.exec(
                select(ProviderDefinitionModel)
                .where(ProviderDefinitionModel.provider_type == provider_type)
                .order_by(ProviderDefinitionModel.is_builtin.desc(), ProviderDefinitionModel.id)
            ).all()
        seen: dict[str, dict] = {}
        for d in definitions:
            dt = d.driver_type or ""
            if dt and dt not in seen:
                seen[dt] = {
                    "provider_type": d.provider_type,
                    "provider_key": d.provider_key,
                    "driver_type": dt,
                    "label": d.label,
                    "description": d.description,
                    "default_auth_mode": d.default_auth_mode,
                    "auth_modes": d.get_auth_modes(),
                    "fields": d.get_fields(),
                }
        return list(seen.values())

    def _get_driver_defaults(self, provider_type: str, driver_type: str) -> dict | None:
        """从 DB 中查找同 driver_type 的已有 definition 作为模板。"""
        with Session(engine) as session:
            ref = session.exec(
                select(ProviderDefinitionModel)
                .where(ProviderDefinitionModel.provider_type == provider_type)
                .where(ProviderDefinitionModel.driver_type == driver_type)
                .order_by(ProviderDefinitionModel.is_builtin.desc(), ProviderDefinitionModel.id)
            ).first()
            if not ref:
                return None
            return {
                "default_auth_mode": ref.default_auth_mode,
                "auth_modes": ref.get_auth_modes(),
                "fields": ref.get_fields(),
            }

    # ── 写入 ────────────────────────────────────────────────────────

    def save(
        self,
        *,
        definition_id: int | None,
        provider_type: str,
        provider_key: str,
        label: str,
        description: str,
        driver_type: str,
        enabled: bool,
        default_auth_mode: str = "",
        metadata: dict | None = None,
    ) -> ProviderDefinitionModel:
        defaults = self._get_driver_defaults(provider_type, driver_type)

        with Session(engine) as session:
            if definition_id:
                item = session.get(ProviderDefinitionModel, definition_id)
                if not item:
                    raise ValueError("provider definition 不存在")
            else:
                item = session.exec(
                    select(ProviderDefinitionModel)
                    .where(ProviderDefinitionModel.provider_type == provider_type)
                    .where(ProviderDefinitionModel.provider_key == provider_key)
                ).first()
                if not item:
                    item = ProviderDefinitionModel(
                        provider_type=provider_type,
                        provider_key=provider_key,
                    )
                    item.created_at = _utcnow()

            item.provider_type = provider_type
            item.provider_key = provider_key
            item.label = label or provider_key
            item.description = description or ""
            item.driver_type = driver_type
            item.default_auth_mode = default_auth_mode or item.default_auth_mode or (defaults.get("default_auth_mode", "") if defaults else "")
            item.enabled = bool(enabled)
            if not item.get_auth_modes() and defaults:
                item.set_auth_modes(list(defaults.get("auth_modes") or []))
            if not item.get_fields() and defaults:
                item.set_fields(list(defaults.get("fields") or []))
            item.set_metadata(dict(metadata or {}))
            item.updated_at = _utcnow()
            session.add(item)
            session.commit()
            session.refresh(item)
            return item

    def delete(self, definition_id: int) -> bool:
        with Session(engine) as session:
            item = session.get(ProviderDefinitionModel, definition_id)
            if not item:
                return False
            has_settings = session.exec(
                select(ProviderSettingModel)
                .where(ProviderSettingModel.provider_type == item.provider_type)
                .where(ProviderSettingModel.provider_key == item.provider_key)
            ).first()
            if has_settings:
                raise ValueError("请先删除对应 provider 配置，再删除 definition")
            session.delete(item)
            session.commit()
            return True
