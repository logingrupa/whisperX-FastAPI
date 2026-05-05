---
name: 260505-l2w-CONTEXT
description: Locked decisions for GET /api/usage + Usage dashboard wire-up
type: context
status: ready_for_planning
---

# Quick Task 260505-l2w: GET /api/usage + Usage dashboard wire-up — Context

**Gathered:** 2026-05-05
**Status:** Ready for planning

<domain>
## Task Boundary

Build a single read-only `GET /api/usage` endpoint surfacing rate-limit counters + trial state + plan tier from existing tables. Rebuild `frontend/src/routes/UsageDashboardPage.tsx` to consume it. Drop the earliest-API-key trial heuristic. Full hard-rules, scope, and per-task breakdown live in `260505-l2w-INPUT-PLAN.md` (locked input from user).

</domain>

<decisions>
## Implementation Decisions

### Meta — engineering posture (user message, locked)
- **"Use best practices and don't overcomplicate."**
- Apply as a tiebreaker against any optional complexity. If a plan task adds machinery beyond what the rules require, drop it.
- DRY/SRP/tiger-style still mandatory (CLAUDE.md), but no extra abstractions, no premature hooks, no chart library if CSS+SVG suffices.

### Refresh cadence (Usage page)
- **One-shot fetch on mount + manual Refresh button.**
- No polling. No focus-refetch.
- Why: simplest UX, matches existing dashboard patterns, satisfies UAT step 13 (manual reload after transcribe shows incremented count).
- How to apply: page-level `useEffect` calls `fetchUsageSummary` once. Add a small Refresh icon-button in the page header that re-runs the same fetch and re-renders. No background timers, no `setInterval`.

### Trial-expired card UX
- **Destructive accent + "Trial expired N days ago" + primary "Upgrade" CTA → `/pricing`.**
- If `/pricing` route does not exist yet, the CTA still renders; the click handler can navigate to `/pricing` (404 acceptable — user owns standing up that route separately).
- Why: forces the upgrade decision at the moment it matters, doesn't quietly hide the trial card.
- How to apply:
  - `plan_tier === 'trial' && trial_expires_at != null && trial_expires_at < now` → expired branch.
  - Render destructive (red) accent border + heading "Trial expired N days ago" + button "Upgrade".
  - Pre-expiry countdown rules from input plan still hold (≤2d destructive, ≤4d warn, >4d default).

### /frontend-design skill timing
- **Inline during execution.** Executor invokes `/frontend-design` when it reaches the Usage-page rewrite task.
- Why: keeps design close to code; avoids re-litigating mid-build; orchestrator stays out of the visual loop.
- How to apply: executor MUST call `/frontend-design` before writing the new `UsageDashboardPage.tsx`, generate 2–3 layout variants, pick one, cite the chosen variant in the page header docstring (one paragraph). Skipping the skill is a verification failure.

### Pricing route
- Treat `/pricing` as the upgrade target even if not yet implemented. Do NOT add a stub for it in this phase. CTA links to `/pricing`; 404 is acceptable until a separate phase ships pricing.

### Claude's Discretion
- Bucket-read repository placement (extend existing rate-limit repo vs. new `UsageReadRepository`) — researcher + planner decide based on actual code shape. Default: extend existing repo if a reasonable home exists; create new only if the existing repo's responsibility would be muddied.
- Skeleton primitive vs. inline pulse — use existing primitive if present; otherwise tasteful inline pulsing div, not a spinner. No new shadcn install.
- Hour-quota visual: progress bar OR radial — designer's call inside `/frontend-design`. Both acceptable per input plan.

</decisions>

<specifics>
## Specific Ideas / References

- Canonical route pattern: `app/api/account_routes.py:46-50` (auth chain), `account_router` registration site for router-mount mirror.
- Canonical DI pattern: `get_account_service` in `app/api/dependencies.py`.
- Canonical schema style: `app/api/schemas/account_schemas.py`.
- Canonical MSW handler pattern: `frontend/src/tests/msw/keys.ts` and `account.ts`.
- Canonical e2e fixture: `frontend/e2e/_fixtures/auth.ts` `signedInPage`.
- Plan-tier limit single-source-of-truth target: `app/core/plan_tiers.py` (create if absent; refactor existing `5`/`30` magic-number sites in same PR).
- OpenAPI regen: match the workflow used in commit `ab32576` (executor must locate this script, not hand-edit yaml/json).

</specifics>

<canonical_refs>
## Canonical References

- `260505-l2w-INPUT-PLAN.md` — full user-supplied plan (this directory). Hard rules, scope-in/out, files-touched list all binding.
- Project `CLAUDE.md` — bun-only, DRY/SRP/tiger-style, subtype-first errors, apiClient sole HTTP entry.
- User global `CLAUDE.md` — DRT, SRP, caveman responses (workflow output formatting).

</canonical_refs>
