# Phase 20: TUS Free-Tier Gate Wiring + Counter Repair - Research

**Researched:** 2026-05-06
**Domain:** FastAPI Depends factory wiring + tuspyserver completion-hook + token-bucket counter repair
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**DI Wiring Shape**
- Extend existing `create_upload_complete_hook` Depends factory in `app/api/tus_upload_api.py` to also resolve `authenticated_user` and `get_free_tier_gate` — same factory pattern already used for `repository`. No new dedicated helper.
- `UploadSessionService` constructor takes `user: User` and `free_tier_gate: FreeTierGate` — service built per-request from hook factory (consistent with `repository` already constructor-injected; SRP — service stays request-scoped to one user).
- Set `task.user_id = int(user.id) if user.id is not None else None` inside `start_transcription` (line 106 area) — byte-mirror of `app/api/audio_api.py:141` idiom.
- Concurrency-slot release path reuses existing generic `process_audio_common` try/finally (`whisperx_wrapper_service.py:302-322`, function `_release_slot_if_authed`). Once `task.user_id` is set, existing release path auto-works. NO TUS-specific release call needed.

**Gate Invocation Semantics**
- `gate.check(...)` slots in AFTER `audio_duration` measurement (current line 96) and BEFORE `repository.add(task)` (current line 116) — byte-identical ordering to `app/api/audio_api.py:117-122`.
- `model="tiny"` passed to `gate.check` — TUS path hardcodes `WhisperModel.tiny` at line 125; DRY by reusing same constant/literal across both call sites.
- `diarize=False` passed to `gate.check` — TUS metadata exposes no diarize controls in v1.2.
- Magic-bytes validation runs FIRST (current order preserved) — bad files rejected with NO rate-limit charge (anti-abuse).

**Failure & Test Coverage**
- Wrap post-gate task-creation in try/except → on any failure between gate-pass and `background_tasks.add_task`, call `free_tier_gate.release_concurrency(user)` AND delete renamed file. Closes slot-leak window (`_check_concurrency` is the LAST gate; legitimate release path is `process_audio_common` try/finally which only fires once `background_tasks.add_task` is invoked).
- Re-raise `RateLimitExceededError` / `FreeTierViolationError` / `TrialExpiredError` / `ConcurrencyLimitError` from hook — existing FastAPI exception handlers translate to canonical 429/403/402 responses on TUS PATCH. No TUS-specific 4xx shape.
- New integration test drives `UploadSessionService.start_transcription` directly (mock file path + measured duration) — faster + deterministic than TUS protocol simulation.

### Claude's Discretion
- Internal helper naming (e.g., extracting `gate.check(...)` arg-build to a private method) at Claude's discretion when more readable.
- Cleanup ordering inside post-gate try/except (release first vs delete first) at Claude's discretion — both must run; release is idempotent.

### Deferred Ideas (OUT OF SCOPE)
- TUS metadata-driven model selection (reading `metadata.get("model")`) — coordinated frontend + backend whitelist work; deferred.
- TUS metadata-driven diarize flag — same coordination cost; deferred.
- Playwright e2e for TUS-path `/dashboard/usage` real-data — existing spec (commit ea68eca) already covers dashboard reading non-zero values.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| REQ-FREETIER-TUS | Free-tier policy (hourly count, file duration, model whitelist, diarization, daily minutes, concurrency slot) MUST be enforced for TUS upload path identically to direct upload | `app/api/audio_api.py:117-122` is canonical `gate.check(...)` byte-mirror reference; FastAPI exception handlers in `app/api/exception_handlers.py` already wired for `RateLimitExceededError`/`FreeTierViolationError`/`TrialExpiredError`/`ConcurrencyLimitError` (4 handlers, 429/403/402); registered globally in `app/main.py:209-213` so TUS PATCH benefits without router-specific wiring. |
| REQ-USAGE-TUS-COUNTER | `/api/usage` MUST return non-zero counters after a TUS transcribe; bucket keys `user:{id}:tx:hour` and `user:{id}:audio_min:day` MUST be `consume()`d on every TUS transcribe | `_check_hourly_rate` + `_check_daily_minutes` (free_tier_gate.py:148-199) are the SOLE writers — calling `gate.check()` exercises both. `UsageQueryService` reads same bucket keys (verified in debug doc `.planning/debug/usage-counter-not-incrementing.md`). |
</phase_requirements>

## Summary

Bug-fix phase. Root cause already pinned at `.planning/debug/usage-counter-not-incrementing.md`: TUS upload completion path bypasses `FreeTierGate.check()`, so the four free-tier policy guards plus the two usage counter buckets never fire. CONTEXT.md is comprehensive — file paths, line numbers, byte-mirror mandate, defensive cleanup contract all locked. Research deliverable is therefore a planner-ready map of (a) every observable post-fix behaviour the test suite must prove, (b) the failure modes that can leak between gate-pass and background-task-scheduled, and (c) the exact pytest fixture shape — building on the existing `tests/integration/test_free_tier_gate.py` pattern.

