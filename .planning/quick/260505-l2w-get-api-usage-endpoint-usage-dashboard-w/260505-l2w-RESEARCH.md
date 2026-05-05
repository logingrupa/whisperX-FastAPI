---
name: 260505-l2w-RESEARCH
description: Research for GET /api/usage + Usage dashboard wire-up (focused on planner inputs)
type: research
status: ready_for_planning
---

# Research: GET /api/usage + Usage dashboard

**Researched:** 2026-05-05
**Mode:** quick-task
**Confidence:** HIGH (all findings cited to file:line in current `main`)

---

## 1. rate_limit_buckets — schema + bucket scheme

**Schema** (`app/infrastructure/database/models.py:419-442`): `id` (PK autoincrement), `bucket_key` (str, UNIQUE), `tokens` (int), `last_refill` (DateTime tz-aware UTC). **Single composite key only — no `user_id` column, no `window_start`, no `window_kind`.** All scoping is encoded in the `bucket_key` string.

**Buckets are token buckets, NOT window buckets.** `app/core/rate_limit.py:26-51` `consume()` does continuous refill: `refilled = min(capacity, tokens + elapsed_seconds * rate)`. There is no "window_start" timestamp anywhere. `last_refill` is the last call time, not a window boundary.

**Bucket keys for this user (literal strings used by `FreeTierGate`):**
- Hourly transcribe count: `f"user:{user_id}:tx:hour"` — `app/services/free_tier_gate.py:175`. Capacity = `policy.max_per_hour` (5 free / 100 pro), rate = `max_per_hour / 3600` (`free_tier_gate.py:179`). **Each transcribe consumes 1 token.**
- Daily audio minutes: `f"user:{user_id}:audio_min:day"` — `free_tier_gate.py:214`. Capacity = `max_daily_seconds // 60` (30 free / 600 pro), rate = `capacity_minutes / 86400`. **Each transcribe consumes `max(1, int(file_seconds/60))` tokens** (`free_tier_gate.py:213`).
- Concurrency slot: `f"user:{user_id}:concurrent"` — out of scope for /api/usage.

**Reconstruction formulas for the response:**
- `hour_count = max(0, hour_limit - bucket.tokens)` after applying refill at `now` (use `core.rate_limit.consume` math with `tokens_needed=0`, OR inline the refill arithmetic in the service). If row absent: `hour_count = 0`.
- `daily_minutes_used = max(0.0, float(daily_minutes_limit - bucket.tokens))` after refill. Row absent → `0.0`.
- **Refill-at-read is mandatory** — the persisted `tokens` value reflects state at the last write; reading raw `tokens` without refill overcounts after time passes.

**`window_resets_at` / `day_resets_at` are computed, not stored.** Token buckets refill continuously — there is no discrete reset boundary in the data model. Recommendations:
- `window_resets_at = now + ceil((1 - tokens_fractional) / rate_per_second)` for "time until 1 more transcribe is available," OR (simpler, matches frontend copy "resets at HH:MM") use top-of-next-hour: `now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)`.
- `day_resets_at = now.replace(hour=0, minute=0, ...) + timedelta(days=1)` (UTC midnight).
- Pick "top of clock hour" / "UTC midnight" for the wire — that's what the input-plan UI copy already implies ("resets at midnight UTC", `INPUT-PLAN.md:92`). Document the divergence (token-bucket continuous vs. wall-clock display) in the service docstring.

**Tz pitfall:** SQLite strips tzinfo from `DateTime(timezone=True)`; `app/infrastructure/database/mappers/rate_limit_bucket_mapper.py` reattaches UTC on read (locked Plan 13-08 fix). The new repo read MUST use the existing mapper — do not bypass it with raw SQL.

**Counts only — no separate `usage_events` query needed** for this endpoint. `app/services/usage_event_writer.py:42-65` writes one row per completed task into `usage_events` (user_id, gpu_seconds, file_seconds, model, idempotency_key, created_at), but **the input-plan response shape can be served entirely from `rate_limit_buckets`**: `audio_min:day` already aggregates minutes consumed today via the token-debit count. Using `usage_events` would double-source the daily-minutes number against the gate's authoritative bucket. Skip it.

---

## 2. Plan-tier limits — current call sites

`app/core/plan_tiers.py` does **NOT exist today**. Single canonical site is `app/services/free_tier_gate.py:37-77` (`TierPolicy` dataclass + `FREE_POLICY` + `PRO_POLICY` constants). `_policy_for(user)` (`free_tier_gate.py:101-104`) maps `plan_tier` → policy with a binary `pro` vs. fallthrough; **`trial` and `team` both fall through to `FREE_POLICY`**, which matches the input-plan "Trial policy: identical to free" lock (`free_tier_gate.py:7`).

**Hardcoded `5` / `30` magic-number sites:**

