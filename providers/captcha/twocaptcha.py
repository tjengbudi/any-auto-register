"""2Captcha — cloud Turnstile solver."""
from core.base_captcha import BaseCaptcha
from providers.registry import register_provider


@register_provider("captcha", "twocaptcha_api")
class TwoCaptcha(BaseCaptcha):
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.api = "https://2captcha.com"

    @classmethod
    def from_config(cls, config: dict) -> 'TwoCaptcha':
        api_key = str(config.get("twocaptcha_key", "") or "")
        if not api_key:
            exc = RuntimeError("2Captcha Key 未配置")
            exc.i18n_key = "providers.1146b4a0"
            exc.i18n_params = {}
            raise exc
        return cls(api_key)

    def solve_turnstile(self, page_url: str, site_key: str) -> str:
        import time
        import requests

        create = requests.post(
            f"{self.api}/in.php",
            data={
                "key": self.api_key,
                "method": "turnstile",
                "sitekey": site_key,
                "pageurl": page_url,
                "json": 1,
            },
            timeout=30,
        )
        create.raise_for_status()
        payload = create.json()
        if payload.get("status") != 1:
            payload_str = str(payload)
            exc = RuntimeError(f"2Captcha 创建任务失败: {payload_str}")
            exc.i18n_key = "providers.bc8aa395"
            exc.i18n_params = {"payload": payload_str}
            raise exc
        task_id = payload.get("request")
        if not task_id:
            payload_str = str(payload)
            exc = RuntimeError(f"2Captcha 未返回任务 ID: {payload_str}")
            exc.i18n_key = "providers.b0f1f4ea"
            exc.i18n_params = {"payload": payload_str}
            raise exc

        for _ in range(60):
            time.sleep(3)
            result = requests.get(
                f"{self.api}/res.php",
                params={
                    "key": self.api_key,
                    "action": "get",
                    "id": task_id,
                    "json": 1,
                },
                timeout=30,
            )
            result.raise_for_status()
            data = result.json()
            if data.get("status") == 1:
                return str(data.get("request") or "")
            if data.get("request") not in {"CAPCHA_NOT_READY", "CAPTCHA_NOT_READY"}:
                data_str = str(data)
                exc = RuntimeError(f"2Captcha 错误: {data_str}")
                exc.i18n_key = "providers.04161146"
                exc.i18n_params = {"data": data_str}
                raise exc
        exc = TimeoutError("2Captcha Turnstile 超时")
        exc.i18n_key = "providers.482309b7"
        exc.i18n_params = {}
        raise exc

    def solve_image(self, image_b64: str) -> str:
        raise NotImplementedError
