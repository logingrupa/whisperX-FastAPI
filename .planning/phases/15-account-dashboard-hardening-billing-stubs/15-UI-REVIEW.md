---
phase: 15
slug: account-dashboard-hardening-billing-stubs
audited: 2026-04-29
baseline: 15-UI-SPEC.md (LOCKED)
screenshots: not captured (no dev server detected on ports 3000 / 5173)
scores:
  copywriting: 4
  visuals: 3
  color: 4
  typography: 4
  spacing: 3
  experience_design: 4
  overall: 22
---

# Phase 15 — UI Review

**Audited:** 2026-04-29
**Baseline:** 15-UI-SPEC.md (LOCKED design contract)
**Screenshots:** not captured (no dev server detected on ports 3000 / 5173)

---

## Pillar Scores

| Pillar | Score | Key Finding |
|--------|-------|-------------|
| 1. Copywriting | 4/4 | All 35+ locked strings match spec verbatim; no generic CTAs |
| 2. Visuals | 3/4 | Success Alert uses `AlertDescription` for `Thanks!` heading instead of `AlertTitle`; skeleton gap correct |
| 3. Color | 4/4 | 60/30/10 intact; `bg-primary` reserved exclusively to Plan CTA (via Button default); destructive gated to danger zone only |
| 4. Typography | 4/4 | Exactly 3 sizes (text-sm/text-lg/text-2xl) + 2 weights (font-medium/font-semibold); within spec budget |
| 5. Spacing | 3/4 | One off-scale value: `gap-3` on Profile card `<dl>` (line 154) — spec mandates multiples of 4 only |
| 6. Experience Design | 4/4 | Skeleton loading, destructive error alerts, disabled gates, retry button, autoFocus, autoComplete=off all present |

**Overall: 22/24**

---

## Top 3 Priority Fixes

1. **`gap-3` in Profile card `<dl>` grid** — Breaks 8-point spacing contract; visual inconsistency with sibling card internal spacing — Change `gap-3` to `gap-2` (8px, matches form-field label-to-input spec) or `gap-4` (16px, matches card internal gap) at `AccountPage.tsx:154`

2. **Success Alert uses `AlertDescription` for `Thanks!` heading** — Semantic mismatch: `AlertTitle` exists in the design system for heading slots inside `Alert`; using a `<p className="font-medium">` inside `AlertDescription` is visually adequate but bypasses the accessibility heading role that `AlertTitle` provides — Replace the inner `<p className="font-medium text-foreground">Thanks!</p>` with `<AlertTitle>Thanks!</AlertTitle>` + a separate `<AlertDescription>` for the body copy at `UpgradeInterestDialog.tsx:116-120`

3. **`LogoutAllDialog` cancel button does not reset error on re-open via Escape** — The `handleOpenChange` clears `error` only when `next === false`, but the cancel `<Button>` calls `handleOpenChange(false)` directly while Escape triggers Radix's `onOpenChange(false)` via the same handler. Both paths are identical — this is actually correct. However, re-opening the dialog after a `Could not sign out` error leaves the error state cleared (correctly) but the button label reverts without any visual "cleared" feedback. Minor polish only.

---

## Detailed Findings

### Pillar 1: Copywriting (4/4)

All spec-locked strings verified verbatim against implementation:

**AccountPage (`frontend/src/routes/AccountPage.tsx`):**
- Page heading `Account` — line 149 PASS
- Profile card heading `Profile` — line 153 PASS
- Email label `Email` — line 155 PASS
- Plan label `Plan` — line 157 PASS
- Plan card heading `Plan` — line 173 PASS
- All 4 plan-tier body strings (free/trial/pro/team) — lines 52-59 PASS (verbatim to character)
- Plan fallback `Plan details unavailable.` — line 62 PASS
- Plan CTA `Upgrade to Pro` — line 177 PASS
- Danger zone heading `Danger zone` — line 184 PASS (lowercase "zone" matches spec)
- Sign-out-all helper text — lines 188-190 PASS (verbatim)
- Sign-out-all button `Sign out of all devices` — line 196 PASS
- Delete-account helper text — lines 202-204 PASS (verbatim)
- Delete-account button `Delete account` — line 210 PASS
- Hydration error `Could not load account.` — lines 102, 105 PASS
- Hydration retry `Reload account` — line 123 PASS
- Password reset hint + mailto link — lines 162-166 PASS

