from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Protocol


EventCounts = Mapping[str, Mapping[date, Mapping[str, int]]]


@dataclass(frozen=True)
class RuleResult:
    progress: int
    target: int
    completed: bool


class RuleContext(Protocol):
    user_id: str
    period_key: str
    period_start: datetime
    period_end: datetime
    target: int
    event_codes: Sequence[str]
    config: Mapping[str, Any]

    async def count_events(self, codes: Sequence[str]) -> int:
        ...

    async def events_per_day(self, codes: Sequence[str]) -> Mapping[date, int]:
        ...

    async def events_per_code(self, codes: Sequence[str]) -> Mapping[str, int]:
        ...

    async def completed_daily_missions(self, in_week: str, mission_codes: Sequence[str] | None = None) -> int:
        ...


class RuleHandler(Protocol):
    type: str

    async def evaluate(self, ctx: RuleContext) -> RuleResult:
        ...


CompletedDailyReader = Any


@dataclass
class InMemoryRuleContext:
    user_id: str
    period_key: str
    period_start: datetime
    period_end: datetime
    target: int
    event_codes: Sequence[str] = field(default_factory=tuple)
    config: Mapping[str, Any] = field(default_factory=dict)
    event_counts: EventCounts = field(default_factory=dict)
    completed_daily_reader: CompletedDailyReader | None = None

    async def count_events(self, codes: Sequence[str]) -> int:
        per_day = await self.events_per_day(codes)
        return sum(per_day.values())

    async def events_per_day(self, codes: Sequence[str]) -> Mapping[date, int]:
        wanted = set(codes)
        days = self.event_counts.get(self.user_id, {})
        result: dict[date, int] = {}
        for day, per_code in days.items():
            total = sum(count for code, count in per_code.items() if code in wanted)
            if total:
                result[day] = total
        return result

    async def events_per_code(self, codes: Sequence[str]) -> Mapping[str, int]:
        wanted = set(codes)
        result = {code: 0 for code in wanted}
        for per_code in self.event_counts.get(self.user_id, {}).values():
            for code, count in per_code.items():
                if code in wanted:
                    result[code] = result.get(code, 0) + count
        return result

    async def completed_daily_missions(self, in_week: str, mission_codes: Sequence[str] | None = None) -> int:
        if self.completed_daily_reader is None:
            return 0
        return await self.completed_daily_reader(self.user_id, in_week, mission_codes)


@dataclass(frozen=True)
class CountRuleHandler:
    type: str = "count"

    async def evaluate(self, ctx: RuleContext) -> RuleResult:
        codes = _event_codes(ctx)
        progress = await ctx.count_events(codes)
        return _result(progress, ctx.target)


@dataclass(frozen=True)
class DistinctDaysRuleHandler:
    type: str = "distinct_days"

    async def evaluate(self, ctx: RuleContext) -> RuleResult:
        codes = _event_codes(ctx)
        per_day_target = _positive_int(ctx.config.get("per_day_target"), 1)
        per_day = await ctx.events_per_day(codes)
        progress = sum(1 for count in per_day.values() if count >= per_day_target)
        return _result(progress, ctx.target)


@dataclass(frozen=True)
class StreakRuleHandler:
    type: str = "streak"

    async def evaluate(self, ctx: RuleContext) -> RuleResult:
        codes = _event_codes(ctx)
        per_day_target = _positive_int(ctx.config.get("per_day_target"), 1)
        per_day = await ctx.events_per_day(codes)
        streak = 0
        for day in _period_days(ctx.period_start, ctx.period_end):
            if per_day.get(day, 0) >= per_day_target:
                streak += 1
            else:
                streak = 0
        return _result(streak, ctx.target)


@dataclass(frozen=True)
class MetaMissionRuleHandler:
    type: str = "meta_mission"

    async def evaluate(self, ctx: RuleContext) -> RuleResult:
        mission_codes = ctx.config.get("source_mission_codes")
        if isinstance(mission_codes, str):
            mission_codes = [mission_codes]
        if mission_codes is not None:
            mission_codes = [str(code) for code in mission_codes]

        week_key = str(ctx.config.get("week_period_key") or ctx.period_key)
        progress = await ctx.completed_daily_missions(week_key, mission_codes)
        return _result(progress, ctx.target)


def default_rule_registry() -> dict[str, RuleHandler]:
    handlers: tuple[RuleHandler, ...] = (
        CountRuleHandler(),
        DistinctDaysRuleHandler(),
        StreakRuleHandler(),
        MetaMissionRuleHandler(),
    )
    return {handler.type: handler for handler in handlers}


def _event_codes(ctx: RuleContext) -> Sequence[str]:
    configured = ctx.config.get("event_codes")
    if configured:
        return [str(code) for code in configured]
    return [str(code) for code in ctx.event_codes]


def _result(progress: int, target: int) -> RuleResult:
    normalized_target = _positive_int(target, 1)
    return RuleResult(
        progress=progress,
        target=normalized_target,
        completed=progress >= normalized_target,
    )


def _positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _period_days(start: datetime, end: datetime) -> list[date]:
    last_day = (end - timedelta(microseconds=1)).date()
    day = start.date()
    days: list[date] = []
    while day <= last_day:
        days.append(day)
        day += timedelta(days=1)
    return days
