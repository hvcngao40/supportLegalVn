from datetime import date

from fastapi.testclient import TestClient

from app import app
from core.gamification.periods import period_key_week
from core.gamification.worker import GamificationSweepWorker, MissionRequirement, ProgressWrite


client = TestClient(app)


class FakeClickHouseAggregateReader:
    def __init__(self):
        self.calls = []
        self.counts = {
            "user-1": {
                date(2026, 7, 5): {
                    "prompt_sent": 1,
                    "upload_doc": 1,
                    "summarize": 1,
                    "find_key_points": 1,
                }
            }
        }

    async def read_event_counts(self, periods, event_codes):
        self.calls.append({"periods": [period.key for period in periods], "event_codes": event_codes})
        return self.counts


class InMemoryGamificationStore:
    def __init__(self):
        self.campaigns = {}
        self.missions = {}
        self.requirements = {}
        self.progress = {}
        self.total_points = {}
        self.weekly_points = {}

    async def create_campaign(self, payload):
        row = {"id": f"campaign-{len(self.campaigns) + 1}", **payload}
        self.campaigns[row["id"]] = row
        return row

    async def create_mission(self, payload):
        row = {"id": f"mission-{len(self.missions) + 1}", **payload}
        self.missions[row["id"]] = row
        return row

    async def create_requirement(self, payload):
        row = {"id": f"requirement-{len(self.requirements) + 1}", **payload}
        self.requirements[row["id"]] = row
        return row

    async def fetch_active_requirements(self, period_type):
        result = []
        for requirement_id, requirement in self.requirements.items():
            mission = self.missions[requirement["mission_id"]]
            if mission["period_type"] != period_type:
                continue
            result.append(
                MissionRequirement(
                    event_mission_id=requirement_id,
                    mission_id=requirement["mission_id"],
                    mission_code=mission["code"],
                    period_type=period_type,
                    rule_type=requirement["rule_type"],
                    event_codes=tuple(requirement.get("event_codes") or []),
                    target=requirement["target"],
                    points=requirement.get("points", 0),
                    config=requirement.get("config") or {},
                )
            )
        return result

    async def upsert_user_progress(self, write: ProgressWrite):
        key = (write.user_id, write.event_mission_id, write.period_key)
        value = {
            "user_id": write.user_id,
            "event_mission_id": write.event_mission_id,
            "mission_id": write.mission_id,
            "period_key": write.period_key,
            "progress": write.progress,
            "target": write.target,
            "status": write.status,
            "points_awarded": write.points_awarded,
        }
        changed = self.progress.get(key) != value
        self.progress[key] = value
        return changed

    async def completed_daily_missions(self, user_id, week_period_key, mission_codes):
        wanted = set(mission_codes or [])
        count = 0
        for row in self.progress.values():
            mission = self.missions[row["mission_id"]]
            if row["user_id"] != user_id or mission["period_type"] != "daily":
                continue
            if row["status"] != "completed":
                continue
            if period_key_week(date.fromisoformat(row["period_key"])) != week_period_key:
                continue
            if wanted and mission["code"] not in wanted:
                continue
            count += 1
        return count

    async def recompute_user_points(self, user_ids):
        for user_id in user_ids:
            self.total_points[user_id] = sum(
                row["points_awarded"]
                for row in self.progress.values()
                if row["user_id"] == user_id
            )

    async def recompute_user_weekly_points(self, user_ids, week_keys):
        for user_id in user_ids:
            for week_key in week_keys:
                self.weekly_points[(user_id, week_key)] = sum(
                    row["points_awarded"]
                    for row in self.progress.values()
                    if row["user_id"] == user_id
                )

    async def refresh_leaderboard(self):
        return None

    async def list_missions(self, period_type, user_id, period_key):
        rows = []
        for requirement_id, requirement in self.requirements.items():
            mission = self.missions[requirement["mission_id"]]
            if mission["period_type"] != period_type:
                continue
            progress = self.progress.get((user_id, requirement_id, period_key), {})
            rows.append(
                {
                    "mission_id": mission["id"],
                    "mission_code": mission["code"],
                    "mission_name": mission["name"],
                    "period_type": period_type,
                    "period_key": period_key,
                    "event_mission_id": requirement_id,
                    "rule_type": requirement["rule_type"],
                    "event_codes": requirement.get("event_codes") or [],
                    "config": requirement.get("config") or {},
                    "progress": progress.get("progress", 0),
                    "target": requirement["target"],
                    "status": progress.get("status", "in_progress"),
                    "points": requirement.get("points", 0),
                    "points_awarded": progress.get("points_awarded", 0),
                    "progress_updated_at": None,
                }
            )
        return rows

    async def get_points(self, user_id, weekly_period_key):
        return {
            "user_id": user_id,
            "total_points": self.total_points.get(user_id, 0),
            "weekly_points": self.weekly_points.get((user_id, weekly_period_key), 0),
            "weekly_period_key": weekly_period_key,
        }

    async def get_progress(self, user_id):
        return [row for row in self.progress.values() if row["user_id"] == user_id]

    async def leaderboard(self, scope, period_key, limit):
        source = (
            {user_id: points for (user_id, key), points in self.weekly_points.items() if key == period_key}
            if scope == "weekly"
            else self.total_points
        )
        ordered = sorted(source.items(), key=lambda item: (-item[1], item[0]))[:limit]
        return [
            {"rank": index + 1, "user_id": user_id, "points": points, "period_key": period_key if scope == "weekly" else None}
            for index, (user_id, points) in enumerate(ordered)
        ]

    async def dashboard(self, user_id, now):
        return {
            "user_id": user_id,
            "points": await self.get_points(user_id, "2026-W27"),
            "daily_missions": await self.list_missions("daily", user_id, "2026-07-05"),
            "weekly_missions": await self.list_missions("weekly", user_id, "2026-W27"),
        }