**UpgradeInterestDialog (`frontend/src/components/dashboard/UpgradeInterestDialog.tsx`):**
- Title `Upgrade to Pro` — line 109 PASS
- Description — line 111 PASS (verbatim)
- Textarea label `What do you want from Pro? — optional` — line 126 PASS
- Placeholder `Diarization on long files, faster turnaround, larger uploads…` — line 133 PASS
- Submit idle `Send` / submitting `Sending…` — line 149 PASS
- Cancel `No thanks` — line 146 PASS
- Success heading `Thanks!` — line 118 PASS (as `<p>` — see Visuals note)
- Success body — line 119 PASS (verbatim)
- Error 429 — line 86 PASS (template matches spec)
- Error other `Could not send. Try again.` — lines 91, 93 PASS

**DeleteAccountDialog (`frontend/src/components/dashboard/DeleteAccountDialog.tsx`):**
- Title `Delete account?` — line 110 PASS
- Description — lines 112-114 PASS (verbatim)
- Email label `Type your email to confirm: {userEmail}` — line 118 PASS
- Placeholder `you@example.com` — line 125 PASS
- Confirm idle `Delete account` / submitting `Deleting…` — line 146 PASS
- Cancel `Keep account` — line 139 PASS
- Error 400 `Confirmation email does not match.` — line 94 PASS
- Error 429 — line 90 PASS
- Error other `Could not delete account. Try again.` — lines 95, 98 PASS

**LogoutAllDialog (`frontend/src/components/dashboard/LogoutAllDialog.tsx`):**
- Title `Sign out of all devices?` — line 74 PASS
- Description — lines 76-78 PASS (verbatim including em dash)
- Confirm idle `Sign out everywhere` / submitting `Signing out…` — line 95 PASS
- Cancel `Stay signed in` — line 87 PASS
- Error 429 `Rate limited. Try again in {N}s.` — line 54 PASS
- Error other `Could not sign out. Try again.` — lines 56, 58 PASS

No generic labels (`Cancel`, `OK`, `Submit`, `Save`) found in any Phase 15 file.

---

### Pillar 2: Visuals (3/4)

**Structural compliance:**
- Three-card layout (Profile / Plan / Danger Zone) matches spec `§116-139` — PASS
- `max-w-2xl mx-auto` wrapper present on all render branches (ready/loading/error) — PASS
- Danger Zone card `border-destructive/40` secondary focal point — line 183 PASS
- Plan card has sole `bg-primary` CTA via `<Button>` default variant — PASS
- Skeleton state uses 3 `SkeletonCard` components with `bg-muted` placeholder lines — lines 135-137 PASS (no "Loading…" text per spec §253)
- `<dl>` grid for Profile email/plan fields — readable two-column layout on `≥ sm` — PASS
- DialogFooter uses shadcn `flex flex-col-reverse gap-2 sm:flex-row sm:justify-end` — verified from `dialog.tsx:96` — PASS

**Minor issue:**
- `UpgradeInterestDialog.tsx:116-120`: Success Alert uses `<AlertDescription>` wrapping two `<p>` tags (one styled with `font-medium text-foreground` as the heading). Spec §173 says `heading Thanks!, body …`. The shadcn `<Alert>` has a dedicated `<AlertTitle>` slot that renders with semantic heading styling and appropriate spacing. The current implementation renders correctly visually (the `font-medium` paragraph is visually distinct), but misses the semantic `AlertTitle` component. This is a minor deviation — copy is correct, visual weight is approximated, but the component contract is not fully honored. Accessibility impact is low (Alert is not a heading landmark), but parity with shadcn conventions is off.

---

### Pillar 3: Color (4/4)

**60/30/10 split verified:**
- Dominant (60%) `bg-background` / `oklch(1 0 0)` white — page wraps and dialog content backgrounds via shadcn defaults — PASS
- Secondary (30%) `bg-card` / `bg-muted` — card surfaces (Plan/Profile/Danger Zone `<Card>`), skeleton lines (`bg-muted`) — PASS
- Accent (10%) `bg-primary` — zero explicit `bg-primary` class in any Phase 15 file; accent delivered exclusively via `<Button>` default variant (which resolves to `bg-primary text-primary-foreground` at render) on the Plan card CTA only — PASS

