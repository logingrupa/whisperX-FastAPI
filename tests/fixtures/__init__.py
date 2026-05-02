"""Test fixtures package.

Phase 19 Plan 13: the legacy `TestContainer` (subclass of
`app.core.container.Container`) was deleted alongside `container.py` and
the `dependency_injector` library. All integration tests now drive the
slim FastAPI app via `app.dependency_overrides[get_db]` (Plan 19-10).
"""
