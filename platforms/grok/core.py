"""
Grok (x.ai) 自动注册 - 纯协议实现
Grok (x.ai) automated registration - pure protocol implementation
"""
import re, struct, random, string, time
from typing import Callable, Optional

from curl_cffi import requests as cffi_requests

from platforms.grok._i18n_helpers import _emit_log_key

ACCOUNTS_URL = "https://accounts.x.ai"
TURNSTILE_SITEKEY = "0x4AAAAAAAhr9JGVDZbrZOo0"
NEXT_ACTION = "7f69646bb11542f4cad728680077c67a09624b94e0"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


def _pb_string(field: int, value: str) -> bytes:
    encoded = value.encode('utf-8')
    tag = (field << 3) | 2
    return _varint(tag) + _varint(len(encoded)) + encoded


def _varint(n: int) -> bytes:
    buf = []
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            buf.append(b | 0x80)
        else:
            buf.append(b)
            break
    return bytes(buf)


def _grpc_frame(body: bytes) -> bytes:
    return b'\x00' + struct.pack('>I', len(body)) + body


def _rand_name(n=6):
    return ''.join(random.choices(string.ascii_lowercase, k=n)).capitalize()


def _rand_password(n=12):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=n)) + ',,,aA1'


class GrokRegister:
    def __init__(self, captcha_solver=None, yescaptcha_key='', proxy=None, log_fn=print, log_key_fn: Optional[Callable[[str, dict], None]] = None):
        self.captcha_solver = captcha_solver
        self.key = yescaptcha_key
        self.log = log_fn
        self._log_key_fn = log_key_fn
        self.s = cffi_requests.Session(impersonate="chrome131")
        if proxy:
            self.s.proxies = {"http": proxy, "https": proxy}
        self.s.headers.update({"user-agent": UA})

    def log_key(self, key: str, **params) -> None:
        _emit_log_key(self.log, self._log_key_fn, key, **params)

    def _grpc_post(self, path: str, body: bytes) -> bytes:
        r = self.s.post(f'{ACCOUNTS_URL}{path}',
            headers={'content-type': 'application/grpc-web+proto',
                     'x-grpc-web': '1',
                     'origin': 'https://accounts.x.ai',
                     'referer': 'https://accounts.x.ai/sign-up'},
            data=_grpc_frame(body))
        return r.content

    def _solve_turnstile(self) -> str:
        self.log_key("grok.f6167694")
        # was: self.log("获取 Turnstile token...") — was: self.log("Getting the Turnstile token...")
        solver = self.captcha_solver
        if not solver:
            from core.base_captcha import YesCaptcha
            solver = YesCaptcha(self.key)
        token = solver.solve_turnstile('https://accounts.x.ai/sign-up', TURNSTILE_SITEKEY)
        self.log(f"  Turnstile: {token[:40]}...")
        return token

    def step1_send_otp(self, email: str):
        self.log_key("grok.89bd438f", email=email)
        # was: self.log(f"Step1: 发送验证码到 {email}...") — was: self.log(f"Step1: sending the verification code to {email}...")
        body = _pb_string(1, email)
        self._grpc_post('/auth_mgmt.AuthManagement/CreateEmailValidationCode', body)
        self.log_key("grok.6cbfeaf9")
        # was: self.log("  验证码已发送") — was: self.log("  Verification code sent")

    def step2_verify_otp(self, email: str, code: str) -> bool:
        self.log_key("grok.91d3a0aa", code=code)
        # was: self.log(f"Step2: 验证码校验 {code}...") — was: self.log(f"Step2: verifying the code {code}...")
        body = _pb_string(1, email) + _pb_string(2, code)
        resp = self._grpc_post('/auth_mgmt.AuthManagement/VerifyEmailValidationCode', body)
        ok = b'grpc-status:0' in resp
        status = 'OK' if ok else 'FAIL'
        self.log_key("grok.a8514109", status=status)
        # was: self.log(f"  校验: {'OK' if ok else 'FAIL'}") — was: self.log(f"  Verification: {'OK' if ok else 'FAIL'}")
        return ok

    def step3_signup(self, email: str, password: str, code: str,
                     given_name: str, family_name: str) -> str:
        turnstile = self._solve_turnstile()
        self.log_key("grok.85e9553d")
        # was: self.log("Step3: 提交注册...") — was: self.log("Step3: submitting registration...")
        payload = [{
            'emailValidationCode': code,
            'createUserAndSessionRequest': {
                'email': email,
                'givenName': given_name,
                'familyName': family_name,
                'clearTextPassword': password,
                'tosAcceptedVersion': 1,
            },
            'turnstileToken': turnstile,
        }]
        r = self.s.post(f'{ACCOUNTS_URL}/sign-up',
            headers={'content-type': 'application/json',
                     'next-action': NEXT_ACTION,
                     'origin': 'https://accounts.x.ai',
                     'referer': 'https://accounts.x.ai/sign-up'},
            json=payload)
        self.log(f"  sign-up status={r.status_code}")
        return r.text

    def step4_set_cookies(self, signup_body: str):
        self.log_key("grok.9e7cc7c6")
        # was: self.log("Step4: 设置 session cookies...") — was: self.log("Step4: setting session cookies...")
        urls = re.findall(r'https://auth\.[^"\s\\]+/set-cookie[^"\s\\]*', signup_body)
        for url in urls:
            url = url.replace('\\u0026', '&').replace('\\u003d', '=')
            self.log(f"  {url[:70]}...")
            self.s.get(url, headers={'user-agent': UA, 'accept': 'text/html',
                                     'referer': 'https://accounts.x.ai/'},
                       allow_redirects=True)
