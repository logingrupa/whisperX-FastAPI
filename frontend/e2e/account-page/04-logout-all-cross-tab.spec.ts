import { test, expect } from '../_fixtures/auth';
import { installAccountMocks, mockLogoutAll } from '../_fixtures/mocks';

/**
 * UAT 4 — Logout-all cross-tab BroadcastChannel('auth') propagation.
 *
 * Two same-context pages (tabs) — same browser context shares
 * BroadcastChannel scope. authStore subscribes to 'auth' channel; on receiving
 * `{type: 'logout'}` it sets user=null. RequireAuth then redirects to /login
 * on next render OR navigation.
 *
 * Why same context (not separate contexts): BroadcastChannel is bound by
 * browsing context group / origin. Two `context.newPage()` calls give us
 * "same origin, two tabs" — exactly what the cross-tab UX test requires.
 *
 * Flow:
 *   1. tab A authed at /dashboard/account
 *   2. tab B authed at /dashboard/account
 *   3. tab A -> Sign out everywhere -> 204 + redirect
 *   4. tab B receives BroadcastChannel msg -> user cleared -> redirected on next nav
 */

test('logout-all propagates across tabs via BroadcastChannel', async ({
  context,
  signedInPage: tabA,
}) => {
  // Tab A (signed-in via fixture). Mount logout-all mock + open second tab.
  await mockLogoutAll(tabA);
  await tabA.goto('dashboard/account');
  await expect(tabA.getByRole('heading', { name: 'Account', level: 1 })).toBeVisible();

  // Tab B — same context => shared BroadcastChannel scope. Mount its own
  // mocks (page.route is per-page).
  const tabB = await context.newPage();
  await installAccountMocks(tabB);
  await mockLogoutAll(tabB);
  await tabB.goto('dashboard/account');
  await expect(tabB.getByRole('heading', { name: 'Account', level: 1 })).toBeVisible();
  await tabB.screenshot({
    path: 'e2e/screenshots/04-logout-all-cross-tab/01-tab-b-before.png',
    fullPage: true,
  });

  // Tab A: open dialog -> confirm
  await tabA.getByRole('button', { name: 'Sign out of all devices' }).click();
  const dialogA = tabA.getByRole('dialog');
  await expect(dialogA).toBeVisible();

  const logoutResp = tabA.waitForResponse(
    (resp) => resp.url().includes('/auth/logout-all') && resp.request().method() === 'POST',
  );
  await Promise.all([
    tabA.waitForURL(/\/ui\/login(\?.*)?$/, { timeout: 5_000 }),
    dialogA.getByRole('button', { name: 'Sign out everywhere' }).click(),
  ]);
  const response = await logoutResp;
  expect(response.status()).toBe(204);
  await expect(tabA).toHaveURL(/\/ui\/login(\?.*)?$/);

  // Tab B: BroadcastChannel listener inside zustand store sets user=null.
  // RequireAuth subscribes to user via useAuthStore -> re-renders -> redirect
  // happens in-place WITHOUT a full reload. Wait for the URL change.
  await expect(tabB).toHaveURL(/\/ui\/login(\?.*)?$/, { timeout: 5_000 });

  await tabB.screenshot({
    path: 'e2e/screenshots/04-logout-all-cross-tab/02-tab-b-after.png',
    fullPage: true,
  });
});
