---
quick_task: 260505-l2w
plan: 01
title: GET /api/usage + Usage dashboard wire-up
status: complete
completed: 2026-05-06
duration: ~50 minutes (autonomous executor)
worktree: agent-a50dc78fed90bc1de
base_commit: 267ceda8af0d71798d1de671317c4315a4cedbda
final_commit: ea68eca
commits_landed: 8
files_changed:
  new:
    - app/core/plan_tiers.py
    - app/api/schemas/usage_schemas.py
    - app/services/usage_query_service.py
    - app/api/usage_routes.py
    - tests/unit/services/test_usage_query_service.py
    - tests/integration/test_usage_routes.py
    - frontend/src/lib/api/usageApi.ts
    - frontend/src/tests/msw/usage.handlers.ts
    - frontend/src/routes/UsageDashboardPage.test.tsx
    - frontend/e2e/usage-page/01-real-data.spec.ts
  modified:
    - app/services/free_tier_gate.py
    - app/api/dependencies.py
    - app/api/__init__.py
    - app/main.py
    - app/docs/openapi.json
    - app/docs/openapi.yaml
    - frontend/src/tests/msw/handlers.ts
    - frontend/src/routes/UsageDashboardPage.tsx
    - frontend/e2e/_fixtures/mocks.ts
key_decisions:
  - extract-tier-policy-to-plan-tiers-module
  - refill-on-read-via-consume-tokens-needed-zero
  - wall-clock-reset-time-approximation
  - bucket-key-string-as-sole-scoping-mechanism
  - design-variant-horizontal-bar-quota-cards
---

# Quick Task 260505-l2w Summary

**One-liner:** Replace Phase-14 "No data yet" stub on `/dashboard/usage` with real, server-driven usage metrics via a new read-only `GET /api/usage` endpoint that surfaces token-bucket counters + trial state + plan tier; drop the earliest-API-key trial heuristic.

## Atomic Commits Landed

| # | Hash      | Type       | Subject                                                                          |
| - | --------- | ---------- | -------------------------------------------------------------------------------- |
| 1 | 5e69460   | refactor   | extract TierPolicy to app/core/plan_tiers.py (DRY single source for free-tier limits) |
| 2 | 30d9f00   | test (RED) | add failing tests for UsageQueryService                                          |
| 3 | 80f812b   | feat (GREEN)| UsageQueryService + UsageSummaryResponse schema                                 |
| 4 | 7425f4a   | test (RED) | add failing integration tests for GET /api/usage                                 |
| 5 | c8b865d   | feat (GREEN)| add GET /api/usage endpoint + regen OpenAPI                                     |
| 6 | 4deb435   | feat       | usageApi.ts + MSW usage handlers                                                 |
| 7 | c651231   | feat       | rewrite UsageDashboardPage to consume /api/usage (drop trial heuristic, drop placeholders) |
| 8 | ea68eca   | test       | playwright e2e for /dashboard/usage real-data                                    |

Eight commits — one over plan target (~9 with checkpoint waivers); two TDD pairs (Task 2 + Task 3 each ship RED then GREEN).

## Verifier-Grep Results

| # | Gate                                                                                       | Expected | Actual | Status |
| - | ------------------------------------------------------------------------------------------ | -------- | ------ | :----: |
| 1 | `grep -nE '\b5\b' app/services/free_tier_gate.py`                                          | 0 (biz)  | 0      |   OK   |
| 2 | `grep -c 'class TierPolicy' app/core/plan_tiers.py`                                        | 1        | 1      |   OK   |
| 3 | `grep -c 'class TierPolicy' app/services/free_tier_gate.py`                                | 0        | 0      |   OK   |
| 4 | `grep -c '/api/usage' app/docs/openapi.json`                                               | >= 1     | 2      |   OK   |
| 5 | `grep -c 'include_router(usage_router)' app/main.py`                                       | 1        | 1      |   OK   |
| 6 | `grep -cE '^\s+if .*\bif\b' app/services/usage_query_service.py`                           | 0        | 0      |   OK   |
| 7 | `grep -rn "No data yet" frontend/src/routes/`                                              | 0        | 0      |   OK   |
| 8 | `grep -rn "computeTrialInfo" frontend/src/`                                                | 0        | 0      |   OK   |
| 9 | `grep -nE "\b5\b\|\b30\b" frontend/src/routes/UsageDashboardPage.tsx`                      | 0        | 0      |   OK   |
| 10 | `grep -c "fetchUsageSummary" frontend/src/routes/UsageDashboardPage.tsx`                  | >= 2     | 4      |   OK   |
| 11 | `grep -c "usageHandlers" frontend/src/tests/msw/handlers.ts`                              | 1+       | 2      |   OK   |
| 12 | `grep -F "@design-variant:" frontend/src/routes/UsageDashboardPage.tsx`                   | >= 1     | 1      |   OK   |