**Reserved-for lists honored:**
- `bg-primary` (sole): Plan card "Upgrade to Pro" Button — PASS
- `bg-destructive` / `text-destructive` / `border-destructive`: Danger Zone button variants (lines 192, 206), danger zone heading (line 184), danger zone card border (line 183), error Alerts across all 3 dialogs and AccountPage — PASS
- No hardcoded hex or `rgb()` values found in any Phase 15 file — PASS

**Badge tier map:**
- `free` → `secondary`, `trial` → `outline`, `pro` → `default`, `team` → `default` — `PLAN_BADGE_VARIANT` record at lines 34-42 PASS

**Registry audit:** shadcn initialized; 0 third-party registries declared in UI-SPEC. No vetting gate required. Clean.

---

### Pillar 4: Typography (4/4)

**Sizes found across 4 Phase 15 files:**
- `text-sm` (14px) — body copy, form labels, description text
- `text-lg` (18px) — card headings (Profile, Plan, Danger zone)
- `text-2xl` (24px) — page heading "Account"

3 sizes total. Spec allows 3 sizes (14/18/24). No `text-xs`, `text-base`, `text-xl`, `text-3xl` found. PASS

**Weights found:**
- `font-medium` — `<dt>` labels in Profile `<dl>`, "Thanks!" paragraph in success Alert
- `font-semibold` — card headings, page heading

2 weights. Spec allows 2 weights (400/600); `font-medium` (500) is shadcn primitive inheritance on Label/Button — accepted per spec §73. No `font-bold`, `font-normal`, `font-light` applied directly. PASS

**Line-height:** No explicit `leading-` overrides in Phase 15 files; body defaults to Tailwind `leading-normal` (1.5), headings inherit `leading-none` / `leading-tight` from shadcn Card / Dialog primitives. Consistent with spec. PASS

---

### Pillar 5: Spacing (3/4)

**Declared 8-point scale (4/8/16/24/32/48):**

Tailwind equivalents: `gap-1`/`p-1` (4px), `gap-2`/`p-2` (8px), `gap-4`/`p-4` (16px), `gap-6`/`p-6` (24px), `gap-8`/`p-8` (32px), `p-12` (48px).

**Spacing audit results:**

| Location | Class | px | Status |
|----------|-------|----|--------|
| Outer wrapper (all branches) | `gap-4 md:gap-6` | 16px / 24px | PASS |
| Card internal gap | `gap-4 p-6` on each `<Card>` | 16px / 24px | PASS — gap-4 overrides Card default gap-6 via tailwind-merge |
| Danger zone rows | `gap-4 md:gap-4` | 16px | PASS |
| UpgradeInterestDialog form field stack | `gap-2` | 8px | PASS — matches spec §52 |
| UpgradeInterestDialog success Alert | `my-2` | 8px | PASS — on-scale |
| UpgradeInterestDialog form wrapper | `my-4` | 16px | PASS |
| UpgradeInterestDialog error Alert | `mb-4` | 16px | PASS |
| DeleteAccountDialog form field | `my-6` | 24px | PASS |
| DeleteAccountDialog error Alert | `mb-4` | 16px | PASS |
| LogoutAllDialog error Alert | `mt-4` | 16px | PASS |
| LogoutAllDialog DialogFooter | `mt-4` | 16px | PASS |
| **Profile card `<dl>` grid** | **`gap-3`** | **12px** | **FAIL — off-scale** |

**Off-scale value:**
- `AccountPage.tsx:154`: `<dl className="grid grid-cols-1 gap-3 sm:grid-cols-[6rem_1fr]">` — `gap-3` = 12px. Not on the declared 8-point scale (closest on-scale values are `gap-2`=8px or `gap-4`=16px). Spec §38-54 declares no exceptions. This is the single violation.

**Arbitrary values:**
- `UpgradeInterestDialog.tsx:37`: `focus-visible:ring-[3px]` — this is identical to the shadcn `input.tsx` canonical token (confirmed by reading `input.tsx:12`). Not a custom arbitrary value — it is copy-pasted verbatim from the locked design system primitive. Not flagged.

**Card native `py-6` + passed `p-6`:** `cn()` uses `tailwind-merge` (confirmed at `utils.ts:4`) — `p-6` in className correctly overrides `py-6` from the Card base. No padding conflict. PASS.

**Fix:** Change `gap-3` → `gap-2` (tighter, 8px) or `gap-4` (wider, 16px) based on visual preference. Given the `<dl>` renders label + value pairs where visual density matters, `gap-2` is the better on-scale fit.

---

