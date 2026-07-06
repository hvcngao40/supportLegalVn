from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

from core.audit_log.config import AuditLogConfig
from core.gamification.clickhouse_reader import ClickHouseGamificationReader
from core.gamification.periods import VN_TZ, period_key_day, period_key_week
from core.gamification.postgres_store import PostgresGamificationStore
from core.gamification.worker import GamificationSweepWorker


router = APIRouter(prefix="/gamification", tags=["gamification"])


class CampaignCreateRequest(BaseModel):
    code: str
    name: str
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    is_active: bool = True


class MissionCreateRequest(BaseModel):
    campaign_id: str
    code: str
    name: str
    period_type: Literal["daily", "weekly"]
    is_active: bool = True
    sort_order: int = 0


class RequirementCreateRequest(BaseModel):
    mission_id: str
    rule_type: Literal["count", "distinct_days", "streak", "meta_mission"]
    target: int = Field(gt=0)
    points: int = 0
    sort_order: int = 0
    event_id: str | None = None
    event_codes: list[str] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)


class BackfillRequest(BaseModel):
    period_keys: list[str] = Field(min_length=1)
    mission_filter: list[str] | None = None


@router.post("/campaigns")
async def create_campaign(payload: CampaignCreateRequest, request: Request):
    store = await _get_store(request)
    return await store.create_campaign(payload.model_dump())


@router.post("/missions")
async def create_mission(payload: MissionCreateRequest, request: Request):
    store = await _get_store(request)
    return await store.create_mission(payload.model_dump())


@router.post("/mission-requirements")
async def create_requirement(payload: RequirementCreateRequest, request: Request):
    store = await _get_store(request)
    return await store.create_requirement(payload.model_dump())


@router.get("/missions/daily")
async def daily_missions(
    request: Request,
    x_user_id: str | None = Header(default=None),
    period_key: str | None = None,
):
    user_id = _require_user_id(x_user_id)
    store = await _get_store(request)
    key = period_key or period_key_day(datetime.now(tz=VN_TZ))
    return {"period_type": "daily", "period_key": key, "missions": await store.list_missions("daily", user_id, key)}


@router.get("/missions/weekly")
async def weekly_missions(
    request: Request,
    x_user_id: str | None = Header(default=None),
    period_key: str | None = None,
):
    user_id = _require_user_id(x_user_id)
    store = await _get_store(request)
    key = period_key or period_key_week(datetime.now(tz=VN_TZ))
    return {"period_type": "weekly", "period_key": key, "missions": await store.list_missions("weekly", user_id, key)}


@router.get("/leaderboard")
async def leaderboard(
    request: Request,
    scope: Literal["alltime", "weekly"] = "alltime",
    limit: int = Query(default=50, ge=1, le=100),
    period_key: str | None = None,
):
    store = await _get_store(request)
    week_key = period_key or period_key_week(datetime.now(tz=VN_TZ))
    return {
        "scope": scope,
        "period_key": week_key if scope == "weekly" else None,
        "entries": await store.leaderboard(scope, week_key, limit),
    }


@router.get("/me/points")
async def my_points(request: Request, x_user_id: str | None = Header(default=None)):
    user_id = _require_user_id(x_user_id)
    store = await _get_store(request)
    week_key = period_key_week(datetime.now(tz=VN_TZ))
    return await store.get_points(user_id, week_key)


@router.get("/me/progress")
async def my_progress(request: Request, x_user_id: str | None = Header(default=None)):
    user_id = _require_user_id(x_user_id)
    store = await _get_store(request)
    return {"user_id": user_id, "items": await store.get_progress(user_id)}


@router.get("/me/dashboard")
async def my_dashboard(request: Request, x_user_id: str | None = Header(default=None)):
    user_id = _require_user_id(x_user_id)
    store = await _get_store(request)
    return await store.dashboard(user_id, datetime.now(tz=VN_TZ))


@router.post("/backfill")
async def backfill(payload: BackfillRequest, request: Request):
    worker = await _get_worker(request)
    summary = await worker.backfill(payload.period_keys, payload.mission_filter)
    return {
        "periods": summary.periods,
        "users_seen": summary.users_seen,
        "progress_rows_written": summary.progress_rows_written,
        "dirty_users": summary.dirty_users,
    }


async def _get_store(request: Request) -> Any:
    injected = getattr(request.app.state, "gamification_store", None)
    if injected is not None:
        return injected

    pool = getattr(request.app.state, "postgres_pool", None)
    if pool is None:
        try:
            import asyncpg
        except ImportError as exc:
            raise HTTPException(status_code=503, detail="asyncpg is not installed") from exc

        database_url = os.getenv(
            "DATABASE_URL",
            "postgresql://legal:legal@127.0.0.1:5432/support_legal",
        )
        try:
            pool = await asyncpg.create_pool(database_url, min_size=1, max_size=5)
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Postgres unavailable: {exc}") from exc
        request.app.state.postgres_pool = pool

    store = PostgresGamificationStore(pool)
    request.app.state.gamification_store = store
    return store


async def _get_worker(request: Request) -> GamificationSweepWorker:
    injected = getattr(request.app.state, "gamification_worker", None)
    if injected is not None:
        return injected

    store = await _get_store(request)
    worker = GamificationSweepWorker(
        event_reader=ClickHouseGamificationReader(AuditLogConfig.from_env()),
        state_store=store,
    )
    request.app.state.gamification_worker = worker
    return worker


def _require_user_id(user_id: str | None) -> str:
    if user_id and user_id.strip():
        return user_id.strip()
    raise HTTPException(status_code=401, detail="X-User-Id header is required")
