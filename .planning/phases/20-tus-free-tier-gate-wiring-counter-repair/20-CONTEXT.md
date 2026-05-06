# Phase 20: TUS Free-Tier Gate Wiring + Counter Repair - Context

**Gathered:** 2026-05-06
**Status:** Ready for planning

<domain>
## Phase Boundary

Wire `FreeTierGate.check()` into the TUS upload completion path so all six free-tier policies (hourly transcribe rate, file duration, model whitelist, diarization, daily audio minutes, concurrency slot) are enforced for `/uploads/files/` (TUS chunked) identically to `/speech-to-text` (direct). After fix, the rate-limit buckets `user:{id}:tx:hour` and `user:{id}:audio_min:day` (the SOLE writers being `FreeTierGate._check_hourly_rate` + `_check_daily_minutes`) are written on every TUS transcribe, so `/api/usage` returns non-zero counters via either upload path. Closes the free-tier-policy escape hole identified at `.planning/debug/usage-counter-not-incrementing.md`.

In scope: backend wiring (`app/api/tus_upload_api.py`, `app/services/upload_session_service.py`), integration tests (`tests/integration/test_tus_*.py`), task `user_id` assignment for TUS-created tasks.

Out of scope: TUS metadata-driven model/diarize selection (forward-compat — keeps `WhisperModel.tiny` + `diarize=False` hardcoded as today); new Playwright e2e for `/dashboard/usage` (existing spec from commit ea68eca already exercises real-data display).

</domain>

<decisions>
## Implementation Decisions

### DI Wiring Shape
- Extend the existing `create_upload_complete_hook` Depends factory in `app/api/tus_upload_api.py` to also resolve `authenticated_user` and `get_free_tier_gate` — same factory pattern already used for `repository`. No new dedicated helper.
- `UploadSessionService` constructor takes `user: User` and `free_tier_gate: FreeTierGate` — service is built per-request from the hook factory (consistent with `repository` already being constructor-injected; SRP — service stays request-scoped to one user).
- Set `task.user_id = int(user.id) if user.id is not None else None` inside `start_transcription` (line 106 area) — byte-mirror of `app/api/audio_api.py:141` idiom. DRY: same construction, same conditional.
- Concurrency slot release path reuses the existing generic `process_audio_common` try/finally (`app/services/whisperx_wrapper_service.py:308-322`) — once `task.user_id` is set, the existing release path auto-works via `repo.get_by_id(identifier)` → `user_repo.get_by_id(task.user_id)` → `free_tier_gate.release_concurrency(user)`. No TUS-specific release call needed.