### Pillar 6: Experience Design (4/4)

**Loading state:**
- 3 `SkeletonCard` components (one per final card) rendered during `summary === null && error === null` — lines 135-137 PASS
- No "Loading…" text or spinner — PASS per spec §253

**Error state:**
- AccountPage hydration error: `<Alert variant="destructive">` + `<Button variant="outline" size="sm">Reload account</Button>` — lines 117-126 PASS
- All 3 dialogs: `<Alert variant="destructive">` inline above action button on error — PASS
- Subtype-first error chain (RateLimitError before ApiClientError before generic) in AccountPage, UpgradeInterestDialog, DeleteAccountDialog, LogoutAllDialog — PASS

**Disabled states:**
- UpgradeInterestDialog: textarea `disabled={submitting}`, submit `disabled={submitting}` — lines 135, 148 PASS
- DeleteAccountDialog: input `disabled={submitting}`, confirm `disabled={!isMatched || submitting}` — lines 129, 144 PASS (gate correct: disabled when empty or mismatch; enabled only on case-insensitive match)
- LogoutAllDialog: confirm `disabled={submitting}` — line 93 PASS

**Destructive confirmation gates:**
- Delete account: type-email match gate (`isMatched` with `userEmail.length > 0` defensive guard) — lines 55-57 PASS
- Logout all: single-confirm pattern (mirrors RevokeKeyDialog) — PASS
- Both: navigate('/login', { replace: true }) after success — PASS

**Accessibility:**
- `autoFocus` on textarea (UpgradeInterestDialog:136) and email input (DeleteAccountDialog:126) — PASS
- `autoComplete="off"` + `spellCheck={false}` on delete confirmation email input — line 127-128 PASS
- `aria-label` not needed on text-labeled buttons (spec §405) — PASS
- Radix `Dialog` inherits focus trap, Escape key, restored focus, `role="dialog"`, `aria-labelledby`, `aria-describedby` — PASS
- DialogFooter `flex-col-reverse sm:flex-row` — verified from `dialog.tsx:96` — mobile bottom confirm, desktop right confirm — PASS

**501 stub swallow:**
- UpgradeInterestDialog `err.status === 501` → `setSuccess(true)` — line 87-89 PASS (T-15-07)

**Cross-tab logout:**
- Both DeleteAccountDialog and LogoutAllDialog call `logoutLocal()` (not `logout()`) after successful server-side session clear — avoids 401 race on stale cookie (WR-02 mitigation) — PASS

**Empty state:** AccountPage has no empty state by design (authenticated user always has a profile) — spec §255 acknowledges this; falls through to error state. PASS.

---

## Registry Safety

shadcn initialized. 0 third-party registries declared in UI-SPEC §369-375. Registry vetting gate not triggered.

---

## Files Audited

- `frontend/src/routes/AccountPage.tsx` — primary audit target (224 lines)
- `frontend/src/components/dashboard/UpgradeInterestDialog.tsx` — dialog audit target (157 lines)
- `frontend/src/components/dashboard/DeleteAccountDialog.tsx` — dialog audit target (153 lines)
- `frontend/src/components/dashboard/LogoutAllDialog.tsx` — dialog audit target (101 lines)
- `frontend/src/index.css` — OKLCH token palette (58 lines)
- `frontend/components.json` — shadcn config (22 lines)
- `frontend/src/routes/KeysDashboardPage.tsx` — sibling parity comparison (164 lines)
- `frontend/src/components/dashboard/CreateKeyDialog.tsx` — sibling dialog comparison (150 lines)
- `frontend/src/components/dashboard/RevokeKeyDialog.tsx` — sibling destructive comparison (97 lines)
- `frontend/src/components/ui/card.tsx` — Card base class analysis (tailwind-merge conflict check)
- `frontend/src/components/ui/input.tsx` — Input ring token comparison (ring-[3px] canonical)
- `frontend/src/components/ui/dialog.tsx` — DialogFooter responsive stacking verification
- `frontend/src/lib/utils.ts` — tailwind-merge confirmation
- `.planning/phases/15-account-dashboard-hardening-billing-stubs/15-UI-SPEC.md` — design contract (437 lines)
- `.planning/phases/15-account-dashboard-hardening-billing-stubs/15-CONTEXT.md` — locked decisions
- `.planning/phases/15-account-dashboard-hardening-billing-stubs/15-06-SUMMARY.md` — execution summary