def setup_function():
    store = InMemoryGamificationStore()
    reader = FakeClickHouseAggregateReader()
    app.state.gamification_store = store
    app.state.gamification_worker = GamificationSweepWorker(reader, store)
    app.state.fake_clickhouse_reader = reader


def teardown_function():
    for name in ("gamification_store", "gamification_worker", "fake_clickhouse_reader"):
        if hasattr(app.state, name):
            delattr(app.state, name)


def test_full_flow_create_backfill_read_leaderboard_and_progress():
    campaign = client.post(
        "/api/v1/gamification/campaigns",
        json={"code": "gamification_mvp", "name": "Gamification MVP"},
    ).json()
    daily = client.post(
        "/api/v1/gamification/missions",
        json={
            "campaign_id": campaign["id"],
            "code": "daily_core_actions",
            "name": "Daily Core Actions",
            "period_type": "daily",
        },
    ).json()
    weekly = client.post(
        "/api/v1/gamification/missions",
        json={
            "campaign_id": campaign["id"],
            "code": "weekly_daily_finisher",
            "name": "Weekly Finisher",
            "period_type": "weekly",
        },
    ).json()
    client.post(
        "/api/v1/gamification/mission-requirements",
        json={
            "mission_id": daily["id"],
            "rule_type": "count",
            "event_codes": ["prompt_sent", "upload_doc", "summarize", "find_key_points"],
            "target": 4,
            "points": 40,
        },
    )
    client.post(
        "/api/v1/gamification/mission-requirements",
        json={
            "mission_id": weekly["id"],
            "rule_type": "meta_mission",
            "target": 1,
            "points": 120,
            "config": {"source_mission_codes": ["daily_core_actions"]},
        },
    )

    backfill = client.post(
        "/api/v1/gamification/backfill",
        json={"period_keys": ["2026-07-05", "2026-W27"]},
    )
    assert backfill.status_code == 200
    assert backfill.json()["dirty_users"] == 1
    assert app.state.fake_clickhouse_reader.calls[0]["periods"] == ["2026-07-05", "2026-W27"]

    second_backfill = client.post(
        "/api/v1/gamification/backfill",
        json={"period_keys": ["2026-07-05", "2026-W27"]},
    )
    assert second_backfill.status_code == 200
    assert second_backfill.json()["dirty_users"] == 0

    headers = {"X-User-Id": "user-1"}
    daily_progress = client.get(
        "/api/v1/gamification/missions/daily?period_key=2026-07-05",
        headers=headers,
    ).json()
    weekly_progress = client.get(
        "/api/v1/gamification/missions/weekly?period_key=2026-W27",
        headers=headers,
    ).json()
    leaderboard = client.get("/api/v1/gamification/leaderboard?scope=weekly&period_key=2026-W27").json()
    points = client.get("/api/v1/gamification/me/points", headers=headers).json()

    assert daily_progress["missions"][0]["status"] == "completed"
    assert weekly_progress["missions"][0]["status"] == "completed"
    assert leaderboard["entries"][0]["points"] == 160
    assert points["total_points"] == 160