### Gate Invocation Semantics
- `gate.check(...)` slots in AFTER `audio_duration` measurement (current line 96) and BEFORE `repository.add(task)` (current line 116) — byte-identical ordering to `app/api/audio_api.py:117-122`.
- `model="tiny"` passed to `gate.check` — TUS path hardcodes `WhisperModel.tiny` at line 125; DRY by extracting/reusing the same constant or literal across both call sites.
- `diarize=False` passed to `gate.check` — TUS metadata exposes no diarize controls in v1.2; matches current behavior. Forward-compat metadata-driven flag deferred.
- Magic-bytes validation runs FIRST (current order preserved) — bad files rejected with NO rate-limit charge (anti-abuse: invalid uploads must not consume the user's hour quota).

### Failure & Test Coverage
- Wrap post-gate task-creation in try/except → on any failure between gate-pass and `background_tasks.add_task`, call `free_tier_gate.release_concurrency(user)` AND delete the renamed file. Closes the slot-leak window: `_check_concurrency` is the LAST gate (so a successful `gate.check()` always consumed the slot); the legitimate release path is `process_audio_common`'s try/finally, which only fires once `background_tasks.add_task` is invoked. Without the defensive release, a `repository.add` failure leaks the slot.
- Re-raise `RateLimitExceededError` / `FreeTierViolationError` / `TrialExpiredError` / `ConcurrencyLimitError` from the hook — existing FastAPI exception handlers translate to the canonical 429/403/402 responses on the TUS PATCH. No TUS-specific 4xx shape.
- New integration test drives `UploadSessionService.start_transcription` directly (mock file path + measured duration) — faster + deterministic than TUS protocol simulation. Coverage targets:
  1. Counter-bump (hour bucket = 1, daily minutes = ceil(file_seconds/60)) after a single transcribe.
  2. 6th-transcribe-blocked: 5 successes then a `RateLimitExceededError` (free-tier hourly cap = 5).
  3. File-duration cap: file > free-tier `max_file_seconds` → `FreeTierViolationError`.
  4. Concurrency-leak-on-error: simulated `repository.add` raise → assert slot was released (bucket back to capacity).
- Skip new Playwright e2e — existing dashboard real-data spec (commit ea68eca) already covers the user-facing surface.

### Acceptance Coverage (mirrors ROADMAP)
- `/api/usage` hour quota = N+1 after N+1 TUS transcribes.
- `/api/usage` daily minutes increments by `floor(audio_duration / 60)` per transcribe (tokens_needed = `max(1, int(file_seconds/60))`).
- 30-min daily cap blocks 6th 5-min file via TUS just like via direct upload.
- File-duration cap, model whitelist, diarization gate, concurrency slot all enforced for TUS.
- All existing direct-upload tests still pass (no `audio_api.py` regression).

### Claude's Discretion
- Internal helper naming (e.g., extracting `gate.check(...)` arg-build to a private method) is at Claude's discretion when the resulting code is more readable; otherwise inline matches `audio_api.py` shape.
- Specific cleanup ordering inside the post-gate try/except (release first vs delete first) is at Claude's discretion — both must run; release should be idempotent already.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `app/api/audio_api.py:117-141` — canonical `gate.check(...)` invocation + `task.user_id = int(user.id) if user.id is not None else None` task-construction idiom. TUS path mirrors this byte-for-byte where applicable.
- `app/api/dependencies.py:159` — `get_free_tier_gate` Depends provider already wired (FreeTierGate ← RateLimitService ← rate_limit_repository_v2 ← session).
- `app/api/dependencies.py:318` + `app/api/dependencies.py:355` — `authenticated_user` and `get_scoped_task_repository` already chain correctly; tuspyserver hook already 401s anonymous requests through this chain (root-cause analysis confirms `user.id` is resolvable in hook scope).
- `app/services/whisperx_wrapper_service.py:308-322` — `_release_concurrency_slot(repo, user_repo, free_tier_gate, identifier)` flat-guard helper; auto-handles release once `task.user_id` is non-null.
- `app/services/free_tier_gate.py:84-111` — `FreeTierGate.check(*, user, file_seconds, model, diarize)` — keyword-only args, 6 fail-fast guards. Public contract identical for both call sites.

### Established Patterns
- Constructor injection for request-scoped services (e.g., `UploadSessionService(repository)` today; extend to `UploadSessionService(repository, user, free_tier_gate)`).
- Tiger-style fail-loud ordering: validate → measure → gate → persist → schedule background. `audio_api.py` is the canonical sequence.
- Subtype-first error handling: `RateLimitExceededError` extends nothing relevant in user code, but global exception handlers are registered for it + `FreeTierViolationError` + `TrialExpiredError` + `ConcurrencyLimitError`.
- DRY single-source: `policy_for(user.plan_tier)` + `concurrency_bucket_key(user_id)` + bucket-key string format `user:{user_id}:tx:hour` + `user:{user_id}:audio_min:day` — never re-derived ad hoc.

### Integration Points
- `app/api/tus_upload_api.py:23-51` — single edit site for hook signature.
- `app/services/upload_session_service.py:38-180` — single edit site for service constructor + `start_transcription` body.
- `tests/integration/` — new `test_tus_upload_increments_usage.py` (or sibling) drops in next to existing TUS tests.

</code_context>

<specifics>
## Specific Ideas

- Mirror `app/api/audio_api.py:117-122` exactly when calling `gate.check(...)` — same kwarg shape, same `diarize_requested` semantics (though for TUS, `diarize_requested = False` always since TUS metadata has no diarize controls in v1.2).
- Mirror `app/api/audio_api.py:141` exactly when assigning `task.user_id`.
- Defensive cleanup branch (release_concurrency + file delete) is the ONLY net-new safety logic vs direct-upload path. `audio_api.py` doesn't need it because it doesn't move/rename a file before task creation; TUS does (line 90 `shutil.move`).

</specifics>

<deferred>
## Deferred Ideas

- TUS metadata-driven model selection (e.g., reading `metadata.get("model")` to pass to `gate.check` and `WhisperModelParams`). Would require coordinated frontend metadata field + backend whitelist enforcement; bigger than this phase. Filed for future work.
- TUS metadata-driven diarize flag — same coordination cost; defer.
- Playwright e2e for TUS-path `/dashboard/usage` real-data — existing spec (commit ea68eca) already covers the dashboard reading non-zero values; adding a TUS-specific path would be duplicative.

</deferred>
