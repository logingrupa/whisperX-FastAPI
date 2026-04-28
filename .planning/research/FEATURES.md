# Feature Research — WhisperX v1.2 SaaS Auth + API Keys + Billing-Ready

**Domain:** Multi-tenant SaaS — auth, API key management, free-tier rate limit, Stripe-ready billing schema
**Researched:** 2026-04-29
**Confidence:** HIGH (patterns well-established across Linear, Vercel, Stripe Dashboard, Cloudflare, GitHub, Resend, OpenAI Platform)

## Scope Note

Research covers ONLY auth/billing UX for v1.2. Existing transcription/upload features out of scope. Caveman mode for content (token economy).

---

## 1. Registration UX

### Table Stakes

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Single-page form, email + password | 2026 norm. Multi-step feels enterprise/heavy. Linear/Vercel/Resend all single-page. | S | One screen, submit, redirect to dashboard |
| Inline validation on blur | Instant feedback. No "submit then read errors" anti-pattern. | S | Use react-hook-form + zod |
| Password min 8 chars, mixed | OWASP 2024 baseline. Reject obvious weak (`password123`). | S | Server-side enforce, client-side hint |
| "Already have account? Login" link | Wrong-page recovery. | S | Footer link |
| Show password toggle (eye icon) | Mobile typing accuracy. Universal expectation. | S | shadcn input + lucide Eye/EyeOff |
| ToS + Privacy checkbox OR inline acceptance text | Legal cover. "By signing up you agree to..." inline = lighter than checkbox. | S | Inline link text under submit button — Vercel pattern |
| Email format check client-side | Catch typos before round-trip. | S | zod email() |
| Submit disabled until valid | Stops noise submissions. | S | react-hook-form `formState.isValid` |
| Success state → auto-login + redirect to dashboard | No double-step. Friction kills conversion. | S | Set cookie on register, navigate |
| Generic error "registration failed" on existing email | Email enumeration prevention. | S | Don't say "email already exists" — return same response as success path with generic message OR send "if this is you, login" email (deferred) |

### Differentiators

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Real-time password strength meter | Coaching, not gating. Linear/Vercel use this. | S | zxcvbn-ts lib. Visual bar + tip text. |
| Magic-link option as alternative | Frictionless. Resend, Notion, Slack offer this. | M | Defer — needs SMTP. v1.3. |
| Auto-detect timezone for usage charts | Honest hour boundaries on rate limits. | S | `Intl.DateTimeFormat().resolvedOptions().timeZone` at register |

### Anti-Features

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Multi-step wizard (name → email → password → preferences) | "Looks professional" | Conversion killer. Each step drops 20-30%. | Single page. Collect extras post-signup in dashboard. |
| Required phone number | "Anti-spam" | Privacy hostile, not effective | IP throttle + future captcha |
| Required full name at register | "Personalization" | Friction for no value at signup | Optional, collect in profile |
| Email verification BLOCKING login (v1.2) | "Anti-spam" | No SMTP available. Locks out users. | Defer to v1.3 with SMTP. Soft-warn banner only. |
| Username/handle field | Social-app pattern | API/billing doesn't need it | Email IS the identity |
| Captcha on every register | "Anti-bot" | UX friction, only enable if abuse seen | Reactive — IP throttle now, captcha v1.3 if abuse |

**Complexity:** S overall. Single component, ~200 LOC.

---

## 2. Login UX

### Table Stakes

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Email + password single form | Universal. | S | Same shape as register |
| Generic error "invalid credentials" | No user enumeration. | S | Same message wrong-email vs wrong-password |
| "Remember me" checkbox → 30d session, default 7d | User control over session length. | S | Toggles cookie maxAge. Stored on JWT claim. |
| Forgot password link | Recovery path. | S | v1.2: links `mailto:hey@logingrupa.lv` per PROJECT.md |
| "Don't have account? Register" link | Wrong-page recovery. | S | Footer |
| Show password toggle | Same as register. | S | Reuse component |
| Submit disabled while pending | Prevent double-submit. | S | react-hook-form `isSubmitting` |
| Redirect to intended page after login | Deep-link preservation. User clicks `/dashboard/keys` while logged out → after login lands there. | S | `?next=` query param OR session-stored intent |
| Rate limit feedback (429) inline | "Too many attempts, try again in X min" | S | Read `Retry-After` header |

