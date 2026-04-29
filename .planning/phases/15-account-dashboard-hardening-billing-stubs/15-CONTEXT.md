# Phase 15: Account Dashboard Hardening + Billing Stubs - Context

**Gathered:** 2026-04-29
**Status:** Ready for planning
**Mode:** Smart-discuss (autonomous batch tables, all 3 areas accepted as recommended)

<domain>
## Phase Boundary

Polish the post-cutover account surface — full account deletion, logout-all-devices, Pro upgrade interest capture, and wiring for the existing Stripe checkout/webhook stubs. Phase 15 closes AUTH-06, SCOPE-06, UI-07. BILL-05/06 stubs already exist on the backend (verified 2026-04-29) — Phase 15 only wires UI to them.

In scope:
- **Backend new routes:**
  - `POST /auth/logout-all` — bumps `users.token_version` (existing helper `AuthService.logout_all_devices`); clears session + csrf cookies; returns 204
  - `GET /api/account/me` — returns `{user_id, email, plan_tier, trial_started_at, token_version}` for client-side hydration; auth-required
  - `DELETE /api/account` — body `{email_confirm: str}` must equal `request.state.user.email` exactly (400 on mismatch); cascades user row + tasks + api_keys + subscriptions + usage_events + device_fingerprints + rate_limit_buckets; clears cookies; returns 204
- **Backend service:**
  - Extend `AccountService` with `delete_account(user_id, email_confirm)` — single SQL transaction with FK ON DELETE CASCADE doing the heavy lifting; preserves existing `delete_user_data` (SCOPE-05)
  - `AccountService.get_account_summary(user_id)` for /me
- **Frontend new page** — `AccountPage` replaces `AccountStubPage`:
  - Profile card: email + plan_tier badge
  - Plan card: current tier + "Upgrade to Pro" CTA → opens `<UpgradeInterestDialog>` (shadcn `<Dialog>`)
  - Danger Zone card: "Sign out of all devices" (logout-all confirm dialog) + "Delete account" (type-email confirm dialog)
- **Frontend new dialogs (shadcn + Radix + /frontend-design):**
  - `UpgradeInterestDialog` — single textarea + submit; POSTs `/billing/checkout` (501 expected) + success copy "v1.3 Stripe arriving"
  - `DeleteAccountDialog` — type-exact-email input; destructive button disabled until match; on success: authStore.logout() + redirect `/login`
  - `LogoutAllDialog` — confirm copy; on success: authStore.logout() + redirect `/login`
- **Frontend wiring:**
  - `authStore.refresh()` on app boot via `apiClient.get('/api/account/me')` with `suppress401Redirect` flag (probe-style); user persists across reload
  - New API: `frontend/src/lib/api/accountApi.ts` (DRY single fetch site, mirrors `keysApi.ts` pattern)
- **Tests:**
  - Backend integ: logout-all invalidates issued JWTs, /api/account/me shape, DELETE /api/account cascade + email-mismatch 400
  - Frontend unit: AccountPage renders email/tier; LogoutAll/Delete/Upgrade dialog behaviors; type-email match enables delete; authStore.refresh() hydrates from /me

Out of scope (deferred):
- Real Stripe Checkout integration — v1.3
- Cross-user matrix tests for new endpoints — Phase 16
- README + migration runbook — Phase 17

</domain>

<decisions>
## Implementation Decisions

### API Surface

- `POST /auth/logout-all` — sits next to `/auth/logout` (auth-action symmetry); auth-required; bumps `token_version`; clears cookies; 204
- `GET /api/account/me` — auth-required; returns `AccountSummaryResponse {user_id, email, plan_tier, trial_started_at, token_version}` (token_version exposed for cross-tab refresh debounce)
- `DELETE /api/account` — auth-required; body `{email_confirm: EmailStr}`; mismatch → 400 generic "Confirmation email does not match"; on match → cascade delete + clear cookies; 204
- Account deletion route path: `DELETE /api/account` (existing `/data` preserved as data-only delete per SCOPE-05)

### Account Dashboard UI

- Three vertical cards: Profile / Plan / Danger Zone (in that order, mobile-stack)
- shadcn primitives only — `Card`, `Badge`, `Button`, `Dialog`, `Input`, `Form`, `Alert`; Radix primitives via shadcn
- `/frontend-design` skill drives polish: gap-6 between cards, rounded-xl, dest variant on danger buttons, badge color matched to plan_tier (`free`=secondary, `trial`=outline, `pro`=default, `team`=default)
- Mobile-responsive: cards stack vertically on `< md`, gap-4; Dialog uses shadcn full-screen drawer pattern on `< sm`
- Upgrade-to-Pro CTA → `<UpgradeInterestDialog>`: single textarea ("What do you want from Pro? — optional"), submit POSTs `/billing/checkout` (501 swallowed), success state "Thanks — Stripe ships in v1.3" with auto-close after 2s
- Delete-account: shadcn `<Dialog>` with `<Input type="email">` for type-exact match; destructive `<Button>` disabled until input === user.email; on click: apiClient.delete('/api/account', {email_confirm}) → authStore.logout() → navigate('/login')
- Logout-all: shadcn `<Dialog>` confirm; on confirm: apiClient.post('/auth/logout-all') → authStore.logout() → navigate('/login')

### Wiring + Tests

- `authStore.refresh()` exists already (Plan 14-03); extend it to call `apiClient.get('/api/account/me', {suppress401Redirect: true})` and populate `{id, email, plan_tier}` from server (overrides client-stored email from form input)
- Single `accountApi.ts` exports: `fetchAccountSummary()`, `logoutAllDevices()`, `deleteAccount(emailConfirm)`, `submitUpgradeInterest(message)`
- All HTTP via `apiClient` (single fetch site invariant from Phase 14)
- Backend tests: integration tests use `TestClient` with seeded user + JWT; cross-user 404 path NOT covered here (Phase 16 owns matrix)
- Frontend tests: Vitest + RTL + MSW; AccountPage tests use MSW handlers in `tests/msw/account.handlers.ts` (new file, mirrors keys.handlers.ts pattern)

