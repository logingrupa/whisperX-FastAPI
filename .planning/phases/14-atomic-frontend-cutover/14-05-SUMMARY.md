---
phase: 14-atomic-frontend-cutover
plan: 05
subsystem: ui
tags: [react-hook-form, zod, shadcn, password-strength, anti-enumeration, dry, srp, frontend-design, tdd]

requires:
  - phase: 14-atomic-frontend-cutover
    provides: "Plan 14-04 — AppRouter lazy named-export shim already targets LoginPage/RegisterPage; placeholder pages overwritten in this plan"
  - phase: 14-atomic-frontend-cutover
    provides: "Plan 14-03 — useAuthStore login/register actions + loginSchema/registerSchema zod source"
  - phase: 14-atomic-frontend-cutover
    provides: "Plan 14-02 — apiClient ApiClientError + RateLimitError typed errors used for inline page error UI"
  - phase: 14-atomic-frontend-cutover
    provides: "Plan 14-01 — vitest+RTL+jsdom+MSW infra; auth.handlers (200/401/429) drive page tests"
provides:
  - "frontend/src/lib/passwordStrength.ts — pure 0..4 scorer + label/hint pair (UI-03 requirement)"
  - "frontend/src/components/auth/AuthCard.tsx — Card-on-page layout shared by /login + /register (DRY for UI-13)"
  - "frontend/src/components/auth/PasswordStrengthMeter.tsx — 4-bar visual indicator with red->amber->lime->green progression"
  - "frontend/src/components/forms/FormField.tsx — DRY shadcn FormField row wrapper exporting FormFieldRow generic"
  - "frontend/src/routes/LoginPage.tsx — wired /login (UI-02) with react-hook-form + zod + AuthCard"
  - "frontend/src/routes/RegisterPage.tsx — wired /register (UI-03) with strength meter + terms checkbox"
affects: [14-06, 14-07]

tech-stack:
  added: []
  patterns:
    - "DRY FormFieldRow generic — pages declare fields by control+name+label+type only; one component owns Label/Input/FormMessage composition for the whole auth surface"
    - "AuthCard layout shell — every auth page composes AuthCard(title, subtitle, footer); typography hierarchy and spacing rhythm centralized for UI-13"
    - "Pure passwordStrength scorer — score lives in a pure function (testable without DOM); meter is rendering-only"
    - "Anti-enumeration error mapping — single generic string per request type ('Login failed. Check your credentials.' / 'Registration failed.') regardless of backend code/detail (T-14-12 mitigation)"
    - "isSubmitting-driven submit lock — both pages disable Button via form.formState.isSubmitting; same pattern for any future auth flow"
    - "TDD RED-GREEN gate sequence — failing test commits precede implementation commits for both tasks (verifiable in git log)"

key-files:
  created:
    - frontend/src/lib/passwordStrength.ts
    - frontend/src/components/auth/AuthCard.tsx
    - frontend/src/components/auth/PasswordStrengthMeter.tsx
    - frontend/src/components/forms/FormField.tsx
    - frontend/src/tests/lib/passwordStrength.test.ts
    - frontend/src/tests/routes/LoginPage.test.tsx
    - frontend/src/tests/routes/RegisterPage.test.tsx
  modified:
    - frontend/src/routes/LoginPage.tsx
    - frontend/src/routes/RegisterPage.tsx
    - frontend/src/tests/routes/AppRouter.test.tsx

