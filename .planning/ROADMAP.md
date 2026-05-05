# Roadmap: WhisperX

## Milestones

- ✅ **v1.0 Frontend UI** — Phases 1-6 (shipped 2026-01-29) — see [milestones/v1.0-ROADMAP.md](milestones/v1.0-ROADMAP.md)
- ✅ **v1.1 Chunked Uploads** — Phases 7-9 (shipped 2026-02-05; phase 10 Cloudflare deferred to v1.3)
- ✅ **v1.2 Multi-User Auth + API Keys + Billing-Ready** — Phases 10-19 (shipped 2026-05-05) — see [milestones/v1.2-ROADMAP.md](milestones/v1.2-ROADMAP.md)
- 📋 **v1.3** — planned (Cloudflare e2e + deferred Phase 18 stretch items + observed v1.2 close-out items) — kick off via `/gsd-new-milestone`

## Phases

<details>
<summary>✅ v1.0 Frontend UI (Phases 1-6) — SHIPPED 2026-01-29</summary>

See [milestones/v1.0-ROADMAP.md](milestones/v1.0-ROADMAP.md) for full phase details.

</details>

<details>
<summary>✅ v1.1 Chunked Uploads (Phases 7-9) — SHIPPED 2026-02-05</summary>

- [x] Phase 7: Chunked Upload Foundation — completed 2026-02-05
- [x] Phase 8: Frontend Chunking — completed 2026-02-05
- [x] Phase 9: Resilience and Polish — completed 2026-02-05

Phase 10 (Cloudflare e2e) was deferred to v1.3.

</details>

<details>
<summary>✅ v1.2 Multi-User Auth + API Keys + Billing-Ready (Phases 10-19) — SHIPPED 2026-05-05</summary>

- [x] Phase 10: Alembic Baseline + Auth Schema (4/4 plans) — completed 2026-04-29
- [x] Phase 11: Auth Core Modules + Services + DI (5/5 plans) — completed 2026-04-29
- [x] Phase 12: Admin CLI + Task Backfill (4/4 plans) — completed 2026-04-29
- [x] Phase 13: Atomic Backend Cutover (10/10 plans, atomic pair w/ 14) — completed 2026-04-29
- [x] Phase 14: Atomic Frontend Cutover + Test Infra (7/7 plans, atomic pair w/ 13) — completed 2026-04-29
- [x] Phase 15: Account Dashboard Hardening + Billing Stubs (6/6 plans) — completed 2026-04-29
- [x] Phase 16: Verification + Cross-User Matrix + E2E (6/6 plans) — completed 2026-04-30
- [x] Phase 17: Docs + Migration Runbook + Operator Guide (3/3 plans) — completed 2026-05-01
- [x] Phase 18: Stretch (Optional, closed empty — features deferred to v1.3+) — 2026-05-01
- [x] Phase 19: Auth + DI Structural Refactor (17/17 plans, 21/21 gates verified) — completed 2026-05-05

See [milestones/v1.2-ROADMAP.md](milestones/v1.2-ROADMAP.md) for full phase details.

</details>

### 📋 v1.3 (Planned)

To be defined via `/gsd-new-milestone`. Likely candidates:
- Cloudflare e2e (deferred from v1.1 phase 10)
- Phase 18 stretch items (hCaptcha enable, HaveIBeenPwned check, per-key scopes UI, per-key expiration)
- Observability for ffmpeg / external-binary dependencies
- Multi-worker rate-limit storage (slowapi → redis/limits)

## Progress

| Milestone | Phases | Status | Shipped |
|-----------|--------|--------|---------|
| v1.0 Frontend UI | 1-6 | ✅ Complete | 2026-01-29 |
| v1.1 Chunked Uploads | 7-9 | ✅ Complete | 2026-02-05 |
| v1.2 Multi-User Auth + API Keys + Billing-Ready | 10-19 | ✅ Complete | 2026-05-05 |
| v1.3 | TBD | 📋 Planned | — |

---
*Last updated: 2026-05-05 — v1.2 milestone shipped*
