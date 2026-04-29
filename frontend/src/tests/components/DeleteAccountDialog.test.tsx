/**
 * Plan 15-06 Task 2 — DeleteAccountDialog RTL coverage.
 *
 * Covers (SCOPE-06 client paths):
 *   - submit disabled when input empty
 *   - submit enables on case-insensitive email match
 *   - submit -> calls authStore.logout + navigates /login
 *   - 400 mismatch -> shows "Confirmation email does not match." copy
 *
 * Type-match gate (UI-SPEC §214-227): forgiving case + type-exact otherwise.
 *
 * TEST-05 invariants honored — async clicks awaited; findByRole/findByText
 * after every state change.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { MemoryRouter, Routes, Route } from 'react-router-dom';

import { DeleteAccountDialog } from '@/components/dashboard/DeleteAccountDialog';
import { useAuthStore } from '@/lib/stores/authStore';
import { server } from '@/tests/setup';

const STORED_EMAIL = 'alice@example.com';

function renderDialog() {
  return render(
    <MemoryRouter initialEntries={['/dashboard/account']}>
      <Routes>
        <Route
          path="/dashboard/account"
          element={
            <DeleteAccountDialog
              open
              onOpenChange={() => {}}
              userEmail={STORED_EMAIL}
            />
          }
        />
        <Route path="/login" element={<div>login-marker</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('DeleteAccountDialog', () => {
  beforeEach(() => {
    // Seed authStore with a logout fn that resolves so the success path
    // can complete navigate('/login') without hitting /auth/logout MSW.
    useAuthStore.setState({
      user: {
        id: 1,
        email: STORED_EMAIL,
        planTier: 'trial',
        trialStartedAt: null,
        tokenVersion: 0,
      },
      isHydrating: false,
      logoutLocal: vi.fn(),
    });
  });

  it('submit disabled when input empty', async () => {
    renderDialog();
    const submit = await screen.findByRole('button', {
      name: /^delete account$/i,
    });
    expect(submit).toBeDisabled();
  });

  it('submit enables on case-insensitive match', async () => {
    const user = userEvent.setup();
    renderDialog();
    const input = await screen.findByLabelText(/type your email to confirm/i);
    await user.type(input, 'ALICE@example.com');
    expect(
      await screen.findByRole('button', { name: /^delete account$/i }),
    ).toBeEnabled();
  });

  it('submit calls authStore.logoutLocal + navigates /login', async () => {
    const logoutLocalSpy = vi.fn();
    useAuthStore.setState({ logoutLocal: logoutLocalSpy });
    const user = userEvent.setup();
    renderDialog();
    const input = await screen.findByLabelText(/type your email to confirm/i);
    await user.type(input, STORED_EMAIL);
    await user.click(
      screen.getByRole('button', { name: /^delete account$/i }),
    );
    expect(await screen.findByText('login-marker')).toBeInTheDocument();
    expect(logoutLocalSpy).toHaveBeenCalled();
  });

  it('400 from server shows mismatch copy', async () => {
    server.use(
      http.delete('/api/account', () =>
        HttpResponse.json(
          { detail: { error: { code: 'EMAIL_CONFIRM_MISMATCH' } } },
          { status: 400 },
        ),
      ),
    );
    const user = userEvent.setup();
    renderDialog();
    const input = await screen.findByLabelText(/type your email to confirm/i);
    await user.type(input, STORED_EMAIL);
    await user.click(
      screen.getByRole('button', { name: /^delete account$/i }),
    );
    expect(
      await screen.findByText(/confirmation email does not match/i),
    ).toBeInTheDocument();
  });
});
