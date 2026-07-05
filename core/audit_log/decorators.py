from collections.abc import Callable
from typing import Any, TypeVar


F = TypeVar("F", bound=Callable[..., Any])


def audit_event(event_code: str) -> Callable[[F], F]:
    """Opt-in marker for routes that should emit a gamification event on success."""
    normalized = event_code.strip()

    def decorator(func: F) -> F:
        setattr(func, "__audit_event_code__", normalized)
        return func

    return decorator


def get_audit_event_code(endpoint: Callable[..., Any] | None) -> str:
    if endpoint is None:
        return ""
    return str(getattr(endpoint, "__audit_event_code__", "") or "")
