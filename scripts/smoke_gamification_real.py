import asyncio
import json
import os
import uuid
from datetime import date, datetime
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

import asyncpg
import httpx
from dotenv import load_dotenv
from fastapi.testclient import TestClient

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("TESTING", "1")

from app import app
from core.gamification.periods import period_key_week


async def _run_migration(database_url: str) -> None:
    sql = (ROOT / "scripts" / "postgres_gamification_schema.sql").read_text(encoding="utf-8")
    conn = await asyncpg.connect(database_url)
    try:
        await conn.execute(sql)
    finally:
        await conn.close()


async def _ensure_user(database_url: str, user_id: str) -> None:
    conn = await asyncpg.connect(database_url)
    try:
        await conn.execute(
            "INSERT INTO users (id) VALUES ($1) ON CONFLICT (id) DO NOTHING",
            uuid.UUID(user_id),
        )
    finally:
        await conn.close()


async def _insert_clickhouse_events(user_id: str, day: date, codes: list[str]) -> None:
    clickhouse_url = os.getenv("CLICKHOUSE_URL", "http://127.0.0.1:8123").rstrip("/")
    database = os.getenv("CLICKHOUSE_DATABASE", "default")
    table = os.getenv("CLICKHOUSE_REQUEST_LOG_TABLE", "request_log")
    username = os.getenv("CLICKHOUSE_USER", "default")
    password = os.getenv("CLICKHOUSE_PASSWORD", "")
    auth = (username, password) if username or password else None
    occurred_at = datetime.combine(day, datetime.min.time(), tzinfo=VN_TZ).replace(hour=10)
    rows = []
    for code in codes:
        request_id = str(uuid.uuid4())
        rows.append(
            {
                "log_id": str(uuid.uuid4()),
                "request_id": request_id,
                "phase": "response",
                "user_id": user_id,
                "method": "POST",
                "route": f"/smoke/{code}",
                "path": f"/smoke/{code}",
                "status_code": 200,
                "success": 1,
                "event_code": code,
                "event_instance_id": request_id,
                "occurred_at": occurred_at.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
                "period_day": day.isoformat(),
                "latency_ms": 10,
                "meta": {},
            }
        )

    payload = "\n".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) for row in rows) + "\n"
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            clickhouse_url,
            params={
                "database": database,
                "query": f"INSERT INTO {table} FORMAT JSONEachRow",
                "wait_for_async_insert": 1,
            },
            content=payload.encode("utf-8"),
            auth=auth,
            headers={"Content-Type": "application/x-ndjson"},
        )
        response.raise_for_status()


async def main() -> None:
    load_dotenv()
    database_url = os.environ["DATABASE_URL"]
    today = datetime.now(tz=VN_TZ).date()
    day_key = today.isoformat()
    week_key = period_key_week(today)
    run_id = uuid.uuid4().hex[:8]
    user_id = str(uuid.uuid4())
    event_codes = ["prompt_sent", "upload_doc", "summarize", "find_key_points"]

    await _run_migration(database_url)
    await _ensure_user(database_url, user_id)
    await _insert_clickhouse_events(user_id, today, event_codes)

    for attr in ("gamification_store", "gamification_worker", "postgres_pool"):
        if hasattr(app.state, attr):
            delattr(app.state, attr)

    with TestClient(app) as client:
        campaign = client.post(
            "/api/v1/gamification/campaigns",
            json={"code": f"smoke_campaign_{run_id}", "name": "Smoke Campaign"},
        )
        campaign.raise_for_status()
        campaign_id = campaign.json()["id"]

        daily = client.post(
            "/api/v1/gamification/missions",
            json={
                "campaign_id": campaign_id,
                "code": f"smoke_daily_{run_id}",
                "name": "Smoke Daily",
                "period_type": "daily",
                "sort_order": 10,
            },
        )
        daily.raise_for_status()
        daily_id = daily.json()["id"]

        weekly = client.post(
            "/api/v1/gamification/missions",
            json={
                "campaign_id": campaign_id,
                "code": f"smoke_weekly_{run_id}",
                "name": "Smoke Weekly",
                "period_type": "weekly",
                "sort_order": 20,
            },
        )
        weekly.raise_for_status()
        weekly_id = weekly.json()["id"]

        daily_req = client.post(
            "/api/v1/gamification/mission-requirements",
            json={
                "mission_id": daily_id,
                "rule_type": "count",
                "event_codes": event_codes,
                "target": 4,
                "points": 40,
                "sort_order": 10,
            },
        )
        daily_req.raise_for_status()

        weekly_req = client.post(
            "/api/v1/gamification/mission-requirements",
            json={
                "mission_id": weekly_id,
                "rule_type": "meta_mission",
                "target": 1,
                "points": 120,
                "sort_order": 20,
                "config": {"source_mission_codes": [f"smoke_daily_{run_id}"]},
            },
        )
        weekly_req.raise_for_status()

        backfill = client.post(
            "/api/v1/gamification/backfill",
            json={"period_keys": [day_key, week_key], "mission_filter": [f"smoke_daily_{run_id}", f"smoke_weekly_{run_id}"]},
        )
        backfill.raise_for_status()

        headers = {"X-User-Id": user_id}
        daily_read = client.get(f"/api/v1/gamification/missions/daily?period_key={day_key}", headers=headers)
        daily_read.raise_for_status()
        weekly_read = client.get(f"/api/v1/gamification/missions/weekly?period_key={week_key}", headers=headers)
        weekly_read.raise_for_status()
        points = client.get("/api/v1/gamification/me/points", headers=headers)
        points.raise_for_status()
        leaderboard = client.get(f"/api/v1/gamification/leaderboard?scope=weekly&period_key={week_key}")
        leaderboard.raise_for_status()

    result = {
        "run_id": run_id,
        "user_id": user_id,
        "day_key": day_key,
        "week_key": week_key,
        "backfill": backfill.json(),
        "daily_status": next(item for item in daily_read.json()["missions"] if item["mission_code"] == f"smoke_daily_{run_id}")["status"],
        "weekly_status": next(item for item in weekly_read.json()["missions"] if item["mission_code"] == f"smoke_weekly_{run_id}")["status"],
        "points": points.json(),
        "leaderboard_has_user": any(entry["user_id"] == user_id for entry in leaderboard.json()["entries"]),
    }
    assert result["daily_status"] == "completed", result
    assert result["weekly_status"] == "completed", result
    assert result["points"]["total_points"] >= 160, result
    assert result["leaderboard_has_user"] is True, result
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