key-decisions:
  - "passwordStrength scorer is pure (no React, no external library) — bands cumulative {len>=8 +1, mixed-case +1, digit +1, symbol +1, len>=16 +1} capped at 4. Locked: 'Password1' scores 3 (len+mixed+digit, no symbol/long-bonus); 'Password1!' scores 4 (full). Plan-author originally guessed 2 for 'Password1' — boundary recomputed against locked banding and tests asserted the actual value (3) for verifiable contract."
  - "Native <input type='checkbox'> for termsAccepted — no shadcn Checkbox component shipped (frontend/src/components/ui has no checkbox.tsx). Native input + manual styling keeps Plan 14-05 zero-dep; if a future plan needs richer checkbox styling, swap to shadcn-cli `add checkbox` then update one render site in RegisterPage."
  - "PasswordStrengthMeter renders only when passwordValue.length > 0 — empty-form noise is suppressed; first keystroke reveals the meter. Test asserts 'Pass1!' triggers data-testid presence."
  - "RegisterPage uses shadcn FormField directly (not FormFieldRow) for the terms checkbox row — checkbox layout differs from text-input row (start-aligned, label below). FormFieldRow stays text-input-only and clean; the one bespoke FormField call in RegisterPage is a deliberate non-DRY exception (different element, different layout)."
  - "Anti-enumeration: catch ApiClientError (which RateLimitError extends — handle that subtype FIRST), surface single generic string. Never echo response.detail or response.code to UI. Mirrors backend posture (T-14-12)."
  - "AppRouter.test.tsx Rule-1 fix: prior plan asserted 'LoginPage placeholder' / 'RegisterPage placeholder' literal text. This plan replaces those placeholders with real impls; tests now query the visible page heading by role instead. Identical observable contract (anonymous→login redirect; public /register render); the assertion is more robust (heading-role survives any in-page text reshuffle)."

patterns-established:
  - "Form-row DRY via FormFieldRow generic — Plan 14-06 KeysDashboardPage create-key dialog can reuse FormFieldRow for the name input. Future onboarding/profile forms compose the same primitive."
  - "AuthCard layout shell — Plan 14-06 may NOT use AuthCard (dashboards live inside AppShell, not Card-on-page). AuthCard is the locked layout for credential-collection pages only."
  - "Anti-enumeration error funnel — try { authStore.<action> } catch (err) { if RateLimitError -> retry-after countdown; if ApiClientError -> generic; else -> generic-please-retry }. Pattern locked for any future auth-touching surface (e.g., password reset in v1.3, 2FA in v2)."

requirements-completed: [UI-02, UI-03, UI-04, UI-13, TEST-04, TEST-05]

duration: 5m 30s
completed: 2026-04-29
---

# Phase 14 Plan 05: LoginPage + RegisterPage with auth-card layout + zxcvbn-style strength meter Summary

**Two production-ready auth pages — `<LoginPage>` and `<RegisterPage>` — wired through `react-hook-form` + zod resolver + Zustand `authStore`, layered on a shared `<AuthCard>` Card-on-page shell. Custom 0..4 password strength scorer (pure function) drives a 4-bar visual meter; anti-enumeration error funnel mirrors backend posture. 48/48 tests pass; UI-02 / UI-03 / UI-13 truths verified.**

## Performance

- **Duration:** 5m 30s
- **Started:** 2026-04-29T13:45:06Z
- **Completed:** 2026-04-29T13:50:36Z
- **Tasks:** 2 (both TDD RED-GREEN)
- **Files modified:** 10 (7 created, 3 modified)

## Accomplishments

