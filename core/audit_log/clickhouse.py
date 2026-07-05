import json
import logging
from typing import Any

import httpx

from core.audit_log.config import AuditLogConfig

logger = logging.getLogger(__name__)


class ClickHouseAuditWriter:
    def __init__(self, config: AuditLogConfig) -> None:
        self._config = config
        self._disabled_reason = ""

    async def insert_row(self, row: dict[str, Any], *, wait_for_async_insert: bool | None = None) -> None:
        if not self._config.enabled or self._disabled_reason:
            return

        settings = {
            "database": self._config.database,
            "async_insert": int(self._config.async_insert),
            "wait_for_async_insert": int(
                self._config.wait_for_async_insert
                if wait_for_async_insert is None
                else wait_for_async_insert
            ),
        }
        query = f"INSERT INTO {self._config.table} FORMAT JSONEachRow"
        payload = json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
        auth = None
        if self._config.username or self._config.password:
            auth = (self._config.username, self._config.password)

        try:
            async with httpx.AsyncClient(timeout=self._config.timeout_seconds) as client:
                response = await client.post(
                    self._config.clickhouse_url,
                    params={**settings, "query": query},
                    content=payload.encode("utf-8"),
                    auth=auth,
                    headers={"Content-Type": "application/x-ndjson"},
                )
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            body = _truncate_response_body(exc.response.text)
            if status_code in {401, 403}:
                self._disabled_reason = f"ClickHouse rejected audit log credentials with HTTP {status_code}"
                logger.error(
                    "%s. Audit logging is disabled for this process until restart. "
                    "Set CLICKHOUSE_USER/CLICKHOUSE_PASSWORD or CLICKHOUSE_PASSWORD_FILE, "
                    "and make sure the user can INSERT into %s.%s. Response body: %s",
                    self._disabled_reason,
                    self._config.database,
                    self._config.table,
                    body,
                )
                return

            logger.warning(
                "Failed to write audit log row to ClickHouse: HTTP %s. Response body: %s",
                status_code,
                body,
            )
        except httpx.RequestError:
            logger.warning("Failed to connect to ClickHouse for audit logging", exc_info=True)
        except Exception:
            logger.warning("Unexpected failure while writing audit log row to ClickHouse", exc_info=True)


def _truncate_response_body(body: str, limit: int = 800) -> str:
    compact = " ".join(body.split())
    if len(compact) <= limit:
        return compact
    return compact[:limit] + "..."