### Differentiators

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| 2FA stub UI (settings page only, no enforcement) | Future-proof, signals security focus | M | Defer to v1.3. Place "Coming soon" disabled section. |
| Magic link alternative | Frictionless return. | M | Defer — SMTP. |
| Login activity log on dashboard | Trust signal — "last login from IP X at time Y" | S | Cheap, leverage device fingerprint already in scope |
| WebAuthn/passkey | Future-proof | L | Defer to v2. |

### Anti-Features

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Security questions | "Backup recovery" | Easily socially engineered, OWASP deprecated | Email reset only |
| SMS 2FA | "Security" | SIM swap attacks, SMS unreliable, costs money | TOTP/WebAuthn (deferred v1.3+) |
| CAPTCHA always-on | "Anti-bot" | UX friction | Only after N failed attempts (already covered by IP throttle) |
| Force password rotation every 90 days | "Compliance theater" | NIST 2017 explicitly says don't | Long passphrase + breach detection |
| Persistent session forever | "Convenience" | Stolen device = stolen account forever | 7d sliding (default) / 30d (remember me) |

**Complexity:** S overall. Component, ~150 LOC.

---

## 3. Session Management

### Table Stakes

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| HttpOnly + Secure + SameSite=Lax cookie session | XSS protection. localStorage JWT = security anti-pattern in 2026. | S | Already in PROJECT.md decision |
| Sliding expiration (7d default, refresh on use) | "Active users stay logged in" expectation | S | Refresh cookie on each authenticated request |
| Logout button → clear cookie, server invalidate | Universal. | S | POST `/api/auth/logout`, delete cookie |
| Auto-redirect to login on 401 | Session expiry handling. | S | Axios/fetch interceptor → navigate('/login') |
| CSRF token for state-changing requests | Mandatory with cookie auth. | M | Double-submit cookie pattern. Token in meta tag + header. |
| Session survives page refresh | Universal SPA expectation. | S | Cookie + bootstrap GET `/api/auth/me` on app mount |

### Differentiators

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| "Logout all devices" button | Stolen device recovery. Linear/GitHub have this. | M | Bump `token_version` on user, JWTs check version |
| Active sessions list (browser, IP, last seen) | Transparency, security trust. | M | Use device fingerprint table already in scope |
| Refresh token rotation | Long-lived auth without re-login | L | DEFER — adds two-token complexity. 7d cookie sufficient for v1.2. |

### Anti-Features

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| localStorage JWT | "It's stateless" | XSS = full account compromise. 2026 consensus is HttpOnly cookie. | HttpOnly cookie (already chosen) |
| Separate access + refresh tokens via JS | "OAuth pattern" | Cookie session does same job simpler for browser auth | Single cookie session for browser, raw API key for external |
| Sliding session forever (no max) | "UX" | Stolen cookie = forever access | Hard cap 30d even with sliding |
| Session in URL (`?session=...`) | Anything | Leaks via referrer, logs, screenshots | Cookie only |

**Complexity:** M overall (CSRF is the chunk). ~300 LOC backend + interceptors.

---

## 4. API Key Management UI

