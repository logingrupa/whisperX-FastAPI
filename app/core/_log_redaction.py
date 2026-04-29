"""Logging filter that redacts sensitive substrings from structured fields.

Per .planning/phases/11-auth-core-modules-services-di/11-CONTEXT.md §83-90 (locked):
- Sensitive keys: password, secret, api_key, token (case-insensitive substring).
- Replacement: literal '***REDACTED***'.
- Defense-in-depth — services SHOULD never log these in the first place;
  this filter is a backstop.
"""

from __future__ import annotations

import logging
import re

# Tiger-style invariants — fail loudly at module load if sensitive list drifts.
_SENSITIVE_KEY_PATTERN = re.compile(r"(password|secret|api_key|token)", re.IGNORECASE)
_REDACTED = "***REDACTED***"
assert _REDACTED == "***REDACTED***", "Redaction marker drift"


class RedactingFilter(logging.Filter):
    """Scrub sensitive structured fields and dict args from log records.

    Side note: this does NOT scrub message format-string interpolations
    like `logger.info("token=%s", token_value)`. Service code MUST avoid
    embedding sensitive raw values in messages — this filter only catches
    structured `extra={...}` fields and `record.args` dicts.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        # Redact sensitive structured fields (extra={...} attaches to record.__dict__).
        for attr in list(record.__dict__):
            if _SENSITIVE_KEY_PATTERN.search(attr):
                setattr(record, attr, _REDACTED)
        # Redact in dict-shaped args (e.g. logger.info("...", {"password": "x"}))
        if isinstance(record.args, dict):
            record.args = {
                k: (_REDACTED if _SENSITIVE_KEY_PATTERN.search(k) else v)
                for k, v in record.args.items()
            }
        return True
