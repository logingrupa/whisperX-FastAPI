# Phase 15: Account Dashboard Hardening + Billing Stubs - Research

**Researched:** 2026-04-29
**Domain:** FastAPI account management + React dashboard wiring + FK cascade integrity
**Confidence:** HIGH (codebase verified line-by-line; CONTEXT.md + UI-SPEC.md locked; all assumptions cross-checked against existing code)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**API Surface**
- `POST /auth/logout-all` — sits next to `/auth/logout`; auth-required; bumps `token_version`; clears cookies; 204
- `GET /api/account/me` — auth-required; returns `AccountSummaryResponse {user_id, email, plan_tier, trial_started_at, token_version}` (token_version exposed for cross-tab refresh debounce)
- `DELETE /api/account` — auth-required; body `{email_confirm: EmailStr}`; mismatch → 400 generic "Confirmation email does not match"; on match → cascade delete + clear cookies; 204
- Account deletion route path: `DELETE /api/account` (existing `/data` preserved as data-only delete per SCOPE-05)

**Account Dashboard UI**
- Three vertical cards: Profile / Plan / Danger Zone (in that order, mobile-stack)
- shadcn primitives only — `Card`, `Badge`, `Button`, `Dialog`, `Input`, `Form`, `Alert`; Radix primitives via shadcn
- `/frontend-design` skill drives polish: gap-6 between cards, rounded-xl, dest variant on danger buttons, badge color matched to plan_tier (`free`=secondary, `trial`=outline, `pro`=default, `team`=default)
- Mobile-responsive: cards stack vertically on `< md`, gap-4; Dialog uses shadcn full-screen drawer pattern on `< sm`
- Upgrade-to-Pro CTA → `<UpgradeInterestDialog>`: single textarea ("What do you want from Pro? — optional"), submit POSTs `/billing/checkout` (501 swallowed), success state "Thanks — Stripe ships in v1.3" with auto-close after 2s
- Delete-account: shadcn `<Dialog>` with `<Input type="email">` for type-exact match; destructive `<Button>` disabled until input === user.email; on click: apiClient.delete('/api/account', {email_confirm}) → authStore.logout() → navigate('/login')
- Logout-all: shadcn `<Dialog>` confirm; on confirm: apiClient.post('/auth/logout-all') → authStore.logout() → navigate('/login')

**Wiring + Tests**
- `authStore.refresh()` exists already (Plan 14-03); extend it to call `apiClient.get('/api/account/me', {suppress401Redirect: true})` and populate `{id, email, plan_tier}` from server (overrides client-stored email from form input)
- Single `accountApi.ts` exports: `fetchAccountSummary()`, `logoutAllDevices()`, `deleteAccount(emailConfirm)`, `submitUpgradeInterest(message)`
- All HTTP via `apiClient` (single fetch site invariant from Phase 14)
- Backend tests: integration tests use `TestClient` with seeded user + JWT; cross-user 404 path NOT covered here (Phase 16 owns matrix)
- Frontend tests: Vitest + RTL + MSW; AccountPage tests use MSW handlers in `tests/msw/account.handlers.ts` (new file, mirrors keys.handlers.ts pattern)

**Code Quality (locked from invocation args)**
- **DRY**: Single `accountApi.ts` site for HTTP; single `accountService.delete_account` for cascade; single `AccountSummaryResponse` schema reused by /me + UI types; dialog components share a small `<DangerActionDialog>` primitive only if logout-all + delete-account share enough surface (assess during plan; do NOT abstract until 2nd usage demands it)
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

### Deferred Ideas (OUT OF SCOPE)

- Real Stripe Checkout integration — v1.3 (FUTURE-01)
- Account audit log / per-session revoke list — v1.3 (FUTURE-08)
- Email change flow — v1.3 (FUTURE-12)
- Plan tier upgrade in-app (without Stripe) — v1.3
- Cross-user matrix tests for the new account endpoints — Phase 16
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| AUTH-06 | User can "logout all devices" via a `token_version` bump that invalidates every existing session | `AuthService.logout_all_devices` already implemented at `app/services/auth/auth_service.py:91`. JWT `ver` claim embedded by `jwt_codec.encode_session`; `TokenService.verify_and_refresh` rejects mismatch. New work: HTTP route only. |
| SCOPE-06 | `DELETE /api/account` cascades to tasks, api_keys, subscriptions, usage_events, device_fingerprints, rate_limit_buckets; type-email confirm at UI | **Critical finding (HIGH):** `tasks.user_id` ON DELETE **SET NULL** (not CASCADE) per `alembic/versions/0002_auth_schema.py:204`. `rate_limit_buckets` has **no FK** (uses `bucket_key` text). Cannot use single `DELETE FROM users` — see "FK Cascade Coverage" section. |
| UI-07 | `/dashboard/account` page with email, plan_tier card, "Upgrade to Pro" CTA, delete-account flow with type-email confirmation | UI-SPEC.md §116-160 locks layout + dialogs; `KeysDashboardPage` + `CreateKeyDialog` + `RevokeKeyDialog` provide complete patterns to mirror. |
| BILL-05 | `POST /billing/checkout` is a 501 stub | **Already complete** (`app/api/billing_routes.py:46-60`, verified 2026-04-29). Phase 15 wires UI dialog only. |
| BILL-06 | `POST /billing/webhook` is a 501 stub with header-schema validation | **Already complete** (`app/api/billing_routes.py:63-81`). No UI work — Stripe calls server-to-server only. |
</phase_requirements>

---

## Summary

Phase 15 closes the v1.2 account-management surface: full row deletion, logout-all-devices, account hydration via `/me`, and UI-only wiring of two pre-existing 501 billing stubs. The backend service + repository + entity primitives all exist; the new work is one route per requirement (3 routes), one schema file (`account_schemas.py`), an AccountService extension (delete_account + get_account_summary), one `accountApi.ts` typed wrapper, one new page (`AccountPage`), three dialogs, and an authStore.refresh() extension.

The single highest-risk finding is FK cascade coverage. `tasks.user_id` is ON DELETE **SET NULL** (not CASCADE) and `rate_limit_buckets` has no FK at all. A naive `DELETE FROM users WHERE id = :uid` would orphan tasks (set their `user_id` to NULL, then fail the NOT NULL constraint added in migration 0003) and would leave per-user rate-limit buckets behind. The recommended approach is **service-orchestrated explicit pre-delete** for the two non-CASCADE tables, then the user row delete which triggers CASCADE for the remaining four. This avoids a fourth Alembic migration in Phase 15 and keeps the delete logic auditable in one Python method.

The second-highest risk is the apiClient `suppress401Redirect` gap: it currently exists only on `post`, not `get`. The boot probe `apiClient.get('/api/account/me', {suppress401Redirect: true})` requires extending the GET method signature — a small but mandatory wave-0 task before authStore.refresh() can land.

Everything else is mechanical pattern-mirroring: routes mirror `auth_router` cookie-clearing, the service mirrors `delete_user_data`, dialogs mirror `RevokeKeyDialog`/`CreateKeyDialog`, the API wrapper mirrors `keysApi.ts`, MSW handlers mirror `keys.handlers.ts`, and integration tests mirror `test_account_routes.py`.

**Primary recommendation:** Plan a 4-wave structure: (W0) apiClient GET suppress401Redirect + AccountSummaryResponse schema + accountApi.ts skeleton + MSW handlers; (W1) backend routes + AccountService.delete_account / get_account_summary + integration tests; (W2) authStore.refresh extension + AppRouter swap to AccountPage; (W3) AccountPage + 3 dialogs + RTL tests. W0 unblocks W1 (frontend types) and W2-W3 (HTTP wrapper); W1 + W3 are independent.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| token_version bump | API / Backend | Database / Storage | AUTH-06 invariant lives in `users.token_version` column + JWT `ver` claim; only DB write owns it |
| Cascade row delete | API / Backend | Database / Storage | Service orchestrates explicit pre-deletes (tasks, rate_limit_buckets) + user delete; FK CASCADE finishes the rest |
| Cookie clearing | API / Backend (route) | — | Sits in route handler returning `Response(204)` with `delete_cookie` calls — same pattern as `/auth/logout` (lesson from Plan 13-03) |
| Account summary read | API / Backend | Database / Storage | Pure read of `users` row; no domain transformation needed |
| Type-email confirm gate | API / Backend (defence) + Browser/Client (UX) | — | Browser disables submit until match for UX; backend re-checks for defence-in-depth (T-15-02) |
| Plan-tier badge rendering | Browser / Client | — | Pure UI mapping of `plan_tier` string → shadcn Badge variant |
| Upgrade interest capture | Browser / Client | API / Backend (501 stub) | Form lives client-side; POST hits the 501 stub which is swallowed as success |
| App-boot session hydration | Browser / Client (authStore) | API / Backend (`/me`) | Probe-style fetch with `suppress401Redirect`; sets store from response |
| Cross-tab logout sync | Browser / Client (BroadcastChannel) | — | Existing UI-12 mechanism; `authStore.logout()` already broadcasts |

---

## Standard Stack

### Core (Backend) [VERIFIED: codebase grep + pyproject.toml]

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | (project pin) | HTTP routes | Locked across milestone — every existing route uses APIRouter + Depends pattern |
| Pydantic v2 | (project pin) | Request/response schemas | All `app/api/schemas/*.py` use BaseModel + EmailStr + Field |
| SQLAlchemy 2.x | (project pin) | ORM + session | `session.execute(text(...))` for raw SQL; `session.delete(orm)` for cascade; `Mapped[]` for ORM |
| pyjwt | (project pin) | HS256 token decode/encode | Single decode site `app/core/jwt_codec.py` (AUTH-08) |
| dependency-injector | (project pin) | DI Container override in tests | Test fixtures use `providers.Factory` to swap session_factory |

