import asyncio
import json

import httpx
import pytest
from fastapi import FastAPI
from sse_starlette.sse import EventSourceResponse

from core.audit_log import AuditLogConfig, ClickHouseAuditLogMiddleware, audit_event
from core.audit_log.clickhouse import ClickHouseAuditWriter


def _config() -> AuditLogConfig:
    return AuditLogConfig(
        enabled=True,
        clickhouse_url="http://clickhouse.invalid:8123",
        database="default",
        table="request_log",
        username="default",
        password="",
        timeout_seconds=0.1,
        async_insert=True,
        wait_for_async_insert=False,
        wait_for_gamification_insert=False,
        meta_headers=("user-agent",),
        capture_body=True,
        max_body_bytes=32768,
        redact_keys=frozenset({"authorization", "cookie", "set-cookie", "password", "token", "api_key", "secret"}),
    )


@pytest.mark.asyncio
async def test_mapped_success_response_has_event_code(monkeypatch):
    rows = []

    async def fake_insert(self, row, *, wait_for_async_insert=None):
        rows.append(row)

    monkeypatch.setattr(ClickHouseAuditWriter, "insert_row", fake_insert)

    app = FastAPI()
    app.add_middleware(ClickHouseAuditLogMiddleware, config=_config())

    @app.get("/mapped")
    @audit_event("mapped_event")
    async def mapped():
        return {"ok": True}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/mapped", headers={"X-Request-Id": "req-1", "X-User-Id": "user-1"})

    await asyncio.sleep(0)

    assert response.status_code == 200
    assert len(rows) == 2
    request_row, response_row = rows
    assert request_row["phase"] == "request"
    assert request_row["event_code"] == ""
    assert response_row["phase"] == "response"
    assert response_row["route"] == "/mapped"
    assert response_row["user_id"] == "user-1"
    assert response_row["event_code"] == "mapped_event"
    assert response_row["event_instance_id"] == "req-1"


@pytest.mark.asyncio
async def test_unmapped_and_error_responses_keep_event_code_empty(monkeypatch):
    rows = []

    async def fake_insert(self, row, *, wait_for_async_insert=None):
        rows.append(row)

    monkeypatch.setattr(ClickHouseAuditWriter, "insert_row", fake_insert)

    app = FastAPI()
    app.add_middleware(ClickHouseAuditLogMiddleware, config=_config())

    @app.get("/unmapped")
    async def unmapped():
        return {"ok": True}

    @app.get("/mapped-error")
    @audit_event("should_not_emit")
    async def mapped_error():
        raise RuntimeError("boom")

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.get("/unmapped", headers={"X-Request-Id": "req-2"})).status_code == 200
        assert (await client.get("/mapped-error", headers={"X-Request-Id": "req-3"})).status_code == 500

    await asyncio.sleep(0)

    response_rows = [row for row in rows if row["phase"] == "response"]
    assert len(response_rows) == 2
    assert response_rows[0]["event_code"] == ""
    assert response_rows[0]["event_instance_id"] == ""
    assert response_rows[1]["success"] == 0
    assert response_rows[1]["event_code"] == ""
    assert response_rows[1]["event_instance_id"] == ""


@pytest.mark.asyncio
async def test_json_request_and_response_bodies_are_captured(monkeypatch):
    rows = []

    async def fake_insert(self, row, *, wait_for_async_insert=None):
        rows.append(row)

    monkeypatch.setattr(ClickHouseAuditWriter, "insert_row", fake_insert)

    app = FastAPI()
    app.add_middleware(ClickHouseAuditLogMiddleware, config=_config())

    @app.post("/echo")
    @audit_event("echo_event")
    async def echo(payload: dict):
        return {"received": payload, "token": "response-secret"}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/echo",
            json={"query": "Xin chao", "password": "request-secret", "nested": {"token": "abc"}},
            headers={"X-Request-Id": "req-body"},
        )

    await asyncio.sleep(0)

    assert response.status_code == 200
    assert response.json()["received"]["query"] == "Xin chao"

    request_meta = rows[0]["meta"]
    response_meta = rows[1]["meta"]
    assert isinstance(request_meta, dict)
    assert isinstance(response_meta, dict)
    assert request_meta["request_body"]["query"] == "Xin chao"
    assert request_meta["request_body"]["password"] == "[REDACTED]"
    assert request_meta["request_body"]["nested"]["token"] == "[REDACTED]"
    assert request_meta["request_body_size"] > 0
    assert request_meta["request_body_truncated"] is False
    assert response_meta["response_body"]["received"]["query"] == "Xin chao"
    assert response_meta["response_body"]["token"] == "[REDACTED]"
    assert response_meta["response_body_truncated"] is False


@pytest.mark.asyncio
async def test_json_body_capture_truncates_large_payload(monkeypatch):
    rows = []
    config = _config()
    config = type(config)(
        **{
            **config.__dict__,
            "max_body_bytes": 20,
        }
    )

    async def fake_insert(self, row, *, wait_for_async_insert=None):
        rows.append(row)

    monkeypatch.setattr(ClickHouseAuditWriter, "insert_row", fake_insert)

    app = FastAPI()
    app.add_middleware(ClickHouseAuditLogMiddleware, config=config)

    @app.post("/large")
    async def large(payload: dict):
        return {"ok": True}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/large", json={"text": "x" * 200})

    await asyncio.sleep(0)

    assert response.status_code == 200
    request_meta = rows[0]["meta"]
    assert isinstance(request_meta, dict)
    assert request_meta["request_body_size"] > 20
    assert request_meta["request_body_truncated"] is True


@pytest.mark.asyncio
async def test_streaming_response_body_is_not_consumed(monkeypatch):
    rows = []

    async def fake_insert(self, row, *, wait_for_async_insert=None):
        rows.append(row)

    monkeypatch.setattr(ClickHouseAuditWriter, "insert_row", fake_insert)

    app = FastAPI()
    app.add_middleware(ClickHouseAuditLogMiddleware, config=_config())

    @app.post("/events")
    @audit_event("stream_event")
    async def events(payload: dict):
        async def event_generator():
            yield {"event": "message", "data": json.dumps({"ok": payload["ok"]})}

        return EventSourceResponse(event_generator())

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/events", json={"ok": True}, headers={"X-Request-Id": "req-stream"})

    await asyncio.sleep(0)

    assert response.status_code == 200
    assert "data:" in response.text
    request_meta = rows[0]["meta"]
    response_meta = rows[1]["meta"]
    assert isinstance(request_meta, dict)
    assert isinstance(response_meta, dict)
    assert request_meta["request_body"]["ok"] is True
    assert response_meta["response_body_skipped_reason"] == "streaming_response"
    assert rows[1]["event_code"] == "stream_event"