All 12 verifier-grep gates pass.

## Test Counts

### Backend (pytest)

- **New tests:** 18
  - `tests/unit/services/test_usage_query_service.py` — 12 cases (DTO shape, refill-on-read for hour + daily buckets, refill-replays-elapsed-time, pro/trial limits, trial expires_at, missing-user 401 parity, window/day reset boundaries, read-only invariant)
  - `tests/integration/test_usage_routes.py` — 6 cases (401 unauth, no-buckets zero counts, hour-bucket real count, pro tier limits, csrf-not-required-on-GET, response shape locked)
- **Targeted re-runs (no regression):** 83/83 GREEN across `test_usage_query_service`, `test_usage_routes`, `test_free_tier_gate`, `test_account_routes`, `test_rate_limit`, `tests/unit/services/auth/*`.
- **Pre-existing failures (deferred):** 10 (audio_processing_service, task_lifecycle FK errors, jwt_attacks cookie variant on full-suite, whisperx_services GPU, test_default_values config) — tracked in `.planning/phases/{10,13,19}/deferred-items.md`. Not introduced by this task.

### Frontend (vitest)

- **New tests:** 7
  - `frontend/src/routes/UsageDashboardPage.test.tsx` — happy-path trial, free-no-trial card hidden, trial-expired Upgrade CTA, hour quota at-limit destructive, daily near-limit warn, 500 error alert, Refresh button re-fetch.
- **Full suite:** 145/145 GREEN (was 138 baseline + 7 new).

### Frontend (Playwright e2e)

- **New spec:** 1 (`frontend/e2e/usage-page/01-real-data.spec.ts`).
- **Coverage:** card numbers visible, "No data yet" copy gone, per-breakpoint screenshots (mobile/tablet/desktop) under gitignored `e2e/screenshots/usage-page/`.
- **Spec result:** GREEN.
- **Pre-existing failures (deferred):** 4 — `account-page/03-delete-account.spec.ts`, `account-page/04-logout-all-cross-tab.spec.ts`, `phase19/01-hard-reload-keeps-session.spec.ts`, `phase19/02-login-latency.spec.ts`. Verified pre-existing on base commit (`267ceda`); phase19 specs require a real backend running.

### Lint (ESLint)

- **Pre-existing baseline:** 20 errors + 2 warnings.
- **Post-task:** 20 errors + 2 warnings (unchanged — none in new files).

## Plan-Tier Limit Refactor Blast Radius (Task 1)

Sites changed:

| File                                            | Change                                                                                  |
| ----------------------------------------------- | --------------------------------------------------------------------------------------- |
| `app/core/plan_tiers.py` (NEW)                  | Single source: `TierPolicy`, `FREE_POLICY`, `PRO_POLICY`, `TRIAL_DAYS`, `policy_for()`. |
| `app/services/free_tier_gate.py`                | Replace inline dataclass + constants with `from app.core.plan_tiers import …`. `_policy_for(user)` body collapses to `return policy_for(user.plan_tier)`. Re-exports `FREE_POLICY/PRO_POLICY/TierPolicy/TRIAL_DAYS` via `__all__` for backward-compat with 7 existing call sites. |

Sites NOT changed (intentional — out of scope per CONTEXT/INPUT-PLAN):

- `frontend/src/routes/AccountPage.tsx:53` — hardcoded "5 transcribes per hour, 30 min/day" prose copy. PLAN constraint: "AccountPage.tsx:53 is OUT OF SCOPE — do not touch." Separate phase will tier-aware-ify this string.
- `app/schemas/websocket_schemas.py:85` — "transcription operations (5-30 minutes)" prose, unrelated to tier limits.
- `.env.example:135` — comment line; not load-bearing.

Magic-number grep gates (`\b5\b`, `\b30\b`) verified clean in `free_tier_gate.py`, `usage_query_service.py`, `usage_routes.py`, `UsageDashboardPage.tsx` business logic.

## Bucket Scheme Summary (replicated for future maintainers)