### Core (Frontend) [VERIFIED: codebase grep + package.json patterns]

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| React | 19.x | Component runtime | UI-13 locked |
| react-router-dom | 7.x | Routing | UI-01 locked |
| Zustand | (existing dep) | Auth store state | UI-12 locked, no Provider boilerplate |
| shadcn/ui (new-york preset) | (existing) | UI primitives — Card, Button, Badge, Dialog, Input, Label, Alert, Form | UI-13 locked, all required primitives already vendored at `frontend/src/components/ui/` |
| lucide-react | (existing) | Icons (Trash2, LogOut, Sparkles) | UI-SPEC.md locked |
| Tailwind v4 | (existing) | Styling | UI-13 locked |
| MSW | 2.13 | HTTP mocks for tests | TEST-03 locked |
| Vitest + RTL + jsdom | 3.2 / 16.1 | Test runner + matchers | TEST-01/02 locked |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pydantic.EmailStr | v2 | Email format validation in `email_confirm` | DELETE /api/account body — fails at parse time if not RFC-shaped |
| sqlalchemy.text | 2.x | Raw SQL DELETE for tasks + rate_limit_buckets | Pre-cascade orchestration in `AccountService.delete_account` |
| FastAPI Response | — | Returning 204 with cookie deletions | Mirrors `/auth/logout` — must return new Response, not the injected one (lesson from Plan 13-03) |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Service-orchestrated pre-delete | New 0004_cascade_tasks migration flipping `tasks.user_id` to ON DELETE CASCADE | Migration is cleaner long-term but adds DB-deploy risk to Phase 15. Service approach contained, reversible, and `/data` SCOPE-05 already does explicit task deletion — pattern is established. |
| react-hook-form + zod for `email_confirm` | Plain `useState` | CONTEXT.md §80 explicitly says "pick whichever yields fewer nested-ifs" — for a single field with one validation rule (`lower(input) === lower(user.email)`), useState wins on simplicity. RHF/zod adds value when 3+ fields with cross-validation; not here. |
| Shared `<DangerActionDialog>` primitive | Three separate dialogs | CONTEXT.md §72 says "do NOT abstract until 2nd usage demands it". LogoutAll has no form field, DeleteAccount has email-match gate, Upgrade is non-destructive — surfaces diverge enough that a wrapper would carry too many props. Defer. |

**Installation:** No new packages. Every dep already in pyproject.toml + frontend/package.json.

**Version verification:** [VERIFIED: code references] All listed packages are already imported in the codebase — no `npm view` / `pip show` lookup needed for Phase 15. Package versions are governed by Phase 11 (backend) and Phase 14 (frontend) lockfiles.

---

## Architecture Patterns

### System Architecture Diagram

```
                                                                   ┌─ INPUT ─────────────────────────────────────────────────┐
                                                                   │                                                          │
                                          App boot                 │  User opens dashboard                                    │
                                          (any tab)                │  /dashboard/account                                      │
                                              │                    │                                                          │
                                              ▼                    │  Click "Sign out everywhere"  /  "Delete account"       │
                              ┌─────────────────────────────┐      │                                                          │
                              │ authStore.refresh()         │      │  Type email → submit                                     │
                              │ (Zustand store)             │      └──────────────────────┬───────────────────────────────────┘
                              │                             │                             │
                              │ apiClient.get(              │                             ▼
                              │   '/api/account/me',        │      ┌──────────────────────────────────────────┐
                              │   suppress401Redirect=true  │      │ AccountPage / 3 Dialogs                   │
                              │ )                           │      │  - LogoutAllDialog                        │
                              └─────────────┬───────────────┘      │  - DeleteAccountDialog (email-match gate) │
                                            │                      │  - UpgradeInterestDialog                  │
                                            │                      └────────┬─────────────────────────────────┘
                                            │                               │
                                            │                               ▼
                                            │                    ┌──────────────────────────┐
                                            │                    │ accountApi.ts            │
                                            │                    │  fetchAccountSummary()   │
                                            │                    │  logoutAllDevices()      │
                                            │                    │  deleteAccount(email)    │
                                            │                    │  submitUpgradeInterest() │
                                            │                    └────────────┬─────────────┘
                                            │                                 │
                                            ▼                                 ▼
                              ┌─────────────────────────────────────────────────────────┐
                              │ apiClient (single fetch site, UI-11)                    │
                              │  attaches credentials + X-CSRF-Token                    │
                              │  401 → redirect /login?next= (unless suppressed)        │
                              │  429 → throw RateLimitError                             │
                              └────────────┬────────────────────────────────────────────┘
                                           │
                                           ▼ (HTTP cookie session)
                              ┌─────────────────────────────────────────────────────────┐
                              │ DualAuthMiddleware                                      │
                              │  decodes cookie JWT → request.state.user                │
                              │  rejects ver-mismatch with 401 (token_version invariant)│
                              └────────────┬────────────────────────────────────────────┘
                                           │
                                           ▼
                              ┌─────────────────────────────────────────────────────────┐
                              │ FastAPI routes (auth_router + account_router)           │
                              │                                                          │
                              │  POST /auth/logout-all                                   │
                              │    → AuthService.logout_all_devices(user_id)            │
                              │    → user_repository.update_token_version(uid, ver+1)   │
                              │    → return Response(204) + _clear_auth_cookies         │
                              │                                                          │
                              │  GET /api/account/me                                     │
                              │    → AccountService.get_account_summary(user_id)        │
                              │    → return AccountSummaryResponse                       │
                              │                                                          │
                              │  DELETE /api/account                                     │
                              │    → AccountService.delete_account(uid, email_confirm)  │
                              │    → return Response(204) + _clear_auth_cookies         │
                              │                                                          │
                              │  POST /billing/checkout (BILL-05, EXISTING)              │
                              │    → 501 stub (no work in Phase 15)                     │
                              └────────────┬────────────────────────────────────────────┘
                                           │
                                           ▼
                              ┌─────────────────────────────────────────────────────────┐
                              │ AccountService.delete_account(uid, email_confirm)       │
                              │                                                          │
                              │  1. assert email_confirm.lower() == user.email.lower()  │
                              │     (else raise ValidationError → 400)                  │
                              │  2. delete_user_data(uid)  ← reuses SCOPE-05 path        │
                              │     (removes tasks + uploaded files)                    │
                              │  3. DELETE FROM rate_limit_buckets                      │
                              │     WHERE bucket_key LIKE 'user:<uid>:%'                │
                              │  4. user_repository.delete(uid)                         │
                              │     → ORM cascade fires for                             │
                              │        api_keys / subscriptions / usage_events /        │
                              │        device_fingerprints                              │
                              │  5. session.commit()                                    │
                              └────────────┬────────────────────────────────────────────┘
                                           │
                                           ▼
                              ┌─────────────────────────────────────────────────────────┐
                              │ SQLite (PRAGMA foreign_keys=ON, SCHEMA-05 enforced)     │
                              │  users / tasks / api_keys / subscriptions /             │
                              │  usage_events / device_fingerprints /                   │
                              │  rate_limit_buckets                                     │
                              └─────────────────────────────────────────────────────────┘
```

### Recommended Project Structure

**Backend additions:**
```
app/
├── api/
│   ├── account_routes.py        # ADD: GET /me, DELETE /api/account; KEEP existing DELETE /data
│   ├── auth_routes.py           # ADD: POST /auth/logout-all
│   └── schemas/
│       └── account_schemas.py   # NEW: AccountSummaryResponse, DeleteAccountRequest
└── services/
    └── account_service.py       # ADD: delete_account, get_account_summary; KEEP delete_user_data
```

**Frontend additions:**
```
frontend/src/
├── routes/
│   └── AccountPage.tsx                            # NEW (replaces AccountStubPage)
├── components/dashboard/
│   ├── UpgradeInterestDialog.tsx                  # NEW
│   ├── DeleteAccountDialog.tsx                    # NEW
│   └── LogoutAllDialog.tsx                        # NEW
├── lib/
│   ├── api/
│   │   └── accountApi.ts                          # NEW (mirrors keysApi.ts)
│   ├── apiClient.ts                               # MODIFY: add suppress401Redirect to GET
│   └── stores/
│       └── authStore.ts                           # MODIFY: add refresh() method + AccountUser fields
└── tests/msw/
    ├── account.handlers.ts                        # NEW (mirrors keys.handlers.ts)
    └── handlers.ts                                # MODIFY: import + spread accountHandlers
```

### Pattern 1: Cookie-Clearing Route Returns Brand-New Response

**What:** Routes that mutate cookies must return a NEW `Response(...)` object, not the injected one — otherwise FastAPI discards the `Set-Cookie` deletion headers.

**When to use:** `/auth/logout-all` and `DELETE /api/account` (cookie clearing on success).

**Example:**
```python
# Source: app/api/auth_routes.py:182-194 (logout pattern, verified)
@auth_router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_all(
    user: User = Depends(get_authenticated_user),
    auth_service: AuthService = Depends(get_auth_service),
) -> Response:
    auth_service.logout_all_devices(int(user.id))
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    _clear_auth_cookies(response)
    return response
```

**Anti-pattern (T-15-04):** Accepting `response: Response` as a Depends() parameter and calling `_clear_auth_cookies(response); return Response(204)` — the injected response is discarded; cookies stay live.

### Pattern 2: Service-Orchestrated Cascade with FK Backstop

**What:** When some FKs are CASCADE and others are SET NULL / no FK, the service orchestrates explicit deletes for the non-CASCADE rows, then triggers ORM `session.delete(user)` to fire the CASCADE for the rest.

**When to use:** `AccountService.delete_account` — see "FK Cascade Coverage" section.

**Example:**
```python
# Source: app/services/account_service.py:29-43 (delete_user_data pattern, verified)
def delete_account(self, user_id: int, email_confirm: str) -> dict[str, int]:
    """Cascade-delete the user. Email-confirm verified at boundary."""
    assert user_id > 0, "user_id must be positive"            # tiger-style boundary
    assert email_confirm.strip(), "email_confirm required"    # tiger-style boundary

    user = self.user_repository.get_by_id(user_id)
    if user is None:
        raise InvalidCredentialsError()                       # generic error (anti-enumeration)
    if email_confirm.strip().lower() != user.email.lower():
        raise ValidationError(
            message="Confirmation email does not match",
            code="EMAIL_CONFIRM_MISMATCH",
            user_message="Confirmation email does not match",
        )

    # Step 1: tasks + uploaded files (SET NULL FK + on-disk files)
    counts = self.delete_user_data(user_id)

    # Step 2: rate_limit_buckets (no FK — bucket_key text matching)
    bucket_count = self.session.execute(
        text("DELETE FROM rate_limit_buckets WHERE bucket_key LIKE :pattern"),
        {"pattern": f"user:{user_id}:%"},
    ).rowcount or 0

    # Step 3: user row → CASCADE fires for api_keys / subscriptions / usage_events / device_fingerprints
    deleted = self.user_repository.delete(user_id)
    if not deleted:
        raise InvalidCredentialsError()
    self.session.commit()
    logger.info(
        "Account deleted user_id=%s tasks=%s files=%s buckets=%s",
        user_id, counts["tasks_deleted"], counts["files_deleted"], bucket_count,
    )
    return {**counts, "rate_limit_buckets_deleted": bucket_count}
```

### Pattern 3: Probe-Style Boot Hydration with suppress401Redirect

**What:** On app boot, fetch `/api/account/me` with the redirect-suppressed flag. A 401 silently leaves user=null; RequireAuth then redirects normally. Avoids double-redirect race.

**When to use:** `authStore.refresh()` called once on app mount.

