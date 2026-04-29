---
phase: 15
plan: 06
type: execute
wave: 4
depends_on: ["15-01", "15-02", "15-03", "15-04", "15-05"]
files_modified:
  - frontend/src/routes/AccountPage.tsx
  - frontend/src/components/dashboard/UpgradeInterestDialog.tsx
  - frontend/src/components/dashboard/DeleteAccountDialog.tsx
  - frontend/src/components/dashboard/LogoutAllDialog.tsx
  - frontend/src/routes/AppRouter.tsx
  - frontend/src/routes/AccountStubPage.tsx
  - frontend/src/tests/routes/AccountPage.test.tsx
  - frontend/src/tests/components/UpgradeInterestDialog.test.tsx
  - frontend/src/tests/components/DeleteAccountDialog.test.tsx
  - frontend/src/tests/components/LogoutAllDialog.test.tsx
autonomous: false
requirements: [UI-07, AUTH-06, SCOPE-06, BILL-05]
user_setup: []
must_haves:
  truths:
    - "AccountPage renders user email + plan_tier badge after server hydration"
    - "Upgrade-to-Pro CTA opens UpgradeInterestDialog; submission swallows 501 as success and auto-closes"
    - "Delete-account dialog enables submit only when typed email matches user.email (case-insensitive)"
    - "Delete-account success calls authStore.logout() then navigates /login"
    - "Logout-all-devices dialog confirms then calls /auth/logout-all + authStore.logout() + navigate /login"
    - "AppRouter mounts AccountPage (lazy) at /dashboard/account, replacing AccountStubPage"
    - "Mobile-responsive layout verified at sm/md/lg breakpoints (human verify)"
  artifacts:
    - path: "frontend/src/routes/AccountPage.tsx"
      provides: "Profile/Plan/Danger Zone three-card page"
      contains: "PLAN_BADGE_VARIANT"
      min_lines: 100
    - path: "frontend/src/components/dashboard/UpgradeInterestDialog.tsx"
      provides: "501-swallow upgrade interest dialog"
      contains: "submitUpgradeInterest"
      min_lines: 80
    - path: "frontend/src/components/dashboard/DeleteAccountDialog.tsx"
      provides: "Type-email confirmation dialog"
      contains: "isMatched"
      min_lines: 80
    - path: "frontend/src/components/dashboard/LogoutAllDialog.tsx"
      provides: "Single-confirm logout-all dialog"
      contains: "logoutAllDevices"
      min_lines: 60
    - path: "frontend/src/routes/AppRouter.tsx"
      provides: "Updated /dashboard/account route mounting AccountPage"
      contains: "AccountPage"
  key_links:
    - from: "frontend/src/routes/AccountPage.tsx"
      to: "frontend/src/lib/api/accountApi.ts:fetchAccountSummary"
      via: "useEffect-driven page-local fetch"
      pattern: "fetchAccountSummary"
    - from: "frontend/src/components/dashboard/DeleteAccountDialog.tsx"
      to: "frontend/src/lib/api/accountApi.ts:deleteAccount"
      via: "submit handler"
      pattern: "deleteAccount\\("
    - from: "frontend/src/components/dashboard/LogoutAllDialog.tsx"
      to: "frontend/src/lib/api/accountApi.ts:logoutAllDevices"
      via: "confirm handler"
      pattern: "logoutAllDevices\\("
    - from: "frontend/src/components/dashboard/UpgradeInterestDialog.tsx"
      to: "frontend/src/lib/api/accountApi.ts:submitUpgradeInterest"
      via: "submit handler with 501-as-success branch"
      pattern: "submitUpgradeInterest\\("
    - from: "frontend/src/routes/AppRouter.tsx"
      to: "frontend/src/routes/AccountPage.tsx"
      via: "lazy-loaded route element"
      pattern: "AccountPage"
---

<objective>
Build the AccountPage UI surface: three-card page (Profile / Plan / Danger Zone), three dialogs (UpgradeInterestDialog, DeleteAccountDialog, LogoutAllDialog), AppRouter swap from AccountStubPage to AccountPage, and 4 RTL test files. Polish via `/frontend-design` skill at sm/md/lg breakpoints. Closes UI-07 + adds the UI-side wiring of AUTH-06, SCOPE-06, BILL-05 from the previous plans.

Purpose: User-facing surface for the account-management features. UI-SPEC.md contract is the locked design; this plan executes it.
Output: 4 new components + 1 router update + 1 stub deletion + 4 test files + a human-verify mobile-responsive checkpoint.

Note on scope: 10 files-modified is at the planner threshold; UI work is cohesive (single user-facing surface) and tasks are file-disjoint (Task 1 owns components + router + stub; Task 2 owns the 4 test files; Task 3 is human-verify only). No shared-mutable-file conflicts within the plan.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/15-account-dashboard-hardening-billing-stubs/15-CONTEXT.md
@.planning/phases/15-account-dashboard-hardening-billing-stubs/15-RESEARCH.md
@.planning/phases/15-account-dashboard-hardening-billing-stubs/15-UI-SPEC.md
@.planning/phases/15-account-dashboard-hardening-billing-stubs/15-PATTERNS.md
@.planning/phases/15-account-dashboard-hardening-billing-stubs/15-01-groundwork-PLAN.md
@.planning/phases/15-account-dashboard-hardening-billing-stubs/15-05-auth-hydration-PLAN.md
@frontend/src/routes/KeysDashboardPage.tsx
@frontend/src/routes/AccountStubPage.tsx
@frontend/src/routes/AppRouter.tsx
@frontend/src/components/dashboard/CreateKeyDialog.tsx
@frontend/src/components/dashboard/RevokeKeyDialog.tsx
@frontend/src/components/ui/card.tsx
@frontend/src/components/ui/dialog.tsx
@frontend/src/components/ui/badge.tsx
@frontend/src/lib/api/accountApi.ts
@frontend/src/lib/stores/authStore.ts
@frontend/src/lib/apiClient.ts

