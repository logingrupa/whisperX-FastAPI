import { test, expect, request as pwRequest } from '@playwright/test';
import { freshUser, registerViaApi, loginViaApi, BACKEND_BASE } from './_helpers';

/**
 * Phase 19 manual verification #2 (user-stated bug — login latency):
 *
 * After Phase 19's structural elimination of the per-request session leak,
 * sequential logins must complete in < 1s wall-clock.
 *
 * Spec said "20 sequential logins all complete < 1s" but the backend rate
 * limiter caps `/auth/login` at 10/hour per /24 IP (see auth_routes.py:161
 * `@limiter.limit("10/hour")`). Running 20 from localhost guarantees a 429
 * after #10 — no env bypass exists today. So we run 10 (the cap) which is
 * enough to detect the regression class (a single session leak compounds
 * within 2-3 cycles, not 20).
 *
 * Hits real backend via Vite proxy. Each iteration uses a FRESH request
 * context so cookies don't accumulate (mimics independent fetch from a
 * fresh tab — strictest perf test).
 */
test.describe('phase 19: login latency under 1s', () => {
  test('sequential logins each complete < 1000ms (until rate-limit cap)', async ({ request }) => {
    const user = freshUser('latency');
    await registerViaApi(request, user);

    const MAX_ATTEMPTS = 10;
    const MIN_SAMPLES = 3;
    const THRESHOLD_MS = 1000;
    const durations: number[] = [];

    for (let i = 0; i < MAX_ATTEMPTS; i++) {
      const isolatedContext = await pwRequest.newContext();
      const result = await loginViaApi(isolatedContext, user);
      await isolatedContext.dispose();

      if (result.status === 429) {
        console.log(
          `[phase19/login-latency] hit rate limit at attempt #${i + 1} — collected ${durations.length} samples (per-IP login budget shared with other tests/manual traffic)`,
        );
        break;
      }

      expect(result.status, `login #${i + 1} status`).toBe(200);
      expect(result.durationMs, `login #${i + 1} duration`).toBeLessThan(THRESHOLD_MS);
      durations.push(result.durationMs);
    }

    expect(
      durations.length,
      `need at least ${MIN_SAMPLES} successful logins to claim p99 — got ${durations.length}; rate budget likely exhausted, wait an hour and retry`,
    ).toBeGreaterThanOrEqual(MIN_SAMPLES);

    const sorted = [...durations].sort((a, b) => a - b);
    const p50 = sorted[Math.floor(sorted.length * 0.5)];
    const max = sorted[sorted.length - 1];
    console.log(
      `[phase19/login-latency] samples=${sorted.length} p50=${p50.toFixed(0)}ms max=${max.toFixed(0)}ms threshold=${THRESHOLD_MS}ms`,
    );

    expect(max).toBeLessThan(THRESHOLD_MS);
  });

  test('rate-limit guard: 11th login returns 429 (proves cap is enforced, not bypassed)', async ({ request }) => {
    test.skip(
      !process.env.PHASE19_FULL_RATE_LIMIT_PROBE,
      'Set PHASE19_FULL_RATE_LIMIT_PROBE=1 to exercise the 11th-login 429 — eats the per-IP login budget for 1 hour',
    );

    const user = freshUser('ratelimit');
    await registerViaApi(request, user);

    let lastStatus = 200;
    for (let i = 0; i < 11; i++) {
      const ctx = await pwRequest.newContext();
      const r = await loginViaApi(ctx, user);
      await ctx.dispose();
      lastStatus = r.status;
    }
    expect(lastStatus, '11th login should be rate-limited').toBe(429);
    void BACKEND_BASE;
  });
});
