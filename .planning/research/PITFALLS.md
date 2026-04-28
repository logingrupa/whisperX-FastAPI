# Pitfalls Research: v1.2 Multi-User Auth + API Keys + Stripe-Ready Schema

**Domain:** Add auth + API keys + billing schema to existing single-user FastAPI/SQLite app
**Researched:** 2026-04-29
**Confidence:** HIGH (verified against OWASP, Alembic docs, slowapi, recent CVEs, codebase grep)

**Scope:** Pitfalls SPECIFIC to this codebase — `app/main.py` calling `Base.metadata.create_all()` (no migrations), `BearerAuthMiddleware` env-token shared, `app/api/websocket_api.py` zero auth on `/ws/tasks/{task_id}`, `app/api/tus_upload_api.py` with CORS-exposed TUS headers, React frontend with raw `fetch()` no auth. NOT generic auth advice.

---

## Critical Pitfalls (cause data loss, auth bypass, or rewrite)

### 1. `user_id` FK on populated `tasks` table — NOT NULL backfill order

**What goes wrong:**
Add `user_id INTEGER NOT NULL REFERENCES users(id)` migration → SQLite rejects on existing rows (NULL violates NOT NULL). Or worse: dev runs `Base.metadata.create_all()` (still in `app/main.py:48`) which silently does NOT alter existing tables — schema drift between dev and prod.

**Why it happens:**
- Codebase has `Base.metadata.create_all(bind=engine)` in `app/main.py` line 48. `create_all` only creates missing tables, NEVER alters existing. So adding column to model file does nothing on already-populated DB.
- Naive Alembic migration adds column with NOT NULL + FK → fails on row 1.
- Dev with empty DB succeeds, prod with 10k rows fails.

**Warning signs:**
- `Base.metadata.create_all()` still called after Alembic introduced (must remove)
- Migration uses `nullable=False` directly without backfill step
- "OperationalError: NOT NULL constraint failed" on prod, works in tests

**Prevention:**
1. Three-step migration pattern (mandatory):
   - Step A: add column `nullable=True` (no FK enforcement yet on SQLite without `PRAGMA foreign_keys=ON`)
   - Step B: backfill UPDATE — assign existing tasks to a system/admin user (`SELECT id FROM users WHERE email='admin@...'`)
   - Step C: `batch_alter_table` to set `nullable=False` + add FK constraint
2. Delete `Base.metadata.create_all(bind=engine)` from `app/main.py` line 48 in same phase Alembic introduced. Replace with `alembic upgrade head` in startup or CI.
3. Smoke-test migration against COPY of `records.db` with real row count before deploy.

**Phase to address:** Phase 11 (Alembic baseline + users/api_keys schema). Backfill rule documented BEFORE first migration written.