### Table Stakes

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| List view: name, prefix, created, last used, status | Stripe/OpenAI/Vercel exact pattern. | S | Table with shadcn data-table |
| "Create key" button → modal with name input | Universal. | S | shadcn Dialog |
| Show-once full key in modal with COPY button | Plaintext stored is security antipattern. Show once or never again. | S | Big monospaced key, copy-to-clipboard, "I've saved it" confirm before close |
| Key prefix shown in list (`whsk_xxxx...`) | Identification without revealing secret. | S | First 8 chars + ellipsis |
| Last used timestamp + IP | "Is this still in use?" Decision support for revoke. | S | Update on every API call (sampled) |
| Revoke with confirm dialog | Destructive, needs friction. | S | shadcn AlertDialog. Type the name OR explicit "Revoke" button. |
| Revoked keys disappear (or show greyed with revoke timestamp) | Audit trail vs cleanliness. | S | Soft-delete recommended — show 30d then hard-delete |
| Empty state with "Create your first key" CTA | Onboarding. | S | shadcn empty state pattern |
| Copy success toast | Feedback that copy worked. | S | Sonner / shadcn toast |

### Differentiators

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Per-key scopes (read, write, transcribe) | Defense in depth. PROJECT says "scopes-ready". | M | UI: checkboxes in create modal. Backend already prepared per PROJECT.md |
| Per-key rate limit override | Power users. | L | DEFER — v1.3 |
| Per-key expiration date (optional) | Rotate easily. GitHub PAT pattern. | M | Date picker in create modal. Background job revokes expired. |
| Last used IP + user agent | Security audit. | S | Already collected via device fingerprint |
| Per-key usage chart | Visibility on which keys are hot. | M | Defer to v1.3 alongside billing dashboard |
| "Regenerate" button | Faster than revoke + create | S | DEFER — same as revoke + create. Don't add. |

### Anti-Features

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Show full key after creation (in list) | "Convenience" | Plaintext storage = breach catastrophe. Hash on create. | Show-once at create, hash storage |
| Edit key name inline | "Convenience" | Adds inline-edit complexity for tiny value | Revoke + recreate, or modal edit |
| Email-on-key-creation | "Security" | No SMTP. Self-action, low value. | Visible in dashboard, no email |
| Unlimited keys per user | "Power user" | Abuse vector, DB bloat | Soft cap 25 per user (matches Stripe) |
| Plaintext key in URL/email/log | Anywhere | Leak vector | Hash-only storage, show-once display |

**Complexity:** M overall. ~500 LOC (table + modal + revoke flow + clipboard).

---

## 5. Free Tier UX

### Table Stakes

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Quota counter visible on dashboard | "How much do I have left?" universal SaaS question. | S | "3 of 5 requests this hour" — top-right or banner |
| Quota counter on upload screen | Decision support before action. | S | "4 of 5 requests left this hour" near submit |
| Trial countdown banner ("5 days left in trial") | Awareness, conversion driver. | S | Soft banner, dismissible per session |
| Reset time visible ("resets in 23 minutes") | Reduce confusion. | S | Live countdown — `setInterval` |
| Upgrade CTA (placeholder) when near/over limit | Conversion. v1.2 stub: button → "Coming soon" toast. | S | "Upgrade to Pro" button, disabled state with tooltip "Pro launching soon" |
| Free-tier limit boundaries documented | "What CAN I do?" expectation. | S | Help/FAQ link or inline tooltip explaining 5/hr, file size, duration, model caps |
| Soft-warn at 80% used | Heads-up before block. | S | Color shift yellow → red |

### Differentiators

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| "Why upgrade?" comparison table | Conversion clarity. Stripe/Resend pattern. | S | Static table, free vs Pro |
| Email on trial expiry | Re-engagement. | M | DEFER — no SMTP |
| Usage graph (hourly bar chart, 24h window) | Pattern recognition. | M | recharts or visx, simple bar chart |
| Trial extension on email engagement | Goodwill. | M | DEFER — no SMTP |

### Anti-Features

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Aggressive paywall ("UPGRADE NOW" modal blocking app) | "Conversion" | Hostile, drives churn. Linear/Vercel never do this. | Ambient banner, never blocks current task |
| Hide quota until exceeded | "Cleaner UI" | "Surprise! You're locked out" frustrating | Always-visible counter |
| Reset quota on upgrade-button-click | "Conversion bait" | Erodes trust | Honest counter |
| Per-second quota refresh animation | "Slick" | Annoying. Read on action only. | Update on submit / page focus |
| Trial extension by email asking | "Growth hack" | Friction, dark pattern | Honest fixed trial |

