"""Slowapi Limiter with CF-Connecting-IP-aware ``key_func`` (Phase 13).

Per RATE-01 + Phase-13 CONTEXT §107:

* When ``AUTH__TRUST_CF_HEADER=true`` the proxy header
  ``cf-connecting-ip`` (Cloudflare) or the first hop of ``x-forwarded-for``
  is trusted as the client IP source. Otherwise the direct socket peer is
  used.
* IPv4 clients are grouped by ``/24`` subnet; IPv6 clients by ``/64``. This
  matches the anti-DDOS policy from CONTEXT §118 (register 3/hr/ip:/24,
  login 10/hr/ip:/24).
* Slowapi storage backend: in-memory leaky bucket (process-local). Acceptable
  for v1.2 single-worker deploys — the bot-scale attacks the threat model
  (T-13-11 / T-13-12) targets are foiled even by a per-process bucket. Multi-
  worker deployments must swap storage to redis/limits before Phase 18.

Single source of truth: every Phase 13 route that wants slowapi enforcement
imports ``limiter`` from this module. Never instantiate a second Limiter.
"""

from __future__ import annotations

import ipaddress
import logging

from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_DEFAULT_RETRY_AFTER_SECONDS = 60


def _client_subnet_key(request: Request) -> str:
    """Return the ``/24`` (IPv4) or ``/64`` (IPv6) subnet of the client.

    Used as slowapi's ``key_func`` so register/login throttles apply to
    blocks of related clients, not single sockets — cheap defence against
    NATed bot farms (CONTEXT §107).
    """
    settings = get_settings()
    raw_ip = ""
    if settings.auth.TRUST_CF_HEADER:
        cf_ip = request.headers.get("cf-connecting-ip", "")
        xff = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        raw_ip = cf_ip or xff
    if not raw_ip:
        raw_ip = get_remote_address(request)
    try:
        addr = ipaddress.ip_address(raw_ip)
    except ValueError:
        return raw_ip or "unknown"
    if isinstance(addr, ipaddress.IPv4Address):
        net = ipaddress.ip_network(f"{addr}/24", strict=False)
        return f"{net.network_address}/24"
    net = ipaddress.ip_network(f"{addr}/64", strict=False)
    return f"{net.network_address}/64"


# Module-level singleton — used by `@limiter.limit("3/hour")` decorators on
# /auth/register, /auth/login, etc. App wiring (mounting limiter onto
# `app.state.limiter`) lives in plan 13-09.
limiter = Limiter(key_func=_client_subnet_key, default_limits=[])


def _extract_retry_after(detail: str) -> int:
    """Pull the seconds value out of slowapi's "X per Y second" detail string."""
    parts = detail.split()
    for index, token in enumerate(parts):
        if token.startswith("second") and index > 0:
            try:
                return int(parts[index - 1])
            except ValueError:
                return _DEFAULT_RETRY_AFTER_SECONDS
    return _DEFAULT_RETRY_AFTER_SECONDS


async def rate_limit_handler(
    request: Request, exc: RateLimitExceeded
) -> JSONResponse:
    """Format slowapi's RateLimitExceeded into a JSON 429 with Retry-After.

    Per RATE-12 the header is REQUIRED so clients (and our anti-bot UX) can
    schedule retries instead of hammering the bucket.
    """
    retry_after = _extract_retry_after(str(exc.detail))
    logger.info("rate_limit_exceeded path=%s", request.url.path)
    return JSONResponse(
        status_code=429,
        content={"detail": "Too many requests. Please try again later."},
        headers={"Retry-After": str(retry_after)},
    )
