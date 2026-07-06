from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from core.gamification.worker import GamificationSweepWorker, MissionRequirement, ProgressWrite


VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


class FakeEventReader:
    def __init__(self, counts):
        self.counts = counts
        self.calls = []

    async def read_event_counts(self, periods, event_codes):
        self.calls.append((periods, event_codes))
        return self.counts


class FakeStateStore:
    def __init__(self):
        self.requirements = {
            "daily": [
                MissionRequirement(
                    event_mission_id="daily-req",
                    mission_id="daily-mission",
                    mission_code="daily_core_actions",
                    period_type="daily",
                    rule_type="count",
                    event_codes=("prompt_sent", "upload_doc", "summarize", "find_key_points"),
                    target=4,
                    points=40,
                    config={},
                )
            ],
            "weekly": [
                MissionRequirement(
                    event_mission_id="weekly-req",
                    mission_id="weekly-mission",
                    mission_code="weekly_daily_finisher",
                    period_type="weekly",
                    rule_type="meta_mission",
                    event_codes=(),
                    target=1,
                    points=120,
                    config={"source_mission_codes": ["daily_core_actions"]},
                )
            ],
        }
        self.progress = {}
        self.total_points = {}
        self.weekly_points = {}
        self.refresh_count = 0

    async def fetch_active_requirements(self, period_type):
        return self.requirements[period_type]

    async def upsert_user_progress(self, write: ProgressWrite):
        key = (write.user_id, write.event_mission_id, write.period_key)
        value = (
            write.mission_id,
            write.progress,
            write.target,
            write.status,
            write.points_awarded,
        )
        changed = self.progress.get(key) != value
        self.progress[key] = value
        return changed

    async def completed_daily_missions(self, user_id, week_period_key, mission_codes):
        return sum(
            1
            for (progress_user_id, event_mission_id, period_key), value in self.progress.items()
            if progress_user_id == user_id
            and event_mission_id == "daily-req"
            and period_key.startswith("2026-07-")
            and value[3] == "completed"
        )

    async def recompute_user_points(self, user_ids):
        for user_id in user_ids:
            self.total_points[user_id] = sum(
                value[4]
                for (progress_user_id, _, _), value in self.progress.items()
                if progress_user_id == user_id
            )

    async def recompute_user_weekly_points(self, user_ids, week_keys):
        for user_id in user_ids:
            for week_key in week_keys:
                self.weekly_points[(user_id, week_key)] = sum(
                    value[4]
                    for (progress_user_id, _, _), value in self.progress.items()
                    if progress_user_id == user_id
                )

    async def refresh_leaderboard(self):
        self.refresh_count += 1


@pytest.mark.asyncio
async def test_sweep_updates_daily_before_weekly_and_is_idempotent():
    reader = FakeEventReader(
        {
            "user-1": {
                date(2026, 7, 5): {
                    "prompt_sent": 1,
                    "upload_doc": 1,
                    "summarize": 1,
                    "find_key_points": 1,
                }
            }
        }
    )
    store = FakeStateStore()
    worker = GamificationSweepWorker(reader, store)
    now = datetime(2026, 7, 5, 12, 0, tzinfo=VN_TZ)

    first = await worker.sweep(now=now)
    second = await worker.sweep(now=now)

    assert len(reader.calls) == 2
    assert first.dirty_users == 1
    assert second.dirty_users == 0
    assert store.progress[("user-1", "daily-req", "2026-07-05")][3:] == ("completed", 40)
    assert store.progress[("user-1", "weekly-req", "2026-W27")][3:] == ("completed", 120)
    assert store.total_points["user-1"] == 160
    assert store.refresh_count == 1
