"""Pin: routes that do blocking file or DB work are sync ``def``.

FastAPI runs sync handlers in the threadpool. An ``async def`` handler that
calls blocking code runs it on the event loop, and every other request
(including /health) waits until it returns.
"""

import inspect
from collections.abc import Callable
from typing import Any

import pytest

from app.api.audio_api import speech_to_text, speech_to_text_url
from app.api.audio_services_api import align, combine, diarize, transcribe
from app.api.task_api import (
    delete_task,
    get_all_tasks_status,
    get_task_progress,
    get_transcription_status,
)

BLOCKING_ROUTES: tuple[Callable[..., Any], ...] = (
    speech_to_text,
    speech_to_text_url,
    transcribe,
    align,
    diarize,
    combine,
    get_all_tasks_status,
    get_transcription_status,
    delete_task,
    get_task_progress,
)


@pytest.mark.unit
@pytest.mark.parametrize("route", BLOCKING_ROUTES, ids=lambda route: route.__name__)
def test_blocking_route_runs_in_threadpool(route: Callable[..., Any]) -> None:
    assert not inspect.iscoroutinefunction(route), (
        f"{route.__name__} is async def but does blocking work on the event loop"
    )
