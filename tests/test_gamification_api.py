from fastapi.testclient import TestClient

from app import app


client = TestClient(app)


class FakeGamificationStore:
    def __init__(self):
        self.created = []

    async def create_campaign(self, payload):
        self.created.append(("campaign", payload))
        return {"id": "campaign-1", **payload}

    async def create_mission(self, payload):
        self.created.append(("mission", payload))
        return {"id": "mission-1", **payload}

    async def create_requirement(self, payload):
        self.created.append(("requirement", payload))
        return {"id": "requirement-1", **payload}

    async def list_missions(self, period_type, user_id, period_key):
        return [
            {
                "mission_id": f"{period_type}-mission",
                "mission_code": f"{period_type}_core",
                "mission_name": f"{period_type} mission",
                "period_type": period_type,
                "period_key": period_key,
                "event_mission_id": f"{period_type}-req",
                "rule_type": "count" if period_type == "daily" else "meta_mission",
                "event_codes": ["prompt_sent"],
                "config": {},
                "progress": 1,
                "target": 2,
                "status": "in_progress",
                "points": 20,
                "points_awarded": 0,
                "progress_updated_at": None,
            }
        ]

    async def get_points(self, user_id, weekly_period_key):
        return {
            "user_id": user_id,
            "total_points": 160,
            "weekly_points": 160,
            "weekly_period_key": weekly_period_key,
        }

    async def get_progress(self, user_id):
        return [{"user_id": user_id, "period_key": "2026-07-05", "status": "completed"}]

    async def leaderboard(self, scope, period_key, limit):
        return [{"rank": 1, "user_id": "user-1", "points": 160, "period_key": period_key if scope == "weekly" else None}]

    async def dashboard(self, user_id, now):
        return {
            "user_id": user_id,
            "points": await self.get_points(user_id, "2026-W27"),
            "daily_missions": await self.list_missions("daily", user_id, "2026-07-05"),
            "weekly_missions": await self.list_missions("weekly", user_id, "2026-W27"),
        }


class FakeBackfillWorker:
    async def backfill(self, period_keys, mission_filter=None):
        class Summary:
            periods = period_keys
            users_seen = 1
            progress_rows_written = 2
            dirty_users = 1

        self.period_keys = period_keys
        self.mission_filter = mission_filter
        return Summary()


def setup_function():
    app.state.gamification_store = FakeGamificationStore()
    app.state.gamification_worker = FakeBackfillWorker()


def teardown_function():
    for name in ("gamification_store", "gamification_worker"):
        if hasattr(app.state, name):
            delattr(app.state, name)


def test_create_campaign_mission_and_requirement():
    campaign = client.post(
        "/api/v1/gamification/campaigns",
        json={"code": "camp", "name": "Campaign"},
    )
    assert campaign.status_code == 200
    assert campaign.json()["id"] == "campaign-1"

    mission = client.post(
        "/api/v1/gamification/missions",
        json={
            "campaign_id": "campaign-1",
            "code": "daily_core",
            "name": "Daily Core",
            "period_type": "daily",
        },
    )
    assert mission.status_code == 200
    assert mission.json()["period_type"] == "daily"

    requirement = client.post(
        "/api/v1/gamification/mission-requirements",
        json={
            "mission_id": "mission-1",
            "rule_type": "count",
            "event_codes": ["prompt_sent", "upload_doc"],
            "target": 2,
            "points": 20,
        },
    )
    assert requirement.status_code == 200
    assert requirement.json()["rule_type"] == "count"


def test_read_missions_points_progress_dashboard_and_leaderboard():
    headers = {"X-User-Id": "user-1"}

    daily = client.get("/api/v1/gamification/missions/daily?period_key=2026-07-05", headers=headers)
    assert daily.status_code == 200
    assert daily.json()["missions"][0]["progress"] == 1

    weekly = client.get("/api/v1/gamification/missions/weekly?period_key=2026-W27", headers=headers)
    assert weekly.status_code == 200
    assert weekly.json()["missions"][0]["rule_type"] == "meta_mission"

    points = client.get("/api/v1/gamification/me/points", headers=headers)
    assert points.status_code == 200
    assert points.json()["total_points"] == 160

    progress = client.get("/api/v1/gamification/me/progress", headers=headers)
    assert progress.status_code == 200
    assert progress.json()["items"][0]["status"] == "completed"

    dashboard = client.get("/api/v1/gamification/me/dashboard", headers=headers)
    assert dashboard.status_code == 200
    assert len(dashboard.json()["daily_missions"]) == 1

    leaderboard = client.get("/api/v1/gamification/leaderboard?scope=weekly&period_key=2026-W27")
    assert leaderboard.status_code == 200
    assert leaderboard.json()["entries"][0]["user_id"] == "user-1"


def test_backfill_endpoint_calls_worker():
    response = client.post(
        "/api/v1/gamification/backfill",
        json={"period_keys": ["2026-07-05", "2026-W27"], "mission_filter": ["daily_core"]},
    )

    assert response.status_code == 200
    assert response.json() == {
        "periods": ["2026-07-05", "2026-W27"],
        "users_seen": 1,
        "progress_rows_written": 2,
        "dirty_users": 1,
    }


def test_create_campaign_with_iso_datetimes():
    campaign = client.post(
        "/api/v1/gamification/campaigns",
        json={
            "code": "camp_with_dates",
            "name": "Campaign with ISO dates",
            "starts_at": "2026-01-01T00:00:00Z",
            "ends_at": "2026-12-31T23:59:59Z",
        },
    )
    assert campaign.status_code == 200
    res = campaign.json()
    assert res["id"] == "campaign-1"
    assert "2026-01-01T00:00:00" in res["starts_at"]
    assert "2026-12-31T23:59:59" in res["ends_at"]
