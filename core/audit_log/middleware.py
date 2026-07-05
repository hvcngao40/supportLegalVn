import asyncio
import json
import time
import uuid
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import Request
from starlette.datastructures import Headers
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response, StreamingResponse
from starlette.routing import Match
from starlette.types import ASGIApp

from core.audit_log.clickhouse import ClickHouseAuditWriter
from core.audit_log.config import AuditLogConfig
from core.audit_log.decorators import get_audit_event_code

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


class ClickHouseAuditLogMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, config: AuditLogConfig | None = None) -> None:
        super().__init__(app)
        self.config = config or AuditLogConfig.from_env()
        self.writer = ClickHouseAuditWriter(self.config)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not self.config.enabled:
            return await call_next(request)

        request_id = _extract_request_id(request.headers)
        request.state.request_id = request_id
        user_id = _extract_user_id(request)
        method = request.method.upper()
        route, endpoint = _resolve_route(request)
        path = request.url.path
        request_started = time.perf_counter()
        request_body = await _read_request_body(request, self.config)
        request_meta = _build_meta(request, self.config)
        request_meta.update(_body_meta("request", request.headers.get("content-type", ""), request_body, self.config))

        self._write_background(
            self._build_row(
                request_id=request_id,
                phase="request",
                user_id=user_id,
                method=method,
                route=route,
                path=path,
                status_code=0,
                success=0,
                latency_ms=0,
                event_code="",
                event_instance_id="",
                meta=request_meta,
            )
        )

        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception:
            user_id = _extract_user_id(request)
            status_code = 500
            latency_ms = _elapsed_ms(request_started)
            self._write_response_row(
                request=request,
                request_id=request_id,
                user_id=user_id,
                method=method,
                route=route,
                endpoint=endpoint,
                path=path,
                status_code=status_code,
                success=0,
                latency_ms=latency_ms,
            )
            raise

        latency_ms = _elapsed_ms(request_started)
        success = 1 if 200 <= status_code < 300 else 0
        user_id = _extract_user_id(request)
        response, response_meta = await _capture_response_meta(response, request, self.config)
        self._write_response_row(
            request=request,
            request_id=request_id,
            user_id=user_id,
            method=method,
            route=route,
            endpoint=endpoint,
            path=path,
            status_code=status_code,
            success=success,
            latency_ms=latency_ms,
            response_meta=response_meta,
        )
        response.headers.setdefault("X-Request-Id", request_id)
        return response

    def _write_response_row(
        self,
        *,
        request: Request,
        request_id: str,
        user_id: str,
        method: str,
        route: str,
        endpoint: Any,
        path: str,
        status_code: int,
        success: int,
        latency_ms: int,
        response_meta: dict[str, Any] | None = None,
    ) -> None:
        event_code = get_audit_event_code(endpoint) if success else ""
        event_instance_id = request_id if event_code else ""
        meta = _build_meta(request, self.config)
        if response_meta:
            meta.update(response_meta)
        self._write_background(
            self._build_row(
                request_id=request_id,
                phase="response",
                user_id=user_id,
                method=method,
                route=route,
                path=path,
                status_code=status_code,
                success=success,
                latency_ms=latency_ms,
                event_code=event_code,
                event_instance_id=event_instance_id,
                meta=meta,
            ),
            wait_for_async_insert=self.config.wait_for_gamification_insert if event_code else None,
        )

    def _write_background(self, row: dict[str, Any], *, wait_for_async_insert: bool | None = None) -> None:
        asyncio.create_task(self.writer.insert_row(row, wait_for_async_insert=wait_for_async_insert))

    @staticmethod
    def _build_row(
        *,
        request_id: str,
        phase: str,
        user_id: str,
        method: str,
        route: str,
        path: str,
        status_code: int,
        success: int,
        latency_ms: int,
        event_code: str,
        event_instance_id: str,
        meta: dict[str, Any],
    ) -> dict[str, Any]:
        occurred_at = datetime.now(tz=VN_TZ)
        occurred_at_value = occurred_at.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        return {
            "log_id": str(uuid.uuid4()),
            "request_id": request_id,
            "phase": phase,
            "user_id": user_id,
            "method": method,
            "route": route,
            "path": path,
            "status_code": status_code,
            "success": success,
            "event_code": event_code,
            "event_instance_id": event_instance_id,
            "occurred_at": occurred_at_value,
            "period_day": occurred_at.date().isoformat(),
            "latency_ms": latency_ms,
            "meta": meta,
        }


