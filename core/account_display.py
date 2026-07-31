from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from core.datetime_utils import serialize_datetime
from i18n import t


def _text(value: Any) -> str:
    return str(value or "").strip()


def _safe_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _format_value(value: Any, lang: str) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, bool):
        return t("core.b5141d3d", lang) if value else t("core.0c70665b", lang)
    return str(value)


def _format_reset_at(value: Any) -> str:
    try:
        timestamp = int(value or 0)
    except (TypeError, ValueError):
        timestamp = 0
    if timestamp <= 0:
        return ""
    return datetime.fromtimestamp(timestamp, timezone.utc).astimezone().strftime("%m/%d %H:%M")


def _format_maybe_timestamp(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, (int, float)):
        return _format_reset_at(value)
    text = _text(value)
    if text.isdigit():
        return _format_reset_at(text)
    return text


def _metric(
    key: str,
    label: str,
    value: Any,
    *,
    lang: str,
    sub: str = "",
    percent: int | float | None = None,
    tone: str = "muted",
) -> dict[str, Any] | None:
    text = _format_value(value, lang)
    if not text:
        return None
    payload: dict[str, Any] = {
        "key": key,
        "label": label,
        "value": text,
        "tone": tone,
    }
    if sub:
        payload["sub"] = sub
    if percent is not None:
        try:
            payload["percent"] = max(0, min(100, round(float(percent), 2)))
        except (TypeError, ValueError):
            pass
    return payload


def _append_metric(items: list[dict[str, Any]], metric: dict[str, Any] | None) -> None:
    if metric:
        items.append(metric)


def _quota_metric(key: str, label: str, limit: dict[str, Any] | None, *, lang: str) -> dict[str, Any] | None:
    if not isinstance(limit, dict):
        return None
    window = _safe_dict(limit.get("primary_window"))
    used_percent = window.get("used_percent")
    try:
        remaining_percent = max(0, min(100, 100 - float(used_percent or 0)))
    except (TypeError, ValueError):
        remaining_percent = None
    reset_label = _format_reset_at(window.get("reset_at"))
    sub = t("core.5912705f", lang, reset_label=reset_label) if reset_label else ""
    if remaining_percent is None:
        return _metric(
            key,
            label,
            t("core.4d99c976", lang) if limit.get("allowed") else t("core.87836358", lang),
            lang=lang,
            sub=sub,
            tone="good" if limit.get("allowed") else "danger",
        )
    tone = "danger" if bool(limit.get("limit_reached")) or remaining_percent <= 0 else ("warning" if remaining_percent <= 20 else "good")
    # t()'s {param} placeholders are bare names only, no format specs — the :g
    # truncation must happen here, before the value reaches t().
    percent_text = f"{remaining_percent:g}"
    return _metric(
        key,
        label,
        t("core.9b4933f8", lang, percent=percent_text),
        lang=lang,
        sub=sub,
        percent=remaining_percent,
        tone=tone,
    )


