---
status: root_caused
trigger: "Transcribed 703.7 MB file (Fotografēšana 2.daļa.mp4) via TUS upload path; queue card shows Done state with SRT/VTT/TXT/JSON export buttons rendered. Then visited https://whisper.kingdom.lv/dashboard/usage — still shows 'Hour quota: 0 of 5' and 'Daily minutes: 0.0 min of 30.0 min'. Hard reload (Ctrl+F5) did not change values. First transcribe since GET /api/usage endpoint shipped (commit 91cb7c6, quick task 260505-l2w)."
created: 2026-05-06
updated: 2026-05-06
---

# Debug: usage-counter-not-incrementing

## Symptoms

- **Expected**: After transcribing a file successfully, `/dashboard/usage` should show non-zero hour quota count (1+ of 5) and non-zero daily minutes (file is 703.7 MB MP4 — likely 30+ min of audio, possibly clipped at 30 min limit).
- **Actual**: Both counters remain at zero. UI shows `data-testid="hour-quota-count">0 of 5` and `data-testid="daily-minutes-count">0.0 min of 30.0 min`.
- **Error messages**: None visible in UI.
- **Timeline**: First transcribe attempt since the /api/usage endpoint was deployed in commit 91cb7c6 (quick task 260505-l2w, 2026-05-05). Counter never worked since shipped.
- **Reproduction**: Upload large file (703.7 MB) through TUS path → wait for transcription completion → navigate to `/dashboard/usage` → both counters still zero.

## Suspect Areas (initial)

1. **/api/usage endpoint** — bucket key mismatch. ELIMINATED, see below.
2. **Counter-increment site** — TUS path missing increment call. CONFIRMED.
3. **Auth context at completion time** — irrelevant; user_id IS available because TUS hook chains through `authenticated_user` Depends. ELIMINATED.
4. **Frontend Refresh button** — irrelevant; backend has zero data to return. ELIMINATED.

## Current Focus

- hypothesis: **CONFIRMED** — TUS upload path's completion hook does not call `FreeTierGate.check()` (the sole counter-write site). Counter buckets `user:{id}:tx:hour` and `user:{id}:audio_min:day` are never `consume()`d on the TUS path.
- test: Compared `app/api/audio_api.py:117` (`/speech-to-text` calls `free_tier_gate.check(...)`) vs `app/services/upload_session_service.py:start_transcription()` (TUS path — no such call).
- expecting: Missing `free_tier_gate.check()` invocation in `UploadSessionService.start_transcription`. **CONFIRMED.**
- next_action: Implement fix — wire FreeTierGate into UploadSessionService and call `check()` in start_transcription before scheduling background work.

## Evidence

- timestamp: 2026-05-06 — `app/services/usage_query_service.py:32-33` defines bucket keys `user:{user_id}:tx:hour` and `user:{user_id}:audio_min:day`, read by `/api/usage`.
- timestamp: 2026-05-06 — `app/services/free_tier_gate.py:148-159` (`_check_hourly_rate`) calls `rate_limit_service.check_and_consume("user:{user_id}:tx:hour", tokens_needed=1, ...)`. This is the ONLY write site for the hour bucket.
- timestamp: 2026-05-06 — `app/services/free_tier_gate.py:184-199` (`_check_daily_minutes`) calls `rate_limit_service.check_and_consume("user:{user_id}:audio_min:day", tokens_needed=max(1, int(file_seconds/60)), ...)`. This is the ONLY write site for the daily bucket.
- timestamp: 2026-05-06 — `_check_hourly_rate` and `_check_daily_minutes` are PRIVATE methods, only invoked from public `FreeTierGate.check()` (free_tier_gate.py:84-111).
- timestamp: 2026-05-06 — Grep across `app/`: `FreeTierGate` / `free_tier_gate` references are only in `app/api/audio_api.py` (direct upload path) + DI wiring in `dependencies.py` + tests. NOT in `tus_upload_api.py` or `upload_session_service.py`.
- timestamp: 2026-05-06 — `app/api/audio_api.py:117` calls `free_tier_gate.check(user=user, file_seconds=audio_duration, ...)` for `/speech-to-text`. `app/api/audio_api.py:219` does same for `/speech-to-text-url`.
- timestamp: 2026-05-06 — `app/services/upload_session_service.py:57-180` (`UploadSessionService.start_transcription`): no FreeTierGate import, no check() call, no rate_limit_repository access. The TUS pipeline goes file_path → magic-bytes validate → audio decode → DomainTask create → `process_audio_common` background task. Counters never touched.
- timestamp: 2026-05-06 — User confirmed hard-reload didn't change values → frontend cache eliminated. Backend has nothing to return because nothing was written.
- timestamp: 2026-05-06 — Auth context IS available at hook fire time: `tus_upload_api.py:55-61` wires `upload_complete_dep=create_upload_complete_hook`; `create_upload_complete_hook` Depends on `get_scoped_task_repository`, which Depends on `authenticated_user` (`dependencies.py:355-367`). FastAPI resolves the chain → 401 fires before hook if anonymous. So `user.id` IS resolvable in the hook scope; the hook just doesn't currently inject it.
- timestamp: 2026-05-06 — Side-effect of the missing wiring: TUS uploads also bypass `_check_file_duration` (free-tier user can transcribe an unlimited-length file), `_check_model`, `_check_diarization`, and `_check_concurrency` (slot never claimed → unbounded concurrent TUS jobs per user). This is a free-tier-policy escape hole, not just a cosmetic counter bug.