**Example (PRESCRIPTIVE):**
```typescript
// Source: pattern derived from frontend/src/lib/apiClient.ts:53,131,158-159 + 14-03 SUMMARY
// IMPORTANT: apiClient.get currently does NOT support suppress401Redirect — Phase 15 W0 must extend it.
refresh: async () => {
  try {
    const summary = await apiClient.get<AccountSummaryResponse>(
      '/api/account/me',
      { suppress401Redirect: true },   // NEW signature — see "API Client Extension" section
    );
    set({
      user: {
        id: summary.user_id,
        email: summary.email,
        planTier: summary.plan_tier,
        trialStartedAt: summary.trial_started_at,
        tokenVersion: summary.token_version,
      },
    });
  } catch (err) {
    // 401 throws AuthRequiredError; leave user=null; RequireAuth handles redirect.
    // Other errors also leave user=null; RequireAuth still redirects to /login.
    // No swallow-then-throw; just keep store at null.
    if (!(err instanceof AuthRequiredError) && !(err instanceof ApiClientError)) {
      throw err;
    }
  }
},
```

### Pattern 4: Type-Email Match Gate (Client + Server)

**What:** Browser disables destructive submit until `confirmEmail.trim().toLowerCase() === user.email.toLowerCase()`. Backend re-validates on receipt as defence-in-depth (T-15-02).

**When to use:** `DeleteAccountDialog` + `DELETE /api/account`.

**Example (frontend gate):**
```tsx
// Source: pattern derived from UI-SPEC.md §214-227
const isMatched = confirmEmail.trim().toLowerCase() === user.email.toLowerCase();
// ...
<Button type="submit" variant="destructive" disabled={!isMatched || submitting}>
  {submitting ? 'Deleting…' : 'Delete account'}
</Button>
```

**Backend match strategy [LOCKED]:** **case-insensitive** (UI-SPEC.md §190 says forgiving while still type-exact for backend). Both sides lowercase before compare. This avoids users typing the wrong case and getting a confusing "doesn't match" error when they typed the right address. Pydantic `EmailStr` does NOT lowercase — must do it in the service method.

### Anti-Patterns to Avoid

- **`tasks.user_id` left as SET NULL after a no-op cascade attempt:** The SET NULL FK is older (Phase 10 — pre-Phase 12 backfill). Phase 12 added a NOT NULL constraint via Migration 0003. A bare `session.delete(user)` would attempt to NULL `user_id` and the column NOT NULL constraint would raise `IntegrityError`. The service MUST delete tasks before the user row.
- **Pre-shaming type-email mismatch (UI-SPEC.md §219):** Don't show an alert while the user is still typing — only show on submit attempt or `400 EMAIL_CONFIRM_MISMATCH` from server. Reduces noise + matches "do not pre-shame" pattern.
- **Logging email or token in /me / delete handlers (T-13-13):** Stick to `user_id=N` only. Mirrors AUTH-09 + Phase 13 logging discipline.
- **Calling `apiClient.delete('/api/account', body)` if apiClient.delete doesn't accept body:** Need to verify in W0; current signature is `delete: <T>(path: string)`. If body unsupported, route should accept `email_confirm` as a query param OR apiClient.delete signature must be extended. **VERIFIED below.**

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Email format validation | Regex on email string | `pydantic.EmailStr` | Already used by `auth_schemas.py:RegisterRequest`; covers RFC edge cases; fails at parse time |
| Cascade delete for FK-CASCADE tables | Hand-rolled `for table in [api_keys, subscriptions, usage_events, device_fingerprints]: DELETE WHERE user_id=:uid` | `user_repository.delete(uid)` + ORM cascade | FK ON DELETE CASCADE already declared in `models.py` + migration 0002. SQLAlchemy fires it automatically with `session.delete(user)`. The orchestration above only adds explicit DELETEs for the two non-CASCADE tables. |
| JWT token-version invalidation | Build a session table / blacklist | `users.token_version` bump + `verify_and_refresh` ver-check | AUTH-06 design pattern already implemented; whole codebase relies on it. Don't introduce a second invalidation channel. |
| Cookie deletion | Manual `Set-Cookie: ...; Max-Age=0` strings | `response.delete_cookie(name, path='/')` via `_clear_auth_cookies` (auth_routes.py:101) | Existing DRY helper; respects domain + path config. |
| Boot-time auth probe | Custom retry loop with redirect coordination | `apiClient.get(path, {suppress401Redirect:true})` once on store creation | Single fetch site invariant (UI-11). Just extend the GET signature. |
| Test fixture DB setup | Manual sqlite3 INSERT + assert FK enforcement | `tmp_db_url` fixture from `test_account_routes.py:55-63` | `Base.metadata.create_all` + global FK listener gives full schema with CASCADE working. |
| Frontend HTTP wrapper for new endpoints | `fetch('/api/account/me', {credentials:'include'})` directly in components | Single `accountApi.ts` module + apiClient | UI-11 single fetch site invariant; verifier-checked. |
| Dialog state machine | Custom hooks library | `useState<'idle'\|'submitting'\|'success'\|'error'>` enum or paired booleans (CONTEXT §80) | Mirrors CreateKeyDialog pattern; no library needed. |
| Type-email validation timer/debounce | Async validation hook | Synchronous derived `isMatched` from input + user.email | UI-SPEC §227 explicit: "purely client-side based on lowercase compare — no debounce, no async". |
| Token version exposure for cross-tab debounce | Custom polling | `AccountSummaryResponse.token_version` field + BroadcastChannel comparison in tab handlers | CONTEXT.md §48 already designs the field; no library needed. |

**Key insight:** Phase 15 is almost entirely *integration* work. The cascade machinery exists in the schema; the AuthService logout-all helper exists; the apiClient + authStore + RequireAuth gate exist; shadcn primitives are vendored. The plan's job is to wire these into 3 routes + 1 page + 3 dialogs without building any new abstractions.

---

## FK Cascade Coverage [VERIFIED: alembic/versions/0002_auth_schema.py + app/infrastructure/database/models.py]

This is the highest-criticality finding. `tasks.user_id` is **SET NULL** (not CASCADE) and `rate_limit_buckets` has **no FK at all**. A single `DELETE FROM users WHERE id = :uid` fails or orphans data.

### Foreign-Key Audit (every FK from `users.id`)

| Table | FK column | nullable | ondelete | Source |
|-------|-----------|----------|----------|--------|
| `tasks` | `user_id` | NOT NULL (after migration 0003) | **SET NULL** | `models.py:140-145`, `0002_auth_schema.py:204` |
| `api_keys` | `user_id` | NOT NULL | CASCADE | `models.py:241-246`, `0002_auth_schema.py:75` |
| `subscriptions` | `user_id` | NOT NULL | CASCADE | `models.py:310-315`, `0002_auth_schema.py:103` |
| `usage_events` | `user_id` | NOT NULL | CASCADE | `models.py:373-378`, `0002_auth_schema.py:130` |
| `device_fingerprints` | `user_id` | NOT NULL | CASCADE | `models.py:466-475`, `0002_auth_schema.py:172` |
| `rate_limit_buckets` | (no FK; `bucket_key` text key like `user:42:hour`) | n/a | n/a | `models.py:419-442`, `app/services/free_tier_gate.py:80,175,214` |

### Cascade Strategy Decision

**Three viable strategies:**

| Strategy | Pros | Cons | Recommendation |
|----------|------|------|----------------|
| **A. Single `DELETE FROM users`** | Smallest code | **Fails:** SET NULL fires on tasks → tries to NULL `user_id` → IntegrityError on NOT NULL constraint added by 0003. Plus `rate_limit_buckets` orphaned. | **REJECT** |
| **B. Add migration 0004 to flip tasks → CASCADE + add user_id FK to rate_limit_buckets** | Cleaner long-term semantics | Requires bucket_key parsing + new column; migration risk inside Phase 15 (not its purpose). | **DEFER** to v1.3 if desired. |
| **C. Service-orchestrated explicit pre-delete + ORM cascade** | Contained, reversible, mirrors existing `delete_user_data` (SCOPE-05) | Slightly more code in service | **RECOMMEND** |

**Locked recommendation: Strategy C.** Order matters:

1. Call `self.delete_user_data(user_id)` — reuses Phase 13 SCOPE-05 path; deletes tasks + uploaded files; commits.
2. `DELETE FROM rate_limit_buckets WHERE bucket_key LIKE 'user:<uid>:%'` — string-prefix match catches all per-user buckets (`user:42:hour`, `user:42:tx:hour`, `user:42:audio_min:day`, `user:42:concurrent`); does NOT match per-IP (`ip:10.0.0.0/24:register:hour`).
3. `self.user_repository.delete(user_id)` → SQLAlchemy `session.delete(orm_user)` fires CASCADE for `api_keys`, `subscriptions`, `usage_events`, `device_fingerprints`. PRAGMA `foreign_keys = ON` is enforced (verified `connection.py:32-56`).
4. `self.session.commit()` — single transaction at the user-delete step (delete_user_data already committed step 1; that's fine — they are independent units).

**Why not single transaction across all 3 steps:** `delete_user_data` calls `self.session.commit()` mid-flow already (`account_service.py:60`). Re-using it preserves the SCOPE-05 contract. Deleting account is rare; transactional atomicity across files-on-disk + DB rows is impossible anyway (file unlink already best-effort). Acceptable trade-off.

### Verification Test (REQUIRED in plan)

Plan a single integration test that seeds a user with one row in **every** dependent table (tasks, api_keys, subscriptions, usage_events, device_fingerprints, rate_limit_buckets), calls DELETE /api/account, and asserts `SELECT COUNT(*) FROM <each_table> WHERE user_id = :uid` returns 0 (and bucket_key LIKE matches return 0). Plus a second test that asserts the `users` row is gone.

---

## Token-Version Invariant [VERIFIED: app/services/auth/auth_service.py:91-97 + app/services/auth/token_service.py:34-49 + app/core/jwt_codec.py:24-45]

### How It Works

1. **Issue:** `TokenService.issue(user_id, token_version)` → `jwt_codec.encode_session(...)` embeds `ver: token_version` in the JWT payload alongside `sub`, `iat`, `exp`, `method`.
2. **Verify:** `TokenService.verify_and_refresh(token, current_token_version)` decodes the JWT, then **explicitly checks** `payload.get("ver") != current_token_version` → raises `JwtTamperedError` (which DualAuthMiddleware maps to 401).
3. **Bump:** `AuthService.logout_all_devices(user_id)` → `user_repository.update_token_version(user_id, user.token_version + 1)`. Atomic update; new value persisted before the route returns.

### Logout-All Idempotency

- Calling logout-all twice for the same user just increments `token_version` from N to N+1 to N+2. No JWT outstanding can match either — invalidation is monotonic.
- The caller's own JWT in the response chain has `ver = N`. After the bump, `current_token_version = N+1`. The caller's NEXT request 401s automatically. Cookie-clearing on the response just makes the UX cleaner (browser stops sending the doomed cookie).
- No race window: the bump is committed before the response is sent. Even if a concurrent request held a `ver=N` JWT, it 401s the moment middleware reads `current_token_version` from DB.

### Implementation Notes

- The route MUST also bump_token_version for **the deletion path** (DELETE /api/account). Otherwise an in-flight request with the old JWT could observe deleted state. Belt-and-braces: when the user row is deleted, all JWTs with `sub=user_id` are dead anyway (the next middleware call to `user_repository.get_by_id` returns None → 401). But explicit cookie-clearing on the response MUST happen for UX consistency.
- DELETE /api/account does NOT need a separate token_version bump — the user row goes away, so future cookie validation lookups all fail. **Locked: don't double-bump on delete.** Cookie clearing alone is sufficient.

---

## API Client Extension [CRITICAL: must land in W0]

### Current Gap

`frontend/src/lib/apiClient.ts:155-166` — only `post` accepts `{suppress401Redirect: boolean}`. `get`, `put`, `patch`, `delete` do not.

```typescript
// Source: frontend/src/lib/apiClient.ts:155-166 (verified)
export const apiClient = {
  get: <T>(path: string, headers?: Record<string, string>) =>
    request<T>({ method: 'GET', path, headers }),
  post: <T>(path: string, body?: unknown, opts?: { suppress401Redirect?: boolean }) =>
    request<T>({ method: 'POST', path, body, suppress401Redirect: opts?.suppress401Redirect }),
  // ... put / patch / delete identical to get (no suppress flag)
};
```

### Required Changes (W0 task)

1. **Extend `get` to accept `{suppress401Redirect}`:**
```typescript
get: <T>(path: string, opts?: { headers?: Record<string, string>; suppress401Redirect?: boolean }) =>
  request<T>({ method: 'GET', path, headers: opts?.headers, suppress401Redirect: opts?.suppress401Redirect }),
```

2. **Verify `delete` accepts a body** (DELETE /api/account needs `{email_confirm}` body):
```typescript
// Source: frontend/src/lib/apiClient.ts:164-165 (verified — current signature has NO body slot)
delete: <T>(path: string) => request<T>({ method: 'DELETE', path }),
```

DELETE /api/account requires a JSON body. **Two options:**

| Option | Pros | Cons |
|--------|------|------|
| Extend `apiClient.delete` to accept body | DRY; matches REST convention (some servers accept body on DELETE) | TypeScript signature change; existing `revokeKey(id)` callsite unaffected (still works without body) |
| Send `email_confirm` as query param | No apiClient change | Breaks RESTful body convention; URL exposes confirmation email in browser history + access logs (privacy regression) |

**Locked recommendation:** Extend `apiClient.delete` to accept an optional body. Implementation:
```typescript
delete: <T>(path: string, body?: unknown) =>
  request<T>({ method: 'DELETE', path, body }),
```
The existing `request()` function already supports body on any method (`buildBody(opts)` line 74-79).

3. **Backend route signature:** FastAPI accepts JSON body on DELETE — supported since Starlette 0.13. No special config needed. Pydantic schema works as `body: DeleteAccountRequest` parameter. [VERIFIED: codebase pattern from `key_routes.py` DELETE — no body, but FastAPI docs allow it.]

### Caller Migration

After the W0 change:
- `accountApi.deleteAccount(emailConfirm)` → `apiClient.delete('/api/account', {email_confirm: emailConfirm})`
- `keysApi.revokeKey(id)` → `apiClient.delete(\`/api/keys/\${id}\`)` — unchanged.
- All existing GET callers unaffected — second positional arg now an options object instead of headers, but the only existing GET caller (`fetchKeys`) doesn't pass headers.

**Verify:** grep `apiClient\.(get|delete)\(` across `frontend/src` to confirm callsite count before refactor.

---

## AccountSummaryResponse Schema [LOCKED]

### Backend (Pydantic)

```python
# app/api/schemas/account_schemas.py — NEW file
from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field


class AccountSummaryResponse(BaseModel):
    """GET /api/account/me — server-side hydration source-of-truth (CONTEXT §48)."""
    user_id: int
    email: EmailStr
    plan_tier: str = Field(..., description="One of free|trial|pro|team")
    trial_started_at: datetime | None = None
    token_version: int = Field(..., description="For cross-tab refresh debounce")


class DeleteAccountRequest(BaseModel):
    """DELETE /api/account body. email_confirm validated against user.email at boundary."""
    email_confirm: EmailStr = Field(
        ..., description="Must equal request.state.user.email (case-insensitive)"
    )
```

### Frontend (TypeScript types in `accountApi.ts`)

```typescript
// frontend/src/lib/api/accountApi.ts — NEW file
import { apiClient } from '@/lib/apiClient';

export interface AccountSummaryResponse {
  user_id: number;
  email: string;
  plan_tier: 'free' | 'trial' | 'pro' | 'team';
  trial_started_at: string | null;   // ISO8601 tz-aware UTC string
  token_version: number;
}

export function fetchAccountSummary(): Promise<AccountSummaryResponse> {
  return apiClient.get<AccountSummaryResponse>(
    '/api/account/me',
    { suppress401Redirect: true },
  );
}

export function logoutAllDevices(): Promise<void> {
  return apiClient.post<void>('/auth/logout-all');
}

export function deleteAccount(emailConfirm: string): Promise<void> {
  return apiClient.delete<void>('/api/account', { email_confirm: emailConfirm });
}

export function submitUpgradeInterest(message: string): Promise<void> {
  // 501 from /billing/checkout is swallowed as success in the dialog handler.
  return apiClient.post<void>('/billing/checkout', { plan: 'pro', message });
}
```

### Datetime Serialization

- Backend: tz-aware UTC `datetime` (verified `app/infrastructure/database/models.py:202-203` + `_created_at_column()` factory) — Pydantic v2 default emits `2026-04-29T12:34:56.123456+00:00` (ISO8601).
- Frontend: parse with `new Date(summary.trial_started_at!)` for display formatting. Treat as opaque string in store; render via `toLocaleDateString()` in components.

### Authoritative Source for Email

- Backend stores email at registration time. Server is source-of-truth.
- Frontend currently stores email from form input (Plan 14-03 trade-off, STATE.md:226). After Phase 15, `authStore.refresh()` overrides with server email. AuthUser.email becomes server-authoritative on every page load.

---

## Frontend authStore.refresh Wiring [CRITICAL]

### What Currently Exists [VERIFIED: frontend/src/lib/stores/authStore.ts]

`authStore` has `login`, `register`, `logout`. **It does NOT have `refresh()`.** CONTEXT.md §64 says "refresh() exists already (Plan 14-03)" — this is **incorrect**. Plan 14-03 SUMMARY explicitly says "refresh()/hydrate-on-boot deliberately omitted — Phase 14 backend has no /api/account/me endpoint." Phase 15 must **add** `refresh()`, not extend it.

### AuthState Shape Extension

Current shape (verified at `authStore.ts:21-25`):
```typescript
export interface AuthUser {
  id: number;
  email: string;
  planTier: string;
}
```

Extended for /me hydration (LOCKED):
```typescript
export interface AuthUser {
  id: number;
  email: string;
  planTier: string;          // server-authoritative after refresh()
  trialStartedAt: string | null;   // ISO8601 string, null until first key
  tokenVersion: number;            // for cross-tab debounce
}

interface AuthState {
  user: AuthUser | null;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;     // NEW
}
```

### Boot Trigger Strategy [LOCKED]

Two viable hooks for triggering `refresh()`:

| Strategy | Pros | Cons |
|----------|------|------|
| Call `refresh()` once at app entry (e.g., `main.tsx` before `<App />` render) | Simple; runs before any route resolves | Renders briefly with `user=null`; RequireAuth could redirect-flash |
| Call `refresh()` inside `<RequireAuth>` via `useEffect` and gate render on a `hydrating` flag | No flash; clean separation | Adds a third state to RequireAuth (loading/auth/anon) |

**LOCKED: Strategy 1 with one tweak — extend `AuthState` with a transient `isHydrating: boolean` initial-true flag. RequireAuth waits one tick if `isHydrating === true`; flips false in `refresh()`'s finally block.** This avoids the redirect-flash without a Suspense boundary.

```typescript
// authStore.ts — locked addition
isHydrating: true,
refresh: async () => {
  try {
    const summary = await apiClient.get<AccountSummaryResponse>(
      '/api/account/me',
      { suppress401Redirect: true },
    );
    set({
      user: {
        id: summary.user_id,
        email: summary.email,
        planTier: summary.plan_tier,
        trialStartedAt: summary.trial_started_at,
        tokenVersion: summary.token_version,
      },
    });
  } catch (err) {
    // 401 / network / etc. — leave user=null; RequireAuth handles redirect
    if (!(err instanceof AuthRequiredError) && !(err instanceof ApiClientError)) {
      throw err;   // re-throw genuinely unexpected errors
    }
  } finally {
    set({ isHydrating: false });
  }
},
```

`main.tsx` (or `App.tsx`) calls `useAuthStore.getState().refresh()` once at module load.

`RequireAuth` (modify `frontend/src/routes/RequireAuth.tsx:12-22`):
```tsx
export function RequireAuth() {
  const user = useAuthStore((s) => s.user);
  const isHydrating = useAuthStore((s) => s.isHydrating);
  const location = useLocation();

  if (isHydrating) return null;   // or a tiny skeleton; locked to null per UI-SPEC §253

  if (user === null) {
    const next = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/login?next=${next}`} replace />;
  }
  return <Outlet />;
}
```

### Test Coverage Required

- `authStore.refresh()` happy path → user populated from response.
- `authStore.refresh()` 401 → user stays null, no redirect (suppress=true), `isHydrating` flips to false.
- `authStore.refresh()` network error → user stays null, isHydrating flips to false.
- `RequireAuth` while `isHydrating=true` renders nothing (does not redirect).
- `RequireAuth` after hydration with user=null redirects to /login?next=.

---

## Type-Email Confirmation Strategy

### UI Side (UI-SPEC.md §190 + §227 — locked)

- Compare: `confirmEmail.trim().toLowerCase() === user.email.toLowerCase()`
- Submit button `disabled={!isMatched || submitting}`; flips on every keystroke once match holds.
- No async validation, no debounce.

### Backend Side (defence-in-depth — T-15-02)

- Pydantic `EmailStr` validates the field is RFC-shaped at parse time (rejects malformed; 422 auto-response from FastAPI).
- AccountService manually compares `email_confirm.strip().lower() == user.email.lower()`. Mismatch → `ValidationError(message="Confirmation email does not match")` → 400 generic body.

### Why Both Layers

- UI-only gate could be bypassed by a malicious browser extension or direct API call from an authenticated session. Backend re-check is the security boundary.
- A `pydantic field_validator` could compare against `request.state.user.email`, but Pydantic schemas are framework-agnostic and shouldn't reach into `request.state`. Service-layer comparison is cleaner SRP.

### Pydantic field_validator vs Service-Level Guard [LOCKED: SERVICE-LEVEL]

| Approach | Verdict |
|----------|---------|
| `@field_validator` on DeleteAccountRequest comparing to user | **REJECT** — schema would need access to authenticated user; breaks SRP; awkward DI. |
| Route-level guard `if body.email_confirm.lower() != user.email.lower()` | OK but couples HTTP layer to business rule. |
| **Service-level guard inside `AccountService.delete_account`** | **LOCKED** — keeps business rule with the data; mirrors `AuthService.login` pattern of comparing inside service. |

---

## Common Pitfalls

### Pitfall 1: Cookie Deletion on Returned Response Discards Headers

**What goes wrong:** Setting `delete_cookie` on the FastAPI-injected `response: Response = Depends(...)` parameter, then returning a separate `Response(...)` — the deletion headers are dropped.

**Why it happens:** FastAPI applies the injected response only when the route returns a non-Response value. Returning an explicit Response instance overrides it.

**How to avoid:** Always create a brand-new `Response(...)` and call `_clear_auth_cookies(response)` on it before returning.

**Warning signs:** Logout-all returns 204 but the browser still sends `session=...` on the next request (cookie wasn't cleared).

**Reference:** `auth_routes.py:182-194` (logout pattern, verified).

### Pitfall 2: Tasks Orphaned by SET NULL on User Delete

**What goes wrong:** Calling `session.delete(user)` triggers SET NULL on `tasks.user_id` — but `tasks.user_id` is NOT NULL after migration 0003. SQLite raises `IntegrityError`.

**Why it happens:** Migration 0002 declared `ondelete="SET NULL"` for tasks (when nullable was OK during backfill). Migration 0003 tightened to NOT NULL but didn't change the FK action.

**How to avoid:** Always `delete_user_data(uid)` (which `DELETE FROM tasks WHERE user_id = :uid` outright) BEFORE the user row delete.

**Warning signs:** Integration test seeding a task + deleting the user fails with `sqlalchemy.exc.IntegrityError: NOT NULL constraint failed: tasks.user_id`.

### Pitfall 3: rate_limit_buckets Orphaned by Lack of FK

**What goes wrong:** User deleted, but per-user buckets (`user:42:hour`, `user:42:concurrent`, etc.) remain in `rate_limit_buckets`. Future user with reused id 42 inherits the buckets — silent data corruption.

**Why it happens:** `rate_limit_buckets` schema uses string `bucket_key` (`user:42:hour`) and has no FK to `users.id` (verified `models.py:419-442`).

**How to avoid:** Service explicitly deletes `WHERE bucket_key LIKE 'user:<uid>:%'` before user-row delete.

**Warning signs:** After two delete-then-create-with-same-email cycles in tests, the new user's first request 429s because the old user's hour-bucket is exhausted.

### Pitfall 4: token_version Not Bumped on Account Delete (T-15-03)

**What goes wrong:** Concurrent in-flight request with valid JWT for a deleted user could observe partially-deleted state during the brief window the user row exists.

**Why it happens:** Race between session.delete commit and the next request's middleware lookup.

**How to avoid:** Not strictly necessary — `user_repository.get_by_id` returns None after the delete commits, so middleware 401s. But explicit cookie-clearing on the response makes the client-side deterministic. **Locked: don't bump token_version on delete; rely on user-row-gone as the invalidation signal.** Cookie clearing handles the client UX.

**Warning signs:** Delete-account integration test passes, but a follow-up request with the same cookie returns 200 instead of 401 — would indicate middleware caching the user lookup. (No such cache exists today; sanity-checked.)

### Pitfall 5: ApiClient `delete()` Currently Ignores Body

**What goes wrong:** Calling `apiClient.delete('/api/account', {email_confirm: ...})` silently sends DELETE with no body. Server gets `{}` body → Pydantic 422 → frontend renders generic error.

**Why it happens:** Current signature is `delete: <T>(path: string) =>` — no second arg. TypeScript error caught by tsc, but runtime devastating if developer ignores tsc.

**How to avoid:** W0 task to extend signature to `delete: <T>(path: string, body?: unknown) =>`. Verify TS error in plan-checker.

**Warning signs:** AccountPage delete dialog reports 422 "field required" even when user typed correct email.

### Pitfall 6: 501 from /billing/checkout Treated as Error (UI-SPEC.md §245)

**What goes wrong:** ApiClient throws `ApiClientError(501, ...)` for non-2xx; `UpgradeInterestDialog` renders error alert instead of "Thanks!" success state.

**Why it happens:** ApiClient's response.ok check (`apiClient.ts:143`) considers 501 an error.

**How to avoid:** Catch `ApiClientError` with `error.statusCode === 501` and treat as success in the dialog handler. Document explicitly in `submitUpgradeInterest` JSDoc.

**Warning signs:** Dialog shows "Could not send. Try again." even when backend stub responds correctly.

### Pitfall 7: Phase 15 Verifier `grep -cE "^\s+if .*\bif\b"` Tripping on Inline Conditionals

**What goes wrong:** `if isMatched: if submitting: ...` style triggers verifier nested-if grep.

**Why it happens:** Beginner instinct to nest. CONTEXT.md §76 locks this verifier.

**How to avoid:** Use guard-clause early returns: `if not isMatched: return error_state; ...`. Or boolean composition: `if isMatched and not submitting: ...`.

**Warning signs:** plan-check or verifier emits "nested-if violation in DeleteAccountDialog.tsx" or "in account_service.py".

---

## Code Examples

### Backend: account_service.delete_account [PRESCRIPTIVE TEMPLATE]

```python
# app/services/account_service.py — extension; preserves existing delete_user_data
def delete_account(self, user_id: int, email_confirm: str) -> dict[str, int]:
    """SCOPE-06: full-row delete + cascade. Email-confirm verified.

    Returns counts: {"tasks_deleted": N, "files_deleted": M,
    "rate_limit_buckets_deleted": K}. user row + api_keys/subscriptions/
    usage_events/device_fingerprints removed via FK CASCADE.
    """
    # Tiger-style boundary assertions
    assert user_id > 0, "user_id must be positive"
    assert email_confirm and email_confirm.strip(), "email_confirm required"

    # Defence-in-depth: re-verify email match server-side (T-15-02)
    user = self._user_repository().get_by_id(user_id)
    if user is None:
        # Generic anti-enumeration error matching Phase 13 patterns
        raise InvalidCredentialsError()
    if email_confirm.strip().lower() != user.email.lower():
        raise ValidationError(
            message="Confirmation email does not match",
            code="EMAIL_CONFIRM_MISMATCH",
            user_message="Confirmation email does not match",
        )

    # Step 1: tasks + uploaded files (handles SET NULL FK + on-disk files)
    counts = self.delete_user_data(user_id)

    # Step 2: rate_limit_buckets (no FK; bucket_key text prefix match)
    bucket_count = self.session.execute(
        text(
            "DELETE FROM rate_limit_buckets WHERE bucket_key LIKE :pattern"
        ),
        {"pattern": f"user:{user_id}:%"},
    ).rowcount or 0

    # Step 3: user row → CASCADE fires for api_keys/subscriptions/
    # usage_events/device_fingerprints (FK ON DELETE CASCADE per
    # alembic 0002_auth_schema.py)
    deleted = self._user_repository().delete(user_id)
    if not deleted:
        raise InvalidCredentialsError()
    self.session.commit()
    logger.info(
        "Account deleted user_id=%s tasks=%s files=%s buckets=%s",
        user_id, counts["tasks_deleted"], counts["files_deleted"], bucket_count,
    )
    return {**counts, "rate_limit_buckets_deleted": bucket_count}


