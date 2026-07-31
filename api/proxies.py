from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.deps import get_ui_language
from application.proxies import ProxiesService
from domain.proxies import ProxyBulkCreateCommand, ProxyCreateCommand
from i18n import t

router = APIRouter(prefix="/proxies", tags=["proxies"])
service = ProxiesService()


class ProxyCreateRequest(BaseModel):
    url: str
    region: str = ""


class ProxyBulkCreateRequest(BaseModel):
    proxies: list[str]
    region: str = ""


@router.get("")
def list_proxies():
    return service.list_proxies()


@router.post("")
def create_proxy(body: ProxyCreateRequest, lang: str = Depends(get_ui_language)):
    item = service.create_proxy(ProxyCreateCommand(url=body.url, region=body.region))
    if not item:
        raise HTTPException(400, t("api.4ab0a7ed", lang))
    return item


@router.post("/bulk")
def bulk_create_proxies(body: ProxyBulkCreateRequest):
    return service.bulk_create_proxies(ProxyBulkCreateCommand(proxies=body.proxies, region=body.region))


@router.delete("/{proxy_id}")
def delete_proxy(proxy_id: int, lang: str = Depends(get_ui_language)):
    result = service.delete_proxy(proxy_id)
    if not result["ok"]:
        raise HTTPException(404, t("api.345790e2", lang))
    return result


@router.patch("/{proxy_id}/toggle")
def toggle_proxy(proxy_id: int, lang: str = Depends(get_ui_language)):
    result = service.toggle_proxy(proxy_id)
    if not result:
        raise HTTPException(404, t("api.345790e2", lang))
    return result


@router.post("/check")
def check_proxies():
    return service.trigger_check()