**Complexity:** S overall for v1.2 (numbers + banner). Charts deferred to v1.3.

---

## 6. Rate Limit Communication (429 UX)

### Table Stakes

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Inline error on form submit, not toast | Action context. | S | Error region under submit button |
| "Try again in X seconds/minutes" with live countdown | Actionable info. | S | Read `Retry-After`, format human-readable |
| Different message for free-tier-exceeded vs IP-throttle | Different remedies. | S | Free-tier → "Upgrade to Pro". IP-throttle → "Slow down, try in X" |
| Disable submit button during retry-after window | Prevent retry storms. | S | Tied to countdown |
| 429 response includes machine-readable JSON | API consumers need it. | S | `{error: "rate_limited", retry_after_seconds: 60, limit_type: "free_tier_hourly"}` |
| Don't reset countdown on retry | Honest behavior. | S | Server is source of truth |

### Differentiators

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Queue position display ("you're #3 in queue") | If queueing implemented (v1.3) | M | DEFER — needs queue worker, in v1.3 backlog per PROJECT.md |
| Predictive "You'll hit limit in ~2 requests" warning | Proactive coaching | M | Compute from current rate vs reset window |
| Auto-retry with backoff on 429 (client-side) | Resilience. v1.1 already does this for upload. | S | Reuse existing exponential backoff hook |

### Anti-Features

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Silent failure on rate limit | "Don't bother user" | Confusing, mistaken-as-bug | Clear inline error |
| Generic "request failed" on 429 | "Simpler error handling" | Drives support tickets | Specific 429 handler |
| Auto-retry forever | "Resilience" | Compounds the rate limit problem | Bounded retries with max 3 (already in v1.1 pattern) |
| Hide rate limit in API docs | "Simpler" | Devs hate surprises | Document limits + headers prominently |

**Complexity:** S overall. Reuse v1.1 retry pattern.

---

## 7. Account Dashboard

### Table Stakes (v1.2)

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Profile section: email (read-only), created date | Identity clarity. | S | Static read |
| Change password form | Universal. | S | Old password + new password + confirm |
| Logout button | Universal. | S | Top-right user menu |
| API keys section (covers section 4) | Per scope. | M | Already covered |
| Usage section (covers section 5) | Per scope. | S | Already covered |
| Delete account flow with confirm | GDPR + trust. PROJECT.md `DELETE /api/account/data`. | M | Type email to confirm, two-step. Hard delete or soft-delete user + cascade delete tasks. |
| Plan tier display ("Free trial — 5 days left" / "Free") | "What plan am I on?" universal. | S | Card on dashboard |

### Differentiators

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Data export (JSON of tasks/transcripts) | GDPR portability + trust signal. | M | Background job, email link OR download. Defer email part — v1.2 do sync download if reasonable size. |
| Billing history section (stub) | Future-proof for Stripe v1.3. | S | Empty state "No billing history yet" placeholder |
| Active sessions list | Security transparency (overlap with section 3) | M | Same component |
| Login activity log | Trust signal | S | Already covered by device fingerprint |
| Theme toggle (light/dark) | Modern expectation, low cost with Tailwind | S | Already likely supported by shadcn defaults |

### Anti-Features

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Email change flow | "Standard feature" | Needs verification → SMTP. Footgun for v1.2. | DEFER to v1.3. Show as disabled with tooltip. |
| Profile picture upload | "Personalization" | Storage, image processing complexity for zero auth value | Gravatar or initials avatar |
| Account merge | "Power user" | Massive complexity, rare need | Don't add |
| Soft-delete with recovery period | "Safety" | Adds undelete UI complexity | 7-day grace via deleted-at column, no UI |
| One-click "delete everything" no-confirm | "Speed" | Disasters | Two-step confirm with type-to-confirm |

