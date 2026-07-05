import os
from dataclasses import dataclass


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _read_password() -> str:
    password = os.getenv("CLICKHOUSE_PASSWORD", "")
    if password:
        return password

    password_file = os.getenv("CLICKHOUSE_PASSWORD_FILE", "").strip()
    if not password_file:
        return ""

    try:
        with open(password_file, encoding="utf-8") as file:
            return file.read().strip()
    except OSError:
        return ""


@dataclass(frozen=True)
class AuditLogConfig:
    enabled: bool
    clickhouse_url: str
    database: str
    table: str
    username: str
    password: str
    timeout_seconds: float
    async_insert: bool
    wait_for_async_insert: bool
    wait_for_gamification_insert: bool
    meta_headers: tuple[str, ...]
    capture_body: bool
    max_body_bytes: int
    redact_keys: frozenset[str]

    @classmethod
    def from_env(cls) -> "AuditLogConfig":
        headers = tuple(
            header.strip().lower()
            for header in os.getenv("AUDIT_LOG_META_HEADERS", "user-agent").split(",")
            if header.strip()
        )
        return cls(
            enabled=_env_bool("AUDIT_LOG_ENABLED", True),
            clickhouse_url=os.getenv("CLICKHOUSE_URL", "http://127.0.0.1:8123").rstrip("/"),
            database=os.getenv("CLICKHOUSE_DATABASE", "default"),
            table=os.getenv("CLICKHOUSE_REQUEST_LOG_TABLE", "request_log"),
            username=os.getenv("CLICKHOUSE_USER", "default"),
            password=_read_password(),
            timeout_seconds=float(os.getenv("CLICKHOUSE_TIMEOUT_SECONDS", "1.5")),
            async_insert=_env_bool("CLICKHOUSE_ASYNC_INSERT", True),
            wait_for_async_insert=_env_bool("CLICKHOUSE_WAIT_FOR_ASYNC_INSERT", False),
            wait_for_gamification_insert=_env_bool("CLICKHOUSE_WAIT_FOR_GAMIFICATION_INSERT", False),
            meta_headers=headers,
            capture_body=_env_bool("AUDIT_LOG_CAPTURE_BODY", True),
            max_body_bytes=_env_int("AUDIT_LOG_MAX_BODY_BYTES", 32768),
            redact_keys=frozenset(
                key.strip().lower()
                for key in os.getenv(
                    "AUDIT_LOG_REDACT_KEYS",
                    "authorization,cookie,set-cookie,password,token,api_key,secret",
                ).split(",")
                if key.strip()
            ),
        )