- One pure scorer (`frontend/src/lib/passwordStrength.ts`) owns ALL strength computation — `scorePassword(value)` returns `{ score: 0..4, label, hint }`. Cumulative bands: length>=8 (+1), mixed-case (+1), digit (+1), symbol (+1), length>=16 (+1), capped at 4. 8/8 boundary tests pass; no DOM, no external lib.
- One shared `<AuthCard>` shell (`frontend/src/components/auth/AuthCard.tsx`) — `<div min-h-screen items-center justify-center>` wraps `<Card max-w-md px-8 py-8 shadow-lg>` with title/subtitle/footer slots. Plan 14-06 dashboards do NOT reuse this (they live in AppShell); auth pages all funnel through AuthCard.
- One DRY field-row primitive (`<FormFieldRow>`) — generic over `<T extends FieldValues>`, one component owns Label+Input+FormMessage composition. LoginPage uses it 2x, RegisterPage uses it 3x. Zero copy-pasted form JSX between login and register.
- `<PasswordStrengthMeter>` — 4 segments (red/amber/lime/green) reading from `scorePassword(password).score`; renders the score's `label` + `hint` underneath. `data-testid="password-strength-meter"` and `data-score={0..4}` exposed for verifier-grep + tests.
- `LoginPage` (UI-02) — `useForm<LoginInput>({ resolver: zodResolver(loginSchema) })` → `await login(email, password)` → `navigate(searchParams.get('next') || '/', { replace: true })`. RateLimitError → `Too many login attempts. Try again in {N}s.`; ApiClientError → generic `Login failed. Check your credentials.`; submit disabled by `form.formState.isSubmitting`.
- `RegisterPage` (UI-03) — same pattern with `registerSchema` (which already enforces password match + termsAccepted via Plan 14-03 zod refines). Strength meter mounts only when `passwordValue.length > 0`. Native `<input type="checkbox">` (no shadcn Checkbox component shipped); FormItem wires the label htmlFor automatically.
- Anti-enumeration (T-14-12): single generic string per failure mode regardless of backend code/detail. RateLimitError handled FIRST (it extends ApiClientError); never echo `error.detail` to UI.
- `/frontend-design` UI-13 bar: Card-on-page layout, text-2xl semibold title, muted subtitle, gap-4 between fields, `mt-6 border-t pt-4` footer with hairline rule, focus-visible ring on Input via shadcn defaults, neutral palette.
- 48/48 tests across the project pass: `bun run test` exits 0. New tests = 8 (passwordStrength) + 5 (LoginPage) + 6 (RegisterPage) = 19; existing 29 still green after AppRouter test reshape.
- `bun run build` clean (5.66s) — LoginPage chunk 1.57 kB, RegisterPage chunk 3.28 kB, shared `auth` chunk 88.96 kB (zod + react-hook-form + @hookform/resolvers); `bunx tsc --noEmit -p tsconfig.app.json` exits 0 errors.

## Task Commits

Each task followed TDD RED-GREEN and committed atomically:

1. **Task 1 RED — failing tests for passwordStrength scorer** — `c56992f` (test)
2. **Task 1 GREEN — passwordStrength + AuthCard + PasswordStrengthMeter + FormFieldRow** — `a93055c` (feat)
3. **Task 2 RED — failing tests for LoginPage + RegisterPage** — `26af6df` (test)
4. **Task 2 GREEN — wire LoginPage + RegisterPage with react-hook-form + zod + AuthCard** — `a2ee586` (feat)

**Plan metadata:** *to be added in final commit*

## Files Created/Modified

- `frontend/src/lib/passwordStrength.ts` — `scorePassword(password): PasswordStrengthResult`; pure 0..4 zxcvbn-style heuristic; const LABELS + HINTS records keyed by score
- `frontend/src/components/auth/AuthCard.tsx` — `AuthCard({ title, subtitle, children, footer })`; flex viewport-center, `<Card max-w-md px-8 py-8 shadow-lg>`, h1 text-2xl semibold, muted subtitle, hairline footer
- `frontend/src/components/auth/PasswordStrengthMeter.tsx` — `PasswordStrengthMeter({ password })`; 4-segment bar with `colorFor(score)` red→amber→lime→green; data-testid + data-score attributes
- `frontend/src/components/forms/FormField.tsx` — `FormFieldRow<T extends FieldValues>({ control, name, label, type, autoComplete, placeholder, rightSlot })`; wraps shadcn `<FormField>` + `<FormItem>` + `<FormLabel>` + `<FormControl>` + `<Input>` + `<FormMessage>`
- `frontend/src/routes/LoginPage.tsx` — replaced placeholder with full impl; useForm<LoginInput> + zodResolver(loginSchema); two FormFieldRow rows (email, password); generic-error Alert; sign-in / register / forgot-password footer
- `frontend/src/routes/RegisterPage.tsx` — replaced placeholder with full impl; useForm<RegisterInput> + zodResolver(registerSchema); three FormFieldRow rows + bespoke FormField for terms checkbox; PasswordStrengthMeter in `rightSlot` of password field; sign-in footer
- `frontend/src/tests/lib/passwordStrength.test.ts` — 8 boundary tests covering every band of the scorer
- `frontend/src/tests/routes/LoginPage.test.tsx` — 5 tests: render, validation, happy-path, 401 generic, 429 retry-after countdown
- `frontend/src/tests/routes/RegisterPage.test.tsx` — 6 tests: render, password-mismatch, terms-required, strength-meter-on-input, happy-path, 422 generic
- `frontend/src/tests/routes/AppRouter.test.tsx` — Rule-1 fix: 4 anonymous-redirect/public-route assertions migrated from placeholder text matching to heading-role queries (`Sign in` / `Create account`)

