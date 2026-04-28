# Stack Research: v1.2 Multi-User Auth + API Keys + Billing-Ready

**Project:** WhisperX FastAPI App
**Researched:** 2026-04-29
**Focus:** Stack additions ONLY — auth, JWT, CSRF, rate limit, migrations, Stripe schema, frontend test infra
**Confidence:** HIGH (versions verified vs PyPI / npm 2026-04 indexes)

---

## Executive Summary

Existing stack stays. Adds 8 backend libs, 7 frontend libs. No replacements. No conflicts with FastAPI 0.128, SQLAlchemy 2.0.44, Pydantic v2, React 19, Vite 7, Bun.

Notable choice: **PyJWT not python-jose** (jose abandoned, FastAPI docs migrated). **slowapi** for rate limit (sliding window strategy supported, key_func for per-user/IP). **fastapi-csrf-protect** double-submit. **Typer** for CLI (matches FastAPI/Pydantic ecosystem). **react-hook-form + zod** for forms. **zustand** for auth state (Context re-render storm avoided).

---

## Backend Additions (Python, uv)

### Core Auth + Security

| Package | Version | Purpose | Rationale |
|---------|---------|---------|-----------|
| **argon2-cffi** | `25.1.0` | Argon2id password hash | OWASP-recommended. Direct lib, no passlib bloat. Maintained by hynek. C bindings via cffi. |
| **PyJWT** | `2.12.1` | JWT sign/verify | python-jose abandoned (~3yr no release, sec issues). FastAPI docs migrated to PyJWT. Drop-in replacement. |
| **fastapi-csrf-protect** | `0.3.3` | Double-submit CSRF | Stateless, signed-token cookie + header. Matches FastAPI lifecycle (Depends-injected). Skip first-party impl — solved problem. |
| **slowapi** | `0.1.9` | Rate limit (sliding window) | Wraps `limits` lib. `strategy="sliding-window"` exists. Custom `key_func` for `user_id`/`ip /24`. In-memory storage works for SQLite single-instance deploy. |

**Note slowapi maintenance:** last release ~12mo ago. Stable but watch for `limits` upstream changes. Acceptable risk vs hand-rolled.

### Database Migrations

| Package | Version | Purpose | Rationale |
|---------|---------|---------|-----------|
| **alembic** | `1.18.4` | Schema migrations | Native SQLAlchemy 2.x support. Project uses SQLAlchemy 2.0.44. Baseline workflow: generate first migration → `alembic stamp head` against existing `records.db`. |

**Init pattern (existing schema baseline):**
```bash
alembic init -t generic migrations
# edit alembic.ini → sqlalchemy.url = sqlite:///records.db
# edit env.py → target_metadata = Base.metadata (from app.infrastructure.database)
alembic revision --autogenerate -m "baseline existing tasks schema"
alembic stamp head  # mark prod DB as current, do NOT run upgrade
# subsequent: alembic revision --autogenerate -m "add users + api_keys + ..."
alembic upgrade head
```

### Billing (Schema Only — v1.2)

| Package | Version | Purpose | Rationale |
|---------|---------|---------|-----------|
| **stripe** | `15.1.0` | Stripe Python SDK | Schema-only milestone — install but unused at runtime. Reserves namespace for v1.3 integration. Python ≥3.9. |

**v1.2 scope:** schema migration only. No webhook handlers. No checkout routes. SDK install gates Pylance imports for `Subscription`/`UsageEvent` typing.

### CLI

| Package | Version | Purpose | Rationale |
|---------|---------|---------|-----------|
| **typer** | `0.24.2` | Admin bootstrap CLI | Built on Click, type-hint driven, matches Pydantic/FastAPI ecosystem (same author Tiangolo). `python -m app.cli create-admin` pattern trivial. argparse too verbose, Click works but Typer is FastAPI-style. |

### Stdlib (No New Deps)

| Concern | Use | Why |
|---------|-----|-----|
| Device fingerprint hash | `hashlib.sha256` (stdlib) | SHA256 of `f"{cookie_session_id}|{ua}|{ip_24}|{device_id}"` sufficient. No lib needed. |
| Constant-time compare | `secrets.compare_digest` (stdlib) | Already used in `app/core/auth.py:76`. Reuse. |
| API key generation | `secrets.token_urlsafe(32)` (stdlib) | `whsk_<urlsafe32>` format. No lib needed. |

### Backend Install (uv)

```bash
uv add argon2-cffi==25.1.0 \
       PyJWT==2.12.1 \
       fastapi-csrf-protect==0.3.3 \
       slowapi==0.1.9 \
       alembic==1.18.4 \
       stripe==15.1.0 \
       typer==0.24.2
```

