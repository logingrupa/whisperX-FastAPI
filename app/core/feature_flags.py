"""Centralized feature-flag helpers.

Single source of truth for boolean toggles read by middleware + route
registration code. Wraps `get_settings().auth.V2_ENABLED` so consumers
don't import AuthSettings directly.
"""
from __future__ import annotations

from app.core.config import get_settings


def is_auth_v2_enabled() -> bool:
    """Phase 13 atomic-cutover flag.

    When False (default in dev): legacy BearerAuthMiddleware is wired
    and Phase 13 routes (auth/keys/account/billing) are NOT registered.
    When True (production deploy): DualAuthMiddleware is wired, all
    new routes active, BearerAuthMiddleware removed.

    The flip from False to True is the atomic deploy moment paired
    with Phase 14 frontend cutover.
    """
    return get_settings().auth.V2_ENABLED


def is_hcaptcha_enabled() -> bool:
    """ANTI-05: hCaptcha verify on register/login. Default off."""
    return get_settings().auth.HCAPTCHA_ENABLED
