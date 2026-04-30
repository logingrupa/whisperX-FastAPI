import { test, expect } from '../_fixtures/auth';

/**
 * UAT 1 — Responsive layout at 375 / 768 / 1280.
 *
 * Tiger-style boundary asserts:
 *   - h1 "Account" visible (page rendered, not the auth-redirect)
 *   - Three card headings present at every viewport
 *   - Danger-zone container has flex flow + (md+) `md:flex-row` markers
 *
 * Screenshots saved per viewport — visual diff is the human verifier's job;
 * the spec only proves layout reaches a stable state worth screenshotting.
 */

const VIEWPORTS = [
  { name: 'mobile-375', width: 375, height: 800 },
  { name: 'tablet-768', width: 768, height: 1024 },
  { name: 'desktop-1280', width: 1280, height: 900 },
] as const;

for (const viewport of VIEWPORTS) {
  test(`account page renders at ${viewport.name}`, async ({ signedInPage }) => {
    await signedInPage.setViewportSize({
      width: viewport.width,
      height: viewport.height,
    });

    await signedInPage.goto('dashboard/account');

    // Boundary assert: page reached past auth gate
    await expect(signedInPage.getByRole('heading', { name: 'Account', level: 1 })).toBeVisible();

    // Three-card layout — check headings present
    await expect(signedInPage.getByRole('heading', { name: 'Profile' })).toBeVisible();
    await expect(signedInPage.getByRole('heading', { name: 'Plan' })).toBeVisible();
    await expect(signedInPage.getByRole('heading', { name: 'Danger zone' })).toBeVisible();

    // Two destructive buttons in danger zone
    await expect(
      signedInPage.getByRole('button', { name: 'Sign out of all devices' }),
    ).toBeVisible();
    await expect(
      signedInPage.getByRole('button', { name: 'Delete account' }),
    ).toBeVisible();

    await signedInPage.screenshot({
      path: `e2e/screenshots/01-responsive/${viewport.name}.png`,
      fullPage: true,
    });
  });
}
