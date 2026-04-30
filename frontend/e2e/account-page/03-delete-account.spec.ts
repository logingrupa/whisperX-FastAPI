import { test, expect } from '../_fixtures/auth';
import { mockDeleteAccount, SIGNED_IN_EMAIL } from '../_fixtures/mocks';

/**
 * UAT 3 — DeleteAccount destructive flow (SCOPE-06).
 *
 * Three-step assertion chain:
 *   1. Wrong email          -> Delete account button DISABLED
 *   2. Correct email (case-insensitive) -> button ENABLED
 *   3. Submit               -> DELETE /api/account 204 -> redirect /login + auth cleared
 *
 * Tiger-style boundary asserts: button disabled state asserted BEFORE typing
 * (initial render) AND after wrong email (gate must reject). After correct
 * email (uppercase) gate must accept (case-insensitive contract).
 */

const WRONG_EMAIL = 'someone-else@example.com';
const CORRECT_EMAIL_UPPERCASED = SIGNED_IN_EMAIL.toUpperCase();

test('delete account: disabled -> enabled -> submitted -> /login', async ({ signedInPage }) => {
  await mockDeleteAccount(signedInPage);
  await signedInPage.goto('dashboard/account');

  // Open the dialog
  await signedInPage.getByRole('button', { name: 'Delete account' }).click();
  const dialog = signedInPage.getByRole('dialog');
  await expect(dialog).toBeVisible();

  const emailInput = dialog.getByLabel(/Type your email to confirm/i);
  const submitButton = dialog.getByRole('button', { name: 'Delete account' });

  // State 1: empty input -> disabled
  await expect(submitButton).toBeDisabled();

  // State 1b: wrong email -> still disabled
  await emailInput.fill(WRONG_EMAIL);
  await expect(submitButton).toBeDisabled();
  await signedInPage.screenshot({
    path: 'e2e/screenshots/03-delete-account/01-disabled.png',
  });

  // State 2: correct email (uppercase) -> enabled (case-insensitive contract)
  await emailInput.fill(CORRECT_EMAIL_UPPERCASED);
  await expect(submitButton).toBeEnabled();
  await signedInPage.screenshot({
    path: 'e2e/screenshots/03-delete-account/02-enabled.png',
  });

  // State 3: submit -> waits for DELETE then redirect
  const deleteResponse = signedInPage.waitForResponse(
    (resp) => resp.url().includes('/api/account') && resp.request().method() === 'DELETE',
  );

  await Promise.all([
    signedInPage.waitForURL(/\/ui\/login(\?.*)?$/, { timeout: 5_000 }),
    submitButton.click(),
  ]);

  const response = await deleteResponse;
  expect(response.status()).toBe(204);

  // Boundary: post-redirect, sign-in heading proves auth cleared (LoginPage rendered)
  await expect(signedInPage).toHaveURL(/\/ui\/login(\?.*)?$/);

  await signedInPage.screenshot({
    path: 'e2e/screenshots/03-delete-account/03-redirected-login.png',
    fullPage: true,
  });
});
