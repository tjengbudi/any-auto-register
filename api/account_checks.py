from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_ui_language
from application.account_checks import AccountChecksService
from i18n import t

router = APIRouter(prefix="/accounts", tags=["account-checks"])
service = AccountChecksService()


@router.post("/check-all")
def check_all_accounts(platform: str = ""):
    return service.check_all_async(platform)


@router.post("/{account_id}/check")
def check_account(account_id: int, lang: str = Depends(get_ui_language)):
    result = service.check_one_async(account_id)
    if not result:
        raise HTTPException(404, t("api.af8bb650", lang))
    return result
