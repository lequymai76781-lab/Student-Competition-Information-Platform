"""Minimal in-memory sliding-window rate limiter (per route key + client IP)."""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

_store: dict[tuple[str, str], deque[float]] = defaultdict(deque)
_lock = threading.Lock()


def rate_limit(bucket: str, limit: int, window_seconds: int = 60):
    def dependency(request: Request) -> None:
        client = request.client.host if request.client else "unknown"
        key = (bucket, client)
        now = time.monotonic()
        with _lock:
            queue = _store[key]
            while queue and now - queue[0] > window_seconds:
                queue.popleft()
            if len(queue) >= limit:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="请求过于频繁，请稍后再试",
                )
            queue.append(now)

    return dependency
