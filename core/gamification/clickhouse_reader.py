from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any

import httpx

from core.audit_log.config import AuditLogConfig
from core.gamification.periods import Period
from core.gamification.rules import EventCounts


@dataclass
class ClickHouseGamificationReader:
    config: AuditLogConfig

    async def read_event_counts(self, periods: list[Period], event_codes: set[str]) -> EventCounts:
        if not periods or not event_codes:
            return {}

        start_day = min(period.start_day for period in periods).isoformat()
        end_day = max(period.end_day for period in periods).isoformat()
        codes = ", ".join(_quote(code) for code in sorted(event_codes))
        query = f"""
SELECT
  user_id,
  period_day,
  event_code,
  countDistinct(event_instance_id) AS cnt
FROM {self.config.table}
WHERE period_day BETWEEN toDate('{start_day}') AND toDate('{end_day}')
  AND phase = 'response'
  AND success = 1
  AND event_code IN ({codes})
GROUP BY user_id, period_day, event_code
FORMAT JSONEachRow
""".strip()

        auth = None
        if self.config.username or self.config.password:
            auth = (self.config.username, self.config.password)

        async with httpx.AsyncClient(timeout=self.config.timeout_seconds) as client:
            response = await client.post(
                self.config.clickhouse_url,
                params={"database": self.config.database, "query": query},
                auth=auth,
            )
            response.raise_for_status()

        return _parse_rows(response.text)


def _parse_rows(raw: str) -> dict[str, dict[date, dict[str, int]]]:
    counts: dict[str, dict[date, dict[str, int]]] = {}
    for line in raw.splitlines():
        if not line.strip():
            continue
        row: dict[str, Any] = json.loads(line)
        user_id = str(row["user_id"])
        day = date.fromisoformat(str(row["period_day"]))
        event_code = str(row["event_code"])
        count = int(row["cnt"])
        counts.setdefault(user_id, {}).setdefault(day, {})[event_code] = count
    return counts


def _quote(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"