| file:line | code | refactor target |
|---|---|---|
| `app/services/free_tier_gate.py:59-61` | `max_per_hour=5, max_file_seconds=5*60, max_daily_seconds=30*60` | Move FREE_POLICY/PRO_POLICY constants verbatim to new `app/core/plan_tiers.py`; re-import here. |
| `frontend/src/routes/UsageDashboardPage.tsx:42` | `"Free-tier limits: 5 transcribes/hour, 30 minutes/day, files up to 5 minutes, tiny & small models."` | Drop hardcoded copy; render `hour_limit` / `daily_minutes_limit` from response (per INPUT-PLAN scope item 12). |
| `frontend/src/routes/AccountPage.tsx:53` | `"You're on the Free plan. 5 transcribes per hour, files up to 5 minutes, 30 min/day, ..."` | **Out of scope.** AccountPage is not in the input-plan files-touched list. Leave as-is — separate phase. |
| `app/schemas/websocket_schemas.py:85` | `"transcription operations (5-30 minutes)"` | Unrelated (transcription duration prose, not a limit). Leave. |
| `.env.example:135` | comment line referencing FREE_POLICY | Update comment to point at new `plan_tiers.py` if the file moves. |

**Refactor scope (per INPUT-PLAN scope item 15):** create `app/core/plan_tiers.py` exporting `TierPolicy`, `FREE_POLICY`, `PRO_POLICY`, plus a single `policy_for(plan_tier: str) -> TierPolicy` helper. Update `free_tier_gate.py` to import from there. Both `UsageQueryService` AND the existing `_check_hourly_rate` / `_check_daily_minutes` paths consume the same module — verifier: `grep -nE '\b5\b' app/services/free_tier_gate.py` returns 0 after refactor.

---

## 3. DI + repo + auth plumbing

- **`get_account_service` chain shape** — `app/api/dependencies.py:172-183`: `Depends(get_db) + Depends(get_user_repository)` → `AccountService(session=db, user_repository=user_repository)`. Mirror this exactly: `get_usage_query_service(db=Depends(get_db), user_repository=Depends(get_user_repository), rate_limit_repository=Depends(get_rate_limit_repository)) -> UsageQueryService(...)`.
- **User repo `get_by_id`** — `app/infrastructure/database/repositories/sqlalchemy_user_repository.py:46` `def get_by_id(self, identifier: int) -> DomainUser | None`. Returns the full `User` domain entity including `trial_started_at` (`app/domain/entities/user.py:39`) and `plan_tier` (line 36).
- **Rate-limit repo dep is named `get_rate_limit_repository`** — `app/api/dependencies.py:103-107`. Returns `IRateLimitRepository`. Read API: `get_by_key(bucket_key: str) -> RateLimitBucket | None` (`app/domain/repositories/rate_limit_repository.py:13`). **Already a clean read API — no new repo method needed.** Per CONTEXT "Claude's Discretion" lock, prefer reusing the existing repo over creating a new `UsageReadRepository`. The service can call `rate_limit_repository.get_by_key("user:{id}:tx:hour")` and `get_by_key("user:{id}:audio_min:day")` directly.
- **`csrf_protected` early-returns for non-state-mutating methods** — `app/api/dependencies.py:393-394`: `if request.method not in STATE_MUTATING_METHODS: return`. So adding `dependencies=[Depends(csrf_protected)]` to the router is safe and idiomatic — GET /api/usage will not require an X-CSRF-Token. Account router does the same (`app/api/account_routes.py:46-50`); GET /me passes through identically.
- **Auth dep is `authenticated_user`** — `app/api/dependencies.py:300-319`. Use as `user: User = Depends(authenticated_user)`. Returns full `User` entity.
- **Router registration:** `app/main.py:226` `app.include_router(account_router)`. Add `app.include_router(usage_router)` adjacent (e.g. line 227).

---

## 4. OpenAPI regen

**No CLI script.** `app/main.py:89` calls `save_openapi_json(app)` inside the FastAPI lifespan startup hook (`app/docs.py:15-30`). Both `app/docs/openapi.yaml` and `app/docs/openapi.json` are written automatically every time the app boots.

**Regen workflow:** start the app once after the new route lands.

```bash
uv run uvicorn app.main:app --port 8000
# wait ~3-5s for lifespan startup; ctrl+c; commit the regen'd files
```

Or for a non-server regen (cleaner for CI/commit), use the existing pattern from commit `ab32576`:

```bash
uv run python -c "from app.main import app; from app.docs import save_openapi_json; save_openapi_json(app)"
```

**Do not hand-edit `app/docs/openapi.yaml` or `app/docs/openapi.json`.** UTF-8 encoding is explicit at write-time (`app/docs.py:27`); preserved by Plan 13-10 Rule 3 fix for Windows cp1252 docstring chars.

---

## 5. Frontend integration points

