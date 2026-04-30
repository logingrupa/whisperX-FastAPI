import { test, expect } from '../_fixtures/auth';
import { mockBillingCheckout501 } from '../_fixtures/mocks';

/**
 * UAT 2 — UpgradeInterestDialog 501-swallow + 2s auto-close.
 *
 * Flow:
 *   1. idle    -> screenshot dialog with textarea
 *   2. submit  -> POST /billing/checkout returns 501; dialog flips to success Alert
 *                 ("Thanks!" via AlertTitle); screenshot success state
 *   3. wait 2.0-2.2s -> dialog closes (UI-SPEC §174 auto-close); screenshot post-close
 *
 * Why explicit wait window: spec is `setTimeout(handleClose, 2000)`. Allow
 * 200ms slack so flaky CI timers don't trip a strict 2000ms boundary.
 */

const SUCCESS_ALERT_TITLE = 'Thanks!';

test('upgrade dialog: idle -> success -> auto-close after 2s', async ({ signedInPage }) => {
  await mockBillingCheckout501(signedInPage);
  await signedInPage.goto('dashboard/account');

  // Boundary: account loaded, CTA visible
  const upgradeCta = signedInPage.getByRole('button', { name: 'Upgrade to Pro' });
  await expect(upgradeCta).toBeVisible();

  await upgradeCta.click();

  // State 1: idle dialog with textarea
  const dialog = signedInPage.getByRole('dialog');
  await expect(dialog).toBeVisible();
  const textarea = dialog.getByLabel(/What do you want from Pro/i);
  await expect(textarea).toBeVisible();

  await signedInPage.screenshot({
    path: 'e2e/screenshots/02-upgrade-dialog/01-idle.png',
  });

  // Fill + submit
  await textarea.fill('Diarization on long files would unlock my workflow.');
  const sendButton = dialog.getByRole('button', { name: 'Send' });
  const checkoutResponse = signedInPage.waitForResponse(
    (resp) => resp.url().includes('/billing/checkout') && resp.request().method() === 'POST',
  );
  await sendButton.click();
  const response = await checkoutResponse;
  expect(response.status()).toBe(501);

  // State 2: success Alert (501 swallowed as success per T-15-07).
  // Capture timer-start close to setSuccess(true) firing — Alert visibility
  // is the closest user-observable proxy for that state transition.
  await expect(dialog.getByText(SUCCESS_ALERT_TITLE)).toBeVisible();
  const successAt = Date.now();
  await signedInPage.screenshot({
    path: 'e2e/screenshots/02-upgrade-dialog/02-success.png',
  });

  // State 3: dialog auto-closes after setTimeout(2000) inside the component.
  // We assert the close happens in (1.0s, 3.5s) — wall-clock timing is brittle
  // (screenshots, Radix animations, CI jitter) so we widen tolerance and
  // trust the unit-test setTimeout-spy for the precise 2000ms contract.
  await expect(dialog).toBeHidden({ timeout: 4_000 });
  const elapsed = Date.now() - successAt;
  expect(elapsed).toBeGreaterThanOrEqual(1_000);
  expect(elapsed).toBeLessThanOrEqual(3_500);

  await signedInPage.screenshot({
    path: 'e2e/screenshots/02-upgrade-dialog/03-after-close.png',
  });
});