<interfaces>
<!-- Pulled from codebase. Use directly. -->

From frontend/src/lib/api/accountApi.ts (Plan 15-01):
```typescript
export interface AccountSummaryResponse {
  user_id: number;
  email: string;
  plan_tier: 'free' | 'trial' | 'pro' | 'team';
  trial_started_at: string | null;
  token_version: number;
}
export function fetchAccountSummary(): Promise<AccountSummaryResponse>;
export function logoutAllDevices(): Promise<void>;
export function deleteAccount(emailConfirm: string): Promise<void>;
export function submitUpgradeInterest(message: string): Promise<void>;
```

From frontend/src/lib/stores/authStore.ts (post-Plan 15-05):
```typescript
export interface AuthUser { id; email; planTier; trialStartedAt; tokenVersion; }
useAuthStore((s) => s.user) -> AuthUser | null
useAuthStore((s) => s.logout) -> () => Promise<void>   // clears + broadcasts
```

From frontend/src/lib/apiClient.ts:
```typescript
export class ApiClientError extends Error { statusCode: number; ... }
export class RateLimitError extends ApiClientError { retryAfterSeconds: number; }
export class AuthRequiredError extends ApiClientError { ... }
```

From frontend/src/routes/AppRouter.tsx (current — line 7 imports AccountStubPage; line ~52 mounts it):
```typescript
import { AccountStubPage } from './AccountStubPage';   // DELETE
// ...
const KeysDashboardPage = lazy(() =>
  import('./KeysDashboardPage').then((m) => ({ default: m.KeysDashboardPage })),
);   // pattern to mirror for AccountPage
// ...
<Route path="/dashboard/account" element={<PageWrap><AccountStubPage /></PageWrap>} />
// REPLACE with: <PageWrap><AccountPage /></PageWrap> using lazy import
```

From frontend/src/routes/KeysDashboardPage.tsx — full pattern for fetch+error+dialog state machine + layout `flex flex-col gap-6 max-w-2xl mx-auto`.
From frontend/src/components/dashboard/CreateKeyDialog.tsx — form-state pattern with submit + error + 429 subtype-first catch.
From frontend/src/components/dashboard/RevokeKeyDialog.tsx — single-confirm destructive pattern.

From frontend/src/components/ui/dialog.tsx (existing shadcn):
- Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter
- DialogContent default `sm:max-w-lg`; footer `flex flex-col-reverse sm:flex-row sm:justify-end gap-2`
</interfaces>

<copywriting>
All copy locked verbatim from UI-SPEC.md §270-333. Executor MUST use these strings exactly. US English.

**AccountPage:**
- Heading: `Account`
- Profile heading: `Profile`
- Profile email label: `Email`
- Profile plan label: `Plan`
- Password reset hint: `For password reset, email hey@logingrupa.lv.` (mailto link)
- Plan heading: `Plan`
- Plan body — `free`: `You're on the Free plan. 5 transcribes per hour, files up to 5 minutes, 30 min/day, tiny + small models only.`
- Plan body — `trial`: `You're on the 7-day Free trial. Upgrade to Pro to keep diarization, large-v3, and 100 req/hr after it ends.`
- Plan body — `pro`: `You're on Pro. 100 req/hr, files up to 60 min, 600 min/day, all models, diarization enabled. Thanks for the support.`
- Plan body — `team`: `You're on Team. All Pro features, plus shared workspace primitives shipping post-v1.2.`
- Plan body — fallback: `Plan details unavailable.`
- Upgrade CTA: `Upgrade to Pro` (only when planTier !== 'pro' && !== 'team')
- Danger Zone heading: `Danger zone`
- Sign-out-all helper: `End every active session, including this one. Useful if you suspect a leaked cookie or want to log out a forgotten device.`
- Sign-out-all button: `Sign out of all devices`
- Delete-account helper: `Permanently delete your account and every task, API key, subscription, and usage record. This cannot be undone.`
- Delete-account button: `Delete account`
- Hydration error: `Could not load account.`
- Reload button: `Reload account`
- Rate-limit error: `Rate limited. Try again in {n}s.`

**UpgradeInterestDialog:**
- Title: `Upgrade to Pro`
- Description: `Tell us what you need from Pro. Real Stripe checkout ships in v1.3.`
- Textarea label: `What do you want from Pro? — optional`
- Textarea placeholder: `Diarization on long files, faster turnaround, larger uploads…`
- Submit idle: `Send`
- Submit submitting: `Sending…`
- Cancel: `No thanks`
- Success heading: `Thanks!`
- Success body: `Stripe checkout arrives in v1.3. We'll email you when it goes live.`
- Error 429: `Too many requests. Try again in {n}s.`
- Error other: `Could not send. Try again.`

**DeleteAccountDialog:**
- Title: `Delete account?`
- Description: `This permanently deletes your account, API keys, tasks, and usage history. This cannot be undone.`
- Email input label: `Type your email to confirm: {user.email}`
- Email input placeholder: `you@example.com`
- Confirm idle: `Delete account`
- Confirm submitting: `Deleting…`
- Cancel: `Keep account`
- Error 400: `Confirmation email does not match.`
- Error 429: `Too many requests. Try again in {n}s.`
- Error other: `Could not delete account. Try again.`

