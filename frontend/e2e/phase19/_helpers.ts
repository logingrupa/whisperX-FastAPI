import type { APIRequestContext, Page } from '@playwright/test';

export const BACKEND_BASE = 'http://127.0.0.1:5273';

export interface RealUser {
  email: string;
  password: string;
}

export function freshUser(tag: string): RealUser {
  const stamp = Date.now();
  const rand = Math.random().toString(36).slice(2, 8);
  return {
    email: `phase19-${tag}-${stamp}-${rand}@e2e-auto.dev`,
    password: 'TestPassword!23456',
  };
}

export async function registerViaApi(
  request: APIRequestContext,
  user: RealUser,
): Promise<void> {
  const response = await request.post(`${BACKEND_BASE}/auth/register`, {
    data: { email: user.email, password: user.password },
    headers: { 'Content-Type': 'application/json' },
  });
  if (response.status() !== 201) {
    throw new Error(`register expected 201, got ${response.status()}: ${await response.text()}`);
  }
}

export async function loginViaApi(
  request: APIRequestContext,
  user: RealUser,
): Promise<{ status: number; durationMs: number }> {
  const start = performance.now();
  const response = await request.post(`${BACKEND_BASE}/auth/login`, {
    data: { email: user.email, password: user.password },
    headers: { 'Content-Type': 'application/json' },
  });
  const durationMs = performance.now() - start;
  return { status: response.status(), durationMs };
}

export async function logoutViaApi(request: APIRequestContext): Promise<void> {
  const cookies = await request.storageState();
  const csrf = cookies.cookies.find((c) => c.name === 'csrf_token')?.value ?? '';
  await request.post(`${BACKEND_BASE}/auth/logout`, {
    headers: { 'X-CSRF-Token': csrf },
  });
}

export async function clearAuthCookies(page: Page): Promise<void> {
  await page.context().clearCookies();
}
