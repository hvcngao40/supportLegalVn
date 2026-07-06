from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from core.gamification.rules import (
    CountRuleHandler,
    DistinctDaysRuleHandler,
    InMemoryRuleContext,
    MetaMissionRuleHandler,
    StreakRuleHandler,
)


VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def _ctx(**overrides):
    base = {
        "user_id": "user-1",
        "period_key": "2026-07-05",
        "period_start": datetime(2026, 7, 1, tzinfo=VN_TZ),
        "period_end": datetime(2026, 7, 8, tzinfo=VN_TZ),
        "target": 1,
        "event_codes": ("prompt_sent",),
        "config": {},
        "event_counts": {},
    }
    base.update(overrides)
    return InMemoryRuleContext(**base)


@pytest.mark.asyncio
async def test_count_or_group_uses_deduped_clickhouse_counts():
    ctx = _ctx(
        target=3,
        event_codes=("prompt_sent", "upload_doc"),
        event_counts={
            "user-1": {
                date(2026, 7, 1): {
                    "prompt_sent": 1,
                    "upload_doc": 1,
                    "ignored": 99,
                },
                date(2026, 7, 2): {
                    "prompt_sent": 1,
                },
            }
        },
    )

    result = await CountRuleHandler().evaluate(ctx)

    assert result.progress == 3
    assert result.completed is True


@pytest.mark.asyncio
async def test_distinct_days_does_not_require_consecutive_days():
    ctx = _ctx(
        target=4,
        config={"per_day_target": 1},
        event_counts={
            "user-1": {
                date(2026, 7, 1): {"prompt_sent": 1},
                date(2026, 7, 3): {"prompt_sent": 1},
                date(2026, 7, 5): {"prompt_sent": 1},
                date(2026, 7, 7): {"prompt_sent": 1},
            }
        },
    )

    result = await DistinctDaysRuleHandler().evaluate(ctx)

    assert result.progress == 4
    assert result.completed is True


@pytest.mark.asyncio
async def test_streak_resets_to_zero_when_a_day_breaks():
    start = datetime(2026, 7, 1, tzinfo=VN_TZ)
    ctx = _ctx(
        target=2,
        period_start=start,
        period_end=start + timedelta(days=3),
        config={"per_day_target": 1},
        event_counts={
            "user-1": {
                date(2026, 7, 1): {"prompt_sent": 1},
                date(2026, 7, 2): {"prompt_sent": 1},
            }
        },
    )

    result = await StreakRuleHandler().evaluate(ctx)

    assert result.progress == 0
    assert result.completed is False


@pytest.mark.asyncio
async def test_meta_mission_counts_completed_daily_missions():
    async def reader(user_id, week_key, mission_codes):
        assert user_id == "user-1"
        assert week_key == "2026-W27"
        assert mission_codes == ["daily_core_actions"]
        return 4

    ctx = _ctx(
        period_key="2026-W27",
        target=4,
        config={"source_mission_codes": ["daily_core_actions"]},
        completed_daily_reader=reader,
    )

    result = await MetaMissionRuleHandler().evaluate(ctx)

    assert result.progress == 4
    assert result.completed is True