---

## Frontend Additions (Bun, npm registry)

### Test Infrastructure

| Package | Version | Purpose | Rationale |
|---------|---------|---------|-----------|
| **vitest** | `^3.2.0` | Test runner | Vite 7 requires Vitest ≥3.2. Native ESM, Vite-config sharing. Latest is 4.1 but 3.2 LTS-stable, less churn. |
| **@vitest/ui** | `^3.2.0` | Test UI | Optional. Browser dashboard for failures. |
| **@testing-library/react** | `^16.1.0` | Component test utils | First version with React 19 support. v15 fails peer-dep check. |
| **@testing-library/user-event** | `^14.6.1` | Realistic event sim | Compatible with RTL 16. Async API mandatory (`await user.click()`). |
| **@testing-library/jest-dom** | `^6.6.3` | Custom matchers | `toBeInTheDocument`, `toHaveAttribute`, etc. Configure once in setup file. |
| **jsdom** | `^29.0.2` | DOM env in Node | Vitest `environment: 'jsdom'`. Alternative `happy-dom` faster but less spec-compliant — pick jsdom for fewer surprises with Radix portals. |
| **msw** | `^2.13.4` | API mocking | Framework-agnostic. Service-worker (browser) + node interceptor (tests). Works React 19. v2 syntax (`http.get`) — do NOT use v1 examples. |

### Form Handling

| Package | Version | Purpose | Rationale |
|---------|---------|---------|-----------|
| **react-hook-form** | `^7.60.0` | Form state | Uncontrolled inputs, minimal re-renders. Matches React 19. shadcn/ui has first-class `<Form>` integration. |
| **zod** | `^3.25.76` | Schema validation | TS-first, runtime + compile-time types. Reuse server-side too if pydantic-zod bridge later. |
| **@hookform/resolvers** | `^5.1.1` | RHF↔zod glue | `zodResolver(schema)` → `useForm({ resolver: ... })`. |

### Auth State Mgmt

| Package | Version | Purpose | Rationale |
|---------|---------|---------|-----------|
| **zustand** | `^5.0.12` | Auth store | React Context triggers full subtree re-render on auth changes. Zustand selector-based subscription = surgical re-renders. Project has zero global state lib — clean slate. |

### Frontend Install (Bun)

```bash
bun add react-hook-form@^7.60.0 zod@^3.25.76 @hookform/resolvers@^5.1.1 zustand@^5.0.12

bun add -d vitest@^3.2.0 @vitest/ui@^3.2.0 \
            @testing-library/react@^16.1.0 \
            @testing-library/user-event@^14.6.1 \
            @testing-library/jest-dom@^6.6.3 \
            jsdom@^29.0.2 \
            msw@^2.13.4
```

**Vite config:** add `test: { environment: 'jsdom', setupFiles: './src/test/setup.ts', globals: true }` to `vite.config.ts`.

**MSW setup:** `npx msw init public/ --save` for browser worker. Test setup imports `setupServer` from `msw/node`.

---

## Alternatives Considered

| Picked | Rejected | Why Not Rejected |
|--------|----------|------------------|
| argon2-cffi | passlib[argon2] | passlib unmaintained since 2020, drags bcrypt + extras. Direct argon2-cffi simpler. |
| argon2-cffi | bcrypt | Argon2id wins OWASP comparisons (memory-hard, GPU-resistant). |
| PyJWT | python-jose | Abandoned. Vulnerable deps. FastAPI docs migrated. |
| PyJWT | authlib | Heavyweight (OAuth2 server, OIDC). Overkill for cookie + bearer. |
| fastapi-csrf-protect | starlette-csrf | starlette-csrf middleware-only, less FastAPI-idiomatic. fastapi-csrf-protect uses Depends pattern. |
| fastapi-csrf-protect | hand-rolled | Risky — CSRF bugs subtle (timing, cookie flags). Use vetted impl. |
| slowapi | fastapi-limiter | fastapi-limiter requires Redis. SQLite single-container deploy = no Redis. slowapi in-memory fallback works. |
| slowapi | hand-rolled | Reinventing limits library. Sliding-window math non-trivial. |
| Typer | Click | Click works but no type-hint inference. Pydantic ecosystem favors Typer. |
| Typer | argparse | Verbose, no type coercion, no rich help. |
| zustand | React Context | Auth state changes trigger every consumer re-render. Zustand selectors fix this. |
| zustand | Redux Toolkit | Overkill. No reducers/actions for 1 store. |
| zod | yup | Yup type inference weaker. Zod TS-first. |
| zod | valibot | Newer, smaller, but RHF resolver less mature. Zod = safe bet. |
| jsdom | happy-dom | Faster but Radix UI portal/focus tests flake. jsdom safer. |
| msw | nock | Nock fetch-only, msw covers fetch + XHR + WebSocket-ish. |

