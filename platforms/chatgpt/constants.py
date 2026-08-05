"""
常量定义

Constant definitions.
"""

import os
import random
from datetime import datetime
from enum import Enum
from typing import Dict, List, Tuple


# ============================================================================
# 枚举类型 — Enum types
# ============================================================================

class AccountStatus(str, Enum):
    """账户状态 — Account status."""
    ACTIVE = "active"
    EXPIRED = "expired"
    BANNED = "banned"
    FAILED = "failed"


class TaskStatus(str, Enum):
    """任务状态 — Task status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class EmailServiceType(str, Enum):
    """邮箱服务类型 — Mailbox service type."""
    TEMPMAIL = "tempmail"
    OUTLOOK = "outlook"
    CUSTOM_DOMAIN = "custom_domain"
    TEMP_MAIL = "temp_mail"


# ============================================================================
# 应用常量 — Application constants
# ============================================================================

APP_NAME = "OpenAI/Codex CLI 自动注册系统"
APP_VERSION = "2.0.0"
APP_DESCRIPTION = "自动注册 OpenAI/Codex CLI 账号的系统"

# ============================================================================
# OpenAI OAuth 相关常量 — OpenAI OAuth-related constants
# ============================================================================

# OpenAI 基础 URL（支持通过环境变量覆盖） — OpenAI base URL (overridable via env var)
OPENAI_AUTH = os.environ.get("OPENAI_AUTH_BASE_URL", "https://auth.openai.com")
CHATGPT_APP = os.environ.get("CHATGPT_APP_URL", "https://chatgpt.com")
PLATFORM_LOGIN_ENTRY = os.environ.get("PLATFORM_LOGIN_ENTRY", "https://platform.openai.com/login")

# OAuth 参数（支持通过环境变量覆盖） — OAuth parameters (overridable via env var)
# 注册阶段使用 ChatGPT Web client（无 add_phone 要求） — Registration uses the ChatGPT Web client (no add_phone requirement)
OAUTH_CLIENT_ID = os.environ.get("OAUTH_CLIENT_ID", "app_X8zY6vW2pQ9tR3dE7nK1jL5gH")
OAUTH_AUTH_URL = f"{OPENAI_AUTH}/api/accounts/authorize"
OAUTH_TOKEN_URL = f"{OPENAI_AUTH}/oauth/token"
OAUTH_REDIRECT_URI = "https://chatgpt.com/api/auth/callback/openai"
OAUTH_SCOPE = "openid email profile offline_access model.request model.read organization.read organization.write"

# Token 获取使用 Codex CLI client（公开客户端，支持 PKCE） —
# Token retrieval uses the Codex CLI client (public client, PKCE-enabled)
CODEX_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
CODEX_REDIRECT_URI = "http://localhost:1455/auth/callback"
CODEX_SCOPE = "openid email profile offline_access"

# Sentinel（PoW 防护）- 版本号可能随 OpenAI 更新而变化（支持通过环境变量覆盖） —
# Sentinel (PoW defense) - version numbers may shift with OpenAI updates (overridable via env var)
SENTINEL_BASE = os.environ.get("SENTINEL_BASE_URL", "https://sentinel.openai.com")
SENTINEL_SDK_VERSION = os.environ.get("SENTINEL_SDK_VERSION", "20260124ceb8")
SENTINEL_FRAME_VERSION = os.environ.get("SENTINEL_FRAME_VERSION", "20260219f9f6")
SENTINEL_SDK_URL = f"{SENTINEL_BASE}/sentinel/{SENTINEL_SDK_VERSION}/sdk.js"
SENTINEL_REQ_URL = f"{SENTINEL_BASE}/backend-api/sentinel/req"
SENTINEL_FRAME_URL = f"{SENTINEL_BASE}/backend-api/sentinel/frame.html?sv={SENTINEL_FRAME_VERSION}"

# OAuth consent 页面表单选择器 — Form selector for the OAuth consent page
OAUTH_CONSENT_FORM_SELECTOR = 'form[action*="/sign-in-with-chatgpt/"][action*="/consent"]'

# OpenAI API 端点 — OpenAI API endpoints
OPENAI_API_ENDPOINTS = {
    "sentinel": SENTINEL_REQ_URL,
    "signup": f"{OPENAI_AUTH}/api/accounts/authorize/continue",
    "register": f"{OPENAI_AUTH}/api/accounts/user/register",
    "send_otp": f"{OPENAI_AUTH}/api/accounts/email-otp/send",
    "validate_otp": f"{OPENAI_AUTH}/api/accounts/email-otp/validate",
    "create_account": f"{OPENAI_AUTH}/api/accounts/create_account",
    "select_workspace": f"{OPENAI_AUTH}/api/accounts/workspace/select",
}

# OpenAI 页面类型（用于判断账号状态） — OpenAI page types (used to determine account status)
OPENAI_PAGE_TYPES = {
    "EMAIL_OTP_VERIFICATION": "email_otp_verification",  # 已注册账号，需要 OTP 验证 — Already-registered account, requires OTP verification
    "PASSWORD_REGISTRATION": "password",  # 新账号，需要设置密码 — New account, requires setting a password
}

# ============================================================================
# 邮箱服务相关常量 — Mailbox service-related constants
# ============================================================================

# Tempmail.lol API 端点 — Tempmail.lol API endpoints
TEMPMAIL_API_ENDPOINTS = {
    "create_inbox": "/inbox/create",
    "get_inbox": "/inbox",
}

# 自定义域名邮箱 API 端点 — Custom-domain mailbox API endpoints
CUSTOM_DOMAIN_API_ENDPOINTS = {
    "get_config": "/api/config",
    "create_email": "/api/emails/generate",
    "list_emails": "/api/emails",
    "get_email_messages": "/api/emails/{emailId}",
    "delete_email": "/api/emails/{emailId}",
    "get_message": "/api/emails/{emailId}/{messageId}",
}

# 邮箱服务默认配置 — Default mailbox service configuration
EMAIL_SERVICE_DEFAULTS = {
    "tempmail": {
        "base_url": "https://api.tempmail.lol/v2",
        "timeout": 30,
        "max_retries": 3,
    },
    "outlook": {
        "imap_server": "outlook.office365.com",
        "imap_port": 993,
        "smtp_server": "smtp.office365.com",
        "smtp_port": 587,
        "timeout": 30,
    },
    "custom_domain": {
        "base_url": "",  # 需要用户配置 — Requires user configuration
        "api_key_header": "X-API-Key",
        "timeout": 30,
        "max_retries": 3,
    }
}

# ============================================================================
# 注册流程相关常量 — Registration flow-related constants
# ============================================================================

# 验证码相关 — OTP-related
OTP_CODE_PATTERN = r"(?<!\d)(\d{6})(?!\d)"
OTP_MAX_ATTEMPTS = 40  # 最大轮询次数 — Max polling attempts

# 验证码提取正则（增强版） — OTP extraction regex (enhanced)
# 简单匹配：任意 6 位数字 — Simple match: any 6 digits
OTP_CODE_SIMPLE_PATTERN = r"(?<!\d)(\d{6})(?!\d)"
# 语义匹配：带上下文的验证码（如 "code is 123456", "验证码 123456"） —
# Semantic match: OTP with surrounding context (e.g. "code is 123456", or the Chinese phrasing "验证码 123456")
OTP_CODE_SEMANTIC_PATTERN = r'(?:code\s+is|验证码[是为]?\s*[:：]?\s*)(\d{6})'

# OpenAI 验证邮件发件人 — OpenAI verification-email senders
OPENAI_EMAIL_SENDERS = [
    "noreply@openai.com",
    "no-reply@openai.com",
    "@openai.com",     # 精确域名匹配 — Exact domain match
    ".openai.com",     # 子域名匹配（如 otp@tm1.openai.com） — Subdomain match (e.g. otp@tm1.openai.com)
]

# OpenAI 验证邮件关键词 — OpenAI verification-email keywords
OPENAI_VERIFICATION_KEYWORDS = [
    "verify your email",
    "verification code",
    "验证码",
    "your openai code",
    "code is",
    "one-time code",
]

# 密码生成 — Password generation
PASSWORD_CHARSET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
DEFAULT_PASSWORD_LENGTH = 12

# 用户信息生成（用于注册） — User info generation (for registration)

# 常用英文名 — Common English names
FIRST_NAMES = [
    "James", "John", "Robert", "Michael", "William", "David", "Richard", "Joseph", "Thomas", "Charles",
    "Emma", "Olivia", "Ava", "Isabella", "Sophia", "Mia", "Charlotte", "Amelia", "Harper", "Evelyn",
    "Alex", "Jordan", "Taylor", "Morgan", "Casey", "Riley", "Jamie", "Avery", "Quinn", "Skyler",
    "Liam", "Noah", "Ethan", "Lucas", "Mason", "Oliver", "Elijah", "Aiden", "Henry", "Sebastian",
    "Grace", "Lily", "Chloe", "Zoey", "Nora", "Aria", "Hazel", "Aurora", "Stella", "Ivy"
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez",
    "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin",
    "Lee", "Perez", "Thompson", "White", "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson",
    "Walker", "Young", "Allen", "King", "Wright", "Scott", "Torres", "Nguyen", "Hill", "Flores"
]

def generate_random_user_info() -> dict:
    """
    生成随机用户信息

    Returns:
        包含 name 和 birthdate 的字典

    Generate random user info.

    Returns:
        A dict containing name and birthdate.
    """
    first_name = random.choice(FIRST_NAMES)
    last_name = random.choice(LAST_NAMES)
    name = f"{first_name} {last_name}"

    # 生成随机生日（25-40岁，避免边界年龄问题） — Generate a random birthdate (age 25-40, avoiding edge-case ages)
    current_year = datetime.now().year
    birth_year = random.randint(current_year - 40, current_year - 25)
    birth_month = random.randint(1, 12)
    # 根据月份确定天数 — Determine day count based on month
    if birth_month in [1, 3, 5, 7, 8, 10, 12]:
        birth_day = random.randint(1, 31)
    elif birth_month in [4, 6, 9, 11]:
        birth_day = random.randint(1, 30)
    else:
        # 2月，简化处理 — February, simplified handling
        birth_day = random.randint(1, 28)

    birthdate = f"{birth_year}-{birth_month:02d}-{birth_day:02d}"

    return {
        "name": name,
        "birthdate": birthdate
    }

# 保留默认值供兼容 — Kept for backward compatibility
DEFAULT_USER_INFO = {
    "name": "Neo",
    "birthdate": "2000-02-20",
}

# ============================================================================
# 代理相关常量 — Proxy-related constants
# ============================================================================

PROXY_TYPES = ["http", "socks5", "socks5h"]
DEFAULT_PROXY_CONFIG = {
    "enabled": False,
    "type": "http",
    "host": "127.0.0.1",
    "port": 7890,
}

# ============================================================================
# 数据库相关常量 — Database-related constants
# ============================================================================

# 数据库表名 — Database table names
DB_TABLE_NAMES = {
    "accounts": "accounts",
    "email_services": "email_services",
    "registration_tasks": "registration_tasks",
    "settings": "settings",
}

# 默认设置 — Default settings
DEFAULT_SETTINGS = [
    # (key, value, description, category)
    ("system.name", APP_NAME, "系统名称", "general"),
    ("system.version", APP_VERSION, "系统版本", "general"),
    ("logs.retention_days", "30", "日志保留天数", "general"),
    ("openai.client_id", OAUTH_CLIENT_ID, "OpenAI OAuth Client ID", "openai"),
    ("openai.auth_url", OAUTH_AUTH_URL, "OpenAI 认证地址", "openai"),
    ("openai.token_url", OAUTH_TOKEN_URL, "OpenAI Token 地址", "openai"),
    ("openai.redirect_uri", OAUTH_REDIRECT_URI, "OpenAI 回调地址", "openai"),
    ("openai.scope", OAUTH_SCOPE, "OpenAI 权限范围", "openai"),
    ("proxy.enabled", "false", "是否启用代理", "proxy"),
    ("proxy.type", "http", "代理类型 (http/socks5)", "proxy"),
    ("proxy.host", "127.0.0.1", "代理主机", "proxy"),
    ("proxy.port", "7890", "代理端口", "proxy"),
    ("registration.max_retries", "3", "最大重试次数", "registration"),
    ("registration.timeout", "120", "超时时间（秒）", "registration"),
    ("registration.default_password_length", "12", "默认密码长度", "registration"),
    ("webui.host", "0.0.0.0", "Web UI 监听主机", "webui"),
    ("webui.port", "8000", "Web UI 监听端口", "webui"),
    ("webui.debug", "true", "调试模式", "webui"),
]

# ============================================================================
# Web UI 相关常量 — Web UI-related constants
# ============================================================================

# WebSocket 事件 — WebSocket events
WEBSOCKET_EVENTS = {
    "CONNECT": "connect",
    "DISCONNECT": "disconnect",
    "LOG": "log",
    "STATUS": "status",
    "ERROR": "error",
    "COMPLETE": "complete",
}

# API 响应状态码 — API response status codes
API_STATUS_CODES = {
    "SUCCESS": 200,
    "CREATED": 201,
    "BAD_REQUEST": 400,
    "UNAUTHORIZED": 401,
    "FORBIDDEN": 403,
    "NOT_FOUND": 404,
    "CONFLICT": 409,
    "INTERNAL_ERROR": 500,
}

# 分页 — Pagination
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

# ============================================================================
# 错误消息 — Error messages
# ============================================================================

ERROR_MESSAGES = {
    # 通用错误 — General errors
    "DATABASE_ERROR": "数据库操作失败",
    "CONFIG_ERROR": "配置错误",
    "NETWORK_ERROR": "网络连接失败",
    "TIMEOUT": "操作超时",
    "VALIDATION_ERROR": "参数验证失败",

    # 邮箱服务错误 — Mailbox service errors
    "EMAIL_SERVICE_UNAVAILABLE": "邮箱服务不可用",
    "EMAIL_CREATION_FAILED": "创建邮箱失败",
    "OTP_NOT_RECEIVED": "未收到验证码",
    "OTP_INVALID": "验证码无效",

    # OpenAI 相关错误 — OpenAI-related errors
    "OPENAI_AUTH_FAILED": "OpenAI 认证失败",
    "OPENAI_RATE_LIMIT": "OpenAI 接口限流",
    "OPENAI_CAPTCHA": "遇到验证码",

    # 代理错误 — Proxy errors
    "PROXY_FAILED": "代理连接失败",
    "PROXY_AUTH_FAILED": "代理认证失败",

    # 账户错误 — Account errors
    "ACCOUNT_NOT_FOUND": "账户不存在",
    "ACCOUNT_ALREADY_EXISTS": "账户已存在",
    "ACCOUNT_INVALID": "账户无效",

    # 任务错误 — Task errors
    "TASK_NOT_FOUND": "任务不存在",
    "TASK_ALREADY_RUNNING": "任务已在运行中",
    "TASK_CANCELLED": "任务已取消",
}

# ============================================================================
# 正则表达式 — Regular expressions
# ============================================================================

REGEX_PATTERNS = {
    "EMAIL": r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$",
    "URL": r"https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+",
    "IP_ADDRESS": r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
    "OTP_CODE": OTP_CODE_PATTERN,
}

# ============================================================================
# 时间常量 — Time constants
# ============================================================================

TIME_CONSTANTS = {
    "SECOND": 1,
    "MINUTE": 60,
    "HOUR": 3600,
    "DAY": 86400,
    "WEEK": 604800,
}


# ============================================================================
# Microsoft/Outlook 相关常量 — Microsoft/Outlook-related constants
# ============================================================================

# Microsoft OAuth2 Token 端点 — Microsoft OAuth2 token endpoints
MICROSOFT_TOKEN_ENDPOINTS = {
    # 旧版 IMAP 使用的端点 — Endpoint used by legacy IMAP
    "LIVE": "https://login.live.com/oauth20_token.srf",
    # 新版 IMAP 使用的端点（需要特定 scope） — Endpoint used by new IMAP (requires specific scope)
    "CONSUMERS": "https://login.microsoftonline.com/consumers/oauth2/v2.0/token",
    # Graph API 使用的端点 — Endpoint used by Graph API
    "COMMON": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
}

# IMAP 服务器配置 — IMAP server configuration
OUTLOOK_IMAP_SERVERS = {
    "OLD": "outlook.office365.com",  # 旧版 IMAP — Legacy IMAP
    "NEW": "outlook.live.com",       # 新版 IMAP — New IMAP
}

# Microsoft OAuth2 Scopes
MICROSOFT_SCOPES = {
    # 旧版 IMAP 不需要特定 scope — Legacy IMAP does not need a specific scope
    "IMAP_OLD": "",
    # 新版 IMAP 需要的 scope — Scope required by new IMAP
    "IMAP_NEW": "https://outlook.office.com/IMAP.AccessAsUser.All offline_access",
    # Graph API 需要的 scope — Scope required by Graph API
    "GRAPH_API": "https://graph.microsoft.com/.default",
}

# Outlook 提供者默认优先级 — Default Outlook provider priority
OUTLOOK_PROVIDER_PRIORITY = ["imap_new", "imap_old", "graph_api"]