**Primary recommendation:** Drive `UploadSessionService.start_transcription(...)` directly with a tmp DB + mocked audio pipeline + tmp file on disk. Skip TUS protocol simulation entirely (no Tus-Resumable headers, no chunk POSTs). Mirror the slim-app fixture shape from `tests/integration/test_free_tier_gate.py:89-237` for ORM user seeding and `_set_plan_tier` helpers.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|--------------|----------------|-----------|
| Resolve authenticated user for TUS PATCH | API / Backend (Depends chain) | — | `authenticated_user` Depends already resolves before `get_scoped_task_repository` — root-cause analysis confirmed. Hook just doesn't currently inject the resolved user. |
| Enforce free-tier policy for TUS uploads | API / Backend (FreeTierGate) | — | `FreeTierGate.check()` is the SINGLE policy-enforcement point. Lives at the API boundary, before persistence. |
| Persist task with `user_id` ownership | API / Backend (DomainTask construction) | Database | Constructor-injection of `user.id`; `repository.add(task)` writes the row. Same idiom as `audio_api.py:141`. |
| Release concurrency slot on completion | Worker / Background (process_audio_common try/finally) | API / Backend (FreeTierGate.release_concurrency) | Generic helper `_release_slot_if_authed` at `whisperx_wrapper_service.py:302-322` already handles this once `task.user_id` is non-null. |
| Defensive slot-release on synchronous failure | API / Backend (start_transcription try/except) | — | NEW. `audio_api.py` doesn't need this because it doesn't move/rename a file before task creation; TUS does (`shutil.move` at line 90). Slot-leak protection lives ONLY at the TUS site. |

## Standard Stack

### Core (already installed — verified `pyproject.toml`)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `fastapi` | 0.128.0 | Web framework + Depends DI | Existing project framework |
| `tuspyserver` | 4.2.3 | TUS protocol router with `upload_complete_dep` Depends-factory hook | Existing project dependency; hook contract verified at `.venv/Lib/site-packages/tuspyserver/router.py:39-71` and invocation at `routes/core.py:193, 277-282` |
| `pytest` | 9.0.2 | Test runner | Project standard for backend tests |
| `sqlalchemy` (sessionmaker) | (existing) | tmp test DB binding | Existing test pattern in `test_free_tier_gate.py:89-102` |

No new dependencies. All wiring uses existing stack. **[VERIFIED: pyproject.toml lines 31, 41, 66 + grep of tuspyserver source]**

### Already in Project (Reuse)

| Component | Purpose | Source Location |
|-----------|---------|-----------------|
| `FreeTierGate.check()` | Public 6-gate fail-fast contract | `app/services/free_tier_gate.py:84-111` |
| `FreeTierGate.release_concurrency()` | Slot refund (already idempotent — `RateLimitService.release` no-ops on missing bucket) | `app/services/free_tier_gate.py:119-133`; `app/services/auth/rate_limit_service.py:53-88` |
| `get_free_tier_gate` Depends provider | Built per-request, chains off `get_rate_limit_service` → `get_rate_limit_repository` → `get_db` | `app/api/dependencies.py:159-163` |
| `authenticated_user` Depends | Resolves bearer-then-cookie; raises 401 on failure (already chained by `get_scoped_task_repository`) | `app/api/dependencies.py:318-337` |
| `_release_slot_if_authed` flat-guard | Reads completed task, looks up user, releases slot — already wired into `process_audio_common` finally | `app/services/whisperx_wrapper_service.py:302-322`, called at line 619 |
| Exception handlers (429/403/402) | `rate_limit_exceeded_handler`, `concurrency_limit_handler`, `free_tier_violation_handler`, `trial_expired_handler` — registered globally in `app/main.py:209-213` | `app/api/exception_handlers.py:230-303` |

## Architecture Patterns

### Data Flow (Post-Fix)

```
Client TUS PATCH (final chunk)
    ↓
tuspyserver core_route assembles file → invokes options.upload_complete_dep
    ↓ (FastAPI resolves Depends chain in this order)
get_db → get_rate_limit_repository → get_rate_limit_service → get_free_tier_gate
get_db → get_user_repository (via _resolve_*) → authenticated_user → get_scoped_task_repository
    ↓
create_upload_complete_hook(background_tasks, repository, user, free_tier_gate)
    ↓ returns
async handler(file_path, metadata)
    ↓
UploadSessionService(repository, user, free_tier_gate).start_transcription(...)
    │
    ├─ 1. Magic-bytes validate    [bad → ValueError, NO rate charge]
    ├─ 2. shutil.move (rename)
    ├─ 3. process_audio_file + get_audio_duration
    ├─ 4. free_tier_gate.check(user, audio_duration, "tiny", False)   ← INSERT POINT
    │       [trial expired → TrialExpiredError → 402]
    │       [hourly cap → RateLimitExceededError → 429 + Retry-After]
    │       [file too long → FreeTierViolationError → 403]
    │       [concurrency held → ConcurrencyLimitError → 429]
    ├─ 5. DomainTask(uuid, ..., user_id=int(user.id) if user.id else None)
    ├─ 6. try:
    │       repository.add(task)
    │       background_tasks.add_task(process_audio_common, params)
    │     except Exception:
    │       free_tier_gate.release_concurrency(user)  ← defensive (slot already taken by check)
    │       Path(renamed_path).unlink(missing_ok=True)
    │       raise
    │
    ↓ (background)
process_audio_common(params)
    │
    ├─ try: transcribe → align → diarize → ...
    ├─ except: log + repo.update(failed)
    └─ finally:
         _release_slot_if_authed(repo, user_repo, params.identifier, gate)
              ├─ repo.get_by_id(identifier) → completed_task
              ├─ if task.user_id is None: return  ← was the bug; now non-null
              ├─ user_repo.get_by_id(task.user_id) → user
              └─ gate.release_concurrency(user)   ← W1 invariant restored
```

### Pattern 1: Depends-Factory Composition for tuspyserver Hook