## Decisions Made

- **Pure scorer, no external lib** — zxcvbn the library would add ~400 KB gzip; for a v1.2 strength hint the cumulative heuristic is sufficient and zero-cost. The pure-function shape lets us swap to zxcvbn later without touching the meter component (only the underlying scorePassword internals).
- **`Password1` scores 3, not 2 (plan-doc band rederivation)** — plan body suggested score 2-3; locked banding gives 3 (length>=8 +1, mixed +1, digit +1 = 3, no symbol, no length>=16). Tests assert the actual computed value (3), not the plan's loose hint. This avoids plan/code drift and keeps the test suite a binding contract.
- **Native checkbox vs shadcn Checkbox** — shadcn-cli was never run to add `<Checkbox>`; the components/ui directory has no checkbox.tsx. Using native `<input type="checkbox">` keeps this plan zero-dep. RegisterPage's FormField wraps it via Controller so `field.value` and `field.onChange` flow normally; FormItem wires the FormLabel's htmlFor automatically.
- **RateLimitError BEFORE ApiClientError in catch chain** — RateLimitError extends ApiClientError; if checked second, the rate-limit branch is unreachable. Locked the order in both pages and exposed it as a pattern for future auth-touching surfaces.
- **Strength meter is conditional on password.length > 0** — first-render shows clean Card without a "Very weak" buzzer next to the empty password field. Test asserts the meter appears AFTER first keystroke. Renders are cheap; the optimization is UX-driven (no false-positive alarm before user types anything).
- **AppRouter test migrated to heading-role queries** — placeholder text was a Plan 14-04 transient. Heading-role queries survive any in-page text reshuffle (e.g., Plan 14-08 might add a "Welcome to WhisperX!" hero above the form); they assert the page-identity contract (which page rendered) rather than a specific copy snippet.
- **Bespoke FormField for terms checkbox (deliberate non-DRY)** — checkbox row layout (input + label + error stacked) differs from text-input row (label above input). FormFieldRow stays text-input-only and clean. RegisterPage's one bespoke FormField call is the deliberate exception, not a missed DRY opportunity. If a future plan adds three checkboxes to a settings page, that's the trigger to extract a `FormCheckboxRow` primitive.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] AppRouter.test.tsx assertions migrated from placeholder-text to heading-role queries**

