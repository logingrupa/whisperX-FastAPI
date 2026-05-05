import { test, expect } from '@playwright/test';
import { freshUser, registerViaApi, BACKEND_BASE } from './_helpers';

/**
 * Phase 19 manual verification #1 (REFACTOR-03):
 *
 * Hard-reload signed-in user lands on `/` (not `/ui/login`).
 *
 * Why this matters: Phase 19 restructured `authenticated_user` and the boot
 * probe (`main.tsx` -> `authStore.refresh()` -> GET /api/account/me). The bug
 * class being eliminated was a session leak that timed out the boot probe
 * after a reload, falsely sending an authenticated user back to /login.
 *
 * Hits the REAL backend through the Vite proxy so the cookie/JWT session is
 * exercised end-to-end. Cannot be done with mocks.
 */
test.describe('phase 19: hard-reload keeps session', () => {
  test('register -> navigate to / -> Ctrl+F5 -> still on /', async ({ page, request }) => {
    const user = freshUser('reload');
    await registerViaApi(request, user);

    await page.goto('/login');
    await page.getByLabel(/email/i).fill(user.email);
    await page.getByLabel(/password/i).fill(user.password);
    await page.getByRole('button', { name: /sign in|log in/i }).click();

    await page.waitForURL(/\/$/, { timeout: 10_000 });
    expect(page.url()).toMatch(/\/$/);

    await page.reload({ waitUntil: 'load' });

    await expect.poll(() => page.url(), { timeout: 10_000 }).toMatch(/\/$/);
    expect(page.url()).not.toContain('/login');

    const meResponse = await page.request.get(`${BACKEND_BASE}/api/account/me`);
    expect(meResponse.status()).toBe(200);
    const body = await meResponse.json();
    expect(body.email).toBe(user.email);
  });
});
