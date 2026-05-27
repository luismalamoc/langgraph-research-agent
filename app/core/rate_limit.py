"""Rate limiting en memoria por IP — backpressure simple sin Redis."""

import time
from collections import defaultdict, deque
from collections.abc import Callable

from fastapi import Request

REQUESTS_PER_MINUTE = 10
WINDOW_SECONDS = 60

# {ip: deque[timestamp]} — asyncio es single-threaded; lecturas concurrentes son seguras
_ip_timestamps: dict[str, deque[float]] = defaultdict(deque)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def is_rate_limited(request: Request) -> bool:
    """True si el IP superó REQUESTS_PER_MINUTE en la ventana deslizante."""
    ip = _client_ip(request)
    now = time.monotonic()
    window_start = now - WINDOW_SECONDS
    timestamps = _ip_timestamps[ip]

    while timestamps and timestamps[0] < window_start:
        timestamps.popleft()

    if len(timestamps) >= REQUESTS_PER_MINUTE:
        return True

    timestamps.append(now)
    return False


def rate_limit_dependency(request: Request) -> None:
    """FastAPI dependency — lanza 429 vía HTTPException en routes."""
    from fastapi import HTTPException

    if is_rate_limited(request):
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded: max {REQUESTS_PER_MINUTE} requests per minute per IP",
        )
