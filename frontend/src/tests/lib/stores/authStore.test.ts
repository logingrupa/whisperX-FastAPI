/**
 * authStore tests — verify single source of auth state, HTTP delegation
 * to apiClient, and BroadcastChannel('auth') cross-tab sync (UI-04, UI-12).
 *
 * Default MSW handlers (auth.handlers.ts):
 *   POST /auth/login    -> 200 { user_id: 1, plan_tier: 'trial' } (401 when password === 'wrong')
 *   POST /auth/register -> 201 { user_id: 1, plan_tier: 'trial' }
 *   POST /auth/logout   -> 204 No Content
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { useAuthStore } from '@/lib/stores/authStore';

describe('authStore', () => {
  beforeEach(() => {
    useAuthStore.setState({ user: null });
  });

  it('initial state has user=null', () => {
    expect(useAuthStore.getState().user).toBe(null);
  });

  it('login sets user from /auth/login response', async () => {
    await useAuthStore.getState().login('alice@example.com', 'password123');
    const u = useAuthStore.getState().user;
    expect(u).not.toBe(null);
    expect(u!.id).toBe(1);
    expect(u!.email).toBe('alice@example.com');
    expect(u!.planTier).toBe('trial');
  });

  it('login failure (401) leaves user null and propagates error', async () => {
    await expect(
      useAuthStore.getState().login('alice@example.com', 'wrong'),
    ).rejects.toThrow();
    expect(useAuthStore.getState().user).toBe(null);
  });

  it('register sets user from /auth/register response', async () => {
    await useAuthStore.getState().register('bob@example.com', 'password123');
    expect(useAuthStore.getState().user!.email).toBe('bob@example.com');
  });

  it('logout clears user via /auth/logout 204', async () => {
    await useAuthStore.getState().login('alice@example.com', 'password123');
    expect(useAuthStore.getState().user).not.toBe(null);
    await useAuthStore.getState().logout();
    expect(useAuthStore.getState().user).toBe(null);
  });

  it('cross-tab BroadcastChannel logout clears user (UI-12)', async () => {
    await useAuthStore.getState().login('alice@example.com', 'password123');
    expect(useAuthStore.getState().user).not.toBe(null);

    const otherTab = new BroadcastChannel('auth');
    otherTab.postMessage({ type: 'logout' });
    await new Promise((r) => setTimeout(r, 0));
    expect(useAuthStore.getState().user).toBe(null);
    otherTab.close();
  });

  it('login broadcasts a login message on the auth channel', async () => {
    const otherTab = new BroadcastChannel('auth');
    const messages: unknown[] = [];
    otherTab.addEventListener('message', (e) => messages.push(e.data));

    await useAuthStore.getState().login('alice@example.com', 'password123');
    await new Promise((r) => setTimeout(r, 0));

    const loginMsg = messages.find(
      (m) => (m as { type: string }).type === 'login',
    ) as { userId: number; email: string };
    expect(loginMsg).toBeDefined();
    expect(loginMsg.userId).toBe(1);
    expect(loginMsg.email).toBe('alice@example.com');
    otherTab.close();
  });

  it('multiple logins update state idempotently', async () => {
    await useAuthStore.getState().login('alice@example.com', 'password123');
    const first = useAuthStore.getState().user;
    await useAuthStore.getState().login('alice@example.com', 'password123');
    const second = useAuthStore.getState().user;
    expect(first?.email).toBe(second?.email);
  });
});
