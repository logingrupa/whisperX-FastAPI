import { test, expect } from '../_fixtures/auth';
import { mockUsageSummary, DEFAULT_USAGE_SUMMARY_E2E } from '../_fixtures/mocks';

/**
 * Quick task 260505-l2w — UAT: /dashboard/usage shows real numbers from
 * the mocked GET /api/usage payload (no Phase-14 placeholder strings).
 *
 * Tiger-style boundary asserts:
 *   - h1 "Usage" visible (page rendered, not the auth-redirect)
 *   - Hour quota card contains "2 of 5"
 *   - Daily minutes card contains "7.5 min"
 *   - Plan badge "Trial" present
 *   - Phase-14 "No data yet" stub copy is GONE
 *
 * Screenshots saved per viewport (gitignored under e2e/screenshots/usage-page/).
 */

const VIEWPORTS = [
  { name: 'mobile', width: 375, height: 720 },
  { name: 'tablet', width: 768, height: 900 },
  { name: 'desktop', width: 1280, height: 800 },
] as const;

test.describe('UAT: /dashboard/usage real data', () => {
  test.beforeEach(async ({ signedInPage }) => {
    await mockUsageSummary(signedInPage);
  });

  test('shows real numbers, not "No data yet"', async ({ signedInPage }) => {
    await signedInPage.goto('dashboard/usage');

    // Boundary assert: page reached past auth gate.
    await expect(
      signedInPage.getByRole('heading', { name: /usage/i }),
    ).toBeVisible();

    // Hour quota count "2 of 5".
    await expect(
      signedInPage.getByTestId('hour-quota-count'),
    ).toContainText(`${DEFAULT_USAGE_SUMMARY_E2E.hour_count} of ${DEFAULT_USAGE_SUMMARY_E2E.hour_limit}`);

    // Daily minutes count "7.5 min" appears in the daily-minutes card.
    await expect(
      signedInPage.getByTestId('daily-minutes-count'),
    ).toContainText(/7\.5 min/i);

    // Plan badge "Trial" rendered (use first match — the trial card heading
    // also contains "Trial"; both are valid signals).
    await expect(signedInPage.getByText('Trial').first()).toBeVisible();

    // Phase-14 placeholder copy is GONE.
    await expect(signedInPage.getByText(/no\s+data\s+yet/i)).toHaveCount(0);

    // Per-breakpoint screenshots (gitignored, regen each run).
    for (const viewport of VIEWPORTS) {
      await signedInPage.setViewportSize({
        width: viewport.width,
        height: viewport.height,
      });
      await signedInPage.screenshot({
        path: `e2e/screenshots/usage-page/${viewport.name}.png`,
        fullPage: true,
      });
    }
  });
});
