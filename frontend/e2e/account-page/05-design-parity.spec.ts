import { test, expect } from '../_fixtures/auth';
import { mockKeysEmpty } from '../_fixtures/mocks';

/**
 * UAT 5 — /frontend-design parity: /dashboard/account vs /dashboard/keys.
 *
 * Both pages use the same dashboard chrome (AppShell), the same Card
 * component, the same gap-6 spacing, and the same destructive-tone
 * conventions. Two screenshots at viewport 1280 → human verifier diffs
 * them side-by-side per UI-SPEC contract.
 *
 * Spec asserts only the "page rendered without errors" boundary;
 * pixel-level parity is the human's call.
 */

const VIEWPORT = { width: 1280, height: 900 } as const;

test('design parity: /dashboard/account screenshot at 1280', async ({ signedInPage }) => {
  await signedInPage.setViewportSize(VIEWPORT);
  await signedInPage.goto('dashboard/account');
  await expect(signedInPage.getByRole('heading', { name: 'Account', level: 1 })).toBeVisible();
  await expect(signedInPage.getByRole('heading', { name: 'Danger zone' })).toBeVisible();

  await signedInPage.screenshot({
    path: 'e2e/screenshots/05-design-parity/account-1280.png',
    fullPage: true,
  });
});

test('design parity: /dashboard/keys screenshot at 1280', async ({ signedInPage }) => {
  await mockKeysEmpty(signedInPage);
  await signedInPage.setViewportSize(VIEWPORT);
  await signedInPage.goto('dashboard/keys');

  // Page heading varies — fall back to AppShell-level assertion.
  // Use the Create-key CTA empty-state landmark, which is stable per UI-05.
  await expect(
    signedInPage.getByRole('button', { name: /Create.*key/i }).first(),
  ).toBeVisible();

  await signedInPage.screenshot({
    path: 'e2e/screenshots/05-design-parity/keys-1280.png',
    fullPage: true,
  });
});
