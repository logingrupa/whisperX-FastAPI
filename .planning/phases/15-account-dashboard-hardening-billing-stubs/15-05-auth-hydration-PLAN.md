---
phase: 15
plan: 05
type: execute
wave: 3
depends_on: ["15-01", "15-03"]
files_modified:
  - frontend/src/lib/stores/authStore.ts
  - frontend/src/routes/RequireAuth.tsx
  - frontend/src/main.tsx
  - frontend/src/routes/AppRouter.tsx
  - frontend/src/tests/lib/stores/authStore.test.ts
  - frontend/src/tests/routes/RequireAuth.test.tsx
autonomous: true
requirements: [UI-07]
must_haves:
  truths:
    - "authStore exposes refresh() that hydrates user from /api/account/me"
    - "authStore exposes isHydrating boolean (initial true, flips false after refresh resolves/rejects)"
    - "AuthUser interface includes trialStartedAt + tokenVersion fields server-authoritative after refresh"
    - "RequireAuth renders nothing while isHydrating=true (suppresses redirect-flash on boot)"
    - "RequireAuth redirects to /login?next= after isHydrating=false when user is null"
    - "main.tsx triggers refresh() once at module load before App renders"
    - "AppRouter mount points unchanged (account stub swap is in Plan 15-06)"
  artifacts:
    - path: "frontend/src/lib/stores/authStore.ts"
      provides: "Extended AuthUser + AuthState; refresh() method; isHydrating flag"
      contains: "refresh: async ()"
    - path: "frontend/src/routes/RequireAuth.tsx"
      provides: "Updated gate with isHydrating short-circuit"
      contains: "isHydrating"
    - path: "frontend/src/main.tsx"
      provides: "Boot-time useAuthStore.getState().refresh() invocation"
      contains: "refresh"
  key_links:
    - from: "frontend/src/lib/stores/authStore.ts:refresh"
      to: "frontend/src/lib/api/accountApi.ts:fetchAccountSummary"
      via: "import + call"
      pattern: "fetchAccountSummary"
    - from: "frontend/src/main.tsx"
      to: "frontend/src/lib/stores/authStore.ts"
      via: "useAuthStore.getState().refresh() pre-render"
      pattern: "useAuthStore\\.getState\\(\\)\\.refresh\\(\\)"
    - from: "frontend/src/routes/RequireAuth.tsx"
      to: "frontend/src/lib/stores/authStore.ts:isHydrating"
      via: "useAuthStore selector"
      pattern: "isHydrating"
---

<objective>
Wire frontend session hydration: add `authStore.refresh()` (calls fetchAccountSummary from Plan 15-01), add `isHydrating: boolean` flag, extend AuthUser with trialStartedAt + tokenVersion, gate RequireAuth on isHydrating, trigger refresh() once at app boot in main.tsx. Server becomes the source of truth for user state on every page load (Plan 14-03 trade-off resolved).

Purpose: Bridge the Plan 14-03 "user-is-null-on-reload" gap. Required by Plan 15-06 (AccountPage reads server-authoritative user.email + planTier).
Output: 2 source modifications + 1 boot-trigger + 2 test extensions.
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
@.planning/phases/15-account-dashboard-hardening-billing-stubs/15-PATTERNS.md
@.planning/phases/15-account-dashboard-hardening-billing-stubs/15-01-groundwork-PLAN.md
@frontend/src/lib/stores/authStore.ts
@frontend/src/routes/RequireAuth.tsx
@frontend/src/main.tsx
@frontend/src/routes/AppRouter.tsx
@frontend/src/lib/api/accountApi.ts
@frontend/src/lib/apiClient.ts
@frontend/src/tests/lib/stores/authStore.test.ts
@frontend/src/tests/routes/RequireAuth.test.tsx

<interfaces>
<!-- Pulled from codebase. Use directly. -->

