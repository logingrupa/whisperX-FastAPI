"""TUS upload creation refuses uploads the completion gate would refuse anyway."""

import asyncio
from unittest.mock import MagicMock

import pytest

from app.api.tus_upload_api import create_upload_precheck_hook
from app.domain.entities.user import User
from app.services.free_tier_gate import FreeTierGate
from app.services.upload_session_service import tus_whisper_model

UPLOADER = User(id=3, email="owner@x.com", password_hash="x", plan_tier="trial")


def _handler(gate: MagicMock, *, unlimited: bool) -> object:
    return asyncio.run(
        create_upload_precheck_hook(user=UPLOADER, free_tier_gate=gate, api_key_unlimited=unlimited)
    )


@pytest.mark.unit
class TestTusPrecheck:
    def test_limited_upload_is_checked_against_the_model_it_will_run(self) -> None:
        gate = MagicMock(spec=FreeTierGate)

        _handler(gate, unlimited=False)({"filename": "a.wav"}, {"size": 10})

        gate.check_upload_allowed.assert_called_once_with(UPLOADER, tus_whisper_model())

    def test_unlimited_key_skips_the_check(self) -> None:
        gate = MagicMock(spec=FreeTierGate)

        _handler(gate, unlimited=True)({"filename": "a.wav"}, {"size": 10})

        gate.check_upload_allowed.assert_not_called()
