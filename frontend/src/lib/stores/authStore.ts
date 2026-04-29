/**
 * Auth store — single source of authentication state (UI-04, UI-12).
 *
 * Locked policy (CONTEXT §86-92):
 *   - Zustand for state (lightweight, no Provider boilerplate)
 *   - BroadcastChannel('auth') for cross-tab sync (UI-12)
 *   - login(): apiClient.post('/auth/login') -> set user -> broadcast 'login'
 *   - register(): apiClient.post('/auth/register') -> set user -> broadcast 'login'
 *   - logout(): apiClient.post('/auth/logout') -> clear user -> broadcast 'logout'
 *
 * Hydration on reload: deferred to Phase 15 (backend has no /api/account/me yet).
 * Post-reload UX: cookie session persists 7 days, but in-memory user is null
 * until next login. RequireAuth redirects to /login?next=<currentUrl> seamlessly.
 *
 * SRP: store does state only. Pages do UI only. apiClient does HTTP only.
 */

import { create } from 'zustand';
import { apiClient } from '@/lib/apiClient';

export interface AuthUser {
  id: number;
  email: string;
  planTier: string;
}

interface AuthLoginResponse {
  user_id: number;
  plan_tier: string;
}

interface BroadcastLoginMessage {
  type: 'login';
  userId: number;
  planTier: string;
  email: string;
}

interface BroadcastLogoutMessage {
  type: 'logout';
}

type BroadcastAuthMessage = BroadcastLoginMessage | BroadcastLogoutMessage;

interface AuthState {
  user: AuthUser | null;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

/** Lazily-constructed channel — defers BroadcastChannel construction until first use. */
let _channel: BroadcastChannel | null = null;
function getChannel(): BroadcastChannel {
  if (_channel === null) {
    _channel = new BroadcastChannel('auth');
  }
  return _channel;
}

function broadcast(message: BroadcastAuthMessage): void {
  getChannel().postMessage(message);
}

/** Apply server response to a fresh AuthUser; client-side email is the form input. */
function toAuthUser(response: AuthLoginResponse, email: string): AuthUser {
  return {
    id: response.user_id,
    email,
    planTier: response.plan_tier,
  };
}

export const useAuthStore = create<AuthState>((set) => {
  // Cross-tab listener: when another tab logs out, clear our user.
  // Login broadcast is informational — the originating tab keeps its own state.
  getChannel().addEventListener('message', (event: MessageEvent) => {
    const data = event.data as BroadcastAuthMessage;
    if (data.type === 'logout') {
      set({ user: null });
    }
  });

  return {
    user: null,

    login: async (email, password) => {
      const response = await apiClient.post<AuthLoginResponse>('/auth/login', {
        email,
        password,
      });
      const user = toAuthUser(response, email);
      set({ user });
      broadcast({ type: 'login', userId: user.id, planTier: user.planTier, email });
    },

    register: async (email, password) => {
      const response = await apiClient.post<AuthLoginResponse>('/auth/register', {
        email,
        password,
      });
      const user = toAuthUser(response, email);
      set({ user });
      broadcast({ type: 'login', userId: user.id, planTier: user.planTier, email });
    },

    logout: async () => {
      await apiClient.post('/auth/logout');
      set({ user: null });
      broadcast({ type: 'logout' });
    },
  };
});
