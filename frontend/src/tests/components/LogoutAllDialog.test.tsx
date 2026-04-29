/**
 * Plan 15-06 Task 2 — LogoutAllDialog RTL coverage.
 *
 * Covers (AUTH-06 client paths):
 *   - confirm -> calls authStore.logout + navigates /login
 *   - 429 surfaces "Rate limited. Try again in {n}s." copy
 *   - other errors surface "Could not sign out. Try again." copy
 *
 * TEST-05 invariants honored — async clicks awaited; findByRole/findByText
 * after every state change.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { MemoryRouter, Routes, Route } from 'react-router-dom';

import { LogoutAllDialog } from '@/components/dashboard/LogoutAllDialog';
import { useAuthStore } from '@/lib/stores/authStore';
import { server } from '@/tests/setup';

function renderDialog() {
  return render(
    <MemoryRouter initialEntries={['/here']}>
      <Routes>
        <Route
          path="/here"
          element={<LogoutAllDialog open onOpenChange={() => {}} />}
        />
        <Route path="/login" element={<div>login-marker</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('LogoutAllDialog', () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: {
        id: 1,
        email: 'alice@example.com',
        planTier: 'trial',
        trialStartedAt: null,
        tokenVersion: 0,
      },
      isHydrating: false,
      logoutLocal: vi.fn(),
    });
  });

  it('confirm calls authStore.logoutLocal + navigates /login', async () => {
    const logoutLocalSpy = vi.fn();
    useAuthStore.setState({ logoutLocal: logoutLocalSpy });
    const user = userEvent.setup();
    renderDialog();
    await user.click(
      await screen.findByRole('button', { name: /sign out everywhere/i }),
    );
    expect(await screen.findByText('login-marker')).toBeInTheDocument();
    expect(logoutLocalSpy).toHaveBeenCalled();
  });

  it('429 shows rate-limit copy', async () => {
    server.use(
      http.post('/auth/logout-all', () =>
        HttpResponse.json(
          { detail: 'rate' },
          { status: 429, headers: { 'Retry-After': '15' } },
        ),
      ),
    );
    const user = userEvent.setup();
    renderDialog();
    await user.click(
      await screen.findByRole('button', { name: /sign out everywhere/i }),
    );
    expect(await screen.findByText(/rate limited/i)).toBeInTheDocument();
    expect(await screen.findByText(/15s/)).toBeInTheDocument();
  });

  it('other error shows generic copy', async () => {
    server.use(
      http.post('/auth/logout-all', () =>
        HttpResponse.json({ detail: 'boom' }, { status: 500 }),
      ),
    );
    const user = userEvent.setup();
    renderDialog();
    await user.click(
      await screen.findByRole('button', { name: /sign out everywhere/i }),
    );
    expect(
      await screen.findByText(/could not sign out/i),
    ).toBeInTheDocument();
  });
});
