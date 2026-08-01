from __future__ import annotations

from i18n import t
from services.solver_manager import get_status, restart


class SystemRuntime:
    def solver_status(self) -> dict:
        return get_status()

    def restart_solver(self, lang: str = "zh") -> dict:
        import threading
        threading.Thread(target=restart, daemon=True).start()
        return {"message": t("infrastructure.831e7a7a", lang)}
