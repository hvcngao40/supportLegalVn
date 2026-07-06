from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Sequence

from core.gamification.periods import period_key_day, period_key_week
from core.gamification.worker import MissionRequirement, ProgressWrite


@dataclass
class PostgresGamificationStore:
    pool: Any

    async def create_campaign(self, payload: dict[str, Any]) -> dict[str, Any]:
        starts_at = payload.get("starts_at")
        if isinstance(starts_at, str):
            starts_at = datetime.fromisoformat(starts_at.replace("Z", "+00:00"))
        ends_at = payload.get("ends_at")
        if isinstance(ends_at, str):
            ends_at = datetime.fromisoformat(ends_at.replace("Z", "+00:00"))

        row = await self.pool.fetchrow(
            """
INSERT INTO campaign (code, name, starts_at, ends_at, is_active)
VALUES ($1, $2, COALESCE($3::timestamptz, now()), COALESCE($4::timestamptz, now() + interval '10 years'), COALESCE($5, true))
ON CONFLICT (code) DO UPDATE
  SET name = EXCLUDED.name,
      starts_at = EXCLUDED.starts_at,
      ends_at = EXCLUDED.ends_at,
      is_active = EXCLUDED.is_active
RETURNING id, code, name, starts_at, ends_at, is_active
""",
            payload["code"],
            payload["name"],
            starts_at,
            ends_at,
            payload.get("is_active", True),
        )
        return _row(row)

    async def create_mission(self, payload: dict[str, Any]) -> dict[str, Any]:
        row = await self.pool.fetchrow(
            """
INSERT INTO mission (campaign_id, code, name, period_type, is_active, sort_order)
VALUES ($1, $2, $3, $4, COALESCE($5, true), COALESCE($6, 0))
ON CONFLICT (code) DO UPDATE
  SET campaign_id = EXCLUDED.campaign_id,
      name = EXCLUDED.name,
      period_type = EXCLUDED.period_type,
      is_active = EXCLUDED.is_active,
      sort_order = EXCLUDED.sort_order
RETURNING id, campaign_id, code, name, period_type, is_active, sort_order
""",
            payload["campaign_id"],
            payload["code"],
            payload["name"],
            payload["period_type"],
            payload.get("is_active", True),
            payload.get("sort_order", 0),
        )
        return _row(row)

    async def create_requirement(self, payload: dict[str, Any]) -> dict[str, Any]:
        row = await self.pool.fetchrow(
            """
INSERT INTO event_mission (mission_id, event_id, target, points, sort_order, rule_type, event_codes, config)
VALUES ($1, $2, $3, $4, COALESCE($5, 0), $6, $7, $8::jsonb)
ON CONFLICT (mission_id, sort_order) DO UPDATE
  SET event_id = EXCLUDED.event_id,
      target = EXCLUDED.target,
      points = EXCLUDED.points,
      rule_type = EXCLUDED.rule_type,
      event_codes = EXCLUDED.event_codes,
      config = EXCLUDED.config
RETURNING id, mission_id, event_id, target, points, sort_order, rule_type, event_codes, config
""",
            payload["mission_id"],
            payload.get("event_id"),
            payload["target"],
            payload.get("points", 0),
            payload.get("sort_order", 0),
            payload["rule_type"],
            payload.get("event_codes", []),
            json.dumps(payload.get("config", {})),
        )
        return _row(row)

    async def list_missions(self, period_type: str, user_id: str, period_key: str) -> list[dict[str, Any]]:
        rows = await self.pool.fetch(
            """
SELECT
  m.id AS mission_id,
  m.code AS mission_code,
  m.name AS mission_name,
  m.period_type,
  em.id AS event_mission_id,
  em.rule_type,
  em.event_codes,
  em.config,
  em.target,
  em.points,
  COALESCE(up.progress, 0) AS progress,
  COALESCE(up.status, 'in_progress') AS status,
  COALESCE(up.points_awarded, 0) AS points_awarded,
  up.updated_at AS progress_updated_at
FROM mission m
JOIN campaign c ON c.id = m.campaign_id
JOIN event_mission em ON em.mission_id = m.id
LEFT JOIN user_progress up
  ON up.event_mission_id = em.id
 AND up.user_id = $2
 AND up.period_key = $3
WHERE m.period_type = $1
  AND m.is_active = true
  AND c.is_active = true
  AND now() BETWEEN c.starts_at AND c.ends_at
ORDER BY m.sort_order, em.sort_order, m.code
""",
            period_type,
            user_id,
            period_key,
        )
        return [_mission_row(row, period_key) for row in rows]

    async def get_points(self, user_id: str, weekly_period_key: str) -> dict[str, Any]:
        total = await self.pool.fetchval(
            "SELECT COALESCE(total_points, 0) FROM user_point WHERE user_id = $1",
            user_id,
        )
        weekly = await self.pool.fetchval(
            "SELECT COALESCE(points, 0) FROM user_point_weekly WHERE user_id = $1 AND period_key = $2",
            user_id,
            weekly_period_key,
        )
        return {
            "user_id": user_id,
            "total_points": int(total or 0),
            "weekly_points": int(weekly or 0),
            "weekly_period_key": weekly_period_key,
        }

    async def get_progress(self, user_id: str) -> list[dict[str, Any]]:
        rows = await self.pool.fetch(
            """
SELECT
  up.user_id,
  up.period_key,
  up.progress,
  up.target,
  up.status,
  up.points_awarded,
  up.updated_at,
  m.id AS mission_id,
  m.code AS mission_code,
  m.name AS mission_name,
  m.period_type,
  em.id AS event_mission_id,
  em.rule_type,
  em.event_codes,
  em.config
FROM user_progress up
JOIN mission m ON m.id = up.mission_id
JOIN event_mission em ON em.id = up.event_mission_id
WHERE up.user_id = $1
ORDER BY up.period_key DESC, m.period_type, m.sort_order, em.sort_order
""",
            user_id,
        )
        return [_progress_row(row) for row in rows]

    async def leaderboard(self, scope: str, period_key: str, limit: int) -> list[dict[str, Any]]:
        if scope == "weekly":
            rows = await self.pool.fetch(
                """
SELECT user_id, points
FROM user_point_weekly
WHERE period_key = $1
ORDER BY points DESC, user_id
LIMIT $2
""",
                period_key,
                limit,
            )
            return [
                {"rank": index + 1, "user_id": str(row["user_id"]), "points": int(row["points"]), "period_key": period_key}
                for index, row in enumerate(rows)
            ]

        rows = await self.pool.fetch(
            """
SELECT user_id, total_points AS points
FROM user_point
ORDER BY total_points DESC, user_id
LIMIT $1
""",
            limit,
        )
        return [
            {"rank": index + 1, "user_id": str(row["user_id"]), "points": int(row["points"]), "period_key": None}
            for index, row in enumerate(rows)
        ]

    async def dashboard(self, user_id: str, now: Any) -> dict[str, Any]:
        day_key = period_key_day(now)
        week_key = period_key_week(now)
        return {
            "user_id": user_id,
            "points": await self.get_points(user_id, week_key),
            "daily_missions": await self.list_missions("daily", user_id, day_key),
            "weekly_missions": await self.list_missions("weekly", user_id, week_key),
        }

    async def fetch_active_requirements(self, period_type: str) -> list[MissionRequirement]:
        rows = await self.pool.fetch(
            """
SELECT
  em.id AS event_mission_id,
  m.id AS mission_id,
  m.code AS mission_code,
  m.period_type,
  em.rule_type,
  em.event_codes,
  em.target,
  em.points,
  em.config
FROM event_mission em
JOIN mission m ON m.id = em.mission_id
JOIN campaign c ON c.id = m.campaign_id
WHERE m.period_type = $1
  AND m.is_active = true
  AND c.is_active = true
  AND now() BETWEEN c.starts_at AND c.ends_at
ORDER BY m.period_type, m.code, em.sort_order, em.id
""",
            period_type,
        )
        return [
            MissionRequirement(
                event_mission_id=str(row["event_mission_id"]),
                mission_id=str(row["mission_id"]),
                mission_code=str(row["mission_code"]),
                period_type=str(row["period_type"]),
                rule_type=str(row["rule_type"]),
                event_codes=tuple(str(code) for code in (row["event_codes"] or [])),
                target=int(row["target"]),
                points=int(row["points"]),
                config=_jsonb(row["config"]),
            )
            for row in rows
        ]

    async def upsert_user_progress(self, write: ProgressWrite) -> bool:
        row = await self.pool.fetchrow(
            """
INSERT INTO user_progress (
  user_id, event_mission_id, mission_id, period_key,
  progress, target, status, points_awarded, updated_at
)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, now())
ON CONFLICT (user_id, event_mission_id, period_key)
DO UPDATE SET
  progress = EXCLUDED.progress,
  target = EXCLUDED.target,
  status = EXCLUDED.status,
  points_awarded = EXCLUDED.points_awarded,
  updated_at = now()
WHERE
  user_progress.progress IS DISTINCT FROM EXCLUDED.progress OR
  user_progress.target IS DISTINCT FROM EXCLUDED.target OR
  user_progress.status IS DISTINCT FROM EXCLUDED.status OR
  user_progress.points_awarded IS DISTINCT FROM EXCLUDED.points_awarded
RETURNING 1
""",
            write.user_id,
            write.event_mission_id,
            write.mission_id,
            write.period_key,
            write.progress,
            write.target,
            write.status,
            write.points_awarded,
        )
        return row is not None

    async def completed_daily_missions(
        self,
        user_id: str,
        week_period_key: str,
        mission_codes: Sequence[str] | None,
    ) -> int:
        mission_filter = list(mission_codes or [])
        week_start, week_end = _week_day_range(week_period_key)
        return int(
            await self.pool.fetchval(
                """
SELECT count(DISTINCT m.code)
FROM user_progress up
JOIN mission m ON m.id = up.mission_id
WHERE up.user_id = $1
  AND m.period_type = 'daily'
  AND up.status = 'completed'
  AND up.period_key BETWEEN $2 AND $3
  AND (cardinality($4::text[]) = 0 OR m.code = ANY($4::text[]))
""",
                user_id,
                week_start.isoformat(),
                week_end.isoformat(),
                mission_filter,
            )
            or 0
        )

    async def recompute_user_points(self, user_ids: set[str]) -> None:
        if not user_ids:
            return
        await self.pool.execute(
            """
INSERT INTO user_point (user_id, total_points, updated_at)
SELECT up.user_id, COALESCE(SUM(up.points_awarded), 0)::integer, now()
FROM user_progress up
WHERE up.user_id = ANY($1::uuid[])
GROUP BY up.user_id
ON CONFLICT (user_id)
DO UPDATE SET total_points = EXCLUDED.total_points, updated_at = now()
""",
            list(user_ids),
        )

    async def recompute_user_weekly_points(self, user_ids: set[str], week_keys: set[str]) -> None:
        if not user_ids or not week_keys:
            return
        await self.pool.execute(
            """
INSERT INTO user_point_weekly (user_id, period_key, points, updated_at)
SELECT
  weekly.user_id,
  weekly.period_key,
  COALESCE(SUM(weekly.points_awarded), 0)::integer AS points,
  now()
FROM (
  SELECT
    up.user_id,
    CASE
      WHEN m.period_type = 'weekly' THEN up.period_key
    ELSE to_char(to_date(up.period_key, 'YYYY-MM-DD'), 'IYYY-"W"IW')
    END AS period_key,
    up.points_awarded
  FROM user_progress up
  JOIN mission m ON m.id = up.mission_id
  WHERE up.user_id = ANY($1::uuid[])
    AND (
      m.period_type = 'weekly'
      OR (m.period_type = 'daily' AND up.period_key ~ '^\\d{4}-\\d{2}-\\d{2}$')
    )
) weekly
WHERE weekly.period_key IS NOT NULL
  AND weekly.period_key = ANY($2::text[])
GROUP BY weekly.user_id, weekly.period_key
ON CONFLICT (user_id, period_key)
DO UPDATE SET points = EXCLUDED.points, updated_at = now()
""",
            list(user_ids),
            list(week_keys),
        )

    async def refresh_leaderboard(self) -> None:
        return None