---

## What NOT to Add

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| **python-jose** | Abandoned, security issues, FastAPI dropped recommendation | PyJWT |
| **passlib** | Unmaintained since 2020, drags bcrypt | argon2-cffi direct |
| **bcrypt** for new hashes | GPU-attackable, OWASP prefers Argon2id | argon2-cffi |
| **fastapi-users** | Full auth framework — opinionated, conflicts with custom user model + per-user task scoping + API key dual auth | First-party services using PyJWT + argon2-cffi |
| **fastapi-limiter** | Requires Redis — project is single-container SQLite | slowapi (in-memory) |
| **redis** / **aioredis** | No external service — adds deploy complexity | slowapi in-memory; revisit at v1.3 if multi-worker |
| **sqladmin** / **fastapi-admin** | Out of scope — admin panel not in v1.2 | Typer CLI for bootstrap |
| **react-redux / @reduxjs/toolkit** | Overkill for one auth store | zustand |
| **jotai / recoil** | Atom-based state — wrong abstraction for cookie session | zustand store |
| **formik** | Higher re-render cost, Zod integration awkward | react-hook-form |
| **yup** | Weaker TS inference | zod |
| **happy-dom** | Radix portal tests flake | jsdom |
| **nock** | Fetch-only, limited scope | msw |
| **enzyme** | Dead, no React 19 support | @testing-library/react |
| **karma / mocha / chai** | Pre-Vite era, slow | vitest |
| **email-validator** Python lib | Pydantic v2 has `EmailStr` built-in (needs `email-validator` extra — already pulled by pydantic) | Pydantic `EmailStr` |
| **cryptography** for password hash | Wrong tool — primitives only | argon2-cffi |

---

## Integration Considerations vs Existing Stack

### Existing → New Compatibility

| Existing | New | Note |
|----------|-----|------|
| FastAPI 0.128 | slowapi 0.1.9 | Compatible. `Limiter(app)` integrates via decorator + middleware. |
| FastAPI 0.128 | fastapi-csrf-protect 0.3.3 | Uses `Depends(CsrfProtect)` — matches existing dep injection pattern (`app/core/container.py`). |
| SQLAlchemy 2.0.44 | alembic 1.18.4 | Native 2.x support. Use `DeclarativeBase` (already in `app/infrastructure/database/models.py:8`). |
| Existing `BearerAuthMiddleware` | New dual auth (cookie + bearer) | REPLACE, not extend. New middleware accepts cookie session JWT OR `whsk_*` API key. Keep `API_BEARER_TOKEN` env-var path as legacy fallback OR remove. Decision: remove for v1.2. |
| pydantic-settings | Add `JWT_SECRET`, `CSRF_SECRET`, `COOKIE_DOMAIN`, `RATE_LIMIT_*` | New `AuthSettings` class in `app/core/config.py`. Pattern matches existing `DatabaseSettings`/`WhisperSettings`. |
| dependency-injector 4.41 | Auth service, API key service | Register in `app/core/container.py` as singletons. |
| React 19.2 | All frontend libs | Verified compatible: RTL 16.1+, msw 2.13, zustand 5.0, RHF 7.60. |
| Vite 7.2 | vitest 3.2 | Vitest 3.2 mandatory for Vite 7 — older vitest fails. |
| Bun | All frontend libs | Bun handles npm registry — no Bun-specific gotchas. |
| Tailwind v4 + shadcn/ui | RHF | shadcn `<Form>` component already RHF-aware. |
| react-router-dom 7.13 (unused) | Activate now | Routes: `/ui/login`, `/ui/register`, `/ui/dashboard/keys`, `/ui/dashboard/usage`. SPA handler in `app/spa_handler.py` already supports catch-all. |
| WebSocket auth | Cookie session JWT in WS handshake | tuspyserver TUS endpoints — needs same dual-auth wrapper. |

### Migration Path for Existing `BearerAuthMiddleware`

`app/core/auth.py:56` currently checks single env-var `API_BEARER_TOKEN`. v1.2 replaces with:
1. Try cookie `session` → verify JWT → set `request.state.user_id`
2. Try `Authorization: Bearer whsk_*` → hash → lookup `api_keys.hash_lookup` → set `request.state.user_id`, `request.state.api_key_id`
3. Else 401

