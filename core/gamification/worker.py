from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from core.gamification.periods import Period, period_from_key, period_key_week, sweep_periods
from core.gamification.rules import EventCounts, InMemoryRuleContext, RuleHandler, default_rule_registry


@dataclass(frozen=True)
class MissionRequirement:
    event_mission_id: str
    mission_id: str
    mission_code: str
    period_type: str
    rule_type: str
    event_codes: tuple[str, ...]
    target: int
    points: int
    config: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProgressWrite:
    user_id: str
    event_mission_id: str
    mission_id: str
    period_key: str
    progress: int
    target: int
    status: str
    points_awarded: int


class GamificationEventReader(Protocol):
    async def read_event_counts(self, periods: list[Period], event_codes: set[str]) -> EventCounts:
        ...


class GamificationStateStore(Protocol):
    async def fetch_active_requirements(self, period_type: str) -> list[MissionRequirement]:
        ...

    async def upsert_user_progress(self, write: ProgressWrite) -> bool:
        ...

    async def completed_daily_missions(
        self,
        user_id: str,
        week_period_key: str,
        mission_codes: Sequence[str] | None,
    ) -> int:
        ...

    async def recompute_user_points(self, user_ids: set[str]) -> None:
        ...

    async def recompute_user_weekly_points(self, user_ids: set[str], week_keys: set[str]) -> None:
        ...

    async def refresh_leaderboard(self) -> None:
        ...


@dataclass
class SweepSummary:
    periods: list[str]
    users_seen: int
    progress_rows_written: int
    dirty_users: int


class GamificationSweepWorker:
    def __init__(
        self,
        event_reader: GamificationEventReader,
        state_store: GamificationStateStore,
        registry: Mapping[str, RuleHandler] | None = None,
    ) -> None:
        self.event_reader = event_reader
        self.state_store = state_store
        self.registry = dict(registry or default_rule_registry())

    async def sweep(self, now: datetime | None = None, grace_minutes: int = 15) -> SweepSummary:
        periods = sweep_periods(now=now, grace_minutes=grace_minutes)
        return await self.sweep_periods(periods)

    async def backfill(self, period_keys: Sequence[str], mission_filter: Sequence[str] | None = None) -> SweepSummary:
        periods = [period_from_key(period_key) for period_key in period_keys]
        return await self.sweep_periods(periods, mission_filter=mission_filter)

    async def sweep_periods(
        self,
        periods: list[Period],
        mission_filter: Sequence[str] | None = None,
    ) -> SweepSummary:
        periods = _daily_before_weekly(periods)
        wanted_missions = set(mission_filter or [])
        requirements_by_kind = {
            kind: _filter_requirements(await self.state_store.fetch_active_requirements(kind), wanted_missions)
            for kind in ("daily", "weekly")
        }
        event_codes = {
            code
            for requirements in requirements_by_kind.values()
            for requirement in requirements
            for code in requirement.event_codes
        }
        counts = await self.event_reader.read_event_counts(periods, event_codes)

        dirty_users: set[str] = set()
        weekly_keys: set[str] = set()
        rows_written = 0
        for period in periods:
            users = _users_with_events_in_period(counts, period)
            for user_id in users:
                for requirement in requirements_by_kind.get(period.kind, []):
                    handler = self.registry[requirement.rule_type]
                    ctx = InMemoryRuleContext(
                        user_id=user_id,
                        period_key=period.key,
                        period_start=period.start,
                        period_end=period.end,
                        target=requirement.target,
                        event_codes=requirement.event_codes,
                        config=requirement.config,
                        event_counts=counts,
                        completed_daily_reader=self.state_store.completed_daily_missions,
                    )
                    result = await handler.evaluate(ctx)
                    write = ProgressWrite(
                        user_id=user_id,
                        event_mission_id=requirement.event_mission_id,
                        mission_id=requirement.mission_id,
                        period_key=period.key,
                        progress=result.progress,
                        target=result.target,
                        status="completed" if result.completed else "in_progress",
                        points_awarded=requirement.points if result.completed else 0,
                    )
                    changed = await self.state_store.upsert_user_progress(write)
                    rows_written += 1
                    if changed:
                        dirty_users.add(user_id)
                        weekly_keys.add(period.key if period.kind == "weekly" else period_key_week(period.start))

        if dirty_users:
            await self.state_store.recompute_user_points(dirty_users)
            await self.state_store.recompute_user_weekly_points(dirty_users, weekly_keys)
            await self.state_store.refresh_leaderboard()

        return SweepSummary(
            periods=[period.key for period in periods],
            users_seen=len(counts),
            progress_rows_written=rows_written,
            dirty_users=len(dirty_users),
        )

    async def run_forever(self, interval_seconds: int = 600) -> None:
        while True:
            await self.sweep()
            await asyncio.sleep(interval_seconds)


def _users_with_events_in_period(counts: EventCounts, period: Period) -> list[str]:
    users: list[str] = []
    for user_id, per_day in counts.items():
        if any(period.start_day <= day <= period.end_day for day in per_day):
            users.append(user_id)
    return users


def _filter_requirements(
    requirements: list[MissionRequirement],
    mission_filter: set[str],
) -> list[MissionRequirement]:
    if not mission_filter:
        return requirements
    return [
        requirement
        for requirement in requirements
        if requirement.mission_id in mission_filter or requirement.mission_code in mission_filter
    ]


def _daily_before_weekly(periods: list[Period]) -> list[Period]:
    return sorted(periods, key=lambda period: (0 if period.kind == "daily" else 1, period.start))
