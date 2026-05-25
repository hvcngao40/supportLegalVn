from fastapi import Request, Header, HTTPException, Depends
from typing import Optional
from core.security import rate_limiter
from typing import Any


async def get_redis_from_app(request: Request) -> Optional[Any]:
    """Return the Redis manager instance attached to the app pipeline, if available."""
    try:
        pipeline = request.app.state.pipeline
        redis_mgr = getattr(pipeline, "redis_manager", None)
        return redis_mgr
    except Exception:
        return None

async def get_client_ip(request: Request) -> str:
    """
    Extract client IP from headers or connection info.
    """
    # Try X-Forwarded-For first (for proxies/load balancers)
    x_forwarded_for = request.headers.get("X-Forwarded-For")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    
    # Fallback to direct client address
    if request.client:
        return request.client.host
    
    return "unknown"

async def rate_limit_ask(
    request: Request,
    ip: str = Depends(get_client_ip),
    x_user_id: Optional[str] = Header(None)
):
    """
    Rate limit for expensive Chat/RAG endpoints.
    IP limit: 10 req/min
    User limit: 10 req/min
    """
    # 1. IP Based check
    rate_limiter.check(identifier=f"ip:ask:{ip}", limit=10)
    
    # 2. User Based check (if available)
    if x_user_id:
        rate_limiter.check(identifier=f"user:ask:{x_user_id}", limit=10)
    
    return True

async def rate_limit_search(
    request: Request,
    ip: str = Depends(get_client_ip),
    x_user_id: Optional[str] = Header(None)
):
    """
    Rate limit for Search endpoints (lighter than RAG).
    IP limit: 30 req/min
    User limit: 30 req/min
    """
    # 1. IP Based check
    rate_limiter.check(identifier=f"ip:search:{ip}", limit=30)
    
    # 2. User Based check (if available)
    if x_user_id:
        rate_limiter.check(identifier=f"user:search:{x_user_id}", limit=30)
    
    return True