### Code Quality (locked from invocation args)

- **DRY**: Single `accountApi.ts` site for HTTP; single `accountService.delete_account` for cascade; single `AccountSummaryResponse` schema reused by /me + UI types; dialog components share a small `<DangerActionDialog>` primitive if logout-all + delete-account share enough surface (assess during plan; do NOT abstract until 2nd usage demands it)
- **SRP**: route → service → repository; AccountPage is dumb orchestrator; dialogs own their own form state
- **tiger-style**: assertions at boundaries (`email_confirm` is non-empty + matches; user.id is int > 0); fail-loud on cascade integrity violations; no silent `pass` blocks
- **no nested-if**: verifier-checked `grep -cE "^\s+if .*\bif\b"` == 0 across new files
- **/frontend-design**: skill drives polish for AccountPage + 3 dialogs; mobile-responsive verified at `sm/md/lg` breakpoints
- **self-explanatory naming**: `confirmEmail` not `email2`; `isMatched` not `ok`; full names per CLAUDE.md

### Claude's Discretion

- Choice of how to compose dialogs (shared `<DangerActionDialog>` vs separate) — defer to plan-phase based on actual code symmetry
- Exact wording of Upgrade-Interest copy
- Whether to add `idle/sending/success/error` enum states to dialogs or use boolean flags — pick whichever yields fewer nested-ifs
- Whether `suppress401Redirect` is already a flag in apiClient (likely yes per 14-02 plan §225) or needs adding

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets

- **Backend:**
  - `AuthService.logout_all_devices(user_id)` already implemented at `app/services/auth/auth_service.py:91` — bumps token_version via `user_repository.update_token_version`
  - `AccountService.delete_user_data(user_id)` at `app/services/account_service.py:29` — pattern for cascade-style delete; extend with full-row variant
  - `account_router` mounted at `/api/account`; add new routes alongside `delete_user_data`
  - `auth_router` at `/auth` with `_clear_auth_cookies` DRY helper — reuse for logout-all
  - `get_authenticated_user`, `get_db_session`, `get_account_service` dependencies already exist
  - `User.bump_token_version()` business method already exists at `app/domain/entities/user.py:43`
  - FK ON DELETE CASCADE constraints from Phase 10 schema mean `DELETE FROM users WHERE id = :uid` cleans up tasks/api_keys/subscriptions/usage_events/device_fingerprints/rate_limit_buckets in one statement
- **Frontend:**
  - `AccountStubPage.tsx` — placeholder to replace
  - `KeysDashboardPage.tsx` — pattern for fetch + dialog state machines
  - `CreateKeyDialog.tsx` / `RevokeKeyDialog.tsx` — shadcn `<Dialog>` patterns to mirror
  - `apiClient.ts` — single fetch site with `suppress401Redirect` option already wired (Plan 14-02 §225)
  - `authStore.ts` — `login()`, `logout()`, `refresh()` already scaffolded (Plan 14-03); refresh() needs /me wiring
  - `frontend/src/lib/api/keysApi.ts` — pattern for new `accountApi.ts`
  - shadcn primitives present: `card`, `badge`, `button`, `alert`, `dialog`, `input`, `label`, `form`

### Established Patterns

- Routes return Response objects (not handler-injected) when setting cookies (lesson from Plan 13-03)
- All HTTP via `apiClient` — verifier-grep-enforced single fetch site (14-07 invariant)
- Anti-enumeration generic error strings (e.g. "Invalid credentials", "Registration failed")
- FastAPI dependency injection via `Depends()` — never resolve services manually
- Pydantic schemas under `app/api/schemas/` — one file per domain (account_schemas.py to add)
- Dialog show-once / type-confirm pattern from `CreateKeyDialog` and `RevokeKeyDialog`
- Tests use `pytest`+`TestClient` for backend integ; Vitest+RTL+MSW for frontend; per-test `Container` overrides for DB isolation

### Integration Points

- `app/main.py` — routers already registered; new `/auth/logout-all` lives in existing `auth_router`; new `/api/account/me` and `DELETE /api/account` live in existing `account_router`
- `frontend/src/routes/AppRouter.tsx:52` — replace `AccountStubPage` import + element with `AccountPage`
- `frontend/src/lib/stores/authStore.ts` — extend `refresh()` to call `accountApi.fetchAccountSummary()`; populate user state from server
- `app/api/dependencies.py` — already exposes `get_authenticated_user`, `get_db_session`, `get_account_service`; no new dependencies required
- `frontend/src/tests/msw/handlers.ts` — barrel; add `accountHandlers` from new `account.handlers.ts`

</code_context>

<specifics>
## Specific Ideas

- Mobile-friendly responsive UI per user note — verify with browser dev-tools at sm/md/lg breakpoints
- Use shadcn + Radix only (locked by user across milestone)
- `/frontend-design` skill mandatory for AccountPage polish + 3 new dialogs
- Code MUST be DRY, SRP, tiger-style, no nested-if spaghetti, self-explanatory names — verifier-grep-enforced

</specifics>

<deferred>
## Deferred Ideas

- Real Stripe Checkout integration — v1.3 (FUTURE-01)
- Account audit log / per-session revoke list — v1.3 (FUTURE-08)
- Email change flow — v1.3 (FUTURE-12)
- Plan tier upgrade in-app (without Stripe) — v1.3
- Cross-user matrix tests for the new account endpoints — Phase 16

</deferred>