**What:** Extend `create_upload_complete_hook` signature with the two new Depends. tuspyserver invokes the factory via FastAPI DI (verified at `tuspyserver/router.py:18-19, 39-40` and `routes/core.py:193`).
**When to use:** Any time a tuspyserver upload completion hook needs request-scoped services.
**Source:** Phase 7 RESEARCH.md (`.planning/phases/07-backend-chunk-infrastructure/07-RESEARCH.md` lines 66-95) documents this pattern as the standard approach. CONTEXT.md decision lock confirms.

```python
# Source: app/api/tus_upload_api.py (post-fix shape — derived from CONTEXT.md decision)
from app.api.dependencies import (
    authenticated_user,
    get_free_tier_gate,
    get_scoped_task_repository,
)
from app.domain.entities.user import User
from app.services.free_tier_gate import FreeTierGate

async def create_upload_complete_hook(
    background_tasks: BackgroundTasks,
    repository: ITaskRepository = Depends(get_scoped_task_repository),
    user: User = Depends(authenticated_user),
    free_tier_gate: FreeTierGate = Depends(get_free_tier_gate),
):
    service = UploadSessionService(repository, user, free_tier_gate)
    async def handler(file_path: str, metadata: dict) -> None:
        await service.start_transcription(file_path, metadata, background_tasks)
    return handler
```

### Pattern 2: Byte-Mirror gate.check Invocation

**What:** Same kwarg shape, same ordering relative to audio_duration measurement.
**Source:** `app/api/audio_api.py:117-122` (canonical) — verified.

```python
# audio_api.py:117-122  (canonical reference)
free_tier_gate.check(
    user=user,
    file_seconds=audio_duration,
    model=model_params.model.value,        # "tiny" / "small" / etc.
    diarize=diarize_requested,             # bool
)

# upload_session_service.py  (post-fix — DRY mirror)
free_tier_gate.check(
    user=self._user,
    file_seconds=audio_duration,
    model=WhisperModel.tiny.value,         # hardcoded — TUS metadata has no model field in v1.2
    diarize=False,                         # hardcoded — TUS metadata has no diarize field in v1.2
)
```

`WhisperModel.tiny.value == "tiny"` — verified at `app/schemas/core_schemas.py:177`. `"tiny"` is in `FREE_POLICY.allowed_models` (= `frozenset({"tiny", "small"})`) — verified at `app/core/plan_tiers.py:44`.

### Pattern 3: Constructor-Injected Service with User + Gate

**What:** Promote `UploadSessionService` from `(repository)` to `(repository, user, free_tier_gate)`. Service stays request-scoped (one user per instance — SRP).

```python
# upload_session_service.py  (post-fix shape)
class UploadSessionService:
    def __init__(
        self,
        repository: ITaskRepository,
        user: User,
        free_tier_gate: FreeTierGate,
    ) -> None:
        self._repository = repository
        self._user = user
        self._free_tier_gate = free_tier_gate
```

### Anti-Patterns to Avoid

- **Calling `gate.check()` BEFORE magic-bytes validation** — invalid uploads would consume the user's hour quota. Order: magic-bytes → rename → audio_duration → gate.check → task.add. (Matches CONTEXT.md decision.)
- **Calling `gate.check()` AFTER `repository.add(task)`** — task row exists in DB but free-tier policy not yet checked; orphan tasks on policy reject. Audio_api.py order (gate before add) is canonical.
- **Re-implementing slot release in TUS path** — `_release_slot_if_authed` at `whisperx_wrapper_service.py:302-322` is generic; it auto-works once `task.user_id` is non-null. Adding a TUS-specific release would violate DRY.
- **Catching `RateLimitExceededError` in `start_transcription`** — must re-raise so the global FastAPI handler (`rate_limit_exceeded_handler`) sets 429 + Retry-After on the TUS PATCH response. Same for the other three policy exceptions.
- **Hardcoding `model="tiny"` as a magic string** — reuse `WhisperModel.tiny.value` (already imported in `upload_session_service.py:32`).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Concurrency slot release on background completion | TUS-specific finally hook | Existing `_release_slot_if_authed` in `process_audio_common` finally | Generic helper already wired; auto-handles once `task.user_id` set |
| 429/403/402 response shaping for TUS PATCH | TUS-specific exception handler | Globally registered handlers in `app/main.py:209-213` | Handlers match exception class globally; tuspyserver hook exception propagates naturally (verified at `tuspyserver/routes/core.py:279-282` — `await result` re-raises) |
| Bucket key derivation (`user:{id}:tx:hour` etc.) | Inline string format | `FreeTierGate._check_hourly_rate` / `_check_daily_minutes` already own the format | DRY — never re-derive; tests assert on these private bucket keys directly |
| User resolution from request | New auth helper | `authenticated_user` Depends | Already 401s anonymous through tuspyserver hook chain (verified in debug doc) |
| File-path cleanup on slot-leak | Inline shutil.rmtree | `Path(renamed_path).unlink(missing_ok=True)` | stdlib idempotent delete; defensive cleanup must not raise |

**Key insight:** The fix is overwhelmingly composition of existing pieces. Every component is already wired, exposed, and battle-tested. The bug is one missing wire.

## Failure-Mode Catalog (Phase-Specific)

These are the exact landmines the plan + tests must guard against. Each is mapped to a defensive measure.

### F1. Slot leak between gate-pass and background-task-scheduled

