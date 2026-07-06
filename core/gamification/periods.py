from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo


VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


@dataclass(frozen=True)
class Period:
    kind: str
    key: str
    start: datetime
    end: datetime

    @property
    def start_day(self) -> date:
        return self.start.date()

    @property
    def end_day(self) -> date:
        return (self.end - timedelta(microseconds=1)).date()


def ensure_vn_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=VN_TZ)
    return value.astimezone(VN_TZ)


def period_key_day(value: datetime | date) -> str:
    if isinstance(value, datetime):
        return ensure_vn_datetime(value).date().isoformat()
    return value.isoformat()


def period_key_week(value: datetime | date) -> str:
    day = ensure_vn_datetime(value).date() if isinstance(value, datetime) else value
    iso_year, iso_week, _ = day.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def daily_period(value: datetime | date) -> Period:
    day = ensure_vn_datetime(value).date() if isinstance(value, datetime) else value
    start = datetime.combine(day, time.min, tzinfo=VN_TZ)
    end = start + timedelta(days=1)
    return Period(kind="daily", key=period_key_day(day), start=start, end=end)


def weekly_period(value: datetime | date) -> Period:
    day = ensure_vn_datetime(value).date() if isinstance(value, datetime) else value
    monday = day - timedelta(days=day.weekday())
    start = datetime.combine(monday, time.min, tzinfo=VN_TZ)
    end = start + timedelta(days=7)
    return Period(kind="weekly", key=period_key_week(day), start=start, end=end)


def period_from_key(period_key: str) -> Period:
    if "-W" in period_key:
        year_raw, week_raw = period_key.split("-W", 1)
        monday = date.fromisocalendar(int(year_raw), int(week_raw), 1)
        return weekly_period(monday)
    return daily_period(date.fromisoformat(period_key))


def sweep_periods(now: datetime | None = None, grace_minutes: int = 15) -> list[Period]:
    current = ensure_vn_datetime(now or datetime.now(tz=VN_TZ))
    periods = [daily_period(current), weekly_period(current)]

    day_start = periods[0].start
    if current - day_start < timedelta(minutes=grace_minutes):
        periods.append(daily_period(day_start - timedelta(days=1)))

    week_start = periods[1].start
    if current - week_start < timedelta(minutes=grace_minutes):
        periods.append(weekly_period(week_start - timedelta(days=1)))

    return _daily_before_weekly(periods)


def _daily_before_weekly(periods: list[Period]) -> list[Period]:
    return sorted(periods, key=lambda period: (0 if period.kind == "daily" else 1, period.start))
