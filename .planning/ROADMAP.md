# Roadmap: WhisperX

## Milestones

- ✅ **v1.0 Frontend UI** — Phases 1-6 (shipped 2026-01-29) — see [milestones/v1.0-ROADMAP.md](milestones/v1.0-ROADMAP.md)
- ✅ **v1.1 Chunked Uploads** — Phases 7-9 (shipped 2026-02-05; phase 10 Cloudflare deferred to v1.3)
- ✅ **v1.2 Multi-User Auth + API Keys + Billing-Ready** — Phases 10-19 (shipped 2026-05-05) — see [milestones/v1.2-ROADMAP.md](milestones/v1.2-ROADMAP.md)
- 📋 **v1.3** — planned (Cloudflare e2e + deferred Phase 18 stretch items + observed v1.2 close-out items) — kick off via `/gsd-new-milestone`

## Phases

<details>
<summary>✅ v1.0 Frontend UI (Phases 1-6) — SHIPPED 2026-01-29</summary>

See [milestones/v1.0-ROADMAP.md](milestones/v1.0-ROADMAP.md) for full phase details.

</details>

<details>
<summary>✅ v1.1 Chunked Uploads (Phases 7-9) — SHIPPED 2026-02-05</summary>

- [x] Phase 7: Chunked Upload Foundation — completed 2026-02-05
- [x] Phase 8: Frontend Chunking — completed 2026-02-05
- [x] Phase 9: Resilience and Polish — completed 2026-02-05

Phase 10 (Cloudflare e2e) was deferred to v1.3.

</details>

<details>
<summary>✅ v1.2 Multi-User Auth + API Keys + Billing-Ready (Phases 10-19) — SHIPPED 2026-05-05</summary>

- [x] Phase 10: Alembic Baseline + Auth Schema (4/4 plans) — completed 2026-04-29
- [x] Phase 11: Auth Core Modules + Services + DI (5/5 plans) — completed 2026-04-29
- [x] Phase 12: Admin CLI + Task Backfill (4/4 plans) — completed 2026-04-29
- [x] Phase 13: Atomic Backend Cutover (10/10 plans, atomic pair w/ 14) — completed 2026-04-29
- [x] Phase 14: Atomic Frontend Cutover + Test Infra (7/7 plans, atomic pair w/ 13) — completed 2026-04-29
- [x] Phase 15: Account Dashboard Hardening + Billing Stubs (6/6 plans) — completed 2026-04-29
- [x] Phase 16: Verification + Cross-User Matrix + E2E (6/6 plans) — completed 2026-04-30
- [x] Phase 17: Docs + Migration Runbook + Operator Guide (3/3 plans) — completed 2026-05-01
- [x] Phase 18: Stretch (Optional, closed empty — features deferred to v1.3+) — 2026-05-01
- [x] Phase 19: Auth + DI Structural Refactor (17/17 plans, 21/21 gates verified) — completed 2026-05-05

See [milestones/v1.2-ROADMAP.md](milestones/v1.2-ROADMAP.md) for full phase details.

</details>

### 📋 v1.3 (Planned)

To be defined via `/gsd-new-milestone`. Likely candidates:
- Cloudflare e2e (deferred from v1.1 phase 10)
- Phase 18 stretch items (hCaptcha enable, HaveIBeenPwned check, per-key scopes UI, per-key expiration)
- Observability for ffmpeg / external-binary dependencies
- Multi-worker rate-limit storage (slowapi → redis/limits)

## Progress

| Milestone | Phases | Status | Shipped |
|-----------|--------|--------|---------|
| v1.0 Frontend UI | 1-6 | ✅ Complete | 2026-01-29 |
| v1.1 Chunked Uploads | 7-9 | ✅ Complete | 2026-02-05 |
| v1.2 Multi-User Auth + API Keys + Billing-Ready | 10-19 | ✅ Complete | 2026-05-05 |
| v1.3 | TBD | 📋 Planned | — |

### Phase 20: TUS Free-Tier Gate Wiring + Counter Repair

**Goal:** Close the TUS upload path's bypass of `FreeTierGate.check()` so all four free-tier policies (hourly transcribe count, daily audio minutes, file duration, model whitelist, diarization gate, concurrency slot) are enforced for both `/speech-to-text` (direct upload) and `/uploads/files/` (TUS chunked upload). After fix, `/api/usage` returns non-zero counters when a user transcribes via either path.

**Why now:** Bug discovered 2026-05-06 — large file uploaded via TUS, transcription succeeded, but `/dashboard/usage` showed 0/5 hour quota and 0.0/30 daily minutes. Root cause documented at `.planning/debug/usage-counter-not-incrementing.md`: `UploadSessionService.start_transcription` schedules `process_audio_common` without invoking `FreeTierGate.check()` — the SOLE writer of the rate-limit buckets `user:{id}:tx:hour` and `user:{id}:audio_min:day` that `/api/usage` reads. Direct-upload path (`app/api/audio_api.py:117`) calls the gate correctly; TUS path bypasses it entirely.

**Side effect (bigger than cosmetic counter):** Same bypass means TUS uploads also escape `_check_file_duration` (free-tier user can transcribe unlimited-length file via TUS), `_check_model` (whitelist not enforced), `_check_diarization`, and `_check_concurrency` (slot never claimed → unbounded parallel jobs per user). This is a free-tier-policy escape hole, not just a UI bug.

**Requirements:** REQ-FREETIER-TUS, REQ-USAGE-TUS-COUNTER
**Depends on:** Phase 19 (Auth + DI refactor — `FreeTierGate` DI wiring lives there)
**Plans:** 0 plans (run `/gsd-plan-phase 20`)

**Acceptance:**
- `/api/usage` hour quota = N+1 after N+1 TUS transcribes (matches direct-upload behavior)
- `/api/usage` daily minutes increments by `floor(audio_duration / 60)` per transcribe
- 30-min daily cap blocks 6th 5-min file via TUS just like via direct upload
- File-duration cap, model whitelist, diarization gate, concurrency slot all enforced for TUS
- All existing direct-upload tests still pass

**Files (estimated):**
- `app/api/tus_upload_api.py` — extend `create_upload_complete_hook` Depends to resolve `authenticated_user` + `get_free_tier_gate`
- `app/services/upload_session_service.py` — accept `FreeTierGate` + `User`; call `free_tier_gate.check(...)` after `audio_duration` measured, before `repository.add(task)`; set `task.user_id = int(user.id)` (mirror `audio_api.py:141`)
- `app/dependencies.py` — DI wiring updates if needed
- `tests/integration/test_tus_*.py` — coverage for: TUS completion hook → counter buckets bumped → `/api/usage` returns non-zero; cap-blocking
- `frontend/e2e/` — optional Playwright regression for `/dashboard/usage` real-data display

**Threat model:** No new auth surface. Authenticated user already required at TUS PATCH time (Depends chain resolves `authenticated_user` before hook fires; otherwise 401). The fix CLOSES an existing free-tier policy bypass; it does not open a new one.

---
*Last updated: 2026-05-05 — v1.2 milestone shipped*