**What goes wrong:** `gate.check()` consumes the concurrency token (last sub-check at `_check_concurrency`). Then `repository.add(task)` raises (e.g., DB constraint, transient SQLite lock, or the ORM-mapper raises on a malformed metadata field). `background_tasks.add_task` never fires. `process_audio_common`'s try/finally never runs. Slot stays consumed → user locked out (1 free / 3 pro) until token-bucket auto-refill (rate=0 means **never** for concurrency).
**Why it happens:** Concurrency bucket is `rate=0.0` — only `release_concurrency()` refunds it (`free_tier_gate.py:202-212` comment "release is the only path back to a full bucket (W1)").
**Defensive measure:** Wrap step 5+6 (DomainTask construct → repository.add → background_tasks.add_task) in try/except. On any exception: `free_tier_gate.release_concurrency(user)` AND `Path(renamed_path).unlink(missing_ok=True)`, then re-raise.
**Test:** `test_tus_slot_released_when_repository_add_raises` — monkeypatch `repository.add` to raise `RuntimeError`; assert `_check_concurrency` is reusable afterward (i.e., bucket back to capacity=1).

### F2. File orphan when gate.check rejects

**What goes wrong:** Magic-bytes pass → `shutil.move` renames → `audio_duration` measured → `gate.check` raises (e.g., `RateLimitExceededError` on 6th transcribe). The renamed file sits forever in `TUS_UPLOAD_DIR/tus/` since the cleanup scheduler only sweeps stale TUS sessions, not post-rename files.
**Why it happens:** `shutil.move` happens BEFORE the gate (necessary for ffmpeg to read the right extension). Gate rejection mid-stream leaves a renamed file on disk.
**Defensive measure:** Must be inside the SAME try/except as F1 — gate exception path also deletes file. Critical: the try MUST start at `shutil.move` (or earlier if `process_audio_file` writes temp artifacts), NOT at `repository.add`. CONTEXT.md decision is explicit: cleanup on "any failure between gate-pass and `background_tasks.add_task`" — but a stricter read says cleanup-on-gate-reject is also required.

