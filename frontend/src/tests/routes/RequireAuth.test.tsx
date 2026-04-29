/**
 * Plan 15-05 — RequireAuth gate tests.
 *
 * Verifies the isHydrating short-circuit (no redirect-flash on boot) plus the
 * standard authed/unauthed branches. RequireAuth becomes a 3-state gate:
 *   isHydrating=true              -> render null
 *   isHydrating=false, user=null  -> Navigate to /login?next=
 *   isHydrating=false, user=set   -> Outlet
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';

import { RequireAuth } from '@/routes/RequireAuth';
import { useAuthStore } from '@/lib/stores/authStore';

function renderWithRouter(initialPath: string) {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route path="/login" element={<div>login-marker</div>} />
        <Route element={<RequireAuth />}>
          <Route path="/dashboard/keys" element={<div>keys-marker</div>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

describe('RequireAuth', () => {
  beforeEach(() => {
    useAuthStore.setState({ user: null, isHydrating: true });
  });

  it('renders nothing while isHydrating=true (no redirect-flash)', () => {
    useAuthStore.setState({ user: null, isHydrating: true });
    renderWithRouter('/dashboard/keys');
    expect(screen.queryByText('keys-marker')).not.toBeInTheDocument();
    expect(screen.queryByText('login-marker')).not.toBeInTheDocument();
  });

  it('redirects to /login?next= after hydration completes with user=null', () => {
    useAuthStore.setState({ user: null, isHydrating: false });
    renderWithRouter('/dashboard/keys');
    expect(screen.getByText('login-marker')).toBeInTheDocument();
  });

  it('renders Outlet child when user is populated and not hydrating', () => {
    useAuthStore.setState({
      user: {
        id: 1,
        email: 'alice@example.com',
        planTier: 'trial',
        trialStartedAt: null,
        tokenVersion: 0,
      },
      isHydrating: false,
    });
    renderWithRouter('/dashboard/keys');
    expect(screen.getByText('keys-marker')).toBeInTheDocument();
  });
});