def _build_chatgpt_metrics(overview: dict[str, Any], lang: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    primary: list[dict[str, Any]] = []
    secondary: list[dict[str, Any]] = []
    usage = _safe_dict(overview.get("chatgpt_usage") or overview.get("wham_usage"))
    if not usage:
        return primary, secondary

    _append_metric(primary, _quota_metric("chatgpt_weekly_limit", t("core.eeac8033", lang), _safe_dict(usage.get("rate_limit")), lang=lang))
    _append_metric(primary, _quota_metric("chatgpt_code_review_weekly_limit", t("core.06042f69", lang), _safe_dict(usage.get("code_review_rate_limit")), lang=lang))

    credits = _safe_dict(usage.get("credits"))
    if credits:
        if credits.get("unlimited"):
            _append_metric(secondary, _metric("chatgpt_credits", "Credits", t("core.8651f50c", lang), lang=lang, tone="good"))
        elif credits.get("balance") not in (None, ""):
            _append_metric(secondary, _metric("chatgpt_credits", "Credits", credits.get("balance"), lang=lang, tone="muted"))
        if credits.get("approx_local_messages") not in (None, ""):
            _append_metric(secondary, _metric("chatgpt_local_messages", t("core.96b65251", lang), credits.get("approx_local_messages"), lang=lang, tone="muted"))
        if credits.get("approx_cloud_messages") not in (None, ""):
            _append_metric(secondary, _metric("chatgpt_cloud_messages", t("core.326ec710", lang), credits.get("approx_cloud_messages"), lang=lang, tone="muted"))
    return primary, secondary


def _build_generic_usage_metrics(overview: dict[str, Any], lang: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    primary: list[dict[str, Any]] = []
    secondary: list[dict[str, Any]] = []
    sections: list[dict[str, Any]] = []

    _append_metric(primary, _metric("remaining_credits", t("core.ff93499b", lang), overview.get("remaining_credits"), lang=lang, tone="good"))
    _append_metric(primary, _metric("usage_total", t("core.b808aeaa", lang), overview.get("usage_total"), lang=lang, tone="muted"))
    _append_metric(secondary, _metric("plan_credits", t("core.4a282655", lang), overview.get("plan_credits"), lang=lang, tone="muted"))
    _append_metric(secondary, _metric("reset_days", t("core.1d18be89", lang), overview.get("days_until_reset"), lang=lang, sub=t("core.49da61ce", lang), tone="muted"))
    _append_metric(secondary, _metric("next_reset_at", t("core.a51b657c", lang), _format_maybe_timestamp(overview.get("next_reset_at")), lang=lang, tone="muted"))

    usage_models = _safe_list(overview.get("usage_models"))
    if usage_models:
        sections.append(
            {
                "key": "usage_models",
                "title": t("core.e40294c6", lang),
                "items": [
                    {
                        "title": _text(item.get("model")) or "model",
                        "metrics": [
                            metric
                            for metric in [
                                _metric("num_requests", t("core.855754c1", lang), item.get("num_requests"), lang=lang),
                                _metric("remaining_requests", t("core.e742a113", lang), item.get("remaining_requests"), lang=lang, tone="good"),
                                _metric("num_tokens", "Token", item.get("num_tokens"), lang=lang),
                                _metric("remaining_tokens", t("core.0ad699eb", lang), item.get("remaining_tokens"), lang=lang, tone="good"),
                            ]
                            if metric
                        ],
                    }
                    for item in usage_models
                    if isinstance(item, dict)
                ],
            }
        )

    usage_breakdowns = _safe_list(overview.get("usage_breakdowns"))
    if usage_breakdowns:
        sections.append(
            {
                "key": "usage_breakdowns",
                "title": t("core.10e9a7c8", lang),
                "items": [
                    {
                        "title": _text(item.get("display_name")) or "usage",
                        "metrics": [
                            metric
                            for metric in [
                                _metric("current_usage", t("core.937683da", lang), item.get("current_usage"), lang=lang),
                                _metric("usage_limit", t("core.8e7ddbee", lang), item.get("usage_limit"), lang=lang),
                                _metric("remaining_usage", t("core.d6822b04", lang), item.get("remaining_usage"), lang=lang, tone="good"),
                                _metric("trial_status", t("core.e6a314b1", lang), item.get("trial_status"), lang=lang),
                                _metric("trial_expiry", t("core.2753a45a", lang), item.get("trial_expiry"), lang=lang),
                                _metric("trial_remaining_usage", t("core.f0ce7ca5", lang), item.get("trial_remaining_usage"), lang=lang, tone="good"),
                            ]
                            if metric
                        ],
                    }
                    for item in usage_breakdowns
                    if isinstance(item, dict)
                ],
            }
        )

    return primary, secondary, sections


def build_account_display_summary(
    *,
    platform: str,
    email: str,
    lifecycle_status: str,
    validity_status: str,
    plan_state: str,
    plan_name: str,
    display_status: str,
    overview: dict[str, Any] | None,
    provider_resources: list[dict[str, Any]] | None = None,
    lang: str = "zh",
) -> dict[str, Any]:
    overview = _safe_dict(overview)
    checked_at = overview.get("checked_at")
    if isinstance(checked_at, datetime):
        checked_at_value = serialize_datetime(checked_at)
    else:
        checked_at_value = _text(checked_at)

    primary_metrics: list[dict[str, Any]] = []
    secondary_metrics: list[dict[str, Any]] = []
    sections: list[dict[str, Any]] = []

    effective_plan_name = _text(plan_name or overview.get("plan_name") or overview.get("plan"))
    if effective_plan_name:
        _append_metric(secondary_metrics, _metric("plan_name", t("core.c1cfa134", lang), effective_plan_name, lang=lang, tone="muted"))
    if plan_state and plan_state != "unknown":
        _append_metric(secondary_metrics, _metric("plan_state", t("core.a2004596", lang), plan_state, lang=lang, tone="muted"))
    if checked_at_value:
        _append_metric(secondary_metrics, _metric("checked_at", t("core.85c449ce", lang), checked_at_value, lang=lang, tone="muted"))

    chatgpt_primary, chatgpt_secondary = _build_chatgpt_metrics(overview, lang)
    primary_metrics.extend(chatgpt_primary)
    secondary_metrics.extend(chatgpt_secondary)

    generic_primary, generic_secondary, generic_sections = _build_generic_usage_metrics(overview, lang)
    primary_metrics.extend(generic_primary)
    secondary_metrics.extend(generic_secondary)
    sections.extend(generic_sections)

    warnings: list[dict[str, Any]] = []
    if validity_status == "invalid" or lifecycle_status == "invalid":
        warnings.append({"key": "invalid", "tone": "danger", "message": t("core.b5a31ec8", lang)})
    if validity_status == "unknown":
        warnings.append({"key": "unknown_validity", "tone": "warning", "message": t("core.641e827b", lang)})
    if overview.get("quota_note"):
        warnings.append({"key": "quota_note", "tone": "warning", "message": _text(overview.get("quota_note"))})
    if overview.get("check_error"):
        warnings.append({"key": "check_error", "tone": "danger", "message": _text(overview.get("check_error"))})

    badges = [
        {"label": _text(chip), "tone": "muted"}
        for chip in _safe_list(overview.get("chips"))
        if _text(chip)
    ]
    for resource in provider_resources or []:
        if isinstance(resource, dict) and resource.get("resource_type") == "mailbox" and (resource.get("handle") or resource.get("display_name")):
            badges.append({"label": t("core.72e5f913", lang), "tone": "muted"})
            break

    return {
        "identity": {
            "email": email,
            "remote_email": _text(overview.get("remote_email")),
            "platform": platform,
        },
        "status": {
            "display": display_status,
            "lifecycle": lifecycle_status,
            "validity": validity_status,
            "plan_state": plan_state,
            "plan_name": effective_plan_name,
            "checked_at": checked_at_value,
        },
        "primary_metrics": primary_metrics,
        "secondary_metrics": secondary_metrics,
        "badges": badges,
        "warnings": warnings,
        "sections": sections,
    }