def get_account_summary(self, user_id: int) -> dict:
    """GET /api/account/me — pure read of users row."""
    assert user_id > 0, "user_id must be positive"
    user = self._user_repository().get_by_id(user_id)
    if user is None:
        raise InvalidCredentialsError()
    return {
        "user_id": int(user.id),
        "email": user.email,
        "plan_tier": user.plan_tier,
        "trial_started_at": user.trial_started_at,
        "token_version": user.token_version,
    }
```

**Note:** AccountService currently does NOT have a `_user_repository` member — it only takes `session`. The plan must either inject `user_repository` into `AccountService.__init__` (preserving SCOPE-05 behaviour by making it optional) OR construct one inline from the session: `SQLAlchemyUserRepository(self.session)`. **Locked recommendation: constructor-inject** for testability + DRY across `delete_account` and `get_account_summary`.

### Backend: New Routes

```python
# app/api/account_routes.py — additions
@account_router.get("/me", response_model=AccountSummaryResponse)
async def get_account_me(
    user: User = Depends(get_authenticated_user),
    account_service: AccountService = Depends(get_account_service),
) -> AccountSummaryResponse:
    """GET /api/account/me — return summary for client hydration."""
    summary = account_service.get_account_summary(int(user.id))
    return AccountSummaryResponse(**summary)


@account_router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    body: DeleteAccountRequest,
    user: User = Depends(get_authenticated_user),
    account_service: AccountService = Depends(get_account_service),
) -> Response:
    """DELETE /api/account — cascade delete + clear cookies."""
    account_service.delete_account(int(user.id), body.email_confirm)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    _clear_auth_cookies(response)   # imported from auth_routes
    return response
```

```python
# app/api/auth_routes.py — addition
@auth_router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_all(
    user: User = Depends(get_authenticated_user),
    auth_service: AuthService = Depends(get_auth_service),
) -> Response:
    """POST /auth/logout-all — bump token_version + clear cookies. AUTH-06."""
    auth_service.logout_all_devices(int(user.id))
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    _clear_auth_cookies(response)
    return response
```

**Cookie-clearing reuse:** `_clear_auth_cookies` is currently a private function in `auth_routes.py`. Phase 15 needs it in `account_routes.py` too. **Locked: extract to a shared helper** at `app/api/_cookie_helpers.py` (or expose via re-export from `auth_routes`). DRY.

### Frontend: AccountPage Skeleton

```tsx
// frontend/src/routes/AccountPage.tsx — NEW
import { useEffect, useState } from 'react';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { useAuthStore } from '@/lib/stores/authStore';
import { fetchAccountSummary, type AccountSummaryResponse } from '@/lib/api/accountApi';
import { ApiClientError, RateLimitError } from '@/lib/apiClient';
import { UpgradeInterestDialog } from '@/components/dashboard/UpgradeInterestDialog';
import { DeleteAccountDialog } from '@/components/dashboard/DeleteAccountDialog';
import { LogoutAllDialog } from '@/components/dashboard/LogoutAllDialog';