From frontend/src/lib/stores/authStore.ts (current state, lines 21-113):
```typescript
export interface AuthUser {
  id: number;
  email: string;
  planTier: string;
}

interface BroadcastAuthMessage {
  type: 'login' | 'logout';
}

interface AuthState {
  user: AuthUser | null;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const toAuthUser = (response: { user_id: number; plan_tier: string }, email: string): AuthUser => ({
  id: response.user_id,
  email,
  planTier: response.plan_tier,
});

export const useAuthStore = create<AuthState>((set) => {
  getChannel().addEventListener('message', (event: MessageEvent) => {
    const data = event.data as BroadcastAuthMessage;
    if (data.type === 'logout') {
      set({ user: null });
    }
  });

  return {
    user: null,
    login: async (email, password) => {
      const response = await apiClient.post<{ user_id: number; plan_tier: string }>('/auth/login', { email, password });
      set({ user: toAuthUser(response, email) });
      getChannel().postMessage({ type: 'login' } satisfies BroadcastAuthMessage);
    },
    register: async (email, password) => { /* same shape */ },
    logout: async () => { /* clears + broadcasts */ },
  };
});
```

From frontend/src/routes/RequireAuth.tsx (current state, lines 12-22):
```typescript
export function RequireAuth() {
  const user = useAuthStore((s) => s.user);
  const location = useLocation();

  if (user === null) {
    const next = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/login?next=${next}`} replace />;
  }
  return <Outlet />;
}
```

From frontend/src/lib/api/accountApi.ts (Plan 15-01):
```typescript
export interface AccountSummaryResponse { user_id; email; plan_tier; trial_started_at; token_version }
export function fetchAccountSummary(): Promise<AccountSummaryResponse>;  // suppress401Redirect inside
```

From frontend/src/lib/apiClient.ts (existing exports):
```typescript
export class ApiClientError extends Error { statusCode: number; ... }
export class AuthRequiredError extends ApiClientError { ... }
export class RateLimitError extends ApiClientError { ... }
```

From frontend/src/main.tsx (current — verify by reading; typical Vite entry):
```tsx
import React from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';
import './index.css';

