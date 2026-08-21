"""IP tabanlı yavaşlatma — slowapi."""

from __future__ import annotations

from fastapi import Request
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address


def client_ip(request: Request) -> str:
    if request.client and request.client.host:
        return request.client.host
    return get_remote_address(request) or "unknown"


limiter = Limiter(key_func=client_ip, default_limits=["90/minute"])