**Complexity:** M overall. Multi-section page, ~600 LOC.

---

## 8. Anti-Spam at Register

### Table Stakes (v1.2 per PROJECT.md)

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| IP throttle 3/hr per /24 on register, 10/hr per /24 on login | DDOS basic. PROJECT.md spec. | M | slowapi already in stack |
| Throttle response is silent (generic 429) | Don't tell attackers their fingerprint | S | No "you're throttled because /24" leak |
| Generic register response (success-shaped even if email taken) | Email enumeration prevention. | S | See section 1 |
| Device fingerprint logging | Audit, future detection | S | PROJECT.md scope: cookie + UA hash + IP /24 + device_id |
| Argon2 password hashing | OWASP. PROJECT.md. | S | argon2-cffi |

### Differentiators

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| HaveIBeenPwned check on register | Reject known breached passwords | S | k-anonymity API call, free |
| Disposable-email domain block | Reduce spam accounts | S | Public list, but cat-and-mouse — DEFER |
| Email verification (deferred per PROJECT.md) | Standard | M | DEFER to v1.3 with SMTP |
| hCaptcha on register | Anti-bot | M | DEFER to v1.3 if abuse observed (PROJECT.md confirms) |

### Anti-Features

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Visible "you're being rate-limited because IP X" | Transparency | Helps attackers iterate | Generic 429 |
| Honeypot fields | "Anti-bot" | Bots got smart, breaks accessibility | Real anti-bot (captcha later) or IP throttle |
| Block Tor/VPN at register | "Anti-abuse" | Privacy hostile, blocks legit users | Trust-but-verify with IP throttle |
| Email verification BLOCKING in v1.2 | "Anti-spam" | No SMTP. Locks legit users out. | DEFER. Soft warn only if added pre-SMTP. |
| Force email verify before first transcription | "Anti-abuse" | Same. Locks users out. | Trust-and-monitor in v1.2, harden v1.3 |

**Complexity:** M overall. slowapi config + middleware + fingerprint table.

---

## 9. CSRF UX

### Table Stakes

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Invisible to user — fully background | Universal. User never sees CSRF concept. | M | Double-submit cookie pattern |
| CSRF token bootstrap on app load | Available before first state-change | S | `<meta name="csrf-token">` injected by FastAPI on root HTML |
| Auto-refresh on stale-form 403 | "Form sat too long → submit fails" recovery | M | Axios/fetch interceptor: 403-csrf → refresh token → retry once |
| Token rotation on login/logout | Session boundary hygiene | S | New token in response after auth |
| API key requests EXEMPT from CSRF | Different threat model — bearer auth not vulnerable | S | Middleware: CSRF only required when cookie session present |

### Differentiators

None. CSRF should be invisible. Adding visible UX = doing it wrong.

### Anti-Features

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Visible CSRF error to user | "Helpful" | User can't fix it, drives confusion | Auto-refresh + retry, then generic "session expired" if still fails |
| CSRF tokens in URLs | "Easy" | Logs leak, breaks bookmarks | Header (`X-CSRF-Token`) or hidden form field only |
| Per-request token regeneration | "Max security" | Form races, double-submit fail | Per-session token sufficient |
| Skip CSRF for "safe" GET endpoints | Standard | Already standard practice | GET exempt by definition |

**Complexity:** M overall. Middleware + interceptor + bootstrap. ~150 LOC.

---

## 10. Subscription Upgrade Flow Stub