createRoot(document.getElementById('root')!).render(<App />);
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Extend authStore — AuthUser fields, isHydrating flag, refresh() method, login/register populate new fields</name>
  <files>frontend/src/lib/stores/authStore.ts, frontend/src/tests/lib/stores/authStore.test.ts</files>
  <read_first>
    - frontend/src/lib/stores/authStore.ts (full — current shape + BroadcastChannel wiring + toAuthUser helper)
    - frontend/src/lib/api/accountApi.ts (post-Plan 15-01 — AccountSummaryResponse + fetchAccountSummary)
    - frontend/src/lib/apiClient.ts (AuthRequiredError + ApiClientError exports)
    - frontend/src/tests/lib/stores/authStore.test.ts (existing login/register/logout tests; pattern for vi.mock + MSW)
    - frontend/src/tests/msw/account.handlers.ts (post-Plan 15-01 — /me default 200 mock)
    - .planning/phases/15-account-dashboard-hardening-billing-stubs/15-PATTERNS.md §"frontend/src/lib/stores/authStore.ts (MODIFY)"
    - .planning/phases/15-account-dashboard-hardening-billing-stubs/15-RESEARCH.md §"Frontend authStore.refresh Wiring [CRITICAL]" §621-723
  </read_first>
  <behavior>
    Tests in `authStore.test.ts`:
    - Test 1 `refresh() populates user from /me`: default MSW handler returns 200; await refresh(); user is { id: 1, email: 'alice@example.com', planTier: 'trial', trialStartedAt: '2026-04-22T12:00:00Z', tokenVersion: 0 }; isHydrating === false.
    - Test 2 `refresh() 401 leaves user null without throwing`: server.use override → 401; await refresh() (no rejection); user === null; isHydrating === false.
    - Test 3 `refresh() flips isHydrating from true to false`: assert initial isHydrating=true; after refresh resolves, isHydrating=false.
    - Test 4 `login() still works (no regression)`: existing test pattern — login resolves, user populated; trialStartedAt/tokenVersion stay default-shaped (null + 0) until refresh fires.
    - Test 5 `logout() clears user + isHydrating untouched`: after login, isHydrating already false; logout sets user=null; isHydrating still false (logout does not re-hydrate).
  </behavior>
  <action>
    Per RESEARCH §"AuthState Shape Extension" (LOCKED) + §"Boot Trigger Strategy" (LOCKED Strategy 1 with isHydrating flag) — extend the store, don't rewrite.

    Modify `frontend/src/lib/stores/authStore.ts`:

    1. Extend imports:
    ```typescript
    import { apiClient, ApiClientError, AuthRequiredError } from '@/lib/apiClient';
    import { fetchAccountSummary, type AccountSummaryResponse } from '@/lib/api/accountApi';
    ```

    2. Extend AuthUser interface (preserve existing fields for backward compat with login/register):
    ```typescript
    export interface AuthUser {
      id: number;
      email: string;
      planTier: string;
      trialStartedAt: string | null;
      tokenVersion: number;
    }
    ```

    3. Extend AuthState interface:
    ```typescript
    interface AuthState {
      user: AuthUser | null;
      isHydrating: boolean;
      login: (email: string, password: string) => Promise<void>;
      register: (email: string, password: string) => Promise<void>;
      logout: () => Promise<void>;
      refresh: () => Promise<void>;
    }
    ```

    4. Update `toAuthUser` helper to populate new fields with safe defaults (login/register responses don't include trial_started_at/token_version per Plan 14-03):
    ```typescript
    const toAuthUser = (
      response: { user_id: number; plan_tier: string },
      email: string,
    ): AuthUser => ({
      id: response.user_id,
      email,
      planTier: response.plan_tier,
      trialStartedAt: null,
      tokenVersion: 0,
    });
    ```

    5. Add `isHydrating: true` to initial state and `refresh` method to the store body. RESEARCH §671-695 verbatim:
    ```typescript
    return {
      user: null,
      isHydrating: true,
      login: /* existing */,
      register: /* existing */,
      logout: /* existing */,
      refresh: async () => {
        try {
          const summary = await fetchAccountSummary();
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
          // 401 throws AuthRequiredError; leave user null. Other ApiClientErrors
          // (network, 500, etc.) — also leave user null. Genuinely unexpected
          // errors re-thrown for visibility.
          if (!(err instanceof AuthRequiredError) && !(err instanceof ApiClientError)) {
            throw err;
          }
        } finally {
          set({ isHydrating: false });
        }
      },
    };
    ```

    Tiger-style: try/finally guarantees isHydrating flips false on every code path; explicit error-class branch (no catch-all swallow).
    SRP: store owns hydration state; api module owns HTTP.
    DRY: reuses fetchAccountSummary from Plan 15-01 (zero new fetch sites).
    No nested-if: single flat guard inside catch (`if (!(a) && !(b))`).
    Naming: `summary` (not `s` / `data`); `isHydrating` (not `loading` / `hydrating`).

    6. Add 5 tests to `frontend/src/tests/lib/stores/authStore.test.ts`. Reset state in beforeEach to include `isHydrating: true`:
    ```typescript
    beforeEach(() => {
      useAuthStore.setState({ user: null, isHydrating: true });
    });

    it('refresh() populates user from /me', async () => {
      await useAuthStore.getState().refresh();
      const u = useAuthStore.getState().user;
      expect(u).not.toBe(null);
      expect(u!.id).toBe(1);
      expect(u!.email).toBe('alice@example.com');
      expect(u!.planTier).toBe('trial');
      expect(u!.trialStartedAt).toBe('2026-04-22T12:00:00Z');
      expect(u!.tokenVersion).toBe(0);
      expect(useAuthStore.getState().isHydrating).toBe(false);
    });

    it('refresh() 401 leaves user null without throwing', async () => {
      server.use(
        http.get('/api/account/me', () =>
          HttpResponse.json({ detail: 'Authentication required' }, { status: 401 }),
        ),
      );
      await expect(useAuthStore.getState().refresh()).resolves.toBeUndefined();
      expect(useAuthStore.getState().user).toBe(null);
      expect(useAuthStore.getState().isHydrating).toBe(false);
    });

    it('refresh() flips isHydrating to false on success', async () => {
      expect(useAuthStore.getState().isHydrating).toBe(true);
      await useAuthStore.getState().refresh();
      expect(useAuthStore.getState().isHydrating).toBe(false);
    });

    it('refresh() flips isHydrating to false on network error', async () => {
      server.use(
        http.get('/api/account/me', () => HttpResponse.error()),
      );
      await useAuthStore.getState().refresh();
      expect(useAuthStore.getState().isHydrating).toBe(false);
      expect(useAuthStore.getState().user).toBe(null);
    });

    it('login() still populates new fields with defaults', async () => {
      await useAuthStore.getState().login('alice@example.com', 'password123');
      const u = useAuthStore.getState().user;
      expect(u!.trialStartedAt).toBe(null);
      expect(u!.tokenVersion).toBe(0);
    });
    ```
  </action>
  <verify>
    <automated>cd frontend &amp;&amp; bunx tsc --noEmit &amp;&amp; bun run vitest run src/tests/lib/stores/authStore.test.ts</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "isHydrating: boolean" frontend/src/lib/stores/authStore.ts` returns 1
    - `grep -c "isHydrating: true" frontend/src/lib/stores/authStore.ts` returns 1 (initial state)
    - `grep -c "set({ isHydrating: false })" frontend/src/lib/stores/authStore.ts` returns 1 (in finally block)
    - `grep -c "refresh: async" frontend/src/lib/stores/authStore.ts` returns 1
    - `grep -c "fetchAccountSummary" frontend/src/lib/stores/authStore.ts` returns 1
    - `grep -c "trialStartedAt" frontend/src/lib/stores/authStore.ts` >= 2 (interface + toAuthUser default)
    - `grep -c "tokenVersion" frontend/src/lib/stores/authStore.ts` >= 2
    - `grep -cE "^\s+if .*\bif\b" frontend/src/lib/stores/authStore.ts` returns 0
    - `cd frontend && bunx tsc --noEmit` exits 0
    - `cd frontend && bun run vitest run src/tests/lib/stores/authStore.test.ts` reports >= 5 new tests passing + existing tests still green
  </acceptance_criteria>
  <done>authStore extended with refresh + isHydrating + new AuthUser fields; 5+ tests green; existing login/register/logout tests still green; tsc clean.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Update RequireAuth gate + boot-trigger refresh() in main.tsx + add 2 RequireAuth tests</name>
  <files>frontend/src/routes/RequireAuth.tsx, frontend/src/main.tsx, frontend/src/tests/routes/RequireAuth.test.tsx</files>
  <read_first>
    - frontend/src/routes/RequireAuth.tsx (full — current 11-line gate)
    - frontend/src/main.tsx (full — entry point; identify where to add the boot probe call)
    - frontend/src/routes/AppRouter.tsx (verify RequireAuth is mounted; do not modify yet — Plan 15-06 owns the AccountStub swap)
    - frontend/src/tests/routes/RequireAuth.test.tsx (if exists; otherwise create)
    - .planning/phases/15-account-dashboard-hardening-billing-stubs/15-PATTERNS.md §"frontend/src/routes/RequireAuth.tsx (MODIFY)"
    - .planning/phases/15-account-dashboard-hardening-billing-stubs/15-RESEARCH.md §"Frontend authStore.refresh Wiring/RequireAuth" §700-714 + §"Boot Trigger Strategy" §658-666
  </read_first>
  <behavior>
    - Test 1 `RequireAuth renders nothing while isHydrating=true`: setState({user:null, isHydrating:true}); render <MemoryRouter><RequireAuth /></MemoryRouter>; assert no Outlet rendered + no Navigate (e.g., assert location pathname unchanged).
    - Test 2 `RequireAuth redirects to /login?next= after isHydrating=false + user=null`: setState({user:null, isHydrating:false}); render at /dashboard/keys; assert pathname becomes /login with next query.
    - Test 3 (smoke — existing if any): RequireAuth with user populated renders Outlet.
    - main.tsx: importing the entry triggers `useAuthStore.getState().refresh()` once before rendering — verified by checking the file has a single line invoking refresh at module scope.
  </behavior>
  <action>
    **2a. Modify `frontend/src/routes/RequireAuth.tsx`** — RESEARCH §700-714 verbatim. Two flat guard clauses:
    ```typescript
    import { Navigate, Outlet, useLocation } from 'react-router-dom';

    import { useAuthStore } from '@/lib/stores/authStore';

    export function RequireAuth() {
      const user = useAuthStore((s) => s.user);
      const isHydrating = useAuthStore((s) => s.isHydrating);
      const location = useLocation();

      // Suppress redirect-flash during boot probe — RequireAuth waits one tick
      if (isHydrating) {
        return null;
      }

      if (user === null) {
        const next = encodeURIComponent(location.pathname + location.search);
        return <Navigate to={`/login?next=${next}`} replace />;
      }
      return <Outlet />;
    }
    ```

    Tiger-style: each guard explicit, fail-closed (return null hides UI rather than risk leaking authed routes during hydration).
    SRP: gate-only — does not own hydration trigger.
    No nested-if: 2 separate flat guards, then return Outlet.

    **2b. Modify `frontend/src/main.tsx`** — add the single boot-probe line BEFORE `createRoot(...).render(...)`. Read the file first to see current structure; then add:
    ```typescript
    import { useAuthStore } from '@/lib/stores/authStore';

    // Boot probe — hydrate auth from server cookie session before first render.
    // Resolves regardless of outcome; isHydrating flips false in refresh's finally.
    void useAuthStore.getState().refresh();
    ```

    Place after imports, before `createRoot`. The `void` operator makes the fire-and-forget intent explicit (no unhandled-promise lint warning).

    **2c. Add `frontend/src/tests/routes/RequireAuth.test.tsx`** (or extend if it exists). Use MemoryRouter + a simple assertion strategy:
    ```typescript
    import { describe, it, expect, beforeEach } from 'vitest';
    import { render, screen } from '@testing-library/react';
    import { MemoryRouter, Routes, Route } from 'react-router-dom';

    import { RequireAuth } from '@/routes/RequireAuth';
    import { useAuthStore } from '@/lib/stores/authStore';

    function renderWithRouter(initialPath: string) {
      return render(
        <MemoryRouter initialEntries={[initialPath]}>
          <Routes>
            <Route path="/login" element={<div>login-marker</div>} />
            <Route element={<RequireAuth />}>
              <Route path="/dashboard/keys" element={<div>keys-marker</div>} />
            </Route>
          </Routes>
        </MemoryRouter>,
      );
    }

    describe('RequireAuth', () => {
      beforeEach(() => {
        useAuthStore.setState({ user: null, isHydrating: true });
      });

      it('renders nothing while isHydrating=true (no redirect-flash)', () => {
        useAuthStore.setState({ user: null, isHydrating: true });
        renderWithRouter('/dashboard/keys');
        expect(screen.queryByText('keys-marker')).not.toBeInTheDocument();
        expect(screen.queryByText('login-marker')).not.toBeInTheDocument();
      });

      it('redirects to /login?next= after hydration completes with user=null', () => {
        useAuthStore.setState({ user: null, isHydrating: false });
        renderWithRouter('/dashboard/keys');
        expect(screen.getByText('login-marker')).toBeInTheDocument();
      });

      it('renders Outlet child when user is populated', () => {
        useAuthStore.setState({
          user: {
            id: 1,
            email: 'alice@example.com',
            planTier: 'trial',
            trialStartedAt: null,
            tokenVersion: 0,
          },
          isHydrating: false,
        });
        renderWithRouter('/dashboard/keys');
        expect(screen.getByText('keys-marker')).toBeInTheDocument();
      });
    });
    ```

    Naming: `renderWithRouter`, `keys-marker`, `login-marker` — self-explanatory test scaffolding.
  </action>
  <verify>
    <automated>cd frontend &amp;&amp; bunx tsc --noEmit &amp;&amp; bun run vitest run src/tests/routes/RequireAuth.test.tsx</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "isHydrating" frontend/src/routes/RequireAuth.tsx` >= 2 (selector + guard)
    - `grep -c "if (isHydrating)" frontend/src/routes/RequireAuth.tsx` returns 1
    - `grep -c "if (user === null)" frontend/src/routes/RequireAuth.tsx` returns 1
    - `grep -cE "^\s+if .*\bif\b" frontend/src/routes/RequireAuth.tsx` returns 0
    - `grep -c "useAuthStore.getState().refresh()" frontend/src/main.tsx` returns 1
    - `cd frontend && bunx tsc --noEmit` exits 0
    - `cd frontend && bun run vitest run src/tests/routes/RequireAuth.test.tsx` reports 3 passing
    - Existing AppRouter / smoke tests still pass: `cd frontend && bun run vitest run src/tests/routes/AppRouter.test.tsx`
  </acceptance_criteria>
  <done>RequireAuth gates on isHydrating; main.tsx boot-trigger fires once; 3 RequireAuth tests green; AppRouter smoke unaffected.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Browser boot → /api/account/me probe | suppress401Redirect=true: 401 silently leaves user=null, no redirect side-effect |
| RequireAuth gate → routed children | isHydrating short-circuit prevents authed-route render with stale state |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-15-09 | Information Disclosure | Cross-tab refresh race during hydration | accept | Each tab independently runs refresh on mount; BroadcastChannel logout sync (existing UI-12) handles tab-to-tab logout. Refresh races are idempotent (same /me read). |
| T-15-10 | Availability | plan_tier null/undefined crashes consumers | mitigate | AccountSummaryResponse.plan_tier is required by Pydantic (server side); TypeScript type narrows to literal union; UI defensive fallback in Plan 15-06 |
| (boot-flash) | UX / Information Disclosure | RequireAuth redirects before refresh resolves, then re-redirects on success | mitigate | isHydrating: true initial state + null render until flip; eliminates double-redirect race per RESEARCH §658-666 LOCKED Strategy |
| T-15-04 | Information Disclosure | refresh() throws on unexpected error not silently | mitigate | Catch narrows to AuthRequiredError + ApiClientError; truly unexpected errors propagate (visible in dev console), but isHydrating still flips via finally |
</threat_model>

<verification>
- All authStore + RequireAuth tests pass: `cd frontend && bun run vitest run src/tests/lib/stores/authStore.test.ts src/tests/routes/RequireAuth.test.tsx`
- Existing tests do not regress: `cd frontend && bun run vitest run` (full suite)
- TypeScript compiles: `cd frontend && bunx tsc --noEmit` exits 0
- main.tsx contains exactly one `refresh()` invocation at module scope (not inside React component or event handler)
- Nested-if invariant: 0 across modified files
</verification>

<success_criteria>
1. authStore.refresh() reads /api/account/me and populates user with id/email/planTier/trialStartedAt/tokenVersion
2. authStore.isHydrating starts true and flips false after refresh resolves OR rejects (finally block)
3. RequireAuth renders null while isHydrating=true (no redirect-flash on boot)
4. RequireAuth redirects to /login?next= after isHydrating=false + user=null
5. main.tsx fires refresh() exactly once at module load before App renders
6. AuthUser interface gains trialStartedAt + tokenVersion; existing login/register code populates safe defaults
</success_criteria>

<output>
After completion, create `.planning/phases/15-account-dashboard-hardening-billing-stubs/15-05-SUMMARY.md`
</output>