const PLAN_BADGE_VARIANT: Record<AccountSummaryResponse['plan_tier'], 'default' | 'secondary' | 'outline'> = {
  free: 'secondary',
  trial: 'outline',
  pro: 'default',
  team: 'default',
};

const PLAN_COPY: Record<AccountSummaryResponse['plan_tier'], string> = {
  free: "You're on the Free plan. 5 transcribes per hour, files up to 5 minutes, 30 min/day, tiny + small models only.",
  trial: "You're on the 7-day Free trial. Upgrade to Pro to keep diarization, large-v3, and 100 req/hr after it ends.",
  pro: "You're on Pro. 100 req/hr, files up to 60 min, 600 min/day, all models, diarization enabled. Thanks for the support.",
  team: "You're on Team. All Pro features, plus shared workspace primitives shipping post-v1.2.",
};

export function AccountPage() {
  const user = useAuthStore((s) => s.user);
  const [summary, setSummary] = useState<AccountSummaryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [upgradeOpen, setUpgradeOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [logoutAllOpen, setLogoutAllOpen] = useState(false);

  const refresh = async () => {
    setError(null);
    try {
      setSummary(await fetchAccountSummary());
    } catch (err) {
      // RateLimitError BEFORE ApiClientError (subtype-first per UI-09)
      if (err instanceof RateLimitError) {
        setError(`Rate limited. Try again in ${err.retryAfterSeconds}s.`);
        return;
      }
      if (err instanceof ApiClientError) {
        setError('Could not load account.');
        return;
      }
      setError('Could not load account.');
    }
  };
  useEffect(() => { refresh(); }, []);

  // Loading skeleton + error + ready states (UI-SPEC.md §253-256)
  // ... (locked layout per UI-SPEC.md §116-160)
}
```

### Frontend: Type-Email Match Logic

```tsx
// DeleteAccountDialog.tsx (excerpt — locked from UI-SPEC.md §214-227)
const [confirmEmail, setConfirmEmail] = useState('');
const [submitting, setSubmitting] = useState(false);
const [error, setError] = useState<string | null>(null);

const isMatched =
  confirmEmail.trim().toLowerCase() === userEmail.toLowerCase();

const handleSubmit = async (e: React.FormEvent) => {
  e.preventDefault();
  if (!isMatched) return;     // defence; should never trigger because button disabled
  setSubmitting(true);
  setError(null);
  try {
    await deleteAccount(confirmEmail);
    await authStore.logout();   // clears state + broadcasts
    navigate('/login', { replace: true });
  } catch (err) {
    if (err instanceof RateLimitError) {
      setError(`Too many requests. Try again in ${err.retryAfterSeconds}s.`);
    } else if (err instanceof ApiClientError) {
      setError(err.statusCode === 400
        ? 'Confirmation email does not match.'
        : 'Could not delete account. Try again.');
    } else {
      setError('Could not delete account. Try again.');
    }
  } finally {
    setSubmitting(false);
  }
};
```

---

## Test Patterns

### Backend Integration Tests (mirror `test_account_routes.py`) [VERIFIED PATTERNS]

**Test fixtures already in place:** `tmp_db_url`, `session_factory`, `account_app`, `client`, `_register` helper. Phase 15 extends with:

- `_seed_full_user_universe(session_factory, user_id)` helper that INSERTs one row in each dependent table (tasks, api_keys, subscriptions, usage_events, device_fingerprints, rate_limit_buckets w/ `user:{uid}:hour` key).
- New tests required (≥6 cases per Phase 13 plan-check pattern):

| # | Test Name | Coverage |
|---|-----------|----------|
| 1 | `test_get_account_me_returns_summary` | GET /me happy path; shape matches AccountSummaryResponse |
| 2 | `test_get_account_me_requires_auth` | No cookie → 401 |
| 3 | `test_logout_all_bumps_token_version` | Pre/post DB read of users.token_version; +1; cookie cleared in response headers |
| 4 | `test_logout_all_invalidates_existing_jwt` | Issue JWT pre-bump; bump; same JWT → 401 on next request via TestClient |
| 5 | `test_delete_account_cascade_full_universe` | Seed all 7 tables; DELETE; assert COUNT(*) == 0 in each WHERE user_id = :uid (and bucket_key LIKE) |
| 6 | `test_delete_account_email_mismatch_400` | Body email != user.email → 400 + `EMAIL_CONFIRM_MISMATCH` code; user row + tasks intact |
| 7 | `test_delete_account_email_case_insensitive` | Body `Foo@Example.com` matches stored `foo@example.com` → 204 |
| 8 | `test_delete_account_clears_cookies` | Response Set-Cookie deletes session + csrf_token |
| 9 | `test_delete_account_requires_auth` | No cookie → 401 |
| 10 | `test_delete_account_preserves_other_user_data` | Cross-user isolation (mirrors test 5 of existing /data tests) — Phase 16 owns full matrix but smoke here |

### Frontend Tests (mirror `KeysDashboardPage.test.tsx` + `CreateKeyDialog.test.tsx`) [VERIFIED PATTERNS]

**MSW handlers** in `frontend/src/tests/msw/account.handlers.ts`:

```typescript
// account.handlers.ts — NEW
import { http, HttpResponse } from 'msw';

export const accountHandlers = [
  http.get('/api/account/me', () =>
    HttpResponse.json({
      user_id: 1,
      email: 'alice@example.com',
      plan_tier: 'trial',
      trial_started_at: '2026-04-22T12:00:00Z',
      token_version: 0,
    }),
  ),
  http.delete('/api/account', () => new HttpResponse(null, { status: 204 })),
  http.post('/auth/logout-all', () => new HttpResponse(null, { status: 204 })),
  http.post('/billing/checkout', () =>
    HttpResponse.json(
      { detail: 'Not Implemented', status: 'stub', hint: 'Stripe integration arrives in v1.3' },
      { status: 501 },
    ),
  ),
];
```

**Page + dialog tests:**

| # | Test File | Test Name | Coverage |
|---|-----------|-----------|----------|
| 1 | `AccountPage.test.tsx` | renders email + plan_tier badge after hydration | uses MSW default handler |
| 2 | `AccountPage.test.tsx` | renders error card on /me 500 | override handler |
| 3 | `AccountPage.test.tsx` | reload-account button retries fetch | findByRole click |
| 4 | `AccountPage.test.tsx` | hides Upgrade button when plan_tier='pro' | override handler |
| 5 | `DeleteAccountDialog.test.tsx` | submit disabled when input empty | findByRole('button') + toBeDisabled() |
| 6 | `DeleteAccountDialog.test.tsx` | submit enables on case-insensitive match | type 'ALICE@example.com' for stored 'alice@example.com' |
| 7 | `DeleteAccountDialog.test.tsx` | submit calls authStore.logout + navigates /login | mock logout, assertion on navigate |
| 8 | `DeleteAccountDialog.test.tsx` | 400 mismatch shows error alert | override handler 400 |
| 9 | `LogoutAllDialog.test.tsx` | confirm calls authStore.logout + navigates /login | mock logout |
| 10 | `LogoutAllDialog.test.tsx` | 429 shows Retry-After countdown | override handler |
| 11 | `UpgradeInterestDialog.test.tsx` | submits, swallows 501, shows Thanks copy | default 501 handler |
| 12 | `UpgradeInterestDialog.test.tsx` | auto-closes 2s after success | vi.useFakeTimers + advance 2000 |
| 13 | `authStore.test.tsx` | refresh() populates user from /me | success handler |
| 14 | `authStore.test.tsx` | refresh() 401 leaves user null, no redirect | override 401 |
| 15 | `authStore.test.tsx` | refresh() flips isHydrating to false | initial state assertion |
| 16 | `RequireAuth.test.tsx` | renders nothing while isHydrating=true | mock store |
| 17 | `RequireAuth.test.tsx` | redirects to /login after isHydrating=false + user=null | mock store |
| 18 | `accountApi.test.ts` | deleteAccount sends body with email_confirm | spy on fetch |

**Async pattern (TEST-05 locked):** Always `await user.click(...)` and `await screen.findByRole(...)` — never `screen.getByRole` after a state change.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Backend framework | pytest 8.x + FastAPI TestClient + dependency-injector overrides |
| Backend config file | `pytest.toml` (existing) |
| Backend quick run command | `pytest tests/integration/test_account_routes.py tests/integration/test_auth_routes.py -x -m integration` |
| Backend full suite command | `pytest -m "integration or unit" -x` |
| Frontend framework | Vitest 3.2 + jsdom + @testing-library/react 16.1 + MSW 2.13 |
| Frontend config file | `frontend/vitest.config.ts` (existing) |
| Frontend quick run command | `npm --prefix frontend run test -- AccountPage DeleteAccountDialog LogoutAllDialog UpgradeInterestDialog` |
| Frontend full suite command | `npm --prefix frontend run test` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|--------------|
| AUTH-06 | Logout-all bumps token_version; old JWTs invalid | integration | `pytest tests/integration/test_auth_routes.py::test_logout_all_invalidates_existing_jwt -x` | ❌ Wave 0 / W1 |
| AUTH-06 | Logout-all clears cookies + 204 | integration | `pytest tests/integration/test_auth_routes.py::test_logout_all_clears_cookies -x` | ❌ W1 |
| SCOPE-06 | DELETE /api/account cascades all dependent tables | integration | `pytest tests/integration/test_account_routes.py::test_delete_account_cascade_full_universe -x` | ❌ W1 |
| SCOPE-06 | Email mismatch → 400 + generic copy | integration | `pytest tests/integration/test_account_routes.py::test_delete_account_email_mismatch_400 -x` | ❌ W1 |
| SCOPE-06 | Case-insensitive email match → 204 | integration | `pytest tests/integration/test_account_routes.py::test_delete_account_email_case_insensitive -x` | ❌ W1 |
| UI-07 | AccountPage renders email + plan_tier badge | RTL | `vitest run AccountPage` | ❌ W3 |
| UI-07 | DeleteAccountDialog enables submit on type-email match | RTL | `vitest run DeleteAccountDialog` | ❌ W3 |
| UI-07 | LogoutAllDialog confirm → logout + redirect | RTL | `vitest run LogoutAllDialog` | ❌ W3 |
| UI-07 | UpgradeInterestDialog swallows 501 as success | RTL | `vitest run UpgradeInterestDialog` | ❌ W3 |
| BILL-05 | UI dialog POSTs /billing/checkout (501 OK) | RTL | (covered by UI-07 row above) | ❌ W3 |
| BILL-06 | n/a — server-to-server only | — | — | already complete |
| (extra) | authStore.refresh() hydrates from /me | unit | `vitest run authStore` | ❌ W2 |
| (extra) | RequireAuth waits on isHydrating | unit | `vitest run RequireAuth` | ❌ W2 |

### Sampling Rate

- **Per task commit:** quick run command for the touched layer
- **Per wave merge:** full suite for that side (backend or frontend)
- **Phase gate:** both full suites green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `app/api/schemas/account_schemas.py` — covers SCOPE-06, AUTH-06, UI-07 schemas (NEW file)
- [ ] `frontend/src/lib/api/accountApi.ts` — covers UI-07, AUTH-06, BILL-05 (NEW file)
- [ ] `frontend/src/tests/msw/account.handlers.ts` — covers UI-07, AUTH-06 test mocks (NEW file)
- [ ] `frontend/src/tests/msw/handlers.ts` — extend to spread accountHandlers (MODIFY)
- [ ] `frontend/src/lib/apiClient.ts` — extend `get` + `delete` signatures with body / suppress401Redirect (MODIFY) — **must land before any /me or DELETE caller**
- [ ] `app/api/_cookie_helpers.py` (or re-export from auth_routes) — covers logout-all + delete-account cookie clearing DRY (NEW or refactor)
- [ ] `tests/integration/test_account_routes.py` — extend with 6 new test cases for /me + DELETE (MODIFY existing)
- [ ] `tests/integration/test_auth_routes.py` — extend with 2 new test cases for /logout-all (MODIFY existing)
- [ ] `frontend/src/tests/routes/AccountPage.test.tsx` — covers UI-07 page hydration tests (NEW)
- [ ] `frontend/src/tests/components/DeleteAccountDialog.test.tsx` — covers UI-07 (NEW)
- [ ] `frontend/src/tests/components/LogoutAllDialog.test.tsx` — covers UI-07 (NEW)
- [ ] `frontend/src/tests/components/UpgradeInterestDialog.test.tsx` — covers UI-07 + BILL-05 (NEW)
- [ ] `frontend/src/tests/lib/stores/authStore.test.ts` — extend with refresh() tests (MODIFY or NEW)
- [ ] `frontend/src/tests/routes/RequireAuth.test.tsx` — extend with isHydrating tests (MODIFY or NEW)

*(All test infrastructure (pytest, Vitest, RTL, MSW) already configured per Phase 14. No framework install needed.)*

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| User row preserved on `/data` delete | New `DELETE /api/account` for full row delete | Phase 15 (now) | Two endpoints with clear semantic distinction (data-only vs full account) |
| `authStore.user` null on every reload | `authStore.refresh()` rehydrates from `/me` on boot | Phase 15 (now) | Persistent user across reload as long as cookie session valid |
| `apiClient.get(path, headers?)` second-arg headers | `apiClient.get(path, opts?)` opts = `{headers, suppress401Redirect}` | Phase 15 (now) | Probe-style fetches without redirect side-effects |
| `apiClient.delete(path)` no body | `apiClient.delete(path, body?)` | Phase 15 (now) | DELETE with structured body (matches REST + email_confirm need) |

**Deprecated/outdated:**
- (None — Phase 15 is purely additive on existing infrastructure.)

---

## Project Constraints (from CLAUDE.md)

[VERIFIED: User's global CLAUDE.md present in environment context]

| Directive | Application to Phase 15 |
|-----------|------------------------|
| **DRT (DRY)** — do not repeat yourself | Single `accountApi.ts` HTTP site; single `_clear_auth_cookies` helper extracted; single `AccountService.delete_account` cascade method; single `AccountSummaryResponse` schema reused on both sides |
| **SRP** — Single Responsibility Principle | Routes do HTTP only; AccountService owns business logic; UserRepository owns persistence; AccountPage is dumb orchestrator; dialogs own their own form state |
| **Caveman mode** | Execute mode — concise plans, fragments OK, technical terms exact, code blocks unchanged. Applies during executor phase, not research/planning style. |

(No project-local CLAUDE.md found in `C:/laragon/www/whisperx/CLAUDE.md` — only the global one applies.)

---

## Threat Model (T-15-XX)

| ID | Threat | STRIDE | Mitigation |
|----|--------|--------|------------|
| **T-15-01** | Cascade race — concurrent in-flight request observes orphan rows during multi-step delete | Tampering / Information Disclosure | Service-orchestrated explicit pre-deletes happen BEFORE user-row delete; commit boundary is the user-row delete; middleware lookup of deleted user returns None → 401 on next request |
| **T-15-02** | Missing email_confirm — CSRF replay or compromised cookie deletes account silently | Tampering | (a) DualAuthMiddleware requires CSRF token on state-mutating cookie-auth requests (MID-04); (b) backend service re-validates `email_confirm == user.email` (case-insensitive); (c) UI gates submit button on type-match — defence-in-depth |
| **T-15-03** | Token_version not bumped on delete — zombie session attempts to access deleted user state | Information Disclosure | User row deleted → middleware `get_by_id` returns None → 401. No token_version bump needed; user-row-gone is the invalidation signal. Cookie-clearing on response gives clean client UX. |
| **T-15-04** | Cookie-deletion headers dropped due to mis-returned Response | Information Disclosure | Mirror `/auth/logout` pattern: build new `Response(204)` and call `_clear_auth_cookies(response)` on it before returning. Verifier-checked grep should detect `Depends(Response)` + `return Response(...)` anti-pattern. |
| **T-15-05** | Email enumeration via 400 vs 401 differential on DELETE /api/account | Information Disclosure | (a) email_confirm mismatch → 400 with generic "Confirmation email does not match" copy; (b) auth missing → 401 "Authentication required". 400 only reachable AFTER auth succeeded — no enumeration leak. |
| **T-15-06** | rate_limit_buckets retain old user counters; new user with reused id inherits exhaustion | Tampering | Service explicitly DELETEs `WHERE bucket_key LIKE 'user:<uid>:%'` (string-prefix match) before user-row delete |
| **T-15-07** | 501 stub treated as failure breaks UpgradeInterestDialog success state | Denial of Service (UX) | `submitUpgradeInterest` catches `ApiClientError` with `statusCode === 501` and resolves successfully. Documented in JSDoc; tested via MSW handler. |
| **T-15-08** | apiClient.delete sending no body silently → backend 422; user thinks email match failed | Tampering / DoS | W0 task extends `apiClient.delete(path, body?)` signature; tsc catches missing arg at build; integration test exercises real body. |
| **T-15-09** | Cross-tab logout-all not synchronized — user logs out everywhere on tab A but tab B still authenticated | Information Disclosure | `authStore.logout()` already broadcasts via BroadcastChannel('auth') (UI-12, verified `authStore.ts:107-111`). Caller after logoutAllDevices must invoke `authStore.logout()` to trigger broadcast. UI-SPEC.md §206 locks this sequence. |
| **T-15-10** | Plan_tier null/undefined from `/me` crashes badge map | Availability | Defensive fallback: PLAN_BADGE_VARIANT['unknown'] = 'secondary'; UI-SPEC.md §110 locks the `—` rendering. |
| **T-15-11** | Email leaked in logs during delete-account flow | Information Disclosure | Per AUTH-09 + Phase 13 logging discipline: log `user_id=N` only — never email or token. Verifier grep enforces. |

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | Token-version invariant + AuthService.logout_all_devices (existing) |
| V3 Session Management | yes | Cookie clearing on logout-all + delete; httpOnly + Secure + SameSite=Lax cookies (existing) |
| V4 Access Control | yes | DualAuthMiddleware MID-01..03; CSRF MID-04 |
| V5 Input Validation | yes | Pydantic EmailStr + Field constraints; DeleteAccountRequest body schema |
| V6 Cryptography | n/a | No new crypto in Phase 15 |
| V7 Error Handling | yes | Generic anti-enumeration error strings; 400 vs 401 distinction; logging discipline AUTH-09 |
| V8 Data Protection | yes | DELETE /api/account cascades all PII (tasks, usage_events, device_fingerprints) |
| V13 API & Web Service | yes | RESTful semantics; DELETE with body convention; 204 No Content for empty success |

### Known Threat Patterns for FastAPI + SQLAlchemy + React stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection via bucket_key LIKE | Tampering | Parameterized `:pattern` binding (verified `account_service.py:46-52` style) |
| Mass-assignment via Pydantic body | Tampering | DeleteAccountRequest declares only `email_confirm` field; extras rejected by `model_config` (Pydantic v2 default `extra='ignore'` — confirm or set `extra='forbid'` for strictness) |
| CSRF on cookie-auth DELETE | Tampering | DualAuth + CsrfMiddleware require `X-CSRF-Token` header (MID-04, existing) |
| XSS via email rendered into DOM | Tampering | React auto-escapes; UI-SPEC §314 uses `{user.email}` interpolation (safe) |

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|-------------|-----------|---------|----------|
| Python 3.11+ | Backend | ✓ | (per pyproject.toml) | — |
| FastAPI | Backend | ✓ | (existing) | — |
| Pydantic v2 | Backend schemas | ✓ | (existing) | — |
| SQLAlchemy 2.x | Backend ORM | ✓ | (existing) | — |
| pytest | Backend tests | ✓ | (existing) | — |
| Node 20+ + npm | Frontend build/test | ✓ | (per package.json) | — |
| React 19 + react-router 7 | Frontend | ✓ | (existing) | — |
| shadcn/ui (new-york preset) | Frontend primitives | ✓ | All required primitives present (Card, Badge, Button, Dialog, Input, Label, Alert, Form) per UI-SPEC.md §29 | — |
| Vitest + MSW + RTL | Frontend tests | ✓ | (existing per Phase 14) | — |

**Missing dependencies with no fallback:** none.

**Missing dependencies with fallback:** none.

(All dependencies in place. UI-SPEC.md §28-29 explicitly verifies shadcn primitive inventory. Phase 15 ships zero new packages.)

---

## Runtime State Inventory

(Phase 15 is a feature add — not a rename / refactor / migration. This section is included for completeness; no entries because no live runtime state needs migration.)

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — Phase 15 adds endpoints + UI; no rename of existing data |
| Live service config | None |
| OS-registered state | None |
| Secrets/env vars | None — no new env vars in Phase 15 (Stripe lives in v1.3) |
| Build artifacts | None |

(Verified by inspection of CONTEXT.md scope + REQUIREMENTS.md AUTH-06/SCOPE-06/UI-07 — pure feature addition.)

---

## DRY Surface Assessment

CONTEXT.md §72 mandates "do NOT abstract until 2nd usage demands it." This phase ships three dialogs; assess whether `<DangerActionDialog>` primitive earns its weight:

| Dialog | Header | Body | Form field | Submit handler | Submit label | Cancel label |
|--------|--------|------|-----------|----------------|--------------|--------------|
| LogoutAllDialog | "Sign out of all devices?" | static description | none | `apiClient.post('/auth/logout-all') → authStore.logout()` | "Sign out everywhere" | "Stay signed in" |
| DeleteAccountDialog | "Delete account?" | static description | `<Input type=email>` w/ match-gate | `apiClient.delete('/api/account', body) → authStore.logout()` | "Delete account" | "Keep account" |
| UpgradeInterestDialog | "Upgrade to Pro" | static description | `<Textarea>` (optional) | `apiClient.post('/billing/checkout', {plan, message})` — non-destructive | "Send" | "No thanks" |

**Surface analysis:**
- LogoutAllDialog and DeleteAccountDialog share: destructive variant, dialog-confirm-then-logout-then-navigate pattern, similar error handling.
- UpgradeInterestDialog is non-destructive, has a textarea, swallows 501 as success — fundamentally different.
- DeleteAccountDialog uniquely has a type-match gate; LogoutAllDialog has no form field at all.

**LOCKED RECOMMENDATION:** **DEFER abstraction.** The two destructive dialogs share less than they look — the form field requirement is the dominant divergence. A `<DangerActionDialog>` would carry props for "render form field?" / "render match-gate?" / "submit handler factory" — at which point it's just two functions in a trench coat. Three explicit dialogs (~80 lines each) is clearer than one 150-line abstraction with 6 props.

If a 4th destructive dialog appears in v1.3 (e.g., revoke-all-keys), revisit. For now: separate.

(Plan-checker should validate: no shared `<DangerActionDialog>` component file; each of the 3 dialog files implements its own state machine; no premature `useDangerAction` hook.)

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| (none) | All claims in this research were verified by direct codebase reading or cited from CONTEXT.md / UI-SPEC.md / REQUIREMENTS.md / migration files / source files. No `[ASSUMED]` tags used. |

**This table is empty:** All technical claims were verified or cited. The two implementation choices flagged as "locked recommendation" (Strategy C cascade orchestration; defer DangerActionDialog) are recommendations, not assumptions about facts — they're decisions the planner can adopt or override.

One claim correction worth surfacing for plan-discuss-phase: **CONTEXT.md §64 states "authStore.refresh() exists already (Plan 14-03); extend it"** — this is incorrect per direct codebase inspection (`authStore.ts` has no `refresh` method as of HEAD). Plan must **add** `refresh()`, not extend it. Already noted in §"Frontend authStore.refresh Wiring" section above.

---

## Open Questions (RESOLVED)

1. **Should `_clear_auth_cookies` move to a shared module before being imported by `account_routes.py`?**
   - What we know: It's currently a private function in `auth_routes.py:101`. DRY says one source.
   - What's unclear: whether the planner prefers a new `app/api/_cookie_helpers.py` file vs. promoting the helper to public in `auth_routes` and importing.
   - Recommendation: **Extract to `app/api/_cookie_helpers.py`** for SRP — cookie clearing is a shared HTTP concern, not auth-domain. Trivial 10-line file.
   - RESOLVED: Implemented in Plan 15-01 Task 2 (creates `app/api/_cookie_helpers.py` with public `clear_auth_cookies`; `auth_routes.py /logout` migrated to import the shared helper).

2. **Should AccountService accept a UserRepository in its constructor (DI), or instantiate inline from `self.session`?**
   - What we know: Existing `AccountService.__init__` takes only `session`. New methods need user-row reads.
   - What's unclear: whether plan-checker will flag injection as a constructor change risk to existing `delete_user_data` callers.
   - Recommendation: **Constructor-inject** with default `None` and lazy-construct from session if absent — preserves SCOPE-05 backwards compat, gives test isolation.
   - RESOLVED: Implemented in Plan 15-03 Task 1 (`AccountService.__init__(session, user_repository: IUserRepository | None = None)` with lazy `SQLAlchemyUserRepository(session)` fallback). Plan 15-04 reuses the same `_user_repository` member for `delete_account`.

3. **Should the plan ship a 4th Alembic migration to flip `tasks.user_id` to ON DELETE CASCADE and add a `user_id` FK column to `rate_limit_buckets`?**
   - What we know: Service-orchestrated approach works today.
   - What's unclear: whether migration cleanliness justifies the extra Phase 15 surface area.
   - Recommendation: **DEFER to v1.3.** Service approach is reversible, testable, and contained.
   - RESOLVED: Deferred. Plan 15-04 ships the service-orchestrated cascade (Strategy C — `delete_user_data` → rate_limit_buckets prefix-match → `user_repository.delete` ORM CASCADE) with no schema migration in this phase.

4. **Backend match strategy: case-insensitive vs exact?**
   - What we know: UI-SPEC.md §190 explicitly says case-insensitive.
   - What's unclear: nothing — locked.
   - Recommendation: **case-insensitive** on both UI and backend. Lowercase before compare on both sides.
   - RESOLVED: Backend case-insensitive match in Plan 15-04 (`AccountService.delete_account` lowercases both sides before equality); UI gate in Plan 15-06 (`DeleteAccountDialog.isMatched` lowercases both sides). Verified by `test_delete_account_email_case_insensitive`.

---

## Sources

### Primary (HIGH confidence)

- **Codebase (verified line-by-line):**
  - `app/api/account_routes.py` (existing `/data` route)
  - `app/api/auth_routes.py` (logout cookie pattern)
  - `app/api/billing_routes.py` (existing 501 stubs — BILL-05/06 verified complete)
  - `app/api/dependencies.py` (DI helpers: get_authenticated_user, get_db_session, get_account_service)
  - `app/api/schemas/auth_schemas.py`, `billing_schemas.py`, `key_schemas.py` (Pydantic patterns)
  - `app/services/account_service.py:1-80` (delete_user_data pattern)
  - `app/services/auth/auth_service.py:91-97` (logout_all_devices already implemented)
  - `app/services/auth/token_service.py:34-49` (verify_and_refresh ver-check)
  - `app/core/jwt_codec.py:24-45` (`ver` claim in encoded session token)
  - `app/core/dual_auth.py:1-80` (middleware resolution order + public allowlist)
  - `app/domain/entities/user.py:43-46` (bump_token_version)
  - `app/domain/repositories/user_repository.py:80-89` (delete interface)
  - `app/infrastructure/database/repositories/sqlalchemy_user_repository.py:122-137` (delete impl)
  - `app/infrastructure/database/models.py` (FK ondelete declarations — verified for every dependent table)
  - `app/infrastructure/database/connection.py:32-67` (PRAGMA foreign_keys=ON enforcement + boot assertion)
  - `app/services/free_tier_gate.py:80,175,214` (rate_limit_buckets bucket_key naming convention)
  - `alembic/versions/0002_auth_schema.py` (FK ondelete = SET NULL for tasks; CASCADE for rest)
  - `alembic/versions/0003_tasks_user_id_not_null.py` (NOT NULL constraint added)
  - `frontend/src/lib/apiClient.ts:1-169` (full HTTP client implementation — confirmed gap on suppress401Redirect for GET + body for DELETE)
  - `frontend/src/lib/stores/authStore.ts:1-113` (confirmed NO refresh() method exists)
  - `frontend/src/routes/AccountStubPage.tsx`, `KeysDashboardPage.tsx`, `RequireAuth.tsx`, `AppRouter.tsx`
  - `frontend/src/components/dashboard/CreateKeyDialog.tsx`, `RevokeKeyDialog.tsx`
  - `frontend/src/lib/api/keysApi.ts` (pattern for accountApi.ts)
  - `frontend/src/tests/msw/keys.handlers.ts`, `auth.handlers.ts`, `handlers.ts` (MSW patterns)
  - `tests/integration/test_account_routes.py` (existing 6 test cases — pattern to extend)
  - `tests/integration/test_billing_routes.py` (501 stub coverage)

- **Planning docs (HIGH confidence — locked):**
  - `.planning/phases/15-account-dashboard-hardening-billing-stubs/15-CONTEXT.md` (locked decisions, code quality non-negotiables)
  - `.planning/phases/15-account-dashboard-hardening-billing-stubs/15-UI-SPEC.md` (UI design contract; copy locked verbatim; state machines locked)
  - `.planning/REQUIREMENTS.md` (AUTH-06, SCOPE-06, UI-07, BILL-05/06 — phase mapping table)
  - `.planning/STATE.md` (decisions log: lines 226, 228, 243 — confirms refresh() / hydration deferred and AuthUser.email plan)
  - `.planning/phases/14-atomic-frontend-cutover/14-02-PLAN.md` (apiClient suppress401Redirect implementation context)
  - `.planning/phases/14-atomic-frontend-cutover/14-03-SUMMARY.md` (refresh() trade-offs and Phase 15 hand-off)
  - `.planning/codebase/STRUCTURE.md`, `.planning/codebase/CONVENTIONS.md` (project conventions)

### Secondary (MEDIUM confidence)

- **Web/MCP not used** — every claim in this research was verifiable from the local codebase + planning docs. Context7 / WebSearch / Brave / Exa / Firecrawl not consulted because they would only re-state public docs for libraries already in use (FastAPI, SQLAlchemy, Pydantic, React, shadcn). Existing project patterns are the more authoritative source for "how this codebase handles X."

### Tertiary (LOW confidence)

- (none)

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all packages already in lockfiles; no version assumptions.
- Architecture: HIGH — every new route, service method, schema, and frontend component has a verified existing analogue in the codebase.
- FK cascade coverage: HIGH — directly verified from `models.py` + `0002_auth_schema.py`; SET NULL on tasks is a code-confirmed fact, not a guess.
- token_version invariant: HIGH — full chain from `User.bump_token_version` → `update_token_version` → `verify_and_refresh` → JWT `ver` claim verified line-by-line.
- apiClient gap (suppress401Redirect on GET, body on DELETE): HIGH — directly verified absent in `apiClient.ts:155-166`.
- Pitfalls: HIGH — every pitfall sourced from existing test/route patterns or schema declarations.
- DRY/abstraction call (defer DangerActionDialog): MEDIUM — recommendation, planner can override.
- Test patterns: HIGH — fixtures, MSW handler shapes, and test organization all verified from Phase 13 + Phase 14 test files.

**Research date:** 2026-04-29
**Valid until:** 2026-05-29 (codebase moves fast; re-validate before plan-execute if stale)

**Phase 15 readiness:** Plan can proceed immediately. The single must-do W0 task is `apiClient.get` + `apiClient.delete` signature extension; everything else flows from there.