### Table Stakes (v1.2 STUB only — Stripe integration v1.3)

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| "Upgrade to Pro" button visible on dashboard + when near limit | Conversion path. | S | shadcn Button, prominent |
| Plan comparison table (Free vs Pro €5/mo) | Decision support. | S | Static table, plan_tier enum aware |
| `plan_tier` column on User model | Schema-ready (PROJECT.md). | S | Already in scope |
| `Subscription` table stub | Schema-ready. | S | Already in scope |
| `UsageEvent` log | Future billing reconciliation. | S | Already in scope |
| Click upgrade → "Pro launching soon, want notify?" modal | Honest stub. Capture interest. | S | Email opt-in stored to interest_list table |
| Stripe Checkout redirect pattern PLANNED but not wired | Architecture-ready. | M | Document `success_url` + `cancel_url` shape, no actual Stripe calls in v1.2 |

### Differentiators (v1.3 territory)

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Annual billing option (-15%) | Cash flow, retention | S | v1.3 with Stripe |
| In-app billing portal (Stripe Customer Portal redirect) | Self-serve | S | v1.3, Stripe provides this UI |
| Usage-based add-ons (extra hours pack) | Power-user revenue | M | v1.3+ |
| Team plans | B2B revenue | L | v2 |

### Anti-Features

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Fake "Subscribe" button that does nothing | "Validation testing" | Trust killer when broken | "Pro launching soon — notify me" honest stub |
| Direct Stripe widget embedded in v1.2 | "Move fast" | Half-built billing = data corruption when finished | Stub schema, defer integration to v1.3 |
| Custom payment form | "Brand control" | PCI scope nightmare | Stripe Checkout redirect (v1.3) — never touch card data |
| Annual upfront prepay only | "Cash flow" | Conversion killer | Monthly default, annual optional |
| Auto-charge on trial end without confirmation | "Dark pattern" | Refund hell, chargeback risk | Email reminder + explicit consent before charge (v1.3) |
| Multiple plan tiers at launch (Bronze/Silver/Gold/Platinum) | "Maximize ARPU" | Decision paralysis. Stripe pricing-page research → 2-3 tiers max. | Free + Pro only at v1.3 launch |

**Complexity v1.2:** S (just schema + button stub + interest modal).
**Complexity v1.3:** M (Stripe Checkout + webhooks + Customer Portal).

---

## Feature Dependencies

```
[Registration UX]
    └──requires──> [IP throttle middleware] ──requires──> [slowapi config]
    └──requires──> [Argon2 hashing]
    └──requires──> [Users table + Alembic migration]

[Login UX]
    └──requires──> [Registration] (chronologically — schema same)
    └──requires──> [Cookie session machinery]

[Session Management]
    └──requires──> [JWT secret + Argon2]
    └──requires──> [CSRF middleware]
    └──enhances──> [API key auth via dual-auth middleware]

[CSRF]
    └──requires──> [Cookie session]
    └──conflicts──> [Pure-API-key requests must be exempt]

[API Key Management UI]
    └──requires──> [Login + dashboard shell]
    └──requires──> [API key hashing + show-once flow]

[Free Tier UX]
    └──requires──> [Login (user identity)]
    └──requires──> [Rate limit middleware]
    └──requires──> [UsageEvent table]

[Rate Limit Communication]
    └──requires──> [Free Tier UX backend]
    └──enhances──> [API key requests too]

[Account Dashboard]
    └──requires──> [Login]
    └──contains──> [API Keys, Usage, Plan tier, Delete account]

[Anti-Spam at Register]
    └──requires──> [IP /24 derivation utility]
    └──enhances──> [Login (same throttle pattern)]

[Subscription Upgrade Stub]
    └──requires──> [User identity + plan_tier column]
    └──foreshadows──> [Stripe v1.3]
```

### Dependency Notes

- **Auth core (registration + login + session) is foundational:** all other v1.2 features stack on it. Must be Phase 1 of milestone.
- **CSRF couples to cookie session, exempts API key:** dual-auth middleware needs branch logic.
- **Free tier UX needs UsageEvent writes from rate limit middleware:** schema before UI.
- **API key UI requires dashboard shell:** dashboard scaffold can ship before keys content.
- **Subscription stub is the smallest piece:** can ride along late in milestone with little risk.