- **Found during:** Task 2 GREEN verify (`bun run test` full suite)
- **Issue:** 4 of 5 AppRouter.test.tsx tests asserted literal text `LoginPage placeholder` and `RegisterPage placeholder`; this plan replaces those placeholders with real impls, so the literal strings no longer exist on the rendered page. 4 tests broke after Task 2 GREEN.
- **Fix:** Replaced `findByText(/LoginPage placeholder/i)` with `findByRole('heading', { name: /sign in/i, level: 1 })` (and analogous for RegisterPage's `Create account`). Same observable contract (anonymous redirected to /login renders the LoginPage; public /register renders the RegisterPage); more robust assertion that survives copy reshuffles.
- **Files modified:** `frontend/src/tests/routes/AppRouter.test.tsx`
- **Verification:** Full `bun run test` exits 0 (48/48 pass; was 44 fail-pass + 4 broken before this fix).
- **Committed in:** `a2ee586` (Task 2 GREEN commit)

**2. [Rule 1 - Bug] RegisterPage termsAccepted error-message assertion narrowed**

- **Found during:** Task 2 GREEN initial test run
- **Issue:** Test `blocks submit when terms not accepted` asserted `findByText(/accept the terms/i)`; this matched BOTH the FormLabel ("I accept the terms of service.") AND the FormMessage ("You must accept the terms to continue") — multi-match throws.
- **Fix:** Tightened pattern to `/must accept the terms/i` which uniquely matches the error message and not the label.
- **Files modified:** `frontend/src/tests/routes/RegisterPage.test.tsx`
- **Verification:** RegisterPage suite 6/6 pass.
- **Committed in:** `a2ee586` (Task 2 GREEN commit)

---

**Total deviations:** 2 auto-fixed (both Rule 1 — test contract bugs surfaced by the plan's own implementation completing). No architectural changes; no scope creep. Both fixes are test-file-only; production page contract matches the plan exactly.

## Issues Encountered

- LF→CRLF git warnings on commit (Windows checkout, `core.autocrlf=true`) — cosmetic.

## User Setup Required

None — no external service configuration required. Pages are reachable in dev at `http://localhost:5173/ui/login` and `http://localhost:5173/ui/register` once `bun run dev` runs; production serves the same paths via vite base + FastAPI static mount.

## Next Phase Readiness

- **Plan 14-06 (KeysDashboardPage / UsageDashboardPage)** can `import { FormFieldRow } from '@/components/forms/FormField'` for the create-key dialog name input. Logout button calls `useAuthStore.getState().logout()` (Plan 14-03 ships the action); BroadcastChannel sync handles cross-tab. Dashboards live in AppShell — they do NOT use AuthCard.
- **Plan 14-07 (regression coverage)** has the page-render harness in place — `MemoryRouter` + `LoginPage`/`RegisterPage` direct mount + `useAuthStore.setState({ user: null })` reset is the test rig. No additional setup needed for auth-page regression tests.
- **Phase 13 backend contract verified end-to-end via MSW** — `auth.handlers.ts` returns 200 on valid login, 401 on `password === 'wrong'`, 201 on register, 204 on logout. Plan 14-05 happy-path tests assert the full handler→apiClient→authStore→Page chain. Real backend (Phase 13 v1.2 build) and these mocks share the same response shape (`{ user_id, plan_tier }`); zero contract drift.
- **`/frontend-design` UI-13 bar applied:** AuthCard (Card-on-page max-w-md p-8 shadow-lg), text-2xl semibold title with muted subtitle, gap-4 field rhythm, hairline border-t footer, focus-visible ring on inputs (shadcn default). No further polish needed for v1.2; v1.3 may add brand color, hero illustration, or social-auth options.

---
*Phase: 14-atomic-frontend-cutover*
*Completed: 2026-04-29*

## Self-Check: PASSED

All 9 artifacts (passwordStrength.ts + AuthCard.tsx + PasswordStrengthMeter.tsx + FormFieldRow.tsx + LoginPage.tsx + RegisterPage.tsx + 3 test files) plus SUMMARY.md present on disk. All 4 task commits (`c56992f`, `a93055c`, `26af6df`, `a2ee586`) present in git log. TDD RED-GREEN gate sequence verified: `test(14-05) passwordStrength` (c56992f) → `feat(14-05) impl` (a93055c) → `test(14-05) pages` (26af6df) → `feat(14-05) wire pages` (a2ee586). Full `bun run test` exits 0 (48/48 pass — was 29 before this plan, +19 new tests). `bunx tsc --noEmit -p tsconfig.app.json` exits 0 errors. `bun run build` clean (5.66s, LoginPage 1.57kB / RegisterPage 3.28kB / auth shared chunk 88.96kB). Acceptance grep gates all pass: useAuthStore ≥2 (4 actual), loginSchema ≥1 (2), registerSchema ≥1 (2), PasswordStrengthMeter ≥1 (3), AuthCard ≥2 (8), FormFieldRow ≥4 (9), `fetch(` =0 (✓), isSubmitting ≥2 (4), nested-if =0 (✓).