- **`zod` is a frontend dep** — `frontend/package.json` `"zod": "^3.24.1"`. Confirmed. Use for response-parse boundary in `usageApi.ts`.
- **`apiClient.get` skips CSRF on GET** — `frontend/src/lib/apiClient.ts:65` only attaches `X-CSRF-Token` when `STATE_MUTATING_METHODS.has(opts.method.toUpperCase())`; GET is not in that set. Input-plan assertion verified.
- **`apiClient.get` signature** — `apiClient.ts:156-157`: `get: <T>(path, opts?: { headers?, suppress401Redirect? }) => Promise<T>`. No body, returns parsed JSON (or `undefined` for 204; not relevant here).
- **`RateLimitError` and `ApiClientError`** — `frontend/src/lib/apiErrors.ts:16-45`. Class hierarchy: `RateLimitError extends ApiClientError`. Subtype-first catch order MANDATORY (CLAUDE.md locked policy): catch `RateLimitError` BEFORE `ApiClientError` or the rate-limit branch is unreachable.
- **Re-exports for convenience:** `apiClient.ts:168` already re-exports `ApiClientError`, `AuthRequiredError`, `RateLimitError` — `usageApi.ts` can import them from `@/lib/apiClient` (DRY with sibling wrappers).
- **`signedInPage` fixture path:** `frontend/e2e/_fixtures/auth.ts:38-48`. Confirmed. Composes with `installAccountMocks` from `mocks.ts`. New e2e mock should follow the same `page.route('**/api/usage', ...)` pattern (per INPUT-PLAN scope item 13).
- **MSW barrel:** `frontend/src/tests/msw/handlers.ts` — registers `auth.handlers`, `keys.handlers`, `ws.handlers`, `transcribe.handlers`, `account.handlers`. Add `import { usageHandlers } from './usage.handlers'` and spread into the array. **Convention:** `*.handlers.ts` (plural, dot-separated), NOT `usage.ts` per the file-name pattern actually in use (input-plan §10 says `usage.ts` — this is a minor naming drift; follow the existing `.handlers.ts` convention).
- **No skeleton primitive exists** — `frontend/src/components/ui/` has button/select/badge/card/tooltip/scroll-area/sonner/progress/collapsible/input/label/form/dialog/alert/dropdown-menu but **no `skeleton.tsx`**. Per CONTEXT "Claude's Discretion" lock: use a tasteful inline pulsing div (Tailwind `animate-pulse bg-muted h-… rounded-…`). Do not run `bunx shadcn add skeleton` — out of scope.
- **`Progress` primitive exists** — `frontend/src/components/ui/progress.tsx`. Suitable for hour-quota / daily-minutes horizontal bar variant. Designer's call between bar (uses Progress) vs. radial (custom SVG, no new dep).

---

## 6. Pitfalls

**6.1 Token-bucket math is continuous, not windowed — refill MUST be applied at read time.** The persisted `tokens` value is whatever was written at the last `consume()` call (could be hours ago). Reading `tokens` raw from `rate_limit_buckets` will under-count "available" and over-count "used" once any time has passed. The `UsageQueryService` MUST replay the same refill formula `core.rate_limit.consume()` uses (or call `consume(...tokens_needed=0...)` as a no-op refill). Easiest path: pass `tokens_needed=0` to `consume()` and read the returned `new_state.tokens`. Document this loud in the service docstring; it's the single most surprise-prone behaviour for anyone who thinks the table stores window counts.

**6.2 `window_resets_at` semantics differ from token-bucket reality — pick wall-clock and document.** A token bucket has no discrete reset; tokens trickle back continuously (e.g. ~1 token per 720s for free tier). The frontend copy ("resets at HH:MM", "midnight UTC") implies discrete boundaries. Resolve by serving wall-clock boundaries (top-of-next-hour, midnight UTC) on the wire and noting in the service docstring that this is a UI-friendly approximation, not the token-availability moment. If a user has 0 tokens at 14:55 and the bar shows "resets at 15:00," they'll get **a fraction of capacity** at 15:00 (~5 tokens by 16:00 for free tier), not all 5 at the boundary. This is acceptable per "use best practices and don't overcomplicate" CONTEXT lock — but plan a one-line tooltip / sub-label so a confused user can self-resolve.

**6.3 `usage_events.task_id` is always NULL today — do NOT use `usage_events` as a daily-minutes source.** `app/services/usage_event_writer.py:52` writes `"task_id": None` (locked per Plan 13-08 — the FK is redundant for v1.2 metering). Aggregating `SELECT SUM(file_seconds)/60 FROM usage_events WHERE user_id=? AND created_at >= midnight_utc` would technically work, but it would double-source against the authoritative `audio_min:day` bucket (which is what `_check_daily_minutes` enforces) and surface drift the moment the two diverge. Stick to the bucket. `usage_events` is for v1.3 Stripe metered billing, not for the dashboard.