> **OPEN QUESTION (Q1):** CONTEXT.md says "any failure between gate-pass and `background_tasks.add_task`". This semantically excludes gate-reject itself. Strict mirror of `audio_api.py` would NOT delete the file on gate-reject (audio_api doesn't have a renamed file). For TUS, file is already on disk; not deleting on gate-reject means free-tier abuser's file accumulates per attempt. **Recommendation:** Plan SHOULD wrap from `shutil.move` onward (including the gate.check call) so gate-reject also cleans the file. Mark for plan-checker confirmation. **[ASSUMED]** based on operational hygiene — needs user/planner sign-off.

### F3. `task.user_id` left None → slot never released

**What goes wrong:** Forget to set `task.user_id = int(user.id) if user.id is not None else None` in `DomainTask(...)` constructor. `_release_slot_if_authed` does `if completed_task.user_id is None: return` (`whisperx_wrapper_service.py:317`). Slot never refunded. Same end-state as F1 even on the success path.
**Why it happens:** Easy to miss — current code at `upload_session_service.py:106-114` does NOT pass `user_id` to `DomainTask`.
**Defensive measure:** Byte-mirror `audio_api.py:141`. Test asserts the persisted task row has `user_id == registered_user_id`.
**Test:** `test_tus_task_persisted_with_user_id` — read back `tasks.user_id` from tmp DB after `start_transcription` returns.

### F4. Re-entrant Depends resolution (FastAPI dep cache)

**What goes wrong:** `get_db` is yielded ONCE per request and shared across the dep graph (`dependencies.py:55-83` "ONE Session per request" lock). If the new factory shape accidentally constructs a SECOND `Session` (e.g., by importing a service that builds its own), the rate-limit consume + the task add commit on different sessions → "consumed token but task missing" inconsistency on rollback.
**Why it happens:** Subtle DI mistake.
**Defensive measure:** New deps in `create_upload_complete_hook` MUST chain off the existing providers (`get_free_tier_gate`, `authenticated_user`) — never construct services inline. Verified providers chain correctly: `get_free_tier_gate(Depends(get_rate_limit_service))` → `get_rate_limit_service(Depends(get_rate_limit_repository))` → `get_rate_limit_repository(Depends(get_db))`. Same Session as `get_scoped_task_repository`.
**Test:** Existing `tests/integration/test_no_session_leak.py` invariant covers this for the rest of the app — extend by adding TUS-path coverage if practical.

### F5. tuspyserver swallows hook exception

**What goes wrong:** Hook raises `RateLimitExceededError` but tuspyserver wraps/eats it → TUS PATCH returns 204 (success) instead of 429.
**Why it happens (NOT happening here — verified):** `tuspyserver/routes/core.py:279-282`:
```python
result = on_complete(file_path, file.info.metadata)
if inspect.isawaitable(result):
    await result
```
`await result` propagates exceptions naturally. No try/except wraps this in tuspyserver. FastAPI's exception handlers catch downstream. **[VERIFIED: read of `.venv/Lib/site-packages/tuspyserver/routes/core.py` lines 276-284]**
**Defensive measure:** No mitigation needed — natural exception propagation works. Test confirms.
**Test:** `test_tus_hourly_cap_returns_429_via_patch` (optional — slower; primary coverage via direct `start_transcription` call).

### F6. Duplicate `gate.check` if magic-validate also calls it

**What goes wrong:** Audit reveals that some validator earlier in the chain already calls `gate.check` (would double-charge the hour bucket).
**Audit result (verified):** Grep for `free_tier_gate` / `FreeTierGate` across `app/`:
- `app/api/audio_api.py` (2 sites — `:117` and `:219` — direct paths only)
- `app/api/dependencies.py` (provider only)
- `app/services/free_tier_gate.py` (definition)
- `app/services/whisperx_wrapper_service.py` (release on completion)
- Tests + CONTEXT files

No call site in `tus_upload_api.py`, `upload_session_service.py`, or `magic_validator.py`. Single insertion point — no duplicate risk. **[VERIFIED: grep output, debug doc Eliminated section]**

### F7. Stale concurrency slot on hard crash

**What goes wrong:** Server crashes between `gate.check` and `process_audio_common` start. Slot row in DB is "consumed" forever.
**Why it happens:** Rate-limit storage is durable SQLite — survives restart.
**Defensive measure:** Out of scope for this phase. Mitigation is operational (cleanup script or admin tool). Pre-existing for direct-upload path; TUS introduces no new exposure. Note for plan: the defensive try/except in F1 covers in-process exceptions but NOT process death.

### F8. Pro-user diarize=True silently downgraded

**What goes wrong:** A pro user uploads via TUS; CONTEXT decision hardcodes `diarize=False`. The upload succeeds but transcription doesn't diarize — silent feature loss.
**Why it happens:** TUS metadata has no diarize field in v1.2 (CONTEXT-locked decision).
**Defensive measure:** Accepted limitation — flagged for "Deferred Ideas" in CONTEXT.md. Not a regression for free users (who can't diarize anyway). Pro-user TUS-with-diarize is a deferred forward-compat item.

### F9. WhisperModel hardcoded to "tiny" overrides pro user's allowed models

**What goes wrong:** Pro user wants `large-v3` via TUS — but TUS path hardcodes `tiny`. Same as F8 — TUS metadata has no model field in v1.2.
**Defensive measure:** Accepted limitation — deferred. Tests should NOT pin pro-user model selection through TUS (would block forward-compat).

## Pattern Reuse Audit

| Direct-upload site | TUS-path equivalent | Notes |
|---------------------|---------------------|-------|
| `app/api/audio_api.py:117-122` (`speech_to_text` route) | `upload_session_service.py:96` (after `audio_duration` measure) | **CANONICAL** — byte-mirror this exact call shape. |
| `app/api/audio_api.py:219-224` (`speech_to_text_url` route) | (none — TUS doesn't fetch by URL) | Same shape as audio_api.py:117 — both routes are byte-identical re: `gate.check`. The url variant is **not** "slightly different"; it differs only in pre-gate file acquisition (download vs upload) and `task.url` field assignment. Either is a valid byte-mirror reference. |
| `app/api/audio_api.py:141` (`task = DomainTask(..., user_id=int(user.id) if user.id is not None else None)`) | `upload_session_service.py:106-114` (DomainTask kwargs) | **CANONICAL** — byte-mirror. |
| `audio_api.py` does NOT need post-add try/except | TUS path requires post-gate try/except | New defensive logic — TUS path is unique because it `shutil.move`s a file before task creation. `audio_api.py` works on a temp file owned by `FileService` which has its own cleanup. |

**Conclusion:** `audio_api.py:117-141` IS the canonical reference. The url variant at line 219 is structurally identical. No competing canonical to choose between. CONTEXT.md byte-mirror mandate is unambiguous.

## Common Pitfalls

### Pitfall 1: Forgetting that `release_concurrency` requires `user.id` non-null

**What goes wrong:** Pass a user with `id=None` to `release_concurrency`. `int(user.id)` raises TypeError (`free_tier_gate.py:128`).
**Why it happens:** `User` domain entity allows `id: int | None`; only authenticated users have non-null ids in practice.
**How to avoid:** `authenticated_user` already 401s anonymous (raises HTTPException, never returns None). By the time the hook runs, `user.id` is guaranteed non-null. Defensive `int(user.id) if user.id is not None else None` in `DomainTask` construction is for the type-checker only — the None branch is unreachable in this code path.
**Warning sign:** TypeError on release path — should never fire in practice.

### Pitfall 2: SQLite "BEGIN IMMEDIATE" transaction held across `gate.check` + `repository.add`

**What goes wrong:** `RateLimitService.check_and_consume` does `repository.upsert_atomic` (commits the token consumption). Then `repository.add(task)` runs in same Session. If a second concurrent TUS request hits during this window, the second consume sees the post-consume bucket state (correct) but a different task_id race could in theory matter.
**Why it happens:** Single-Session-per-request invariant means everything shares one transaction.
**How to avoid:** No mitigation needed — the Phase 19 `get_db` invariant + `BEGIN IMMEDIATE` rate-limit semantics already serialize correctly. Tests do not need to exercise concurrent TUS uploads.

### Pitfall 3: `BackgroundTasks` lifecycle vs. exception order

**What goes wrong:** `background_tasks.add_task` schedules but does NOT execute synchronously — execution is deferred until after the response. If exception fires AFTER `add_task` but BEFORE the function returns, the task IS still scheduled (FastAPI does NOT cancel scheduled tasks on exception).
**Why it happens:** FastAPI BackgroundTasks docs: tasks run after response is sent; scheduling is just queueing.
**How to avoid:** Place `background_tasks.add_task` LAST in `start_transcription` body. Anything that can fail must run BEFORE `add_task`. CONTEXT.md try/except scope: "between gate-pass and `background_tasks.add_task`" — i.e., does NOT include `add_task` itself. Correct.
**Warning sign:** Test must NOT assert on scheduled-but-not-running tasks. Use a no-op `process_audio_common` mock.

### Pitfall 4: `_release_slot_if_authed` uses an UNSCOPED task repository

**What goes wrong:** The helper at `whisperx_wrapper_service.py:302` uses `SQLAlchemyTaskRepository(db)` (line 371 — no `set_user_scope` call) inside `process_audio_common`. If the per-user-scoped repo's `get_by_id` filtering would block the release, slot stays held.
**Verification:** Read of `whisperx_wrapper_service.py:370-372` confirms repo is intentionally unscoped here — background path is system-level and needs to find any task. **[VERIFIED]** No issue.

### Pitfall 5: Re-running `repository.set_user_scope` semantics

**What goes wrong:** `get_scoped_task_repository` calls `set_user_scope(int(user.id))`. The hook reuses this same repo. If `start_transcription` somehow constructs a second `User` or scope-mismatches, the task lookup in tests could miss.
**How to avoid:** Don't reconstruct repos. Use the injected one. Use the same `User` instance throughout.
**Warning sign:** Test reads `tasks.user_id` directly via raw SQL (bypass scope), then a separate scoped query — both should return the same row.

### Pitfall 6: Test fixture pollution from limiter / token buckets

**What goes wrong:** Token-bucket state in the tmp DB persists across tests in the same fixture lifecycle. A test that consumes 5/5 hour tokens then yields to next test sees a depleted bucket.
**How to avoid:** `tmp_db_url` fixture in `test_free_tier_gate.py:90-96` rebuilds the schema per-test (`Base.metadata.create_all`). Reuse this exact pattern. Each test gets a fresh DB.

## Test Strategy

### File: `tests/integration/test_tus_upload_increments_usage.py`

**Approach:** Direct `UploadSessionService.start_transcription` driver — no TUS protocol. Mirror `tests/integration/test_free_tier_gate.py` fixture shape (`tmp_db_url`, `session_factory`, `audio_ctrl`, ORM user seeding via `_set_plan_tier`).

### Fixture Plan

```python
# Reused verbatim from test_free_tier_gate.py
@pytest.fixture
def tmp_db_url(tmp_path) -> str: ...               # tmp SQLite + Base.metadata.create_all
@pytest.fixture
def session_factory(tmp_db_url) -> sessionmaker: ...
@pytest.fixture
def audio_ctrl() -> _AudioDurationController: ...  # swap audio_duration per-test

# NEW for TUS — minimal additions
@pytest.fixture
def tmp_upload_file(tmp_path) -> Path:
    """Create a tmp file with valid magic bytes (RIFF...WAVE for .wav)."""
    p = tmp_path / "fake_tus_uuid"
    p.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfmt ")  # minimal valid WAV magic
    return p

@pytest.fixture
def free_user(session_factory) -> tuple[User, int]:
    """Insert a free-tier User; return (domain_user, user_id)."""
    user_id = 9001
    with session_factory() as s:
        s.add(ORMUser(id=user_id, email="t@x.com", password_hash="x", plan_tier="free"))
        s.commit()
    return DUser(id=user_id, email="t@x.com", password_hash="x", plan_tier="free"), user_id

@pytest.fixture
def upload_service(session_factory, free_user, monkeypatch) -> UploadSessionService:
    """UploadSessionService bound to tmp DB + mocked audio pipeline."""
    monkeypatch.setattr(
        "app.services.upload_session_service.process_audio_file",
        lambda _p: np.zeros(16000, dtype=np.float32),
    )
    monkeypatch.setattr(
        "app.services.upload_session_service.get_audio_duration",
        lambda _a: audio_ctrl.value,
    )
    monkeypatch.setattr(
        "app.services.upload_session_service.validate_magic_bytes",
        lambda _p, _ext: (True, "ok", None),
    )
    monkeypatch.setattr(
        "app.services.upload_session_service.process_audio_common",
        lambda *_a, **_k: None,  # background no-op
    )
    user, _ = free_user
    repo = SQLAlchemyTaskRepository(session_factory())
    repo.set_user_scope(int(user.id))
    rls = RateLimitService(SQLAlchemyRateLimitRepository(session_factory()))
    gate = FreeTierGate(rate_limit_service=rls)
    return UploadSessionService(repository=repo, user=user, free_tier_gate=gate)
```

### Direct Bucket-State Reads (Test Assertions)

```python
def _read_bucket_tokens(session_factory, bucket_key: str) -> int | None:
    """Read raw token count for a bucket key; None if bucket absent."""
    with session_factory() as s:
        row = s.execute(
            text("SELECT tokens FROM rate_limit_buckets WHERE bucket_key = :k"),
            {"k": bucket_key},
        ).scalar()
    return row  # None if absent (bucket never written)
```

This is the assertion primitive for proving counter increments. Capacity for free-tier hour bucket = 5; tokens=4 means 1 consumed; tokens=5 means 0 consumed.

### Driving start_transcription Directly

```python
async def _drive(service, file_path, *, taskid="t1", filename="x.wav"):
    bg = BackgroundTasks()
    return await service.start_transcription(
        str(file_path),
        {"filename": filename, "taskId": taskid},
        bg,
    )
```

No TestClient, no TUS PATCH simulation. `start_transcription` returns the task identifier on success; raises on failure.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (line 153) |
| Quick run command | `uv run pytest tests/integration/test_tus_upload_increments_usage.py -x` |
| Full suite command | `uv run pytest -x -m "integration or unit"` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|--------------|
| REQ-USAGE-TUS-COUNTER | After 1 TUS transcribe, `user:{id}:tx:hour` bucket tokens = capacity − 1 (i.e., 4 of 5) | integration | `pytest tests/integration/test_tus_upload_increments_usage.py::test_hour_bucket_decremented_on_tus_transcribe -x` | ❌ Wave 0 |
| REQ-USAGE-TUS-COUNTER | After 1 TUS transcribe of N-second audio, `user:{id}:audio_min:day` bucket tokens = capacity − max(1, int(N/60)) | integration | `pytest tests/integration/test_tus_upload_increments_usage.py::test_daily_minutes_bucket_decremented_by_floor_minutes -x` | ❌ Wave 0 |
| REQ-FREETIER-TUS | 6th TUS transcribe of free user raises `RateLimitExceededError` (hourly cap = 5) | integration | `pytest tests/integration/test_tus_upload_increments_usage.py::test_free_user_6th_tus_transcribe_raises_rate_limit -x` | ❌ Wave 0 |
| REQ-FREETIER-TUS | TUS upload of file > 300s for free user raises `FreeTierViolationError` | integration | `pytest tests/integration/test_tus_upload_increments_usage.py::test_free_user_long_file_raises_free_tier_violation -x` | ❌ Wave 0 |
| REQ-FREETIER-TUS | 30-min daily cap blocks 6th 5-min file via TUS (tokens_needed=5 each → 6th would need 5 of 0 remaining) | integration | `pytest tests/integration/test_tus_upload_increments_usage.py::test_free_user_daily_audio_cap_blocks_via_tus -x` | ❌ Wave 0 |
| REQ-FREETIER-TUS | Concurrent TUS upload (slot held) raises `ConcurrencyLimitError` | integration | `pytest tests/integration/test_tus_upload_increments_usage.py::test_free_user_concurrency_slot_blocks_second_tus -x` | ❌ Wave 0 |
| REQ-FREETIER-TUS | `task.user_id` is set to authenticated user's id on persisted DomainTask | integration | `pytest tests/integration/test_tus_upload_increments_usage.py::test_tus_task_persisted_with_user_id -x` | ❌ Wave 0 |
| REQ-FREETIER-TUS | When `repository.add` raises post-gate, slot is released AND renamed file is deleted | integration | `pytest tests/integration/test_tus_upload_increments_usage.py::test_slot_and_file_released_on_repository_add_failure -x` | ❌ Wave 0 |
| REQ-FREETIER-TUS | When magic-bytes validation fails, NO rate-limit charge occurs (anti-abuse) | integration | `pytest tests/integration/test_tus_upload_increments_usage.py::test_invalid_magic_bytes_does_not_charge_rate_limit -x` | ❌ Wave 0 |
| REQ-FREETIER-TUS | All existing direct-upload tests in `test_free_tier_gate.py` still pass (regression) | integration | `pytest tests/integration/test_free_tier_gate.py -x` | ✅ exists |
| REQ-FREETIER-TUS | `_release_slot_if_authed` correctly refunds the slot for a TUS task once `task.user_id` is set (success path) | integration | `pytest tests/integration/test_tus_upload_increments_usage.py::test_slot_released_via_process_audio_common_finally_for_tus_task -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `uv run pytest tests/integration/test_tus_upload_increments_usage.py tests/integration/test_free_tier_gate.py -x` (~5-15s)
- **Per wave merge:** `uv run pytest -x -m integration` (full integration suite)
- **Phase gate:** Full suite (`uv run pytest -x`) green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/integration/test_tus_upload_increments_usage.py` — covers REQ-FREETIER-TUS + REQ-USAGE-TUS-COUNTER (11 test functions enumerated above)
- [ ] No new framework install needed (pytest 9.0.2 already in `pyproject.toml`)
- [ ] No new shared fixtures needed at conftest.py level — fixtures are file-local; reuse `tmp_db_url` / `session_factory` / `audio_ctrl` patterns from `test_free_tier_gate.py:89-237` (copy or refactor to `tests/integration/conftest.py` if duplication becomes painful — at Claude's discretion)

## Project Constraints (from CLAUDE.md)

| Directive | Implication for this Phase |
|-----------|----------------------------|
| Backend uses `uv` for venv, pytest as runner | Use `uv run pytest` in all sampling commands |
| **DRY** — single source of truth | Byte-mirror `audio_api.py:117-141`; reuse `WhisperModel.tiny.value`; reuse `_release_slot_if_authed`; do NOT re-derive bucket key strings |
| **SRP** — service ≠ transport ≠ orchestration | `UploadSessionService` stays orchestration; `FreeTierGate` stays gating; `process_audio_common` stays background |
| **Tiger-style** — assert at boundaries | Tests assert pre-state (bucket = capacity) AND post-state (bucket = capacity − consumed) |
| **No nested-if spaghetti** — early-return / early-throw | Defensive try/except in `start_transcription`: catch → release → unlink → re-raise (flat) |
| **Self-explanatory names** | Test names like `test_free_user_6th_tus_transcribe_raises_rate_limit`, fixtures like `tmp_upload_file`, `free_user`, `upload_service` |
| **Subtype-first error handling** | `RateLimitExceededError` and `ConcurrencyLimitError` are siblings (not subclass) — order does not matter, but in `start_transcription` defensive except, catch broad `Exception` then re-raise (per CONTEXT decision) |

## Runtime State Inventory

> Bug-fix wiring phase. Not a rename / refactor / migration. **Skipped** per Step 2.5 conditional.

## Environment Availability

> Bug-fix is purely code-and-test changes. No new external dependencies, runtimes, services, or CLIs introduced beyond what already runs the project. **Skipped** per Step 2.6 conditional.

## Security Domain

This phase tightens an existing free-tier policy escape hole. Security implications are intrinsically positive — closing the hole brings TUS path to parity with `/speech-to-text` enforcement.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|------------------|
| V2 Authentication | yes | `authenticated_user` Depends — already wired through tuspyserver hook chain (verified) |
| V4 Access Control | yes | `FreeTierGate.check()` — applies plan-tier policy to authenticated user |
| V5 Input Validation | yes | `validate_magic_bytes` runs FIRST (anti-abuse: invalid uploads do NOT consume rate-limit quota) |
| V11 Business Logic | yes | Hourly + daily caps + concurrency slot — closing the bypass restores intended business policy |

### Known Threat Patterns for FastAPI + tuspyserver

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Anonymous TUS upload | Spoofing | `authenticated_user` 401s before hook fires (verified — root-cause analysis confirmed Depends chain resolves) |
| Rate-limit bypass via alternate upload route | Elevation of Privilege | This phase's fix — wire same gate into both routes |
| File-duration policy bypass via TUS | Information Disclosure (uses unbounded compute) | Closed by `gate.check(file_seconds=audio_duration)` — measured AFTER ffmpeg decode |
| Slot leak / starvation | Denial of Service (self-inflicted lockout) | Defensive try/except + idempotent `release_concurrency` |
| Invalid file consumes hour quota | Denial of Service (anti-abuse) | Magic-bytes validation FIRST; gate runs only on valid files |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Plan SHOULD wrap try/except from `shutil.move` onward (not just from `gate.check` onward), so gate-reject also deletes the renamed file | F2 (failure-mode catalog) | If left strictly as CONTEXT-worded ("between gate-pass and `add_task`"), gate-rejected uploads leak files on disk. Operational hygiene impact only — no functional regression. Recommend planner confirm or escalate to user. |

**All other claims are tagged [VERIFIED] (code read, grep, tuspyserver source inspection) or [CITED] (CONTEXT.md decision-locked, debug doc, project Phase 7 RESEARCH.md).** A1 is the sole [ASSUMED] item.

## Open Questions

1. **Try/except scope: gate.check inclusive or exclusive?** (See A1 + F2.)
   - What we know: CONTEXT.md says "any failure between gate-pass and `background_tasks.add_task`" — strict reading excludes gate-reject itself. But gate-reject leaves a renamed file on disk.
   - What's unclear: Whether file-cleanup-on-gate-reject is in or out of phase scope.
   - Recommendation: Plan should include cleanup-on-gate-reject (i.e., wrap from `shutil.move` onward). Mark for plan-checker / discuss-phase confirmation if reviewer disagrees.

## Sources

### Primary (HIGH confidence — direct code/file reads in this session)

- **CONTEXT.md** (`.planning/phases/20-tus-free-tier-gate-wiring-counter-repair/20-CONTEXT.md`) — locked decisions, byte-mirror mandate, defensive cleanup contract
- **Debug root-cause doc** (`.planning/debug/usage-counter-not-incrementing.md`) — confirmed bypass is single-call missing-wire
- **`app/api/audio_api.py`** lines 117-122, 141, 219-224 — canonical byte-mirror reference
- **`app/api/tus_upload_api.py`** lines 23-51, 55-61 — single edit site for hook signature
- **`app/services/upload_session_service.py`** lines 38-180 — single edit site for service constructor + start_transcription body
- **`app/api/dependencies.py`** lines 159-163 (`get_free_tier_gate`), 318-337 (`authenticated_user`), 355-367 (`get_scoped_task_repository`) — DI chain verified
- **`app/services/free_tier_gate.py`** lines 84-111 (`check`), 119-133 (`release_concurrency`), 148-212 (private guards including `_check_hourly_rate`, `_check_daily_minutes`, `_check_concurrency`) — public contract + bucket key formats
- **`app/services/whisperx_wrapper_service.py`** lines 302-322 (`_release_slot_if_authed`), 370-377 (worker session + repo), 541-628 (try/finally completion hook) — generic release path verified
- **`app/services/auth/rate_limit_service.py`** lines 22-88 — `check_and_consume` and `release` semantics; `release` is no-op-safe on missing bucket
- **`app/api/exception_handlers.py`** lines 230-303 — 4 handlers (402/403/429×2) registered globally in `app/main.py:209-213`
- **`app/core/plan_tiers.py`** lines 40-48 — FREE_POLICY values verified (`max_per_hour=5`, `max_file_seconds=300`, `max_daily_seconds=1800`, `allowed_models={"tiny", "small"}`, `max_concurrent=1`)
- **`app/schemas/core_schemas.py`** line 177 — `WhisperModel.tiny.value == "tiny"`
- **`tests/integration/test_free_tier_gate.py`** — fixture and test patterns to mirror (lines 89-237, 327+)
- **tuspyserver source** (`.venv/Lib/site-packages/tuspyserver/router.py:18-71`, `routes/core.py:190-284`) — verified `upload_complete_dep` Depends-factory contract + `await result` exception propagation
- **`pyproject.toml`** lines 31, 41, 66 — confirmed FastAPI 0.128.0, tuspyserver 4.2.3, pytest 9.0.2

### Secondary (MEDIUM confidence)

- **Phase 7 RESEARCH.md** (`.planning/phases/07-backend-chunk-infrastructure/07-RESEARCH.md`) lines 66-95 — TUS Depends-factory hook pattern documented as standard

### Tertiary (LOW confidence)

- None. No WebSearch / Context7 queries were necessary — all answers derived from in-repo code reads against CONTEXT-locked decisions.

## Metadata

**Confidence breakdown:**

- Standard stack: HIGH — all dependencies in-tree and verified at exact versions
- Architecture: HIGH — byte-mirror mandate + existing canonical reference; tuspyserver hook contract verified at source
- Failure modes: HIGH — root cause + defensive measures both grounded in code reads
- Test strategy: HIGH — direct port of existing `test_free_tier_gate.py` fixture pattern

**Research date:** 2026-05-06
**Valid until:** 2026-06-05 (30 days — stable area; no upstream library changes anticipated)