1. `rate_limit_buckets` schema: `(id, bucket_key UNIQUE, tokens, last_refill)`. NO `user_id` column, NO `window_start`. Scoping lives entirely in the bucket_key string.
2. Hourly transcribes: `bucket_key = f"user:{user_id}:tx:hour"`, capacity = `policy.max_per_hour` (5 free / 100 pro), rate = capacity / 3600. One token per transcribe.
3. Daily audio minutes: `bucket_key = f"user:{user_id}:audio_min:day"`, capacity = `max_daily_seconds // 60` (30 free / 600 pro), rate = capacity_minutes / 86400. `max(1, int(file_seconds/60))` tokens per transcribe.
4. Tokens are STALE on read — `UsageQueryService` MUST replay refill via `app.core.rate_limit.consume(..., tokens_needed=0, now=utcnow)` before computing derived counts. Bucket row absent => counts are zero.
5. `window_resets_at` and `day_resets_at` are wall-clock approximations (top-of-next-hour UTC; next UTC midnight). Documented divergence in service docstring; UI copy implies discrete boundaries even though token refill is continuous.

## Token-Bucket vs Wall-Clock Divergence (design tradeoff)

Token buckets refill continuously (e.g. ~1 token per 720s for free tier hourly cap). Frontend copy ("resets at HH:MM", "midnight UTC") implies discrete boundaries. The service serves wall-clock boundaries on the wire but documents in `usage_query_service.py` module docstring that this is a UI-friendly approximation, not the token-availability moment. A user with 0 tokens at 14:55 sees "resets at 15:00" — at 15:00 they actually receive a fractional refill (~1 token), with full capacity restored ~16:00. Acceptable per CONTEXT lock "use best practices, don't overcomplicate"; future polish can add a tooltip for self-resolution.

## Design Decision (Task 5 inline)

`@design-variant: horizontal-bar-quota-cards` — re-uses existing `<Progress>`, `<Card>`, `<Badge>`, `<Button>`, `<Alert>` primitives; mirrors AccountPage three-card layout idiom (max-w-2xl shell, p-6 cards, gap-4/gap-6 stack); semantic colors via wrapping div data-attrs (`data-quota-state="warn|destructive"` plus tailwind utility classes); inline `bg-muted h-N rounded animate-pulse` skeleton (no shadcn skeleton install). Picked over `radial-progress-cards` (custom SVG, premature complexity) and `compact-grid-with-progress-bars` (data-density highest but design diverges from sibling pages). Tiebreaker: CONTEXT meta lock "use best practices, don't overcomplicate."

## Manual UAT Outcome

**Not executed in this autonomous-executor pass.** PLAN Task 8 lists a manual UAT checklist (start backend `uv run uvicorn`, sign in as trial user, navigate `/dashboard/usage`, observe real numbers, run a transcribe, click Refresh, confirm hour count incremented; optionally flip `plan_tier='pro'` and observe pro limits). Operator should run this prior to merging. Automated coverage spans the same surface via vitest + playwright + pytest, but the live transcribe-then-Refresh roundtrip requires a real backend + worker.

## Outstanding Blockers / Follow-ups

- **`/pricing` route does not exist** — Trial-expired Upgrade CTA navigates to `/pricing`; 404 acceptable per CONTEXT lock. Separate phase ships pricing.
- **AccountPage.tsx:53 hardcoded copy** — Out of scope per PLAN constraint; tier-aware version is a future quick task.
- **"Files up to 5 minutes, tiny & small models" suffix** — Intentionally dropped from UsageDashboardPage (RESEARCH §52 lock). Plan-tier policies still enforce file_seconds + model allowlists at the gate layer; the page no longer surfaces those limits as prose. Future polish can wire them through the response schema.
- **Pre-existing test failures** — 10 backend + 4 e2e (deferred-items.md). Not regression caused by this task; future test-housekeeping plan owns resolution.
- **Lint baseline** — 20 pre-existing ESLint errors unchanged; future plan owns cleanup.
- **Phase 19 manual verifications still outstanding** — hard-reload + login-latency e2e (`phase19/`) need a real backend; not addressable from this autonomous run.

## Self-Check: PASSED

Verified:
- All 10 new files exist on disk under expected paths.
- All 8 commits exist on `worktree-agent-a50dc78fed90bc1de` branch.
- All 12 verifier-grep gates clean.
- 83/83 targeted-pytest GREEN; 145/145 vitest GREEN; 1/1 new playwright spec GREEN.
- Module docstring contains literal `@design-variant: horizontal-bar-quota-cards` marker.