## Eliminated

- /api/usage endpoint reads wrong bucket key — keys match between writer (`free_tier_gate.py`) and reader (`usage_query_service.py`) exactly.
- /api/usage queries wrong column — service uses `user.id` from `authenticated_user`, same identifier the gate uses.
- TUS hook lacks user context — Depends chain resolves `authenticated_user` before hook runs (auth would 401 the upload PATCH otherwise).
- Frontend stale state / cache — hard reload reproduced.
- Daily / hourly window reset timing — buckets consume at write time; reads always see consumed tokens until refill window. Zero reads = zero writes.

## Resolution

- root_cause: **TUS upload path bypasses `FreeTierGate.check()` entirely.** `UploadSessionService.start_transcription` (`app/services/upload_session_service.py`) schedules `process_audio_common` without invoking the gate, so the rate-limit buckets `user:{id}:tx:hour` (capacity = `max_per_hour`) and `user:{id}:audio_min:day` (capacity = `max_daily_seconds // 60` minutes) are never `consume()`d. `/api/usage` reads zero because nothing was ever written. Side effect: free-tier policy (file duration, model, diarize, concurrency) is also unenforced for TUS uploads.

- fix: Inject `FreeTierGate` and the authenticated `User` into the TUS upload completion hook, then call `free_tier_gate.check(user=user, file_seconds=audio_duration, model=<resolved>, diarize=<resolved>)` inside `UploadSessionService.start_transcription` BEFORE `repository.add(task)` and `background_tasks.add_task(...)`. Mirrors the `/speech-to-text` ordering at `app/api/audio_api.py:117-122`. Required edits:
  1. `app/api/tus_upload_api.py` — extend `create_upload_complete_hook` Depends signature to also resolve `authenticated_user` and `get_free_tier_gate`. Pass both into `UploadSessionService` constructor (or into `start_transcription`).
  2. `app/services/upload_session_service.py` — accept `FreeTierGate` + `User` (constructor injection or per-call), invoke `free_tier_gate.check(...)` after `audio_duration` is measured, before `DomainTask` creation. Use TUS metadata or a default `model="tiny"` (the value already hardcoded at line 124) and `diarize=False` (TUS path has no diarize controls today). Set `task.user_id = int(user.id)` explicitly (DRY: mirror audio_api.py:141).
  3. Concurrency-slot release: TUS path must also call `free_tier_gate.release_concurrency(user)` in `process_audio_common`'s try/finally completion hook — verify this is already wired generically, since `_check_concurrency` consumes a token. If not, slot never refunds for TUS jobs.

- verification:
  1. Backend pytest: add a `tests/integration/test_tus_upload_increments_usage.py` that drives a fake TUS completion through `UploadSessionService.start_transcription` and asserts the rate-limit repo's hour + day buckets were consumed (mirror existing `tests/integration/test_audio_api_free_tier_gate.py` pattern if it exists).
  2. Manual: re-transcribe a small file via TUS, GET `/api/usage`, observe `hour_count: 1` and `daily_minutes_used: <ceil(file_minutes)>`.
  3. Existing `/api/usage` regression suite must still pass.

- files_changed: (pending fix application)
  - `app/api/tus_upload_api.py`
  - `app/services/upload_session_service.py`
  - `tests/integration/test_tus_upload_increments_usage.py` (new)

## Specialist Hint

specialist_hint: python