Existing `_is_public` allowlist stays. Add `/api/auth/*` (login, register, csrf-token) as public.

---

## Version Compatibility Matrix

| Package A | Package B | Note |
|-----------|-----------|------|
| `vitest@3.2` | `vite@7.2` | Min Vitest for Vite 7 |
| `@testing-library/react@16.1` | `react@19` | Min RTL for React 19 |
| `msw@2.13` | `node@>=18` | v2 requires modern Node |
| `alembic@1.18` | `sqlalchemy@2.0.44` | Native 2.x compat |
| `slowapi@0.1.9` | `fastapi@0.128` | Compatible, `limits` ≥3.9 transitive |
| `PyJWT@2.12` | `python@3.11` | OK, supports 3.8+ |
| `argon2-cffi@25.1` | `python@3.11` | OK |
| `typer@0.24` | `python@3.11` | OK, requires ≥3.10 |
| `fastapi-csrf-protect@0.3.3` | `pydantic@v2` | Compatible (lib migrated to v2) |

---

## Caveman Mode Quick Reference

**Backend new (uv add):** argon2-cffi==25.1.0, PyJWT==2.12.1, fastapi-csrf-protect==0.3.3, slowapi==0.1.9, alembic==1.18.4, stripe==15.1.0, typer==0.24.2

**Frontend deps (bun add):** react-hook-form@^7.60.0, zod@^3.25.76, @hookform/resolvers@^5.1.1, zustand@^5.0.12

**Frontend dev (bun add -d):** vitest@^3.2.0, @vitest/ui@^3.2.0, @testing-library/react@^16.1.0, @testing-library/user-event@^14.6.1, @testing-library/jest-dom@^6.6.3, jsdom@^29.0.2, msw@^2.13.4

**No add:** redis, passlib, python-jose, fastapi-users, fastapi-limiter, formik, yup, happy-dom, jotai, react-redux

**Stdlib only:** hashlib (fingerprint), secrets (token, compare), datetime (JWT exp)

---

## Sources

- [argon2-cffi PyPI](https://pypi.org/project/argon2-cffi/) — version 25.1.0 confirmed
- [PyJWT PyPI](https://pypi.org/project/PyJWT/) — version 2.12.1 confirmed
- [FastAPI Discussion #11345](https://github.com/fastapi/fastapi/discussions/11345) — python-jose abandonment, PyJWT migration
- [FastAPI Discussion #9587](https://github.com/fastapi/fastapi/discussions/9587) — security concerns w/ python-jose
- [slowapi PyPI](https://pypi.org/project/slowapi/) — version 0.1.9 confirmed
- [SlowApi Docs](https://slowapi.readthedocs.io/) — sliding-window strategy, custom key_func
- [limits library](https://github.com/alisaifee/limits) — backing storage strategies
- [alembic 1.18.4 docs](https://alembic.sqlalchemy.org/en/latest/autogenerate.html) — autogenerate + stamp pattern
- [stripe-python releases](https://github.com/stripe/stripe-python/releases) — version 15.1.0 confirmed (2026-04-24)
- [typer PyPI](https://pypi.org/project/typer/) — version 0.24.2 confirmed (2026-04-22)
- [fastapi-csrf-protect](https://github.com/aekasitt/fastapi-csrf-protect) — double-submit cookie impl
- [Vite 7 release](https://vite.dev/blog/announcing-vite7) — Vitest ≥3.2 requirement
- [@testing-library/react npm](https://www.npmjs.com/package/@testing-library/react) — v16.1 React 19 support
- [msw npm](https://www.npmjs.com/package/msw) — version 2.13.4 confirmed
- [zustand discussion #2686](https://github.com/pmndrs/zustand/discussions/2686) — React 19 compat
- [Zustand vs Context 2026](https://medium.com/@abdurrehman1/state-management-in-2026-redux-vs-zustand-vs-context-api-ad5760bfab0b) — auth state recommendation
- [react-hook-form 2026 guide](https://dev.to/marufrahmanlive/react-hook-form-with-zod-complete-guide-for-2026-1em1) — versions 7.60.0 / 3.25.76 / 5.1.1
- [SQLAlchemy PyPI](https://pypi.org/project/SQLAlchemy/) — 2.0.49 latest, project pinned 2.0.44 in uv.lock

---

*Stack research for: WhisperX v1.2 multi-user auth*
*Researched: 2026-04-29*
*Confidence: HIGH — all versions verified against PyPI / npm 2026-04 indexes*
