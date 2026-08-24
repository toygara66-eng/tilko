"""IP tabanlı yavaşlatma — slowapi."""

from __future__ import annotations

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address


def client_ip(request: Request) -> str:
    """Render / Cloudflare arkasında gerçek istemci IP'sini kullan."""
    forwarded = (request.headers.get("x-forwarded-for") or "").strip()
    if forwarded:
        # İlk adres istemci; kalanlar proxy zinciri.
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    real = (request.headers.get("x-real-ip") or "").strip()
    if real:
        return real
    cf = (request.headers.get("cf-connecting-ip") or "").strip()
    if cf:
        return cf
    if request.client and request.client.host:
        return request.client.host
    return get_remote_address(request) or "unknown"


limiter = Limiter(key_func=client_ip, default_limits=["180/minute"])