def _jsonb(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        return json.loads(value)
    return dict(value)


def _row(row: Any) -> dict[str, Any]:
    return {key: _serialize(value) for key, value in dict(row).items()}


def _mission_row(row: Any, period_key: str) -> dict[str, Any]:
    data = dict(row)
    return {
        "mission_id": str(data["mission_id"]),
        "mission_code": data["mission_code"],
        "mission_name": data["mission_name"],
        "period_type": data["period_type"],
        "period_key": period_key,
        "event_mission_id": str(data["event_mission_id"]),
        "rule_type": data["rule_type"],
        "event_codes": list(data["event_codes"] or []),
        "config": _jsonb(data["config"]),
        "progress": int(data["progress"]),
        "target": int(data["target"]),
        "status": data["status"],
        "points": int(data["points"]),
        "points_awarded": int(data["points_awarded"]),
        "progress_updated_at": _serialize(data["progress_updated_at"]),
    }


def _progress_row(row: Any) -> dict[str, Any]:
    data = dict(row)
    return {
        "user_id": str(data["user_id"]),
        "period_key": data["period_key"],
        "progress": int(data["progress"]),
        "target": int(data["target"]),
        "status": data["status"],
        "points_awarded": int(data["points_awarded"]),
        "updated_at": _serialize(data["updated_at"]),
        "mission": {
            "id": str(data["mission_id"]),
            "code": data["mission_code"],
            "name": data["mission_name"],
            "period_type": data["period_type"],
        },
        "requirement": {
            "id": str(data["event_mission_id"]),
            "rule_type": data["rule_type"],
            "event_codes": list(data["event_codes"] or []),
            "config": _jsonb(data["config"]),
        },
    }


def _serialize(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value) if value.__class__.__name__ == "UUID" else value


def _week_day_range(week_period_key: str) -> tuple[date, date]:
    year_raw, week_raw = week_period_key.split("-W", 1)
    start = date.fromisocalendar(int(year_raw), int(week_raw), 1)
    return start, date.fromisocalendar(int(year_raw), int(week_raw), 7)