**LogoutAllDialog:**
- Title: `Sign out of all devices?`
- Description: `Every active session — including this one — will be ended. You'll need to sign in again on every device.`
- Confirm idle: `Sign out everywhere`
- Confirm submitting: `Signing out…`
- Cancel: `Stay signed in`
- Error 429: `Rate limited. Try again in {n}s.`
- Error other: `Could not sign out. Try again.`
</copywriting>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: AccountPage + 3 dialogs + AppRouter swap (per /frontend-design polish; UI-SPEC verbatim copy)</name>
  <files>frontend/src/routes/AccountPage.tsx, frontend/src/components/dashboard/UpgradeInterestDialog.tsx, frontend/src/components/dashboard/DeleteAccountDialog.tsx, frontend/src/components/dashboard/LogoutAllDialog.tsx, frontend/src/routes/AppRouter.tsx, frontend/src/routes/AccountStubPage.tsx</files>
  <read_first>
    - .planning/phases/15-account-dashboard-hardening-billing-stubs/15-UI-SPEC.md (full — design contract: spacing, typography, color, layout, dialogs, state machines, copy)
    - .planning/phases/15-account-dashboard-hardening-billing-stubs/15-PATTERNS.md §"frontend/src/routes/AccountPage.tsx" + §"UpgradeInterestDialog" + §"DeleteAccountDialog" + §"LogoutAllDialog" + §"frontend/src/routes/AppRouter.tsx (MODIFY)"
    - frontend/src/routes/KeysDashboardPage.tsx (full — layout + fetch+dialog state machine pattern)
    - frontend/src/components/dashboard/CreateKeyDialog.tsx (full — form + submit + 429 + state pattern)
    - frontend/src/components/dashboard/RevokeKeyDialog.tsx (full — single-confirm destructive pattern)
    - frontend/src/routes/AccountStubPage.tsx (current placeholder — to delete)
    - frontend/src/routes/AppRouter.tsx (current — confirm lazy + PageWrap pattern)
    - frontend/src/components/ui/dialog.tsx (sizing + footer-stack defaults)
    - frontend/src/components/ui/card.tsx (default p-6 padding + className overrides)
  </read_first>
  <behavior>
    - AccountPage at `/dashboard/account` renders heading + 3 cards (Profile / Plan / Danger Zone) after fetchAccountSummary resolves; pretty layout matches /frontend-design polish bar.
    - Upgrade button only renders when summary.plan_tier !== 'pro' && !== 'team'.
    - Plan card body switches based on plan_tier; fallback `Plan details unavailable.` on unknown values.
    - Profile card shows email + plan badge with PLAN_BADGE_VARIANT mapping (free=secondary, trial=outline, pro=default, team=default).
    - All three dialogs open from buttons in their respective cards.
    - Mobile responsive: cards stack with gap-4 on `<md`; Danger-zone rows stack helper-text-above-button on `<md`; dialogs use shadcn defaults (max-w-[calc(100%-2rem)] on `<sm`, sm:max-w-lg above).
    - On dialog success:
      - UpgradeInterestDialog: success state then auto-close after 2s (setTimeout); 501 caught + surfaced as success (T-15-07).
      - DeleteAccountDialog: authStore.logout() → navigate('/login', {replace:true}).
      - LogoutAllDialog: authStore.logout() → navigate('/login', {replace:true}).
    - All catch blocks subtype-first: RateLimitError BEFORE ApiClientError; DeleteAccountDialog branches statusCode === 400 to "Confirmation email does not match." copy; UpgradeInterestDialog branches statusCode === 501 to success.
  </behavior>
  <action>
    Per UI-SPEC.md (Dimensions 1-6 locked) + PATTERNS.md analogs (KeysDashboardPage / CreateKeyDialog / RevokeKeyDialog) + locked decisions in CONTEXT.md.

    **/frontend-design skill mandatory** — invoke during execution to polish AccountPage + 3 dialogs at sm/md/lg breakpoints. Run mental review of UI-SPEC §116-160 layout, §163-237 dialog state machines, §266-333 copy verbatim before writing.

    Tiger-style + DRY + SRP + no-nested-if + self-explanatory naming locked from CONTEXT D-Code Quality.

    **1a. Create `frontend/src/routes/AccountPage.tsx`:**

    Implement per RESEARCH §947-1004 + UI-SPEC §116-160. Key constants:
    ```typescript
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
    ```

    State machine: `summary` (AccountSummaryResponse | null), `error` (string | null), three booleans for dialog open state (`upgradeOpen`, `deleteOpen`, `logoutAllOpen`). useEffect on mount calls `refresh()` (page-local fetcher); `refresh()` catch chain is RateLimitError → ApiClientError → generic, all setting `error` (not throwing).

    Layout (UI-SPEC §116-160):
    ```tsx
    <div className="flex flex-col gap-4 md:gap-6 max-w-2xl mx-auto">
      <h1 className="text-2xl font-semibold">Account</h1>
      {/* Profile card */}
      <Card className="p-6">
        <h2 className="text-lg font-semibold">Profile</h2>
        {/* email + plan badge + mailto hint */}
      </Card>
      {/* Plan card */}
      <Card className="p-6">
        <h2 className="text-lg font-semibold">Plan</h2>
        {/* tier-specific body + Upgrade CTA when not pro/team */}
      </Card>
      {/* Danger Zone */}
      <Card className="p-6 border-destructive/40">
        <h2 className="text-lg font-semibold text-destructive">Danger zone</h2>
        {/* Sign-out-all row + Delete-account row, each: helper text + button. Stack on <md, row on >=md */}
      </Card>
      <UpgradeInterestDialog open={upgradeOpen} onOpenChange={setUpgradeOpen} />
      <DeleteAccountDialog open={deleteOpen} onOpenChange={setDeleteOpen} userEmail={summary?.email ?? ''} />
      <LogoutAllDialog open={logoutAllOpen} onOpenChange={setLogoutAllOpen} />
    </div>
    ```

    Loading state: 3 skeleton Cards (Profile/Plan/Danger Zone) each containing 1 placeholder heading + 2 muted lines via `<div class="h-4 w-32 rounded bg-muted">` (UI-SPEC §253). Error state: single Card with destructive Alert + "Reload account" button.

    Hide Upgrade button when `summary.plan_tier === 'pro'` or `'team'` (UI-SPEC §282).

    DangerZone row mobile-stack: `flex flex-col gap-4 md:flex-row md:items-center md:justify-between md:gap-4` per UI-SPEC §148.

    No nested-if rule applies: use early-return loading guard; PLAN_COPY[tier] ?? 'Plan details unavailable.' for fallback (no `if (tier === 'free') ... else if ...` chains).

    **1b. Create `frontend/src/components/dashboard/UpgradeInterestDialog.tsx`:**

    Per UI-SPEC §161-176 + RESEARCH §"UpgradeInterestDialog" + PATTERNS §"UpgradeInterestDialog" — mirror CreateKeyDialog two-state pattern (idle ↔ success). NO shadcn Textarea primitive in inventory; use a styled native `<textarea>` per UI-SPEC §169 (textarea note).

    Props: `{ open: boolean; onOpenChange: (open: boolean) => void }`.

    State: `[message, setMessage]`, `[submitting, setSubmitting]`, `[error, setError]`, `[success, setSuccess]`.

    Submit: setSubmitting(true) → submitUpgradeInterest(message) → catch chain:
    1. `if (err instanceof RateLimitError)` → setError(`Too many requests. Try again in ${err.retryAfterSeconds}s.`)
    2. `else if (err instanceof ApiClientError && err.statusCode === 501)` → setSuccess(true) (T-15-07 swallow 501 as success)
    3. `else if (err instanceof ApiClientError)` → setError('Could not send. Try again.')
    4. `else` → setError('Could not send. Try again.')
    finally setSubmitting(false).

    Auto-close on success: useEffect on `success` flag → setTimeout(handleClose, 2000); cleanup on unmount.

    Naming: `submitUpgradeInterest`, `submitting`, `success`, `error` — explicit.

    **1c. Create `frontend/src/components/dashboard/DeleteAccountDialog.tsx`:**

    Per UI-SPEC §178-193 + §214-227 (state machine) + RESEARCH §"DeleteAccountDialog" + PATTERNS §"DeleteAccountDialog".

    Props: `{ open; onOpenChange; userEmail: string }`.

    State: `[confirmEmail, setConfirmEmail]`, `[submitting, setSubmitting]`, `[error, setError]`.

    Match gate: `const isMatched = confirmEmail.trim().toLowerCase() === userEmail.toLowerCase();`. Submit button: `disabled={!isMatched || submitting}`.

    Submit:
    ```typescript
    if (!isMatched) return;   // defence; button is disabled
    setSubmitting(true);
    setError(null);
    try {
      await deleteAccount(confirmEmail);
      await logout();   // authStore.logout()
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
    ```

    Use `useAuthStore((s) => s.logout)` for `logout`; `useNavigate()` from react-router-dom for `navigate`.

    Input field: `<Input type="email" id="confirm-email" autoFocus autoComplete="off" spellCheck={false} placeholder="you@example.com">`. Label `Type your email to confirm: {userEmail}`.

    No nested-if: ternary inside ApiClientError branch is fine (it's a single expression, not nested `if`).

    **1d. Create `frontend/src/components/dashboard/LogoutAllDialog.tsx`:**

    Per UI-SPEC §194-208 + §229-237 (state machine) + RESEARCH §"LogoutAllDialog" + PATTERNS §"LogoutAllDialog" — mirror RevokeKeyDialog single-confirm destructive pattern.

    Props: `{ open; onOpenChange }`.

    State: `[submitting, setSubmitting]`, `[error, setError]`.

    Confirm:
    ```typescript
    setSubmitting(true);
    setError(null);
    try {
      await logoutAllDevices();
      await logout();
      navigate('/login', { replace: true });
    } catch (err) {
      if (err instanceof RateLimitError) {
        setError(`Rate limited. Try again in ${err.retryAfterSeconds}s.`);
      } else if (err instanceof ApiClientError) {
        setError('Could not sign out. Try again.');
      } else {
        setError('Could not sign out. Try again.');
      }
    } finally {
      setSubmitting(false);
    }
    ```

    No form field; single destructive button + ghost cancel.

    **1e. Modify `frontend/src/routes/AppRouter.tsx`:**
    1. Delete `import { AccountStubPage } from './AccountStubPage';` (line 7)
    2. Add lazy import:
       ```typescript
       const AccountPage = lazy(() =>
         import('./AccountPage').then((m) => ({ default: m.AccountPage })),
       );
       ```
    3. Replace the line `<Route path="/dashboard/account" element={<PageWrap><AccountStubPage /></PageWrap>} />` with the AccountPage variant.

    **1f. Delete `frontend/src/routes/AccountStubPage.tsx`** (rm — no callers remain).

    Verifier-grep for nested-if MUST return 0 across all 4 new files.

    Naming locked: `confirmEmail` (not `email2`), `isMatched` (not `ok`), `summary` (not `s`), `submitting` (not `loading` to disambiguate from React Suspense), `success` (not `done`).
  </action>
  <verify>
    <automated>cd frontend &amp;&amp; bunx tsc --noEmit &amp;&amp; bun run vitest run src/tests/routes/AppRouter.test.tsx</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "export function AccountPage" frontend/src/routes/AccountPage.tsx` returns 1
    - `grep -c "PLAN_BADGE_VARIANT" frontend/src/routes/AccountPage.tsx` >= 1
    - `grep -c "PLAN_COPY" frontend/src/routes/AccountPage.tsx` >= 1
    - `grep -c "max-w-2xl" frontend/src/routes/AccountPage.tsx` >= 1
    - `grep -c "border-destructive" frontend/src/routes/AccountPage.tsx` >= 1
    - `grep -c "submitUpgradeInterest" frontend/src/components/dashboard/UpgradeInterestDialog.tsx` returns 1
    - `grep -c "statusCode === 501" frontend/src/components/dashboard/UpgradeInterestDialog.tsx` returns 1 (T-15-07)
    - `grep -c "setTimeout" frontend/src/components/dashboard/UpgradeInterestDialog.tsx` >= 1 (auto-close)
    - `grep -c "isMatched" frontend/src/components/dashboard/DeleteAccountDialog.tsx` >= 2
    - `grep -c "deleteAccount" frontend/src/components/dashboard/DeleteAccountDialog.tsx` >= 1
    - `grep -c "logoutAllDevices" frontend/src/components/dashboard/LogoutAllDialog.tsx` >= 1
    - `grep -c "AccountStubPage" frontend/src/routes/AppRouter.tsx` returns 0 (stub deleted)
    - `grep -c "AccountPage" frontend/src/routes/AppRouter.tsx` >= 2 (import + element)
    - File `frontend/src/routes/AccountStubPage.tsx` does NOT exist
    - `grep -cE "^\s+if .*\bif\b" frontend/src/routes/AccountPage.tsx frontend/src/components/dashboard/UpgradeInterestDialog.tsx frontend/src/components/dashboard/DeleteAccountDialog.tsx frontend/src/components/dashboard/LogoutAllDialog.tsx` returns 0 (nested-if invariant)
    - `cd frontend && bunx tsc --noEmit` exits 0
    - `cd frontend && bun run vitest run src/tests/routes/AppRouter.test.tsx` passes (no router regression)
  </acceptance_criteria>
  <done>AccountPage + 3 dialogs implemented per UI-SPEC; AppRouter swaps stub → AccountPage; tsc green; AppRouter smoke test passes.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: 4 RTL test files — AccountPage + UpgradeInterestDialog + DeleteAccountDialog + LogoutAllDialog (covers UI-07 + AUTH-06 + SCOPE-06 + BILL-05 client paths)</name>
  <files>frontend/src/tests/routes/AccountPage.test.tsx, frontend/src/tests/components/UpgradeInterestDialog.test.tsx, frontend/src/tests/components/DeleteAccountDialog.test.tsx, frontend/src/tests/components/LogoutAllDialog.test.tsx</files>
  <read_first>
    - frontend/src/tests/routes/KeysDashboardPage.test.tsx (full — pattern for render-helper + auth-store seed + MSW override + 429 inline countdown)
    - frontend/src/tests/components (verify analog tests if any; otherwise pattern from KeysDashboardPage.test.tsx)
    - frontend/src/tests/msw/account.handlers.ts (Plan 15-01 — default 200/204/204/501 handlers)
    - frontend/src/tests/setup.ts (server import + cleanup)
    - .planning/phases/15-account-dashboard-hardening-billing-stubs/15-PATTERNS.md §"frontend/src/tests/routes/AccountPage.test.tsx" + §"frontend/src/tests/components/{Delete,LogoutAll,UpgradeInterest}Dialog.test.tsx"
    - .planning/phases/15-account-dashboard-hardening-billing-stubs/15-RESEARCH.md §"Test Patterns/Page + dialog tests" + §"Async pattern (TEST-05)"
  </read_first>
  <behavior>
    Test cases (≥18 total per UI-SPEC §43-58 sampling map):

    AccountPage.test.tsx (≥4 cases):
    - Renders email + plan badge after hydration (default MSW handler — trial)
    - Renders error card on /me 500 (server.use override)
    - "Reload account" retry button re-fetches
    - Hides Upgrade button when plan_tier='pro'

    UpgradeInterestDialog.test.tsx (≥3 cases):
    - Submits → swallows 501 → shows "Thanks!" copy
    - Auto-closes 2s after success (`vi.useFakeTimers` + `vi.advanceTimersByTime(2000)`)
    - 429 shows retry-after countdown copy

    DeleteAccountDialog.test.tsx (≥4 cases):
    - Submit disabled when input empty
    - Submit enables on case-insensitive match (type 'ALICE@example.com' for stored 'alice@example.com')
    - Submit calls authStore.logout + navigates /login (mock logout + navigate)
    - 400 from server shows "Confirmation email does not match." copy

    LogoutAllDialog.test.tsx (≥3 cases):
    - Confirm calls authStore.logout + navigates /login
    - 429 shows rate-limit copy
    - Other error shows "Could not sign out. Try again."
  </behavior>
  <action>
    Per RESEARCH §1095-1117 + PATTERNS §"frontend/src/tests/routes/AccountPage.test.tsx".

    **TEST-05 invariants:** all async UI tests use `await user.click(...)` + `await screen.findByRole(...)`. Do not use `screen.getByRole` after a state change.

    **2a. AccountPage.test.tsx skeleton:**
    ```typescript
    import { describe, it, expect, beforeEach } from 'vitest';
    import { render, screen } from '@testing-library/react';
    import userEvent from '@testing-library/user-event';
    import { http, HttpResponse } from 'msw';
    import { MemoryRouter } from 'react-router-dom';

    import { AccountPage } from '@/routes/AccountPage';
    import { useAuthStore } from '@/lib/stores/authStore';
    import { server } from '@/tests/setup';

    function renderPage() {
      return render(
        <MemoryRouter>
          <AccountPage />
        </MemoryRouter>,
      );
    }

    describe('AccountPage', () => {
      beforeEach(() => {
        useAuthStore.setState({
          user: {
            id: 1,
            email: 'alice@example.com',
            planTier: 'trial',
            trialStartedAt: '2026-04-22T12:00:00Z',
            tokenVersion: 0,
          },
          isHydrating: false,
        });
      });

      it('renders email + plan_tier badge after hydration', async () => {
        renderPage();
        expect(await screen.findByText('alice@example.com')).toBeInTheDocument();
        expect(screen.getAllByText(/trial/i).length).toBeGreaterThan(0);
      });

      it('renders error card on /me 500', async () => {
        server.use(
          http.get('/api/account/me', () =>
            HttpResponse.json({ detail: 'oops' }, { status: 500 }),
          ),
        );
        renderPage();
        expect(await screen.findByText(/Could not load account/i)).toBeInTheDocument();
      });

      it('"Reload account" button retries fetch', async () => {
        server.use(
          http.get('/api/account/me', () =>
            HttpResponse.json({ detail: 'oops' }, { status: 500 }),
          ),
        );
        const user = userEvent.setup();
        renderPage();
        await screen.findByText(/Could not load account/i);
        // Restore default handler for retry
        server.resetHandlers();
        await user.click(screen.getByRole('button', { name: /reload account/i }));
        expect(await screen.findByText('alice@example.com')).toBeInTheDocument();
      });

      it('hides Upgrade button when plan_tier="pro"', async () => {
        server.use(
          http.get('/api/account/me', () =>
            HttpResponse.json({
              user_id: 1, email: 'alice@example.com', plan_tier: 'pro',
              trial_started_at: null, token_version: 0,
            }),
          ),
        );
        renderPage();
        await screen.findByText('alice@example.com');
        expect(screen.queryByRole('button', { name: /upgrade to pro/i })).not.toBeInTheDocument();
      });
    });
    ```

    **2b. UpgradeInterestDialog.test.tsx** — fake-timers for auto-close:
    ```typescript
    it('submits, swallows 501, shows Thanks copy', async () => {
      const user = userEvent.setup();
      const onOpenChange = vi.fn();
      render(<UpgradeInterestDialog open onOpenChange={onOpenChange} />);
      await user.click(await screen.findByRole('button', { name: /^send$/i }));
      expect(await screen.findByText(/thanks/i)).toBeInTheDocument();
      expect(await screen.findByText(/v1\.3/i)).toBeInTheDocument();
    });

    it('auto-closes 2s after success', async () => {
      vi.useFakeTimers();
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
      const onOpenChange = vi.fn();
      render(<UpgradeInterestDialog open onOpenChange={onOpenChange} />);
      await user.click(screen.getByRole('button', { name: /^send$/i }));
      await vi.advanceTimersByTimeAsync(2100);
      expect(onOpenChange).toHaveBeenCalledWith(false);
      vi.useRealTimers();
    });

    it('429 shows retry-after countdown', async () => {
      server.use(
        http.post('/billing/checkout', () =>
          HttpResponse.json({ detail: 'rate' }, { status: 429, headers: { 'Retry-After': '15' } }),
        ),
      );
      const user = userEvent.setup();
      render(<UpgradeInterestDialog open onOpenChange={() => {}} />);
      await user.click(screen.getByRole('button', { name: /^send$/i }));
      expect(await screen.findByText(/15s/)).toBeInTheDocument();
    });
    ```

    **2c. DeleteAccountDialog.test.tsx** — match gate + logout-redirect path:
    ```typescript
    const STORED_EMAIL = 'alice@example.com';

    function renderDialog() {
      return render(
        <MemoryRouter initialEntries={['/dashboard/account']}>
          <Routes>
            <Route path="/dashboard/account" element={
              <DeleteAccountDialog open onOpenChange={() => {}} userEmail={STORED_EMAIL} />
            } />
            <Route path="/login" element={<div>login-marker</div>} />
          </Routes>
        </MemoryRouter>,
      );
    }

    it('submit disabled when input empty', async () => {
      renderDialog();
      const submit = await screen.findByRole('button', { name: /^delete account$/i });
      expect(submit).toBeDisabled();
    });

    it('submit enables on case-insensitive match', async () => {
      const user = userEvent.setup();
      renderDialog();
      const input = await screen.findByLabelText(/type your email/i);
      await user.type(input, 'ALICE@example.com');
      expect(await screen.findByRole('button', { name: /^delete account$/i })).toBeEnabled();
    });

    it('submit calls authStore.logout + navigates /login', async () => {
      const user = userEvent.setup();
      const logoutSpy = vi.spyOn(useAuthStore.getState(), 'logout').mockResolvedValue();
      renderDialog();
      const input = await screen.findByLabelText(/type your email/i);
      await user.type(input, STORED_EMAIL);
      await user.click(screen.getByRole('button', { name: /^delete account$/i }));
      expect(await screen.findByText('login-marker')).toBeInTheDocument();
      expect(logoutSpy).toHaveBeenCalled();
    });

    it('400 from server shows mismatch copy', async () => {
      server.use(
        http.delete('/api/account', () =>
          HttpResponse.json({ detail: { error: { code: 'EMAIL_CONFIRM_MISMATCH' } } }, { status: 400 }),
        ),
      );
      const user = userEvent.setup();
      renderDialog();
      const input = await screen.findByLabelText(/type your email/i);
      await user.type(input, STORED_EMAIL);
      await user.click(screen.getByRole('button', { name: /^delete account$/i }));
      expect(await screen.findByText(/Confirmation email does not match/i)).toBeInTheDocument();
    });
    ```

    NOTE: spying on `useAuthStore.getState().logout` after render requires Zustand reference identity. Alternative: stub the entire store via `vi.mock('@/lib/stores/authStore', ...)` if the spy approach proves flaky. Pick the working approach — both are valid.

    **2d. LogoutAllDialog.test.tsx** — mirror DeleteAccountDialog pattern but no input:
    ```typescript
    it('confirm calls authStore.logout + navigates /login', async () => {
      const user = userEvent.setup();
      const logoutSpy = vi.spyOn(useAuthStore.getState(), 'logout').mockResolvedValue();
      render(
        <MemoryRouter initialEntries={['/here']}>
          <Routes>
            <Route path="/here" element={<LogoutAllDialog open onOpenChange={() => {}} />} />
            <Route path="/login" element={<div>login-marker</div>} />
          </Routes>
        </MemoryRouter>,
      );
      await user.click(await screen.findByRole('button', { name: /sign out everywhere/i }));
      expect(await screen.findByText('login-marker')).toBeInTheDocument();
      expect(logoutSpy).toHaveBeenCalled();
    });

    it('429 shows rate-limit copy', async () => {
      server.use(
        http.post('/auth/logout-all', () =>
          HttpResponse.json({ detail: 'rate' }, { status: 429, headers: { 'Retry-After': '15' } }),
        ),
      );
      const user = userEvent.setup();
      render(<MemoryRouter><LogoutAllDialog open onOpenChange={() => {}} /></MemoryRouter>);
      await user.click(await screen.findByRole('button', { name: /sign out everywhere/i }));
      expect(await screen.findByText(/Rate limited/i)).toBeInTheDocument();
    });

    it('other error shows generic copy', async () => {
      server.use(
        http.post('/auth/logout-all', () =>
          HttpResponse.json({ detail: 'boom' }, { status: 500 }),
        ),
      );
      const user = userEvent.setup();
      render(<MemoryRouter><LogoutAllDialog open onOpenChange={() => {}} /></MemoryRouter>);
      await user.click(await screen.findByRole('button', { name: /sign out everywhere/i }));
      expect(await screen.findByText(/Could not sign out/i)).toBeInTheDocument();
    });
    ```

    Naming: `STORED_EMAIL` constant, `renderDialog` helper, `logoutSpy`, `login-marker` — explicit.
  </action>
  <verify>
    <automated>cd frontend &amp;&amp; bun run vitest run src/tests/routes/AccountPage.test.tsx src/tests/components/UpgradeInterestDialog.test.tsx src/tests/components/DeleteAccountDialog.test.tsx src/tests/components/LogoutAllDialog.test.tsx</automated>
  </verify>
  <acceptance_criteria>
    - `AccountPage.test.tsx` reports >= 4 passing tests
    - `UpgradeInterestDialog.test.tsx` reports >= 3 passing tests
    - `DeleteAccountDialog.test.tsx` reports >= 4 passing tests
    - `LogoutAllDialog.test.tsx` reports >= 3 passing tests
    - Total >= 14 new test cases across the 4 files
    - All tests use `await user.click` / `await screen.findByRole` (TEST-05 invariant — verifier-grep `screen\.getByRole.*onClick` / similar anti-patterns: 0)
    - Existing test suite does NOT regress: `cd frontend && bun run vitest run` exits 0 across the full project
    - `grep -cE "^\s+if .*\bif\b" frontend/src/tests/routes/AccountPage.test.tsx frontend/src/tests/components/UpgradeInterestDialog.test.tsx frontend/src/tests/components/DeleteAccountDialog.test.tsx frontend/src/tests/components/LogoutAllDialog.test.tsx` returns 0
  </acceptance_criteria>
  <done>14+ RTL tests green covering UI-07/AUTH-06/SCOPE-06/BILL-05 client paths; full Vitest suite green; no regressions; TEST-05 invariants honored.</done>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <name>Task 3: Mobile-responsive + /frontend-design polish human verification (UI-07 polish bar)</name>
  <files>frontend/src/routes/AccountPage.tsx, frontend/src/components/dashboard/UpgradeInterestDialog.tsx, frontend/src/components/dashboard/DeleteAccountDialog.tsx, frontend/src/components/dashboard/LogoutAllDialog.tsx</files>
  <read_first>
    - .planning/phases/15-account-dashboard-hardening-billing-stubs/15-UI-SPEC.md §80-83 (manual verifications) + §412-419 (mobile responsive table) + §427-434 (checker dimensions)
  </read_first>
  <acceptance_criteria>
    - Human reviewer types "approved" after the 8 verification steps below complete cleanly.
    - Any failure: reviewer describes the issue verbatim so the executor can fix-and-re-verify.
  </acceptance_criteria>
  <action>
    Pause execution. Present the verification steps below to the user. Wait for the resume-signal text before continuing the wave or marking the plan complete. Do NOT auto-skip — UI-07 polish bar is locked at UI-SPEC §80-83 as manual-only.
  </action>
  <verify>Human reviewer signals approval (or describes failures) per resume-signal below.</verify>
  <done>Reviewer typed "approved" — mobile-responsive + /frontend-design polish bar verified.</done>
  <what-built>
    AccountPage (Profile / Plan / Danger Zone three-card layout) + 3 dialogs (UpgradeInterestDialog, DeleteAccountDialog, LogoutAllDialog) — automated tests cover behavior; visual polish + mobile-responsive layout require human eyes per UI-SPEC §80-83.
  </what-built>
  <how-to-verify>
    Pre-requisite: `cd frontend && bun run dev` running (Vite default :5173 or whichever this project uses). Have a registered + logged-in user (use any account from earlier phases).

    1. **Desktop (≥1024px wide)**:
       - Visit `/dashboard/account`
       - Verify: page heading "Account", three cards stack vertically with 24px (gap-6) gaps
       - Profile card shows email + plan badge (color matches `plan_tier`: trial=outline, pro=solid black, etc.)
       - Profile card shows "For password reset, email hey@logingrupa.lv." with mailto link
       - Plan card shows tier-specific copy + "Upgrade to Pro" button (only if not pro/team)
       - Danger Zone card has destructive border tint, two rows side-by-side (helper text left, button right), buttons are red destructive variant

    2. **Tablet (≥768px, <1024px)** — Chrome DevTools responsive at 768px:
       - Cards still stack vertically gap-6
       - Danger zone rows still side-by-side

    3. **Mobile (<640px)** — DevTools at 375px:
       - Page max-width respected; outer wrapper gap reduces to 16px (gap-4)
       - Danger zone rows stack: helper text on top, button below at full width
       - Cards retain p-6 internal padding
       - Open each dialog (Upgrade / Delete / Logout-all) — verify they adapt: Dialog max-w-[calc(100%-2rem)], DialogFooter buttons stack with confirm on top, cancel below

    4. **UpgradeInterestDialog** flow:
       - Click "Upgrade to Pro" → dialog opens with textarea + Send/No-thanks buttons
       - Type something → click Send → dialog body replaces with "Thanks! Stripe checkout arrives in v1.3." → auto-closes after ~2 seconds

    5. **DeleteAccountDialog** flow (use a throwaway account — this WILL delete it):
       - Click "Delete account" → dialog opens with email input + disabled Delete button
       - Type wrong email → submit stays disabled
       - Type correct email (any case mix, e.g. ALICE@Example.com) → submit enables → click → redirected to /login
       - Verify the user really cannot log back in (account gone)

    6. **LogoutAllDialog** flow:
       - Log in fresh; in another tab open the same account
       - Tab A: click "Sign out of all devices" → confirm → redirected to /login
       - Tab B: any subsequent navigation 401s; redirected to /login (token_version invariant)

    7. **Polish bar (/frontend-design comparison)**:
       - Side-by-side compare with `/dashboard/keys` (KeysDashboardPage):
         * gap-6 between cards: matches
         * rounded-xl on cards: matches
         * destructive variant on red buttons: matches
         * heading sizes (text-2xl page, text-lg cards): matches
         * font weights (semibold for headings, normal for body): matches

    8. **Accessibility smoke**:
       - Tab through dialog: focus trap works, Esc closes
       - Email input on Delete dialog has autoComplete="off" (verify in DevTools)
  </how-to-verify>
  <resume-signal>Type "approved" if all 8 checks pass. If any failed, describe the issue (e.g., "Danger zone rows did not stack on mobile" / "Auto-close fired before 2s") so the executor can fix and re-verify.</resume-signal>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Browser DOM → DeleteAccountDialog input | UI gate (case-insensitive match) — defence-in-depth; backend re-validates (Plan 15-04) |
| Browser → /billing/checkout (501 stub) | UpgradeInterestDialog catches 501 as success — no PII captured (just optional message text) |
| AuthStore.logout() → BroadcastChannel('auth') | Cross-tab sync — existing UI-12 mechanism |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-15-02 | Tampering | UI gate bypass via dev tools | mitigate | Backend service re-validates email_confirm (Plan 15-04 service-level guard); UI gate is UX, not security; tests assert backend 400 path |
| T-15-07 | DoS (UX) | 501 from /billing/checkout breaks UpgradeInterestDialog success state | mitigate | Catch ApiClientError statusCode === 501 BEFORE generic ApiClientError branch; assert via `swallows 501` test |
| T-15-09 | Information Disclosure | Cross-tab logout-all not synced | mitigate | LogoutAllDialog calls authStore.logout() AFTER /auth/logout-all; logout() broadcasts via BroadcastChannel('auth') (UI-12); other tabs see logout, set user=null |
| T-15-10 | Availability | Unknown plan_tier crashes badge map | mitigate | PLAN_BADGE_VARIANT typed Record narrows; PLAN_COPY[tier] ?? 'Plan details unavailable.' fallback; defensive at type level |
| T-15-11 | Information Disclosure | XSS via email rendered in DOM | mitigate | React auto-escapes `{user.email}` interpolation; no dangerouslySetInnerHTML; UI-SPEC §314 verbatim copy |
| T-13-13 | Information Disclosure | Email in client logs / analytics | accept | No new logging in components; React DevTools shows props in dev only; production trim acceptable |
</threat_model>

<verification>
- All 14+ RTL tests pass: `cd frontend && bun run vitest run src/tests/routes/AccountPage.test.tsx src/tests/components/UpgradeInterestDialog.test.tsx src/tests/components/DeleteAccountDialog.test.tsx src/tests/components/LogoutAllDialog.test.tsx`
- Full frontend test suite passes (no regression): `cd frontend && bun run vitest run`
- TypeScript clean: `cd frontend && bunx tsc --noEmit` exits 0
- AccountStubPage.tsx file does not exist; AppRouter no longer imports it
- Nested-if invariant: 0 across all 4 new component files + 4 new test files
- Single fetch site invariant preserved: `cd frontend && grep -rn "fetch(" frontend/src --include="*.tsx" --include="*.ts" | grep -v "apiClient" | grep -v "tests/" | grep -v "node_modules"` returns 0 (apiClient still the only fetch site)
- Human verify checkpoint: 8 mobile/desktop/dialog/polish checks approved
</verification>

<success_criteria>
1. AccountPage at /dashboard/account renders Profile/Plan/Danger Zone three-card layout
2. Plan-tier badge color matches PLAN_BADGE_VARIANT mapping
3. Plan body copy matches plan_tier per PLAN_COPY mapping
4. Upgrade-to-Pro CTA hidden when plan_tier in {pro, team}
5. UpgradeInterestDialog swallows 501 as success and auto-closes after 2s
6. DeleteAccountDialog enables submit only on case-insensitive email match
7. DeleteAccountDialog success calls authStore.logout() + navigate('/login', {replace:true})
8. LogoutAllDialog confirm calls /auth/logout-all + authStore.logout() + navigate('/login')
9. AppRouter mounts lazy-loaded AccountPage at /dashboard/account
10. AccountStubPage.tsx deleted from disk
11. Mobile-responsive at sm/md/lg breakpoints (human verify approved)
12. /frontend-design polish bar matches sibling KeysDashboardPage (human verify approved)
</success_criteria>

<output>
After completion, create `.planning/phases/15-account-dashboard-hardening-billing-stubs/15-06-SUMMARY.md`
</output>