---

## MVP Definition (v1.2 Scope)

### Launch With (v1.2)

Per PROJECT.md Active scope, MVP for this milestone:

- [ ] **Registration** — single-page email+password, inline validation, generic-error enumeration prevention, ToS inline accept, auto-login on success
- [ ] **Login** — email+password, generic error, remember-me checkbox, redirect-to-intended-page, mailto forgot-password link
- [ ] **Session** — HttpOnly cookie, 7d sliding (30d remember), CSRF double-submit, logout, `/api/auth/me` bootstrap
- [ ] **Logout-all-devices** — token_version bump (cheap differentiator that closes a real risk)
- [ ] **API key management UI** — list, create-modal-show-once, copy button, named, last-used display, revoke-with-confirm, soft-delete
- [ ] **Free tier counter** — visible quota on dashboard + upload screen, reset countdown, soft-warn at 80%
- [ ] **Trial countdown banner** — dismissible, days-left, starts on first key creation
- [ ] **Rate limit 429 UX** — inline retry-after countdown, machine-readable JSON, distinguish free-tier vs IP-throttle
- [ ] **Account dashboard** — profile, change password, plan tier display, delete account flow (type email to confirm)
- [ ] **Anti-spam** — IP throttle 3/hr register + 10/hr login per /24, device fingerprint logging, Argon2
- [ ] **CSRF** — invisible double-submit cookie, auto-retry on stale, API-key requests exempt
- [ ] **Upgrade stub** — Pro button + comparison table + "notify me" interest capture modal

### Add After Validation (v1.3)

- [ ] **Email verification** — needs SMTP first
- [ ] **Magic link login** — needs SMTP
- [ ] **Real Stripe Checkout** — schema proven in v1.2 first
- [ ] **Stripe Customer Portal redirect** — billing self-serve
- [ ] **hCaptcha on register** — only if abuse observed
- [ ] **Per-key scopes UI** — backend ready in v1.2, UI when usage validates need
- [ ] **Per-key expiration** — rotation hygiene
- [ ] **Usage charts** — recharts bar chart, hourly window
- [ ] **Active sessions list** — leverage existing fingerprint data
- [ ] **HaveIBeenPwned check** — k-anonymity, free, low complexity
- [ ] **Data export (JSON dump)** — GDPR portability

### Future Consideration (v2+)

- [ ] **TOTP 2FA** — when user base demands
- [ ] **WebAuthn/passkeys** — when browser support matures further
- [ ] **Team plans / multi-seat** — B2B pivot
- [ ] **Refresh token rotation** — only if 7d cookie proves insufficient
- [ ] **Email change flow** — needs SMTP + verification
- [ ] **Email password reset** — needs SMTP

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Registration single-page | HIGH | LOW | P1 |
| Login + session cookie | HIGH | LOW | P1 |
| Argon2 hashing | HIGH | LOW | P1 |
| CSRF double-submit | HIGH | MEDIUM | P1 |
| API key create-modal show-once | HIGH | LOW | P1 |
| API key list + revoke | HIGH | LOW | P1 |
| Free tier counter visible | HIGH | LOW | P1 |
| 429 retry-after UX | HIGH | LOW | P1 |
| Trial countdown banner | MEDIUM | LOW | P1 |
| IP throttle register/login | HIGH | MEDIUM | P1 |
| Device fingerprint logging | MEDIUM | LOW | P1 |
| Delete account flow | HIGH | MEDIUM | P1 |
| Plan tier schema + display | MEDIUM | LOW | P1 |
| Upgrade stub + interest capture | MEDIUM | LOW | P1 |
| Logout all devices | MEDIUM | LOW | P1 |
| Password strength meter | MEDIUM | LOW | P2 |
| Last-used IP on API key | MEDIUM | LOW | P2 |
| Active sessions list | MEDIUM | MEDIUM | P2 |
| Per-key scopes UI | MEDIUM | MEDIUM | P2 |
| Usage charts | MEDIUM | MEDIUM | P3 |
| Magic link login | HIGH | HIGH | P3 |
| 2FA TOTP | HIGH | HIGH | P3 |
| Email verification | MEDIUM | HIGH | P3 |
| HaveIBeenPwned check | LOW | LOW | P3 |
| Email change flow | LOW | HIGH | P3 |
| Refresh token rotation | LOW | HIGH | P3 |

