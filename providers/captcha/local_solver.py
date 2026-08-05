"""Local Turnstile solver (Camoufox / patchright)."""
from core.base_captcha import BaseCaptcha
from providers.registry import register_provider


@register_provider("captcha", "local_solver")
class LocalSolverCaptcha(BaseCaptcha):
    """调用本地 api_solver 服务解 Turnstile（Camoufox/patchright） —
    call the local api_solver service to solve Turnstile (Camoufox/patchright)"""

    def __init__(self, solver_url: str = ""):
        self.solver_url = solver_url.rstrip("/")

    @classmethod
    def from_config(cls, config: dict) -> 'LocalSolverCaptcha':
        return cls(str(config.get("solver_url", "") or ""))

    def solve_turnstile(self, page_url: str, site_key: str) -> str:
        import requests, time
        # 提交任务 — Submit the task
        r = requests.get(
            f"{self.solver_url}/turnstile",
            params={"url": page_url, "sitekey": site_key},
            timeout=15,
        )
        r.raise_for_status()
        task_id = r.json().get("taskId")
        if not task_id:
            text = r.text
            exc = RuntimeError(f"LocalSolver 未返回 taskId: {text}")
            exc.i18n_key = "providers.4ea7683b"
            exc.i18n_params = {"text": text}
            raise exc
        # 轮询结果 — Poll for the result
        for _ in range(60):
            time.sleep(2)
            res = requests.get(
                f"{self.solver_url}/result",
                params={"id": task_id},
                timeout=10,
            )
            if res.status_code == 200:
                data = res.json()
                if data.get("errorId"):
                    message = str(data.get("errorDescription") or data.get("errorCode") or data)
                    exc = RuntimeError(f"LocalSolver Turnstile 失败: {message}")
                    exc.i18n_key = "providers.78d5466d"
                    exc.i18n_params = {"message": message}
                    raise exc
                status = data.get("status")
                if status == "ready":
                    token = data.get("solution", {}).get("token")
                    if token:
                        return token
                elif status == "CAPTCHA_FAIL":
                    exc = RuntimeError("LocalSolver Turnstile 失败")
                    exc.i18n_key = "providers.17194286"
                    exc.i18n_params = {}
                    raise exc
        exc = TimeoutError("LocalSolver Turnstile 超时")
        exc.i18n_key = "providers.4ccd485e"
        exc.i18n_params = {}
        raise exc

    def solve_image(self, image_b64: str) -> str:
        raise NotImplementedError

    @staticmethod
    def start_solver(headless: bool = True, browser_type: str = "camoufox",
                     port: int = 8889) -> None:
        """在后台线程启动本地 solver 服务 — start the local solver service on a background thread"""
        import subprocess, sys, os
        solver_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "services", "turnstile_solver", "start.py"
        )
        cmd = [
            sys.executable, solver_path,
            "--port", str(port),
            "--browser_type", browser_type,
        ]
        if not headless:
            cmd.append("--no-headless")
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # 等待服务启动 — Wait for the service to start
        import time, requests
        for _ in range(20):
            time.sleep(1)
            try:
                requests.get(f"http://localhost:{port}/", timeout=2)
                return
            except Exception:
                pass
        exc = RuntimeError("LocalSolver 启动超时")
        exc.i18n_key = "providers.850c56bd"
        exc.i18n_params = {}
        raise exc