**Source:** [SQLAlchemy create_all docs](https://docs.sqlalchemy.org/en/20/core/metadata.html#sqlalchemy.schema.MetaData.create_all), [Alembic Cookbook](https://alembic.sqlalchemy.org/en/latest/cookbook.html)

---

### 2. SQLite ALTER TABLE limitation — FK add requires table rebuild

**What goes wrong:**
SQLite cannot `ALTER TABLE ... ADD CONSTRAINT FOREIGN KEY`. Cannot rename/drop columns natively (until 3.35). Naive `op.add_column()` with FK silently produces column WITHOUT enforced FK. Worse: unnamed FK constraints (default in SQLAlchemy on SQLite) cannot be dropped later — renames break.

**Why it happens:**
- SQLite ALTER TABLE only supports rename table, add column (no FK), drop column (3.35+).
- `tuspyserver` may have its own tables — batch operations dropping/recreating `tasks` need every FK reference handled.
- `PRAGMA foreign_keys` is OFF by default per-connection; even if you add FK, SQLite won't enforce unless pragma set on EVERY connection.

**Warning signs:**
- Foreign keys defined in models but `PRAGMA foreign_keys` returns 0 in `sqlite3 records.db`
- Cascade delete doesn't cascade
- Alembic error: "No support for ALTER of constraints in SQLite dialect"
- Tests pass on Postgres (CI), fail on SQLite (prod)

**Prevention:**
1. ALWAYS use `with op.batch_alter_table('tasks') as batch_op:` for SQLite — recreates table.
2. NAME every constraint explicitly: `ForeignKey('users.id', name='fk_tasks_user_id')`. Configure `naming_convention` in `Base.metadata` so Alembic autogenerate produces stable names.
3. Enable FK pragma globally: SQLAlchemy event listener on `connect`:
   ```python
   @event.listens_for(engine, "connect")
   def _fk_pragma(dbapi_conn, _): dbapi_conn.execute("PRAGMA foreign_keys=ON")
   ```
4. Read [Alembic batch.html](https://alembic.sqlalchemy.org/en/latest/batch.html) before writing first FK migration. Test downgrade.

**Phase to address:** Phase 11 (Alembic init). Naming convention + pragma listener part of baseline.

**Source:** [Alembic Batch Migrations](https://alembic.sqlalchemy.org/en/latest/batch.html), [Flask-Migrate issue #97](https://github.com/miguelgrinberg/Flask-Migrate/issues/97)

---

### 3. Alembic baseline diff — autogenerate against existing live schema

**What goes wrong:**
First `alembic revision --autogenerate` on existing DB produces migration that tries to RECREATE `tasks` table (because no baseline). Run it → `IntegrityError: table tasks already exists` or worse, silent data loss if migration drops first.

**Why it happens:**
- Alembic with empty `alembic_version` table sees no history. `target_metadata = Base.metadata` describes ALL tables. Diff = "create everything".
- Dev forgets `alembic stamp head` before first revision.
- Autogenerate misses: server defaults, comment fields (codebase has `comment="..."` on every column — Alembic may regenerate every migration claiming comments differ).

**Warning signs:**
- First migration script contains `op.create_table('tasks', ...)` for already-existing table
- Migration "no-op" but autogenerate keeps producing same diff (comment/default false-positives)
- `alembic current` shows nothing on prod

**Prevention:**
1. Order: (a) `alembic init alembic`, (b) write env.py with `target_metadata = Base.metadata`, (c) write FIRST migration MANUALLY mirroring current `tasks` schema EXACTLY (column-by-column from `app/infrastructure/database/models.py`), (d) on prod: `alembic stamp <baseline_revision_id>`, NOT `upgrade head`.
2. Configure `compare_server_default=True`, `compare_type=True`, but accept first few autogen runs need hand-edits.
3. Set `include_object` filter in `env.py` to ignore tuspyserver tables if they live in same DB.
4. Document in PR: "this migration is baseline — DO NOT run upgrade on populated DB, only stamp".

**Phase to address:** Phase 11 (Alembic init). Baseline migration is FIRST commit; users/api_keys come in subsequent migrations.

**Source:** [Alembic Cookbook: working with existing DB](https://alembic.sqlalchemy.org/en/latest/cookbook.html), [Medium: Zero-state Migration](https://medium.com/@megablazikenabhishek/initialize-alembic-migrations-on-existing-database-for-auto-generated-migrations-zero-state-31ee93632ed1)

---

### 4. Argon2 parameters — login DoS via memory cost

**What goes wrong:**
Pick high `m_cost=65536` (64 MiB) "for security". Login takes 800ms. Concurrent burst of 50 logins → 3.2 GB RAM spike → OOM kill on small VPS. Login becomes self-DoS. Or opposite: pick `m_cost=8192` "for speed", GPU farm cracks leaked DB.

**Why it happens:**
- Devs copy "high security" defaults from blog posts. argon2-cffi default is `m=65536, t=3, p=4` — fine for password manager, oversized for web login.
- Don't benchmark on actual server hardware (CI runner ≠ prod VPS).
- Forget login is on hot path — every wrong password attempt also runs Argon2.

**Warning signs:**
- Login p99 latency > 500ms
- Memory graph shows spikes correlated with login bursts
- Login slow only under concurrent load (CPU/memory contention)
- Brute-force attempts crash the server

**Prevention:**
1. Use OWASP 2024+ baseline: `m=19456 (19 MiB), t=2, p=1` OR `m=47104 (46 MiB), t=1, p=1`. Target ~150ms hash time on prod hardware.
2. Benchmark on prod-equivalent hardware: `python -c "from argon2 import PasswordHasher; ..."` → assert <300ms p99.
3. Pre-rate-limit login (10/hr per /24 already in PROJECT.md) BEFORE Argon2 runs — saves CPU on attack.
4. Wrap PasswordHasher in `app/core/password_hasher.py` (single source) — params changeable in one place.
5. Keep `parallelism=1` for web (low-contention) — `p>1` consumes more CPU per request.

**Phase to address:** Phase 12 (Auth core — registration/login). Benchmark documented in `tests/auth/test_argon2_benchmark.py`.

**Source:** [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html), [argon2-cffi parameters](https://argon2-cffi.readthedocs.io/en/stable/parameters.html)

---

### 5. Bcrypt 72-byte truncation — NOT YOUR LIB but watch transition

**What goes wrong:**
Codebase chose argon2 (good). But if anyone EVER falls back to bcrypt (e.g., importing legacy hashes from another system, or `passlib` configured with both), bcrypt SILENTLY truncates passwords > 72 bytes. UTF-8 emoji password reaches 72 bytes at ~12 chars. Two different long passwords hash identical → auth bypass (CVE-2025-68402, FreshRSS).

**Why it happens:**
- Devs assume hashing libraries fail loudly on too-long input. They don't.
- Multi-byte char password (Latvian: "Pārējais", emoji) — chars look short but bytes long.
- Legacy import path quietly uses passlib bcrypt scheme.

**Warning signs:**
- Two distinct long passwords accept each other on login
- `passlib` in deps alongside argon2-cffi (drop passlib unless needed)
- Code does `password[:72]` anywhere

**Prevention:**
1. argon2-cffi only. NO `passlib` in deps unless legacy hash migration needed.
2. Reject password > 128 chars at Pydantic schema level — rejects bcrypt-truncatable AND prevents Argon2 DoS.
3. If migrating bcrypt hashes later (out of scope v1.2 but document): pre-hash with SHA-256 base64, then bcrypt — `bcrypt(base64(sha256(pw)))` to dodge 72-byte limit.

**Phase to address:** Phase 12 (Auth core). Pydantic `password: str = Field(min_length=8, max_length=128)`.

**Source:** [Pentesterlab FreshRSS bcrypt truncation](https://pentesterlab.com/blog/freshrss-bcrypt-truncation-auth-bypass), [pyca/bcrypt issue 1082](https://github.com/pyca/bcrypt/issues/1082)

---

### 6. JWT algorithm confusion + alg=none

**What goes wrong:**
Default `python-jose.jwt.decode(token, key, algorithms=None)` — no algorithm pinning → attacker forges `{"alg":"none"}` token, server accepts. Or RS256→HS256 swap (sign with PUBLIC key as HMAC secret). v1.2 uses HS256 only (single secret) so RS256 confusion less applicable, but `algorithms=` parameter is STILL mandatory.

**Why it happens:**
- `python-jose` and PyJWT historically defaulted permissive. Multiple CVEs (CVE-2022-29217 PyJWT, CVE-2026-22817 Hono).
- Devs call `jwt.decode(token, secret)` without `algorithms=["HS256"]`.
- Test mocking accepts any JWT, hides bug until prod.

**Warning signs:**
- `jwt.decode(...)` call WITHOUT explicit `algorithms=` keyword arg
- Token with header `{"alg":"none","typ":"JWT"}` and empty signature accepted
- No test asserting forged-alg-none rejected

**Prevention:**
1. Wrap decode in `app/core/jwt_codec.py`. Single function `decode_session(token: str) -> Claims`. Hard-coded `algorithms=["HS256"]`. NEVER pass through user-controlled alg.
2. Test asserts: forged `alg=none` → 401; truncated/missing signature → 401; tampered payload → 401; expired → 401.
3. Pin `python-jose` to vetted version OR switch to `pyjwt[crypto]` (more actively maintained as of 2026).
4. Use minimal claim set: `sub` (user_id), `exp`, `iat`, `jti` (for revocation list later). NO sensitive data in payload (JWT is base64, not encrypted).

**Phase to address:** Phase 12 (Auth core — JWT cookie session). `jwt_codec.py` is single source.

**Source:** [Auth0: Critical vulnerabilities in JWT libraries](https://auth0.com/blog/critical-vulnerabilities-in-json-web-token-libraries/), [PortSwigger Algorithm confusion](https://portswigger.net/web-security/jwt/algorithm-confusion)

---

### 7. JWT in localStorage (XSS) vs cookie (CSRF) — pick correctly

**What goes wrong:**
Frontend dev stores JWT in `localStorage` "for simplicity" → any XSS reads token, attacker exfils. Or stores in non-`HttpOnly` cookie — same problem. Or uses `HttpOnly` cookie but no CSRF token → drive-by POST forges actions.

**Why it happens:**
- Tutorials show `localStorage.setItem('token', jwt)` because it works.
- React app feels safer because of JSX escaping — but third-party npm with malicious code ruins that (supply chain).
- CSRF "feels old" — devs skip it because "we use JWT".

**Warning signs:**
- `localStorage.getItem('token')` or `sessionStorage` anywhere in frontend
- Cookie set without `HttpOnly`, `Secure`, `SameSite=Lax`
- POST endpoint accepts cookie auth without CSRF token check

**Prevention:**
1. Cookie only: `Set-Cookie: session=<jwt>; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=604800`
2. Double-submit CSRF: separate non-HttpOnly cookie `csrftoken=<random>` + frontend reads + sends as `X-CSRF-Token` header on every state-changing request. Server validates header == cookie.
3. API key auth (Bearer) → no cookies → no CSRF needed (different code path).
4. Lint rule: ESLint custom rule banning `localStorage.setItem('token'|'jwt'|'session', ...)`.

**Phase to address:** Phase 12 (cookie set), Phase 13 (CSRF middleware), Phase 16 (frontend integration).

**Source:** [OWASP CSRF Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)

---

### 8. SameSite=Lax 2-min Chrome grace period + GET state-change

**What goes wrong:**
- Chrome's `SameSite=Lax` does NOT enforce on top-level POST for first 120 seconds after cookie set (compatibility quirk). Attacker auto-submit form during window → CSRF.
- ANY state-changing operation reachable via GET bypasses Lax entirely. Codebase has `DELETE /api/account/data` planned — if accidentally exposed as GET (e.g., HTML link `<a href="/api/account/data?action=delete">`), Lax cookie sent, account deleted.

**Why it happens:**
- "SameSite=Lax solves CSRF" misconception. It mitigates, not eliminates.
- Devs add convenience GET handlers ("for debug").
- Method override middleware (`?_method=DELETE`) re-introduces vulnerability.

**Warning signs:**
- ANY non-idempotent action behind GET (`@router.get` decorator on handler that mutates state)
- Cookie session created with no CSRF token
- `_method` query param respected by middleware

**Prevention:**
1. NEVER use GET for state change. Lint check: every `@router.get` must be read-only (audit annotation `# read-only`).
2. CSRF double-submit token even WITH SameSite=Lax — defense in depth.
3. NO method-override middleware. Reject `?_method=` and `X-HTTP-Method-Override` header.
4. For very sensitive actions (`DELETE /api/account/data`, password change), require re-authentication (current password) — protects against the 2-min Chrome window.

**Phase to address:** Phase 13 (CSRF + cookie hardening). Phase 14 includes account-data delete.

**Source:** [PortSwigger SameSite bypass](https://portswigger.net/web-security/csrf/bypassing-samesite-restrictions), [Pulse Security SameSite Lax CSRF](https://pulsesecurity.co.nz/articles/samesite-lax-csrf)

---

### 9. CSRF on TUS upload (file upload form forgery)

**What goes wrong:**
TUS endpoint at `/uploads/files/` accepts POST/PATCH. Browser sends session cookie automatically. Attacker site does cross-origin TUS upload → uploads to victim's account. Made worse by current `app/main.py:174 allow_origins=["*"]` — CORS wide open.

**Why it happens:**
- TUS server (`tuspyserver`) doesn't know about your CSRF token. Adds endpoints OUTSIDE your auth flow.
- `allow_origins=["*"]` MUST change once cookies present (browsers REFUSE wildcard CORS with credentials, but pre-flight pass-through with custom headers is messy).
- TUS protocol headers (`Tus-Resumable`, `Upload-Length`) exposed via CORS — attacker can craft compliant requests.

**Warning signs:**
- `allow_origins=["*"]` in `app/main.py` after cookie auth introduced
- `/uploads/files/` accepts requests without CSRF check or API key
- Cross-origin POST to TUS endpoint succeeds in browser

**Prevention:**
1. TUS endpoint requires API key (Bearer) ONLY — no cookie path. Browser uploads use API key the dashboard issues to user's session.
2. Replace `allow_origins=["*"]` with explicit list (`https://yourdomain.com`). `allow_credentials=True` REQUIRES specific origins (browser enforces).
3. CORS preflight for TUS-Resumable etc. only allowed from same origin.
4. Wrap `tus_upload_router` mount with CSRF-aware dependency that EITHER validates API key OR validates session+CSRF token.

**Phase to address:** Phase 13 (CORS lockdown + TUS auth). Audit `app/api/tus_upload_api.py` mount.

**Source:** Codebase `app/main.py:172-178`, [tuspyserver](https://github.com/edihasaj/tuspyserver)

---

### 10. WebSocket `/ws/tasks/{task_id}` — zero auth, cross-user task leak

**What goes wrong:**
Current `app/api/websocket_api.py:23` — `@websocket_router.websocket("/ws/tasks/{task_id}")` accepts ANY task_id from ANY origin with NO auth. v1.2 adds per-user tasks → User A guesses/scrapes User B's task UUID → connects → reads transcription progress + final result via progress events.

**Why it happens:**
- WebSockets bypass `BearerAuthMiddleware` (the middleware checks REST headers, WS upgrade is different).
- Browsers can't set custom headers on WS — devs put token in URL → ends in nginx/cloudflare/uvicorn access logs.
- Task UUIDs are guessable if sequential or predictable.

**Warning signs:**
- WebSocket connects without any token check (current state — verified at `app/api/websocket_api.py:24-40`)
- `?token=...` in WS URL appears in access logs
- No test asserting "User A cannot subscribe to User B's task"

**Prevention:**
1. Two-step pattern: REST `POST /api/ws/ticket` (cookie or API key auth) → returns short-lived (60s) one-time `ws_ticket`. WS connects with `?ticket=<uuid>`. Server consumes ticket on connect, checks `ticket.user_id == task.user_id`.
2. Validate `task_id` belongs to authenticated user BEFORE accepting WS connection. `await websocket.accept()` only after check.
3. Configure uvicorn/nginx/cloudflare access logs to STRIP query strings on WS URL — or never put secret in URL (use ticket = single-use, not session token).
4. Test: `test_ws_user_a_cannot_subscribe_user_b_task` — explicit scope test.

**Phase to address:** Phase 13 (WS auth ticket flow). MUST ship with cookie auth, not deferred.

**Source:** Codebase `app/api/websocket_api.py:23-40`, [Peter Braden FastAPI WS auth](https://peterbraden.co.uk/article/websocket-auth-fastapi/), [DEV.to WS auth](https://dev.to/hamurda/how-i-solved-websocket-authentication-in-fastapi-and-why-depends-wasnt-enough-1b68)

---

### 11. WebSocket subprotocol header stripped by reverse proxies

**What goes wrong:**
Alternative to query param: pass token in `Sec-WebSocket-Protocol`. But Cloudflare, some nginx configs, AWS ALB strip non-standard subprotocols silently. WS handshake succeeds (because client sends, server doesn't get header) but auth fails on server → confusing intermittent 401. Or worse: server doesn't check, connection allowed unauthenticated.

**Why it happens:**
- Cloudflare WebSocket forwarding strips/normalizes `Sec-WebSocket-Protocol` unless explicitly listed.
- Reverse proxy `proxy_set_header` directive missing.
- Works locally (no proxy), breaks in prod-behind-Cloudflare.

**Warning signs:**
- "WebSocket auth fails in prod, works on localhost"
- Logs show `Sec-WebSocket-Protocol: None` despite client sending
- Inconsistent failure rate

**Prevention:**
1. Use query-string ticket (option 1 above) — simpler, proxy-safe, ticket short-lived.
2. If subprotocol used: test in staging behind Cloudflare BEFORE merging. Document required `proxy_pass_request_headers on` (nginx) or Cloudflare WebSocket setting.
3. Health check: WS connection telemetry from prod confirms subprotocol header arrives.

**Phase to address:** Phase 13 (WS auth design — pick ticket flow, document why). Phase 22 (Cloudflare e2e — verify in staging).

**Source:** [Cloudflare WebSocket guide](https://developers.cloudflare.com/network/websockets/)

---

### 12. API key storage — raw key + timing attack + URL leak

**What goes wrong (multi-pronged):**
- (a) Store raw API key in DB → DB leak = customer keys leaked → GitHub credential scanner fires, Stripe/competitors phish.
- (b) Hash key with bcrypt/argon2 + lookup by FOR EACH key in table → 10k keys × 150ms = 25 minutes per request.
- (c) Use `==` instead of `secrets.compare_digest` for hash compare → timing attack reveals prefix.
- (d) Accept key in `?api_key=` query → ends in access logs + browser history + Sentry breadcrumbs.
- (e) Pass key via env to subprocess → `ps auxe` exposes to other users on host.

**Why it happens:**
- Bare-minimum docs show `db.query(Key).filter(key==input)` — naive equality with raw values.
- Hashing all keys + iterating "feels secure" — exhaustively bad.
- Logs/middleware happily log query strings.

**Warning signs:**
- Schema column named `api_key_raw` or `secret_value` storing string
- Lookup time grows with key count
- `?api_key=` appears in access log
- subprocess.run(env={..., 'API_KEY': key}) anywhere

**Prevention:**
1. Format: `whsk_<8-char-prefix>_<32-char-random>`. Store: `prefix VARCHAR(12) UNIQUE INDEX`, `key_hash VARCHAR(64)` (sha256 of full key). Show full key ONCE on creation, never again.
2. Lookup: `SELECT ... WHERE prefix = :prefix LIMIT 1` (indexed, O(log n)). Then `secrets.compare_digest(sha256(input), row.key_hash)`.
3. SHA-256 (not bcrypt/argon2) for API keys — they have full entropy (32 random chars), don't need slow KDF. Constant-time compare mandatory.
4. Bearer header ONLY. Reject `?api_key=` query param at middleware (return 401 with hint).
5. NEVER log the key. Middleware logs prefix only: `whsk_a1b2c3d4_***`.
6. NEVER pass API key via env to subprocess. If absolutely needed, write to memory tmpfile + delete (still risky — avoid).

**Phase to address:** Phase 14 (API key issuance + middleware). `app/core/api_key.py` is single SRP module.

**Source:** [Stripe API key design](https://stripe.com/docs/keys), [GitHub API key handling](https://docs.github.com/en/rest)

---

### 13. Rate limiting — IPv6 /128 vs /64, X-Forwarded-For trust

**What goes wrong:**
- (a) slowapi default `get_remote_address` reads `request.client.host` → behind Cloudflare = ALWAYS Cloudflare IP → ALL traffic looks like one IP → entire service rate-limited as one user.
- (b) Trust `X-Forwarded-For` blindly → attacker spoofs header → bypasses limits.
- (c) IPv6 user limited per /128 (single address) → attacker trivially rotates within /64 (cheap residential pool) → 18 quintillion bypass attempts.
- (d) PROJECT.md says "/24 per IP" — works for IPv4, meaningless for IPv6. Needs /64 prefix for IPv6.
- (e) sqlite as rate-limit storage backend → write contention under burst → 429 latency spikes or lost increments.

**Why it happens:**
- slowapi default config not Cloudflare-aware.
- Devs assume "IP = identity" without considering CGNAT (multiple users 1 IP) and IPv6 (1 user many IPs).

**Warning signs:**
- All requests rate-limited from `172.x` (Cloudflare) IP in dashboard
- Rate limit counter doesn't increment for IPv6 (`request.client.host` is `::1` in dev, real IPv6 in prod)
- Bursts cause `database is locked` errors

**Prevention:**
1. Use `CF-Connecting-IP` header (if Cloudflare proxy confirmed). Validate with allowlist of Cloudflare's IP ranges — reject if `CF-Connecting-IP` set but request didn't come through Cloudflare.
2. Custom key function:
   ```python
   def rate_limit_key(req):
       ip = req.headers.get('cf-connecting-ip') or req.client.host
       try:
           addr = ipaddress.ip_address(ip)
           return str(ipaddress.ip_network(f"{ip}/24" if addr.version==4 else f"{ip}/64", strict=False))
       except: return ip
   ```
3. Storage: in-memory for v1.2 (single uvicorn worker). DOCUMENT: must move to Redis when scaling to >1 worker. NEVER sqlite for rate limit (write contention + WAL conflict with main app writes).
4. Always set `Retry-After` header on 429 (slowapi does, but verify).
5. Test with explicit IPv4 + IPv6 + spoofed XFF cases.

**Phase to address:** Phase 15 (Rate limit + free tier gates). Custom key function in `app/core/rate_limit_key.py`.

**Source:** [Medium: Rate Limiting Wrong IPs SlowAPI](https://medium.com/@amarharolikar/are-you-rate-limiting-the-wrong-ips-a-slowapi-story-88c2755f5318), [slowapi docs](https://slowapi.readthedocs.io/en/latest/)

---

### 14. Stripe-ready schema — silent decisions that hurt later

**What goes wrong:**
v1.2 stubs `Subscription`, `UsageEvent`, `plan_tier`. Mistakes compound when real Stripe lands:
- (a) `plan_tier: str` (free/pro) → typos `Pro` vs `pro`, no DB-level constraint.
- (b) `customer_id: str` nullable, no UNIQUE → user creates 2 Stripe customers, double-billed, support nightmare.
- (c) No `idempotency_key UNIQUE` on `UsageEvent` → webhook replay creates duplicate usage rows → over-billing.
- (d) Hard delete `Subscription` row on cancel → can't audit "was Pro on date X?", refund disputes lose history.
- (e) `current_period_end: datetime` no TZ → utc/local mismatch, billing cycles drift.
- (f) JSON blob "metadata" instead of explicit columns → can't query "all users on free tier".

**Why it happens:**
- "We'll fix it when Stripe is real" — but real Stripe migration is 10x harder with bad schema.
- Stripe's webhook format teaches `idempotency_key` AFTER first duplicate-charge incident.

**Warning signs:**
- `plan_tier` is `String` not `Enum` with check constraint
- `Subscription.deleted_at` missing
- No `idempotency_key UNIQUE` index on `UsageEvent`
- Datetimes without `timezone=True`

**Prevention:**
1. `plan_tier`: SQLAlchemy `Enum(PlanTier)` Python enum + DB CHECK constraint. v1.2 enum: `FREE = "free"`, `PRO = "pro"`. Add migration when adding `TEAM`.
2. `customer_id`: `String NULL UNIQUE` on User. Idempotent customer creation.
3. `UsageEvent`: `idempotency_key VARCHAR(64) UNIQUE NOT NULL`, `stripe_event_id VARCHAR(64) UNIQUE NULL` (for webhook replay protection).
4. Subscription soft-delete: `cancelled_at TIMESTAMP NULL`, `status` enum (`active`, `cancelled`, `past_due`). NEVER `DELETE FROM subscriptions`.
5. ALL datetime columns: `DateTime(timezone=True)`. SQLAlchemy stores as UTC, converts on read.
6. `current_period_start`, `current_period_end`, `trial_ends_at` as explicit columns NOW — adding columns to populated table later requires backfill.
7. Document constraints in `.planning/research/STACK.md` migration as TYPE-SAFE schema, not "add later".

**Phase to address:** Phase 17 (Stripe schema stub). Single migration with enums + idempotency_key + soft-delete.

**Source:** [Stripe API: idempotency](https://stripe.com/docs/api/idempotent_requests), [Stripe billing events](https://stripe.com/docs/billing/subscriptions/webhooks)

---

### 15. Per-user task scoping — single missed `WHERE user_id = ?` = data leak

**What goes wrong:**
Audit checklist for v1.2 — EVERY endpoint that touches `tasks` MUST filter by `user_id`. Miss ONE → cross-user data exposure. Codebase endpoints to audit:
- `GET /tasks` (`app/api/task_api.py`) — list endpoint
- `GET /tasks/{id}` — detail endpoint
- `DELETE /tasks/{id}`
- `POST /speech-to-text` — must set `user_id` on insert
- `POST /speech-to-text-url` — must set `user_id` on insert
- TUS upload completion (`app/api/tus_upload_api.py:41-49`) — `service.start_transcription(...)` MUST receive user context
- `WS /ws/tasks/{task_id}` (`app/api/websocket_api.py`) — see #10
- Webhook callback (`app/api/callbacks.py`) — incoming webhook updates which user's task?
- `DELETE /api/account/data` — deletes only user's own tasks
- Admin/health endpoints — explicit allowlist

**Why it happens:**
- Tasks router predates auth → easy to forget the filter when migrating.
- Repository pattern abstracts away the WHERE clause → easy to add new method without filter.
- Tests use single user → cross-user bug invisible.

**Warning signs:**
- ANY `repository.get_task_by_id(id)` without user_id parameter
- ANY raw SQL `SELECT * FROM tasks WHERE id = ?` without user_id
- Test suite has only one user fixture

**Prevention:**
1. Refactor `ITaskRepository` interface: every method accepting task_id ALSO accepts `user_id`. NO method returns task without ownership check. Rename `get_task_by_id` → `get_task_by_id_for_user(user_id, task_id)`.
2. Type-level enforcement: `Task` model has `user_id: int` non-nullable. Repository returns `None` if mismatch — caller can't bypass.
3. Two-user fixture in EVERY task-touching test: `user_a`, `user_b`. Test asserts `get(user_a, task_b_id) → None`.
4. Audit checklist (this list) becomes acceptance criteria checklist in roadmap.
5. Static check: grep `repository\.\w+\(.*task_id` — every match must show `user_id` in signature.

**Phase to address:** Phase 14 (per-user task scoping). Verification phase explicitly runs cross-user matrix tests.

**Source:** Codebase grep `app/api/task_api.py`, `app/api/audio_api.py`, `app/api/tus_upload_api.py`, `app/api/callbacks.py`, `app/api/websocket_api.py`

---

### 16. Cookie session — secure flag in dev breaks auth, samesite=strict breaks API

**What goes wrong:**
- Dev runs `http://localhost:8000`. Cookie set `Secure` → browser DROPS it (HTTPS-only). Login appears to succeed (200 OK + Set-Cookie) but next request unauthenticated. Devs spend hours debugging.
- Set `SameSite=Strict` → external link to dashboard from email doesn't carry cookie → user "logged out" on click.
- Domain mismatch: cookie set on `app.domain.com` but API at `api.domain.com` → cookie not sent. (Codebase mounts UI + API same origin, so less risk — BUT future split breaks.)

**Why it happens:**
- "Always set Secure in prod" rule applied uniformly to dev.
- SameSite=Strict feels safer, breaks UX silently.

**Warning signs:**
- Login works in prod, fails in local dev (or vice versa)
- Followed link from email → dashboard logged-out state
- Browser DevTools cookie list shows expected cookie missing on request

**Prevention:**
1. `Secure` flag tied to env: `secure=Config.IS_PRODUCTION`. Local dev (http) → `secure=False`. Document in `.env.example`.
2. `SameSite=Lax` (NOT Strict) — sufficient with CSRF token defense in depth. Lax allows top-level GET nav (email links work).
3. Cookie attributes single source: `app/core/auth_cookies.py:set_session_cookie(response, jwt)` — attributes derived from config, used by login/refresh/logout endpoints. SRP.
4. Test matrix: dev (http, Secure=False), prod (https, Secure=True), Lax cross-site GET allowed, Lax cross-site POST blocked.

**Phase to address:** Phase 12 (cookie session). Single source `app/core/auth_cookies.py`.

**Source:** [MDN SameSite cookies](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Set-Cookie/SameSite)

---

### 17. Refresh token rotation race + logout-in-other-tab staleness

**What goes wrong:**
- (a) Tab A and Tab B both initiate refresh simultaneously (parallel API calls fire). Tab A swaps refresh token → server invalidates old → Tab B's refresh fails → Tab B logged out mid-action. User sees random logout.
- (b) User clicks logout in Tab A. Tab B still has old session in memory, makes API call → 401 → confusing UX. Worse: cookie invalidated but localStorage user data still shown.
- (c) Token refresh during in-flight request — 401, no retry queue → request lost, user sees "save failed".

**Why it happens:**
- No cross-tab coordination (BroadcastChannel/storage events).
- Naive fetch wrapper: no retry-on-401 with refresh.
- v1.2 spec says "7d sliding JWT" — sliding adds complexity over fixed expiry.

**Warning signs:**
- Random logout reported by users with multiple tabs
- "Form save failed" but server received it (request retry didn't happen)
- LocalStorage retains user data after logout

**Prevention:**
1. SLIDING expiry on server (refresh JWT silently when <1d remains, single Set-Cookie reissue). NO separate refresh endpoint (avoids race). Decision: 7d cookie, server reissues when <1d left on any authenticated request → no refresh token at all in v1.2 (simpler, less race surface).
2. If MUST have refresh endpoint: use `BroadcastChannel('auth')` — first tab to refresh broadcasts new token, others skip.
3. Fetch wrapper queues in-flight requests during refresh, replays on success, fails all on refresh failure with cohesive error UI.
4. Logout: explicit storage event listener — Tab B receives logout signal, clears state, redirects to login.
5. Test: Playwright multi-tab scenario.

**Phase to address:** Phase 12 (sliding cookie pattern — choose simpler over refresh-token). Phase 16 (frontend cross-tab handling).

**Source:** [MDN BroadcastChannel](https://developer.mozilla.org/en-US/docs/Web/API/BroadcastChannel)

---

### 18. Free tier abuse — registration throttling trivially bypassed

**What goes wrong:**
PROJECT.md says "3/hr per /24" for register. Bypasses:
- (a) IPv6 — /24 not applicable, attacker gets infinite addresses in /64.
- (b) Residential proxy network ($50/mo) — 1000 unique IPs → 3000 accounts/hr = 72k accounts/day.
- (c) Same person, multiple accounts, share API key → defeats per-user rate limit.
- (d) Disposable email (10minutemail.com) — register, get key, abandon, repeat.
- (e) PROJECT.md "no SMTP" → can't email-verify → can't even slow this with email confirmation.

**Why it happens:**
- IP-based limits are 2010-era thinking for 2026 abuse.
- "We'll fix when abuse happens" — by then, free tier costs $$$$ from GPU usage.

**Warning signs:**
- Spike in registrations from disposable email TLDs
- Many accounts with single API key, single transcription, abandoned
- Cost per user > revenue per paid user

**Prevention (layered, since no single defense works):**
1. Disposable email blocklist on registration (e.g., `disposable-email-domains` package) — won't catch all but raises bar.
2. Per /24 (IPv4) AND per /64 (IPv6) registration limits. Both checked.
3. Per-account abuse signal: account creates >N tasks in first hour → flag for review.
4. PROJECT.md: device fingerprint (cookie + UA hash + IP /24 + device_id). Track fingerprint hash → detect "same device, multiple accounts".
5. Free tier strict limits: 5 req/hr, file size cap, duration cap, model cap (already in PROJECT.md). Must SHIP with these — not deferred.
6. Reserve hCaptcha hook (PROJECT.md says "v1.3 if abuse observed") — actually wire it in v1.2, just disabled by env flag. Then enable instantly when abuse hits.
7. API key cannot be reused across accounts — bind key to user_id, audit access log for "same key, different fingerprint" → revoke.

**Phase to address:** Phase 15 (rate limit + free tier gates). Disposable email + fingerprint logging baseline. hCaptcha integration scaffolded, env-flagged off.

**Source:** PROJECT.md anti-DDOS requirements, [disposable-email-domains list](https://github.com/disposable-email-domains/disposable-email-domains)

---

### 19. Frontend test infrastructure — vitest mocking pitfalls

**What goes wrong:**
- (a) `vi.spyOn(global, 'fetch')` in `beforeEach` without restore → leaks across tests, flaky failures.
- (b) MSW handler order: tests register handlers per-test, but global `setupServer` already has handler → registration order matters, last-registered wins → confusing.
- (c) Auth flow uses async + redirect + cookie set → React Testing Library `act()` warnings flood console → real warnings buried.
- (d) Mock fetch returns synchronous → async auth refresh logic doesn't behave like real fetch → tests pass, prod fails.
- (e) Token in test fixtures committed to git → real test bearer token leaked.

**Why it happens:**
- Vitest + RTL + MSW are new to project (PROJECT.md confirms — "Frontend test infrastructure" still active item).
- React 19 + concurrent rendering + async auth = act() pain.

**Warning signs:**
- Test order matters (run alone passes, run-with-suite fails)
- "Warning: An update to X inside a test was not wrapped in act(...)" floods CI
- `Authorization: Bearer abc123` in committed fixture file
- Tests pass but localhost manual test fails with same code

**Prevention:**
1. MSW setupServer at root, global handlers; per-test override via `server.use()`. `afterEach: server.resetHandlers()`.
2. NEVER use `vi.spyOn(global, 'fetch')` — use MSW. Single source of truth.
3. RTL: wrap user-event in `await user.click()` (await everything async). Use `findByRole` not `getByRole` for post-render queries.
4. Test fixtures NEVER contain real tokens — generate with `crypto.randomUUID()` per test, or use literal `"test-token"`.
5. Lint: `import.meta.env.VITE_TEST_TOKEN` is `.env.test.local` only, gitignored.
6. Set up `vitest.config.ts` with `setupFiles: ['./src/tests/setup.ts']` — single MSW + global mocks bootstrap.

**Phase to address:** Phase 16 (frontend test infra). `setup.ts` is single source.

**Source:** [MSW best practices](https://mswjs.io/docs/best-practices/), [RTL act warnings](https://github.com/testing-library/react-testing-library/issues/1051)

---

### 20. DRY/SRP violation — auth code duplicated across middleware/api/ws

**What goes wrong:**
Codebase will end with:
- `app/core/auth.py` (BearerAuthMiddleware) decoding token
- `app/api/dependencies.py` `get_current_user()` decoding token (different impl)
- `app/api/websocket_api.py` decoding ticket (third impl)
- `app/api/tus_upload_api.py` separate auth check (fourth)

Four places parsing tokens → inconsistent error messages, missed `algorithms=` arg in one, security divergence over time. CLAUDE.md says CAVEMAN + DRT (DRY).

**Why it happens:**
- Each subsystem has different auth source (header/cookie/query/ticket) so devs duplicate.
- "Fix in one place" misses others.

**Warning signs:**
- More than one `jwt.decode` call site
- More than one `BearerAuthMiddleware`-style class
- Differing 401 response shapes across endpoints

**Prevention:**
1. Single `app/core/auth_resolver.py`:
   - `resolve_auth(request) -> AuthContext | None` — checks cookie session, falls through to Bearer API key, returns user/scope.
   - Used by middleware, FastAPI dependency, WS pre-accept.
2. Single `app/core/jwt_codec.py` — `encode_session()`, `decode_session()`. Hard-coded HS256.
3. Single `app/core/api_key.py` — `verify_api_key()`. Prefix lookup + constant-time compare.
4. Single `app/core/auth_cookies.py` — `set_session_cookie()`, `clear_session_cookie()`. Centralizes Secure/SameSite/path.
5. Audit lint: `import jwt` or `from jose import jwt` allowed ONLY in `app/core/jwt_codec.py`. Use `ruff` rule or unit test asserting import locations.
6. WS auth bridges to same resolver via cookie OR ticket (but ticket validation also lives in single place).

**Phase to address:** Phase 12 set up modules; every subsequent phase imports from there. Architecture review at Phase 13 verifies no duplication.

**Source:** CLAUDE.md (DRT, SRP), codebase `app/core/auth.py`

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Keep `Base.metadata.create_all()` alongside Alembic | "Just works" in dev | Schema drift, migrations skipped on prod, NOT NULL backfill failures | **Never** — remove in same commit Alembic introduced |
| `nullable=True` user_id "for now" | No backfill needed | Forgotten forever, all queries become `WHERE user_id IS NOT NULL OR ...`, data leak risk | **Never** for production data — only intermediate migration step |
| Skip CSRF "because we use JWT" | Less code | Lax 2-min window, GET state-change, drive-by attacks | **Never** for cookie auth |
| Allow `?api_key=` in query | Easier curl testing | Logged everywhere, leaked in browser history, support nightmare | **Never** — Bearer header only |
| `plan_tier: str` instead of enum | Faster initial dev | Typos in prod data, "Pro" vs "pro" data quality bugs, expensive cleanup | **Never** for billing data |
| Hard-delete subscription on cancel | Simpler | No audit, refund disputes lose history, GDPR ambiguity | **Never** — soft-delete |
| In-memory rate limit storage | Zero infra | Resets on restart, doesn't scale to >1 worker | OK for v1.2 single-worker, MUST migrate to Redis before horizontal scale |
| Disposable email blocklist | Quick abuse mitigation | Lists go stale, false positives | OK as one layer of defense, not sole defense |
| Same DB for app + rate limiter | Single connection pool | Write contention, locks, WAL conflicts | **Never** for high-write rate-limit; OK for low-rate (<10 req/sec total) |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Cloudflare proxy | Trust `X-Forwarded-For` blindly | Use `CF-Connecting-IP`, validate request actually came through CF |
| Cloudflare WS | Subprotocol header for auth | Use query-string ticket (single-use, 60s) |
| tuspyserver | Mount under same auth as REST | Wrap mount with API-key-only auth dep; disable cookie path |
| python-jose | `jwt.decode(token, secret)` | `jwt.decode(token, secret, algorithms=['HS256'])` always |
| argon2-cffi | Default params | OWASP `m=19456, t=2, p=1`; benchmark on prod |
| slowapi | Default key function | Custom: CF-Connecting-IP + IPv6 /64 + IPv4 /24 |
| Stripe (future) | No idempotency key column | Add `idempotency_key UNIQUE NOT NULL` to UsageEvent NOW |
| MSW | `vi.spyOn(global, 'fetch')` | MSW `setupServer` + per-test `server.use()` |
| FastAPI WS | `BearerAuthMiddleware` covers WS | It does NOT — WS upgrade bypasses HTTP middleware |
| FastAPI cookie + CORS `allow_origins=["*"]` | Browser silently rejects | Explicit origin allowlist with `allow_credentials=True` |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Argon2 m_cost too high | Login p99 > 500ms, OOM under burst | Benchmark on prod hardware, target ~150ms | First concurrent login spike (10+ simultaneous) |
| API key hash lookup linear scan | Bearer auth slow as user count grows | Prefix-indexed lookup + sha256 compare | >1000 keys in DB |
| sqlite WAL contention | "database is locked" errors | Move rate-limit to in-memory; keep app DB separate | Webhook + rate-limit + login concurrent writes |
| JWT decode per request without caching | High CPU under load | Cache user lookup by session ID for request lifetime | >100 req/sec sustained |
| Unindexed `user_id` queries | Task list slow as DB grows | `INDEX idx_tasks_user_id ON tasks(user_id)` | >10k tasks in DB |
| Per-request DB connection (no pool) | Connection storms, slow auth | Verify SQLAlchemy pool config (default OK, but verify) | Burst traffic |
| WebSocket ticket table grows unbounded | Slow ticket validation, disk fill | TTL cleanup (60s) + index on (ticket, expires_at) | >1k WS connections/day |

---

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Token in WS URL query | Logged everywhere | Single-use 60s ticket, not session token |
| `algorithms=None` on JWT decode | alg=none bypass | Hard-code `algorithms=["HS256"]` in single codec module |
| API key in query string | Leaked in logs/history | Bearer header only, reject query param |
| `==` compare for tokens/hashes | Timing attack | `secrets.compare_digest` always |
| Cookie without `HttpOnly` | XSS exfil | `HttpOnly; Secure; SameSite=Lax` |
| `allow_origins=["*"]` with cookies | CORS broken / CSRF wide open | Explicit origin allowlist |
| GET endpoint mutates state | SameSite=Lax bypass | Lint: `@router.get` is read-only |
| Plaintext password in logs | DB leak surfaces actual passwords | Strip auth fields from request logging middleware |
| Reuse same secret for cookie + API key signing | Compromise = total breach | Separate secrets per purpose, env vars |
| API key shown only once not enforced | UX promises broken, support load | Modal with copy button + checkbox "I saved it" |
| Account share via API key (1 key, 100 users) | Free tier abused | Bind device fingerprints to key; alert on N distinct fingerprints |

---

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Login session timeout silent | Form data lost | Sliding expiry; warning banner at 1d remaining |
| Logout in one tab leaves other stale | "I clicked save and got 401" | BroadcastChannel sync; redirect on storage event |
| API key shown only on creation, no warn | User loses key, contacts support | Modal: "save now" + checkbox to dismiss + revoke/regenerate flow |
| 429 with no Retry-After | User mashes button, makes worse | Always set header; frontend disables button + countdown |
| Trial countdown invisible | User surprised by paywall | Header banner: "Trial: 3 days left" |
| Password reset is `mailto:` | User confused, expects auto-flow | Clear UI: "Email us at hey@logingrupa.lv" — explain it's manual |
| CSRF token expires mid-form | "Submission failed" no recovery | Refresh token on form mount; retry with fresh token on 403 |
| Multi-tab login race | Random redirects | BroadcastChannel("auth"); coordinate with leader-election if needed |
| API key in error message | User panics seeing key in UI | Never echo key — show prefix only `whsk_a1b2c3d4_***` |

---

## "Looks Done But Isn't" Checklist

- [ ] **WebSocket auth:** Often missing user_id check on `task_id` ownership — verify `test_ws_user_a_cannot_subscribe_user_b_task` exists and passes
- [ ] **TUS upload auth:** Often missing Bearer check on `/uploads/files/*` — verify cross-origin upload without API key returns 401
- [ ] **Per-user task scoping:** Often missing on ONE endpoint — audit grep `task_repository\.\w+\(.*task_id` shows `user_id` in every signature
- [ ] **CSRF token:** Often missing on `DELETE /api/account/data` — verify cross-origin DELETE without `X-CSRF-Token` returns 403
- [ ] **JWT algorithm pinning:** Often missing `algorithms=["HS256"]` — grep `jwt.decode` returns single result (in jwt_codec.py) with explicit algorithms arg
- [ ] **API key timing-safe compare:** Often missing — verify `secrets.compare_digest` used; `==` for hash compare absent
- [ ] **`Base.metadata.create_all()` removed:** Often forgotten when Alembic introduced — verify line gone from `app/main.py`
- [ ] **PRAGMA foreign_keys=ON:** Often forgotten on SQLite — verify event listener exists; FK constraints actually enforce
- [ ] **Idempotency key on UsageEvent:** Often deferred to "when Stripe is real" — verify schema has `UNIQUE NOT NULL` constraint NOW
- [ ] **CF-Connecting-IP:** Often defaulted to remote_address — verify rate-limit key function uses CF header behind Cloudflare
- [ ] **Disposable email blocklist:** Often skipped — verify registration rejects 10minutemail/mailinator domains
- [ ] **MSW setup file:** Often duplicated per-test — verify single `vitest.config.ts` setupFiles entry
- [ ] **No `localStorage.setItem('token', ...)`:** Verify ESLint rule blocks; grep frontend src returns 0 matches
- [ ] **CORS allow_origins explicit:** Often left as `["*"]` — verify single env-driven allowlist in `app/main.py`
- [ ] **Method override middleware absent:** Verify no `?_method=` or `X-HTTP-Method-Override` honored
- [ ] **Plan tier enum CHECK constraint:** Often `String` — verify migration `CREATE TYPE plan_tier ...` or SQLAlchemy `Enum`
- [ ] **Subscription soft-delete:** Often missing `cancelled_at` — verify column exists and HARD delete absent from code
- [ ] **Datetime columns timezone-aware:** Verify `DateTime(timezone=True)` on all auth/billing columns

---

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| `Base.metadata.create_all()` left in alongside Alembic | LOW | Remove line + verify migrations include all tables + redeploy |
| user_id NOT NULL migration fails on populated DB | MEDIUM | Restore backup, redo migration with nullable→backfill→not-null three-step |
| Cross-user task leak via missed WHERE | HIGH | Audit access logs for cross-user task views, notify affected users (GDPR), patch + add cross-user test matrix |
| Hashed API key with bcrypt + linear scan | MEDIUM | Add prefix column + index, migrate hash to sha256 (re-issue keys to users), drop bcrypt |
| JWT with no `algorithms=` arg | HIGH | Rotate secret, force all sessions invalid, patch jwt_codec.py, redeploy |
| API key leaked in URL query logs | HIGH | Revoke all keys, force user re-issue, audit log retention, grep historical logs |
| WS no auth, task_id leaked | HIGH | Implement ticket flow URGENTLY, audit WS logs for cross-user subscriptions, notify affected users |
| Subscription hard-deleted, can't audit | MEDIUM | Restore from backup, add `cancelled_at` column, replay cancellation events |
| `plan_tier` data inconsistent (Pro vs pro) | LOW | UPDATE migration: `LOWER(plan_tier)` + add CHECK constraint |
| Argon2 params too low, hashes weak | MEDIUM | Bump params; on next login, rehash and update DB (passlib `needs_update` pattern) |

---

## Pitfall-to-Phase Mapping

Roadmap phases v1.2 (proposed numbering 11-22, post v1.1's phase 9 + deferred 10):

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| 1 — user_id FK backfill | Phase 11 (Alembic baseline) + Phase 14 (per-user scoping) | Migration tested against `records.db` copy |
| 2 — SQLite ALTER limits | Phase 11 (Alembic baseline) | All migrations use `batch_alter_table`; PRAGMA listener registered |
| 3 — Alembic baseline diff | Phase 11 (Alembic baseline) | First migration is hand-written mirror; `alembic stamp` documented |
| 4 — Argon2 DoS | Phase 12 (Auth core) | Benchmark test asserts <300ms p99 |
| 5 — Bcrypt 72-byte | Phase 12 (Auth core) | Pydantic max_length=128; no passlib in deps |
| 6 — JWT alg confusion | Phase 12 (Auth core) | jwt_codec.py is single decode site; alg=none test passes |
| 7 — JWT storage XSS/CSRF | Phase 12 + Phase 13 | Cookie attrs verified; localStorage grep clean |
| 8 — SameSite Lax bypass | Phase 13 (CSRF + cookie hardening) | All state-change endpoints POST/PUT/DELETE; CSRF token check enforced |
| 9 — TUS CSRF | Phase 13 + Phase 14 | TUS endpoints API-key-only; allow_origins explicit |
| 10 — WS cross-user leak | Phase 13 (WS auth ticket) | Cross-user matrix test passes |
| 11 — WS subprotocol stripping | Phase 13 (WS auth) | Use ticket query param; staging behind CF verified |
| 12 — API key storage | Phase 14 (API keys) | Prefix-indexed lookup + sha256 + constant-time compare; query-param rejected |
| 13 — Rate limit IP/proxy | Phase 15 (rate limit + free tier) | Custom key function + CF-Connecting-IP test |
| 14 — Stripe schema | Phase 17 (Stripe stub) | Enum + idempotency_key UNIQUE + soft-delete in migration |
| 15 — Per-user task scoping | Phase 14 (per-user scoping) | Endpoint audit checklist + cross-user test matrix |
| 16 — Cookie attrs dev/prod | Phase 12 (Auth core) | auth_cookies.py single source; env-driven Secure |
| 17 — Refresh race / multi-tab | Phase 12 (sliding cookie) + Phase 18 (frontend integration) | BroadcastChannel logout sync; in-flight retry queue |
| 18 — Free tier abuse | Phase 15 (rate limit + free tier) | Disposable email blocklist + fingerprint logging + hCaptcha hook |
| 19 — Vitest/MSW pitfalls | Phase 16 (frontend test infra) | Single setup.ts; MSW reset between tests |
| 20 — Auth code duplication | Phase 12 (auth modules) + ongoing | jwt.decode grep returns single import site |

**Suggested phase order rationale:**
1. **Phase 11 — Alembic baseline FIRST.** Cannot do anything else without migration safety.
2. **Phase 12 — Auth core (registration, login, cookie session).** Foundation modules: jwt_codec, password_hasher, auth_cookies.
3. **Phase 13 — CSRF + WS auth + CORS lockdown.** Complete the "secure cookie session" picture before touching tasks.
4. **Phase 14 — Per-user task scoping + API keys + dual auth middleware.** Now safe because auth foundation solid.
5. **Phase 15 — Rate limit + free tier + anti-DDoS.** Once auth works, lock down abuse vectors.
6. **Phase 16 — Frontend test infrastructure.** Vitest/MSW before frontend feature phases — TDD discipline.
7. **Phase 17 — Stripe-ready schema stub.** Pure schema work, no integration.
8. **Phase 18 — Frontend auth pages (login, register, dashboard).** Now backend is stable.
9. **Phase 19 — Admin CLI + bootstrap + verification + e2e.**

---

## Sources

**Authoritative:**
- [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
- [OWASP CSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
- [Alembic Batch Migrations](https://alembic.sqlalchemy.org/en/latest/batch.html)
- [Alembic Cookbook (existing DB)](https://alembic.sqlalchemy.org/en/latest/cookbook.html)
- [argon2-cffi parameters](https://argon2-cffi.readthedocs.io/en/stable/parameters.html)
- [Auth0: Critical JWT vulnerabilities](https://auth0.com/blog/critical-vulnerabilities-in-json-web-token-libraries/)
- [PortSwigger: JWT algorithm confusion](https://portswigger.net/web-security/jwt/algorithm-confusion)
- [PortSwigger: SameSite bypass](https://portswigger.net/web-security/csrf/bypassing-samesite-restrictions)
- [slowapi documentation](https://slowapi.readthedocs.io/en/latest/)
- [Stripe API: idempotency](https://stripe.com/docs/api/idempotent_requests)

**CVEs referenced:**
- CVE-2025-68402 (FreshRSS bcrypt 72-byte)
- CVE-2022-29217 (PyJWT algorithm confusion)
- CVE-2026-22817 (Hono RS256→HS256)
- CVE-2026-23552 (Keycloak cross-realm)
- CVE-2020-7689 (Node bcrypt truncation)

**Codebase references (specific lines):**
- `app/main.py:48` — `Base.metadata.create_all(bind=engine)` to remove
- `app/main.py:172-178` — `allow_origins=["*"]` to lock down
- `app/core/auth.py` — current single-token middleware to replace with dual-auth
- `app/api/websocket_api.py:23-40` — WS endpoint with zero auth
- `app/api/tus_upload_api.py:55-68` — TUS mount with no auth dep
- `app/infrastructure/database/models.py` — Task model needs `user_id` FK

**Community/Implementation:**
- [Pentesterlab: FreshRSS bcrypt truncation](https://pentesterlab.com/blog/freshrss-bcrypt-truncation-auth-bypass)
- [pyca/bcrypt issue #1082](https://github.com/pyca/bcrypt/issues/1082)
- [Medium: Rate limiting wrong IPs](https://medium.com/@amarharolikar/are-you-rate-limiting-the-wrong-ips-a-slowapi-story-88c2755f5318)
- [DEV.to: FastAPI WS auth](https://dev.to/hamurda/how-i-solved-websocket-authentication-in-fastapi-and-why-depends-wasnt-enough-1b68)
- [Peter Braden: WebSocket auth FastAPI](https://peterbraden.co.uk/article/websocket-auth-fastapi/)
- [Pulse Security: SameSite Lax CSRF](https://pulsesecurity.co.nz/articles/samesite-lax-csrf)

---
*Pitfalls research for: v1.2 multi-user auth + API keys + Stripe-ready schema added to existing single-user FastAPI/SQLite/React app*
*Researched: 2026-04-29*