def _extract_request_id(headers: Headers) -> str:
    return headers.get("x-request-id") or headers.get("x-correlation-id") or str(uuid.uuid4())


def _extract_user_id(request: Request) -> str:
    state_user_id = getattr(request.state, "user_id", "")
    if state_user_id:
        return str(state_user_id)
    for header in ("x-user-id", "x-auth-user", "x-forwarded-user"):
        value = request.headers.get(header)
        if value:
            return value.strip()
    return ""


def _resolve_route(request: Request) -> tuple[str, Any]:
    scope = request.scope
    for route in request.app.router.routes:
        match, _ = route.matches(scope)
        if match == Match.FULL:
            return str(getattr(route, "path", request.url.path)), getattr(route, "endpoint", None)
    return request.url.path, None


def _build_meta(request: Request, config: AuditLogConfig) -> dict[str, Any]:
    headers = {
        header: request.headers.get(header)
        for header in config.meta_headers
        if request.headers.get(header)
    }
    client_host = request.client.host if request.client else ""
    return {
        "client_host": client_host,
        "headers": headers,
        "query": dict(request.query_params),
    }


async def _read_request_body(request: Request, config: AuditLogConfig) -> bytes | None:
    if not config.capture_body:
        return None

    content_type = request.headers.get("content-type", "")
    if not _is_json_content_type(content_type):
        return None

    body = await request.body()
    return body


async def _capture_response_meta(
    response: Response,
    request: Request,
    config: AuditLogConfig,
) -> tuple[Response, dict[str, Any]]:
    if not config.capture_body:
        return response, {}

    content_type = response.headers.get("content-type", "")
    if _is_streaming_response(response, content_type):
        return response, {"response_body_skipped_reason": "streaming_response"}

    if not _is_json_content_type(content_type):
        return response, {"response_body_skipped_reason": "non_json_response"}

    body = b"".join([chunk async for chunk in response.body_iterator])  # type: ignore[attr-defined]
    meta = _body_meta("response", content_type, body, config)
    replayed = Response(
        content=body,
        status_code=response.status_code,
        headers=dict(response.headers),
        media_type=response.media_type,
        background=response.background,
    )
    return replayed, meta


def _is_streaming_response(response: Response, content_type: str) -> bool:
    if "text/event-stream" in content_type.lower():
        return True
    if isinstance(response, StreamingResponse) and not _is_json_content_type(content_type):
        return True
    return False


def _body_meta(prefix: str, content_type: str, body: bytes | None, config: AuditLogConfig) -> dict[str, Any]:
    size_key = f"{prefix}_body_size"
    truncated_key = f"{prefix}_body_truncated"
    body_key = f"{prefix}_body"
    skipped_key = f"{prefix}_body_skipped_reason"

    if not config.capture_body:
        return {skipped_key: "disabled"}
    if body is None:
        return {skipped_key: "non_json_request" if prefix == "request" else "non_json_response"}
    if not _is_json_content_type(content_type):
        return {size_key: len(body), truncated_key: False, skipped_key: "non_json_body"}
    if not body:
        return {size_key: 0, truncated_key: False, body_key: None}

    truncated = len(body) > config.max_body_bytes
    sample = body[: config.max_body_bytes]
    try:
        parsed = json.loads(sample.decode("utf-8"))
        value: Any = _redact_json(parsed, config.redact_keys)
    except (UnicodeDecodeError, json.JSONDecodeError):
        value = sample.decode("utf-8", errors="replace")

    return {
        size_key: len(body),
        truncated_key: truncated,
        body_key: value,
    }


def _is_json_content_type(content_type: str) -> bool:
    normalized = content_type.split(";", 1)[0].strip().lower()
    return normalized == "application/json" or normalized.endswith("+json")


def _redact_json(value: Any, redact_keys: frozenset[str]) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, child in value.items():
            if str(key).lower() in redact_keys:
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = _redact_json(child, redact_keys)
        return redacted
    if isinstance(value, list):
        return [_redact_json(item, redact_keys) for item in value]
    return value


def _elapsed_ms(started_at: float) -> int:
    return max(0, int((time.perf_counter() - started_at) * 1000))