**Priority key:**
- P1: v1.2 milestone scope (must ship)
- P2: v1.3 candidates
- P3: v1.3+ / v2

---

## Competitor Feature Analysis

| Feature | Stripe Dashboard | Vercel | Linear | Cloudflare | Our Approach (v1.2) |
|---------|------------------|--------|--------|------------|---------------------|
| Registration | Single page, email+pw | Single page, GH/Google preferred | Single page, magic link preferred | Single page, email+pw | Single page, email+pw (no OAuth in v1.2) |
| Login session | Cookie + CSRF | Cookie | Cookie | Cookie | Cookie + CSRF |
| API key creation | Show-once modal | Show-once modal | n/a | Show-once modal | Show-once modal |
| Key naming | Required | Required | n/a | Optional | Required |
| Key scopes | Yes (granular) | Yes (limited) | n/a | Yes (granular) | Schema-ready, UI v1.3 |
| Last-used display | Yes | Yes | n/a | Yes | Yes (P1) |
| Rate limit comm | Headers + JSON error | Headers + JSON | Built-in retry | Headers + JSON | Headers + JSON + countdown UI |
| Trial pattern | 14-day, no credit card | 14-day, varies | 14-day | n/a | 7-day from first-key creation |
| Quota visibility | Always-on counter | Dashboard widget | Limit warnings only | Always-on counter | Always-on counter |
| Upgrade CTA | Banner + page CTA | Banner + page CTA | Subtle banner | Page CTA | Banner + dashboard card |
| Delete account | Multi-step confirm | Multi-step confirm | Multi-step confirm | Multi-step confirm | Type-email confirm |
| 2FA | TOTP + WebAuthn | TOTP + WebAuthn | TOTP | TOTP + WebAuthn | DEFER v1.3+ |
| Magic link | No | Yes | Yes (default) | No | DEFER v1.3 |
| Logout all devices | Yes | Yes | Yes | Yes | Yes (token_version) |

**Key takeaway:** v1.2 hits all P1 table stakes that cross all four competitors. Differentiators (magic link, 2FA, granular scope UI) defer cleanly to v1.3 without users perceiving the v1.2 product as broken.

---

## Sources

- Stripe Dashboard API key UX (stripe.com/docs/keys + dashboard, current 2026-04)
- Vercel account/tokens UI (vercel.com/account/tokens, current 2026-04)
- Linear settings/api UI patterns (linear.app/docs/api, current 2026-04)
- Cloudflare API tokens UX (developers.cloudflare.com/api/tokens, current 2026-04)
- GitHub PAT UX (github.com/settings/tokens, current 2026-04)
- OpenAI Platform API keys (platform.openai.com, current 2026-04)
- OWASP ASVS 4.0.3 password storage + session management
- NIST SP 800-63B authenticator guidelines (no forced rotation)
- Resend.com / Notion / Slack magic-link UX patterns (HIGH confidence on industry norm)
- PROJECT.md (v1.2 Active scope, decisions, constraints)
- 2026 SaaS auth norms (Linear, Vercel, Stripe Dashboard cross-validated — HIGH confidence)

**Confidence:** HIGH on table stakes (cross-validated across 5+ products). HIGH on anti-feature judgments (post-mortem and industry consensus). MEDIUM on complexity sizing (frontend stack already shadcn + react-hook-form, lowers most components to S).

---

*Feature research for: WhisperX v1.2 multi-tenant SaaS auth + API keys + billing-ready*
*Researched: 2026-04-29*
