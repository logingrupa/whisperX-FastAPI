---
phase: 20
slug: tus-free-tier-gate-wiring-counter-repair
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-06
---

# Phase 20 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x (existing) |
| **Config file** | `pyproject.toml` (already configured) |
| **Quick run command** | `uv run pytest tests/integration/test_tus_upload_session_service.py -x` |
| **Full suite command** | `uv run pytest tests/integration/ tests/unit/` |
| **Estimated runtime** | ~10s quick, ~120s full |

---

## Sampling Rate

- **After every task commit:** Run quick test command for the file under edit
- **After every plan wave:** Run full integration suite
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

> Filled by gsd-planner during planning. Each task in Phase 20 plans must map to one row below.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| _to be filled by planner_ | | | | | | | | | |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/integration/test_tus_upload_session_service.py` — new test module covering REQ-FREETIER-TUS + REQ-USAGE-TUS-COUNTER
- [ ] Existing `tests/integration/conftest.py` fixtures cover RateLimitService + FreeTierGate construction (no new shared fixtures expected)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Real TUS upload via browser → `/dashboard/usage` shows non-zero counters | REQ-USAGE-TUS-COUNTER | End-to-end browser flow validates HTTP-layer integration; automated tests stop at service-layer boundary | 1. Sign in as free-tier user. 2. Upload small file (<5min) via TUS dropzone. 3. Wait for transcribe completion. 4. Visit `/dashboard/usage`. 5. Confirm hour quota = 1 of 5 and daily minutes ≥ 1. |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
