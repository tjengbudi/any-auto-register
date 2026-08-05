"""YesCaptcha — cloud Turnstile solver."""
from core.base_captcha import BaseCaptcha
from core.tls import insecure_request
from providers.registry import register_provider


@register_provider("captcha", "yescaptcha_api")
class YesCaptcha(BaseCaptcha):
    def __init__(self, client_key: str):
        self.client_key = client_key
        self.api = "https://api.yescaptcha.com"

    @classmethod
    def from_config(cls, config: dict) -> 'YesCaptcha':
        client_key = str(config.get("yescaptcha_key", "") or "")
        if not client_key:
            exc = RuntimeError("YesCaptcha Key 未配置")
            exc.i18n_key = "providers.9bfc5153"
            exc.i18n_params = {}
            raise exc
        return cls(client_key)

    def solve_turnstile(self, page_url: str, site_key: str) -> str:
        import requests, time
        r = insecure_request(requests.post, f"{self.api}/createTask", json={
            "clientKey": self.client_key,
            "task": {"type": "TurnstileTaskProxyless",
                     "websiteURL": page_url, "websiteKey": site_key}
        }, timeout=30)
        task_id = r.json().get("taskId")
        if not task_id:
            text = r.text
            exc = RuntimeError(f"YesCaptcha 创建任务失败: {text}")
            exc.i18n_key = "providers.1b3c747c"
            exc.i18n_params = {"text": text}
            raise exc
        for _ in range(60):
            time.sleep(3)
            d = insecure_request(requests.post, f"{self.api}/getTaskResult", json={
                "clientKey": self.client_key, "taskId": task_id
            }, timeout=30).json()
            if d.get("status") == "ready":
                return d["solution"]["token"]
            if d.get("errorId", 0) != 0:
                d_str = str(d)
                exc = RuntimeError(f"YesCaptcha 错误: {d_str}")
                exc.i18n_key = "providers.4ec76fbc"
                exc.i18n_params = {"d": d_str}
                raise exc
        exc = TimeoutError("YesCaptcha Turnstile 超时")
        exc.i18n_key = "providers.ee9cda95"
        exc.i18n_params = {}
        raise exc

    def solve_image(self, image_b64: str) -> str:
        raise NotImplementedError
