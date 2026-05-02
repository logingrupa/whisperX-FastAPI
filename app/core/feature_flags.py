"""Centralized feature-flag helpers.

Single source of truth for boolean toggles read by route registration code.
The Phase 13 atomic-cutover flag was removed in Phase 19-11 — V2 is the only
auth path; the legacy auth-helper has no remaining call sites.
"""
from __future__ import annotations

from app.core.config import get_settings


def is_hcaptcha_enabled() -> bool:
    """ANTI-05: hCaptcha verify on register/login. Default off."""
    return get_settings().auth.HCAPTCHA_ENABLED
