# Quick Task 260505-l2w — User-Supplied Input Plan

**Date:** 2026-05-05
**Source:** user-provided full plan via `/gsd-quick --full`
**Purpose:** Locked input for discussion / research / planning. Treat all hard rules and scope below as binding.

---

# Phase Plan: GET /api/usage + Usage dashboard wire-up

## Goal

Replace the Phase-14 "No data yet" stub on `/dashboard/usage` with real, server-driven usage metrics. Build a single read-only `GET /api/usage` endpoint that surfaces what the backend already records (rate-limit counters + trial state + plan tier), and rebuild the frontend Usage page to consume it. Drop the earliest-API-key trial heuristic — `users.trial_started_at` is already on the row and now has a clean read path via `/api/account/me`. End-state: every card on `/dashboard/usage` shows a real number sourced from the DB.

## Hard rules (non-negotiable)

- **DRY** — single source of truth per concept. The new `/api/usage` route is the SOLE consumer for usage rendering. Trial state lives only in `users.trial_started_at` (or `/api/account/me`'s response); do NOT recompute it from API key timestamps. apiClient stays the only HTTP entry per UI-11.
- **SRP** — route does HTTP only; a `UsageQueryService` owns business logic; a `UsageRepository` owns SQL. Frontend: page = orchestrator, `usageApi.ts` = transport, `useUsageSummary` hook (or local effect) = state. No mixing.
- **/tiger-style** — assert at boundaries (request → service → repo). Validate inputs at the route, validate invariants at the service. Early-return / early-throw — no nested-if spaghetti. Self-explanatory names: `fetchUsageSummary`, `hourCount`, `hourLimit`, never `u`, `q`, `data1`. Subtype-first error handling on the frontend (RateLimitError before ApiClientError).
- **/frontend-design skill REQUIRED** — invoke the `frontend-design` skill before writing the new Usage page. The current cards are flat shadcn defaults. Goal: distinctive, production-grade UI — radial / bar progress, semantic colors at limit thresholds, motion only where it earns its keep, dark-mode parity. Reference the existing `/dashboard/keys` and `/dashboard/account` pages for visual consistency, but the Usage page is allowed to push further on data viz.
- **No npm.** Frontend is bun-only. Lockfile is `bun.lock`. Use `bun add` if a new dep is needed (only add if truly necessary — first try built-in CSS / SVG before reaching for a chart lib).
- **No backwards-compat shims, no dead code, no premature abstraction.** This is a single endpoint and a single page rewrite — keep it tight.

## Scope (in)

### Backend (Python / FastAPI)

1. **New route module:** `app/api/usage_routes.py`
   - `usage_router = APIRouter(prefix="/api/usage", tags=["Usage"], dependencies=[Depends(csrf_protected)])`
   - `GET ""` (i.e. `GET /api/usage`) → `UsageSummaryResponse`.
   - Auth via the existing `authenticated_user` Depends (Phase 19 chain — see `app/api/account_routes.py:46-50` for the canonical pattern). Match the `account_router` style exactly.
   - The route MUST do HTTP-shape work only: pull `user`, call the service, return a response model. No SQL in the route.

2. **Pydantic response schema:** `app/api/schemas/usage_schemas.py`
   ```python
   class UsageSummaryResponse(BaseModel):
       plan_tier: Literal['free','trial','pro','team']
       trial_started_at: datetime | None
       trial_expires_at: datetime | None  # computed: trial_started_at + 7d if set
       hour_count: int                    # transcribes used in current rolling hour
       hour_limit: int                    # plan-tier limit for the hour window
       daily_minutes_used: float          # minutes consumed in current day
       daily_minutes_limit: float         # plan-tier daily minute cap
       window_resets_at: datetime         # next bucket reset (hour boundary)
       day_resets_at: datetime            # midnight UTC
   ```
   Keep snake_case at the wire — the frontend already converts via apiClient or the wrapper. Match existing schemas style (see `account_schemas.py`).

3. **Service:** `app/services/usage_query_service.py`
   - `class UsageQueryService` with one public method `get_summary(user_id: int) -> UsageSummaryDTO`.
   - Reads `rate_limit_buckets` for the caller's current hour bucket and current day bucket (the bucket key/window scheme is already defined — confirm by reading `app/services/usage_event_writer.py` and any existing rate-limit middleware/service; do NOT invent a new bucket layout).
   - Reads `users.trial_started_at` and `users.plan_tier` via the existing user repository.
   - Resolves plan-tier limits from a single typed config (constant or pydantic settings — DRY: do not hardcode `5` and `30` in three places). The current limit set per CLAUDE.md / page copy: free-tier = 5 transcribes/hour, 30 minutes/day. Other tiers come from the existing tier config — read `app/core/` for the canonical source. If the config doesn't yet exist, create `app/core/plan_tiers.py` with one dataclass / dict and use it from BOTH this service AND the rate-limit enforcement path so we eliminate duplication.
   - Returns a DTO (not the Pydantic schema — keep service decoupled from the wire shape).

4. **Repository:** if `rate_limit_buckets` doesn't already have a clean read API, add one method on the existing repo (or a thin new `UsageReadRepository` if no logical home exists). Single-responsibility: SQL in / DTO out, no business logic, no aggregation beyond `SELECT … WHERE user_id=? AND window_start=?`.

5. **Wire the router:** `app/main.py` (or wherever routers are registered — find the module that already mounts `account_router` and add `usage_router` next to it). One line.

6. **DI:** `app/api/dependencies.py` — add `get_usage_query_service` following the exact pattern of `get_account_service`. Chain off `get_db` → `get_user_repository` → `get_rate_limit_repository` (or whatever the existing rate-limit dep is named). Do NOT introduce a parallel DI chain.

7. **Tests** (`tests/integration/api/test_usage_routes.py` + `tests/unit/services/test_usage_query_service.py`):
   - Auth required (no cookie → 401).
   - CSRF NOT required for GET (matches account/me — verify the csrf_protected dep gates only mutating verbs in our codebase; if it gates all verbs, this route uses the same; do NOT special-case here).
   - Trial user with no events → all counters zero, plan_tier='trial', `trial_started_at` matches DB.
   - User with N hour events in the current bucket → hour_count == N, hour_limit == 5 for trial.
   - User past midnight UTC → daily_minutes_used resets.
   - User on `pro` plan → limits reflect `pro` config (use whatever real values exist in `plan_tiers.py`).
   - Service unit tests cover the DTO shape independent of HTTP.

8. **OpenAPI regen** — after the route lands, run whatever `gsd-*` regen target updates `app/docs/openapi.yaml` + `openapi.json` (last commit `ab32576` shows the team regenerates it; match that workflow). Don't hand-edit the openapi files.

### Frontend (Vite + React 19 + TS, bun-only)

9. **API wrapper:** `frontend/src/lib/api/usageApi.ts`
   - One function: `fetchUsageSummary(): Promise<UsageSummary>`. Returns a typed object — no `any`, no `unknown` casts.
   - Goes through `apiClient` (UI-11 mandate). GET only — no CSRF header.
   - Boundary assertion: `assert response.plan_tier in {'free','trial','pro','team'}` style — use `zod` (already a dep) for parse-time validation so a contract drift is caught at the wrapper, not on render.
   - Error handling subtype-first: `RateLimitError` BEFORE `ApiClientError` (CLAUDE.md locked policy).

10. **MSW handlers:** `frontend/src/tests/msw/usage.ts` + register in the barrel.
    - Default handler returns a happy-path summary (trial user, low usage).
    - Override factories for: trial expired, hour quota near limit, daily near limit, free tier no trial, error 500.
    - DRY: pattern after the existing `keys.ts` / `account.ts` MSW handlers.

11. **Page rewrite:** `frontend/src/routes/UsageDashboardPage.tsx`
    - Drop the entire `computeTrialInfo` function. Drop the `fetchKeys` import. Drop the four hardcoded "No data yet" cards.
    - New cards (final layout decided by /frontend-design):
      a. **Plan tier** — pill badge with tier-specific accent (free=neutral, trial=info, pro=success, team=premium). Pulls from `plan_tier` only. Single source of truth.
      b. **Trial countdown** — only renders when `plan_tier === 'trial' && trial_started_at !== null`. Shows days remaining until `trial_expires_at`. Color shifts at ≤2d (destructive), ≤4d (warn), >4d (default). If `plan_tier !== 'trial'`, this card is hidden — do NOT render an empty placeholder.
      c. **Hour quota** — radial or horizontal progress: `hour_count / hour_limit`. Shows the count, the limit, and a "resets at HH:MM" sub-line derived from `window_resets_at`. At ≥80% → warn color; at 100% → destructive.
      d. **Daily minutes** — same treatment for `daily_minutes_used / daily_minutes_limit`. Format minutes as `12.5 min` (one decimal). Sub-line "resets at midnight UTC" from `day_resets_at`.
    - Loading state: skeleton cards (use the existing skeleton primitive if one exists; otherwise inline a tasteful pulsing placeholder — do NOT block on a spinner).
    - Error state: existing shadcn `Alert` destructive variant. Single retry button optional.
    - Hydration boundary: page-level `useEffect` calling `fetchUsageSummary` once. Suppress 401 redirect is NOT needed (this route is gated by `RequireAuth` already). On 401, let apiClient redirect to `/login?next=/dashboard/usage` per the standard policy.
    - **Use the /frontend-design skill BEFORE coding the visual layer.** Generate 2–3 layout variants, pick one, then implement. The current page is generic; the new one needs to feel intentional (typography hierarchy, generous spacing, semantic color mapping). Dark-mode must be at parity (use the project's existing CSS tokens, not raw hex).

12. **Free-tier limits copy** — the page currently has a hardcoded line "Free-tier limits: 5 transcribes/hour, 30 minutes/day, files up to 5 minutes, tiny & small models." If the new endpoint returns the limits, that line should be data-driven for the caller's tier (e.g. for a `pro` user it should show pro limits, not free limits). At minimum: drive `hour_limit` / `daily_minutes_limit` from the response. The "files up to 5 minutes, tiny & small models" suffix is a constraint we don't ship in the endpoint yet — keep it tier-conditional or move it to a tooltip/help link. Prefer: show *the user's actual limits* in plain text; link "See all plan limits" → `/pricing` (if it exists) or drop the suffix.

13. **Tests:**
    - Unit/integration (Vitest + RTL + MSW): `frontend/src/routes/UsageDashboardPage.test.tsx`
      - Renders happy-path numbers from MSW.
      - Trial-not-started (free tier): trial card not rendered.
      - Trial expired: trial card shows "expired" treatment.
      - Hour quota at limit: progress bar at 100%, destructive color, count == limit.
      - Daily minutes near limit: warn color at 80%.
      - 500 error: alert renders, no crash.
    - E2E (Playwright): add `frontend/e2e/usage-page/01-real-data.spec.ts`
      - Use the `signedInPage` fixture (already exists) + `page.route('**/api/usage', …)` mock.
      - Asserts the four cards are present and contain the mocked numbers (not "No data yet" strings).
      - One screenshot per layout breakpoint into `frontend/e2e/screenshots/usage-page/` (gitignored, regen each run).

### Cross-cutting

14. **Account summary already returns `trial_started_at`** (per `app/api/account_routes.py:63-86` + Phase 19 schema). The Usage page rewrite should NOT duplicate-fetch it from `/api/usage` if `authStore.user` already has it — use the store. BUT: keep `trial_started_at` in the `/api/usage` response anyway, because (a) the endpoint should be self-sufficient for any future Usage-only consumer, (b) duplication of one field across two endpoints is acceptable when both fields come from the same DB column. DRY is about logic, not about fields on the wire.

15. **Plan-tier limit config** — single module (`app/core/plan_tiers.py` if it doesn't already exist). Both `UsageQueryService` AND the existing rate-limit enforcement code MUST consume the same source. If today's enforcement code hardcodes `5` and `30` somewhere in middleware or service code, refactor those call sites to read from the new config in the SAME PR (otherwise we have a documented divergence the moment the values diverge). Find these call sites with `grep -nE '(5|30)\b.*(/hour|hour|minute|daily)'` in `app/`.

## Scope (out)

- No new backend feature for "files up to 5 minutes" or "tiny & small models" enforcement reporting. Out of scope for this phase.
- No historical usage chart (last 7 days, etc.) — that's a Phase 20+ ambition. This phase ships **current state only**.
- No billing UI changes — billing is its own surface.
- No changes to `rate_limit_buckets` schema. Read-only access to the existing rows.
- No new auth surface. Reuse `authenticated_user` and `csrf_protected` deps as-is.
- No `npm`. If the temptation arises, stop and ask.

## Tasks (in order)

1. Read `app/services/usage_event_writer.py`, the rate-limit middleware/service (find via `grep -r "rate_limit_buckets" app/`), and `app/core/` to map the existing bucket scheme + tier config. **Do not start coding until this is mapped — write a 5-line summary of how buckets are keyed (user_id, window_start, window_kind?) into the PLAN.md before proceeding.**
2. Create / consolidate `app/core/plan_tiers.py` (single source of truth for limits). Refactor any call sites currently hardcoding the limits.
3. Implement `UsageQueryService` + repo method. Unit-test the service against an in-memory SQLite with seeded `rate_limit_buckets` rows.
4. Implement `usage_routes.py` + schema + DI dep. Integration-test the route.
5. Wire `usage_router` into the FastAPI app.
6. Regen OpenAPI artifacts.
7. Frontend: implement `usageApi.ts` + zod schema parse + MSW handlers.
8. **Invoke the `frontend-design` skill** to design the Usage page layout. Pick ONE variant. Document the choice in a one-paragraph note inside `frontend/src/routes/UsageDashboardPage.tsx` header docstring (not a separate doc).
9. Implement the page. Convert "Free-tier limits" copy to tier-aware. Drop the earliest-key trial heuristic.
10. Vitest tests for the page (5+ scenarios above).
11. Playwright e2e (one spec, screenshots).
12. Run the full test suite locally: `cd frontend && bun run lint && bun run test && bun run test:e2e` AND `uv run pytest`. All must pass.
13. Manual UAT on local backend at `localhost:8000` via `whisper.kingdom.lv` (Cloudflare tunnel topology is documented in project memory — backend lives on this PC, edge is on Forge). Hit `/dashboard/usage` as a trial user, complete a transcribe, refresh — Hour quota count should increment.

## Verification (definition of done)

- `GET /api/usage` returns the schema above for every plan tier.
- Hour quota shows real `hour_count / hour_limit`, increments visibly after a transcribe, resets at the bucket boundary.
- Daily minutes shows real used / cap, resets at UTC midnight.
- Trial card hidden for non-trial tiers; visible with correct days-remaining for trial users; correct expired treatment past day 7.
- The string "No data yet" no longer appears on the page (grep in `frontend/src/routes/`).
- The earliest-API-key heuristic in `computeTrialInfo` is fully removed (grep in `frontend/src/`).
- All limits read from one config module — `grep -nE '\b5\b|\b30\b'` in business logic should not find the magic numbers in service / route / page code (they only live in `plan_tiers.py`).
- `bun run lint`, `bun run test`, `bun run test:e2e`, `uv run pytest` — all green.
- OpenAPI regenerated and committed.
- /frontend-design skill was actually invoked (not skipped). Cite the chosen variant in the page docstring.

## Files touched (rough)

**New:**
- `app/api/usage_routes.py`
- `app/api/schemas/usage_schemas.py`
- `app/services/usage_query_service.py`
- `app/core/plan_tiers.py` *(if not yet present)*
- `tests/integration/api/test_usage_routes.py`
- `tests/unit/services/test_usage_query_service.py`
- `frontend/src/lib/api/usageApi.ts`
- `frontend/src/tests/msw/usage.ts`
- `frontend/src/routes/UsageDashboardPage.test.tsx`
- `frontend/e2e/usage-page/01-real-data.spec.ts`

**Modified:**
- `app/main.py` *(register router)*
- `app/api/dependencies.py` *(add `get_usage_query_service`)*
- `app/docs/openapi.yaml` + `openapi.json` *(regen, do not hand-edit)*
- `frontend/src/routes/UsageDashboardPage.tsx` *(full rewrite — drop the stub)*
- `frontend/src/tests/msw/index.ts` *(register usage handler in barrel)*
- *(possibly)* the rate-limit enforcement module(s) where `5`/`30` are currently hardcoded — only if duplication exists; identified during Task 1.
