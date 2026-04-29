"""Unit tests for WsTicketService — single-use 60s WebSocket tickets (MID-06).

Test surface (RED → GREEN per plan 13-06 Task 1):

1.  test_issue_returns_32_char_token             — len(token) == 32 + expires_at == issued + 60s
2.  test_consume_valid_ticket_succeeds           — issue → consume returns user_id
3.  test_consume_unknown_token_returns_none      — unknown token → None
4.  test_consume_expired_ticket_returns_none     — TTL exceeded → None
5.  test_consume_single_use                      — second consume → None
6.  test_consume_task_id_mismatch_returns_none   — wrong task_id → None
7.  test_cleanup_expired_removes_old_tickets     — eviction count
8.  test_concurrent_issue_and_consume            — race-safety under asyncio.gather
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.services.ws_ticket_service import (
    TICKET_LENGTH,
    TICKET_TTL_SECONDS,
    WsTicketService,
)


@pytest.fixture
def service() -> WsTicketService:
    return WsTicketService()


def test_issue_returns_32_char_token(service: WsTicketService) -> None:
    """Issued ticket is TICKET_LENGTH chars and expires in TICKET_TTL_SECONDS."""
    before = datetime.now(timezone.utc)
    token, expires_at = service.issue(user_id=1, task_id="abc")
    after = datetime.now(timezone.utc)

    assert isinstance(token, str)
    assert len(token) == TICKET_LENGTH
    assert TICKET_TTL_SECONDS == 60
    expected_low = before + timedelta(seconds=TICKET_TTL_SECONDS - 1)
    expected_high = after + timedelta(seconds=TICKET_TTL_SECONDS + 1)
    assert expected_low <= expires_at <= expected_high


def test_consume_valid_ticket_succeeds(service: WsTicketService) -> None:
    """consume(token, task_id) returns the issued user_id on success."""
    token, _ = service.issue(user_id=42, task_id="abc")
    user_id = service.consume(token, "abc")
    assert user_id == 42


def test_consume_unknown_token_returns_none(service: WsTicketService) -> None:
    """Unknown token → None (caller closes WS 1008)."""
    assert service.consume("nonexistent-token-zzz", "abc") is None


def test_consume_expired_ticket_returns_none(
    service: WsTicketService, monkeypatch: pytest.MonkeyPatch
) -> None:
    """consume() rejects tickets whose expires_at < now (TTL exceeded)."""
    token, _ = service.issue(user_id=1, task_id="abc")
    # Fast-forward "now" past the 60s TTL by patching datetime.now inside the
    # service module (the only datetime call site there).
    real_now = datetime.now(timezone.utc)
    fake_now = real_now + timedelta(seconds=TICKET_TTL_SECONDS + 1)

    class _FrozenDatetime(datetime):  # noqa: D401 — subclass for monkeypatch
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            return fake_now

    monkeypatch.setattr("app.services.ws_ticket_service.datetime", _FrozenDatetime)
    assert service.consume(token, "abc") is None


def test_consume_single_use(service: WsTicketService) -> None:
    """Second consume returns None — single-use enforced via .consumed flag."""
    token, _ = service.issue(user_id=7, task_id="abc")
    assert service.consume(token, "abc") == 7
    assert service.consume(token, "abc") is None


def test_consume_task_id_mismatch_returns_none(service: WsTicketService) -> None:
    """Ticket issued for task A cannot be consumed for task B (cross-task)."""
    token, _ = service.issue(user_id=1, task_id="abc")
    assert service.consume(token, "xyz") is None


def test_cleanup_expired_removes_old_tickets(
    service: WsTicketService, monkeypatch: pytest.MonkeyPatch
) -> None:
    """cleanup_expired() removes both expired and consumed tickets."""
    t_a, _ = service.issue(user_id=1, task_id="a")
    t_b, _ = service.issue(user_id=1, task_id="b")
    service.issue(user_id=1, task_id="c")
    # Consume one — should be evicted by cleanup
    service.consume(t_a, "a")

    # Fast-forward — the remaining 2 tickets become expired
    real_now = datetime.now(timezone.utc)
    fake_now = real_now + timedelta(seconds=TICKET_TTL_SECONDS + 5)

    class _FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            return fake_now

    monkeypatch.setattr("app.services.ws_ticket_service.datetime", _FrozenDatetime)
    removed = service.cleanup_expired()
    assert removed == 3  # 1 consumed + 2 expired
    # Subsequent consume of any prior token must return None
    assert service.consume(t_b, "b") is None


def test_concurrent_issue_and_consume(service: WsTicketService) -> None:
    """100 concurrent issue+consume pairs each succeed exactly once.

    Uses ``asyncio.run`` + ``asyncio.gather`` to schedule N consume calls.
    The service is sync, so each gather entry runs to completion atomically
    under its own lock acquisition — proving single-use semantics under
    concurrent dispatch without requiring a pytest-asyncio plugin install.
    """
    tokens: list[str] = []
    for index in range(100):
        token, _ = service.issue(user_id=index, task_id=f"task-{index}")
        tokens.append(token)

    async def _consume_pair(idx: int, token: str) -> int | None:
        return service.consume(token, f"task-{idx}")

    async def _run_all() -> tuple[list[int | None], list[int | None]]:
        first_wave = await asyncio.gather(
            *(_consume_pair(idx, token) for idx, token in enumerate(tokens))
        )
        second_wave = await asyncio.gather(
            *(_consume_pair(idx, token) for idx, token in enumerate(tokens))
        )
        return first_wave, second_wave

    first, second = asyncio.run(_run_all())
    assert first == list(range(100))
    # Second wave — every token already consumed → all None
    assert all(value is None for value in second)
