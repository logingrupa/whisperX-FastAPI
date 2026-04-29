"""End-to-end test: RedactingFilter scrubs sensitive structured fields.

Covers AUTH-09 (system never logs raw passwords, JWT secrets, full API keys)
at the filter layer. Service-layer log discipline is enforced separately by
code review + the unit-test grep gates.
"""

from __future__ import annotations

import logging

import pytest

from app.core._log_redaction import RedactingFilter


def _make_record(**extras: object) -> logging.LogRecord:
    """DRY helper: build a minimal LogRecord then attach extras to its dict."""
    record = logging.LogRecord(
        name="whisperX",
        level=logging.INFO,
        pathname="x.py",
        lineno=1,
        msg="msg",
        args=(),
        exc_info=None,
    )
    for key, value in extras.items():
        setattr(record, key, value)
    return record


@pytest.mark.integration
class TestRedactingFilter:
    """RedactingFilter scrubs password/secret/api_key/token at runtime."""

    @pytest.fixture
    def filter_instance(self) -> RedactingFilter:
        return RedactingFilter()

    def test_redacting_filter_scrubs_password_attribute(
        self, filter_instance: RedactingFilter,
    ) -> None:
        record = _make_record(password="hunter2")
        filter_instance.filter(record)
        assert record.password == "***REDACTED***"

    def test_redacting_filter_scrubs_secret_attribute(
        self, filter_instance: RedactingFilter,
    ) -> None:
        record = _make_record(jwt_secret="very-secret-key")
        filter_instance.filter(record)
        assert record.jwt_secret == "***REDACTED***"

    def test_redacting_filter_scrubs_api_key_attribute(
        self, filter_instance: RedactingFilter,
    ) -> None:
        record = _make_record(api_key="whsk_abc12345_xxxxxxxxxxxxxxxxxxxxxx")
        filter_instance.filter(record)
        assert record.api_key == "***REDACTED***"

    def test_redacting_filter_scrubs_token_attribute(
        self, filter_instance: RedactingFilter,
    ) -> None:
        record = _make_record(refresh_token="eyJhbGciOiJIUzI1NiJ9...")
        filter_instance.filter(record)
        assert record.refresh_token == "***REDACTED***"

    def test_redacting_filter_scrubs_dict_args_password_value(
        self, filter_instance: RedactingFilter,
    ) -> None:
        record = logging.LogRecord(
            "x", logging.INFO, "x.py", 1, "msg",
            args={"password": "hunter2", "username": "alice"},
            exc_info=None,
        )
        filter_instance.filter(record)
        assert isinstance(record.args, dict)
        assert record.args["password"] == "***REDACTED***"
        # Non-sensitive keys pass through untouched.
        assert record.args["username"] == "alice"

    def test_redacting_filter_passes_non_sensitive_attribute(
        self, filter_instance: RedactingFilter,
    ) -> None:
        record = _make_record(user_id=42, prefix="abc12345")
        filter_instance.filter(record)
        assert record.user_id == 42
        assert record.prefix == "abc12345"

    def test_redacting_filter_attached_to_whisperX_logger(self) -> None:
        """Sanity: importing app.core.logging attaches RedactingFilter."""
        import app.core.logging  # noqa: F401  — side-effect only

        logger = logging.getLogger("whisperX")
        assert any(isinstance(f, RedactingFilter) for f in logger.filters)
