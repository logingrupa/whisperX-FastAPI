/**
 * Central HTTP client — the SINGLE source for all non-WebSocket
 * network calls in the app (UI-11).
 *
 * Locked policy (CONTEXT §74-79):
 *   - credentials: 'include'   (browser sends cookies)
 *   - X-CSRF-Token header attached from csrf_token cookie on
 *     state-mutating methods (POST/PUT/PATCH/DELETE)
 *   - 401  -> redirect to /login?next=<currentUrl>     (NEVER thrown unless suppressed)
 *   - 429  -> throw RateLimitError(retryAfterSeconds)   (caller renders inline)
 *   - other 4xx/5xx -> throw ApiClientError
 *   - network error -> throw ApiClientError(0, ..., 'NETWORK_ERROR')
 *
 * Tiger-style: assertion at module load that env config is sane.
 */

import { readCookie } from './cookies';
import { getApiBaseUrl } from './config';
import {
  ApiClientError,
  AuthRequiredError,
  RateLimitError,
} from './apiErrors';

const STATE_MUTATING_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

/** True at module load only — guards repeated re-redirects in test envs. */
let _redirectingTo401 = false;

/**
 * Tiger-style boot assertion (CONTEXT §138).
 * In dev/prod we use relative URLs; in tests window.location may be mocked.
 * Fail-loud if someone wired a misconfigured base URL.
 */
function assertEnvSane(): void {
  const base = getApiBaseUrl();
  // base === '' is the locked default — relative URLs everywhere.
  // If someone ever sets a non-relative base it MUST be a full http(s) URL.
  if (base !== '' && !base.startsWith('http')) {
    throw new Error(
      `apiClient: getApiBaseUrl() returned non-relative non-http value "${base}" — refusing to boot`,
    );
  }
}
assertEnvSane();

interface RequestOptions {
  method: string;
  path: string;
  body?: unknown;
  headers?: Record<string, string>;
  /** Set true to suppress automatic 401 redirect — used by authStore.refresh on boot. */
  suppress401Redirect?: boolean;
}

function buildHeaders(opts: RequestOptions): Record<string, string> {
  const headers: Record<string, string> = {
    Accept: 'application/json',
    ...opts.headers,
  };
  if (opts.body !== undefined && !(opts.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
  }
  // CSRF: attach on state-mutating methods when csrf_token cookie present
  if (STATE_MUTATING_METHODS.has(opts.method.toUpperCase())) {
    const csrf = readCookie('csrf_token');
    if (csrf) {
      headers['X-CSRF-Token'] = csrf;
    }
  }
  return headers;
}

function buildBody(opts: RequestOptions): BodyInit | undefined {
  if (opts.body === undefined) return undefined;
  if (opts.body === null) return undefined;
  if (opts.body instanceof FormData) return opts.body;
  return JSON.stringify(opts.body);
}

function redirectTo401(): void {
  if (_redirectingTo401) return;
  _redirectingTo401 = true;
  const next = encodeURIComponent(window.location.pathname + window.location.search);
  window.location.href = `/login?next=${next}`;
}

function parseRetryAfter(headers: Headers): number {
  const raw = headers.get('Retry-After');
  if (!raw) return 60;
  const seconds = Number.parseInt(raw, 10);
  return Number.isFinite(seconds) && seconds > 0 ? seconds : 60;
}

interface ParsedErrorBody {
  detail: string;
  code?: string;
  raw: unknown;
}

async function parseErrorBody(response: Response): Promise<ParsedErrorBody> {
  try {
    const body = (await response.json()) as { detail?: string; code?: string };
    return {
      detail: body.detail ?? `HTTP ${response.status}`,
      code: body.code,
      raw: body,
    };
  } catch {
    return { detail: `HTTP ${response.status}`, raw: null };
  }
}

async function request<T>(opts: RequestOptions): Promise<T> {
  const url = `${getApiBaseUrl()}${opts.path}`;
  let response: Response;
  try {
    response = await fetch(url, {
      method: opts.method,
      credentials: 'include',
      headers: buildHeaders(opts),
      body: buildBody(opts),
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Network error';
    throw new ApiClientError(0, message, 'NETWORK_ERROR');
  }

  if (response.status === 401) {
    const body = await parseErrorBody(response);
    if (!opts.suppress401Redirect) {
      redirectTo401();
    }
    throw new AuthRequiredError(body.raw);
  }

  if (response.status === 429) {
    const body = await parseErrorBody(response);
    const seconds = parseRetryAfter(response.headers);
    throw new RateLimitError(seconds, body.raw);
  }

  if (!response.ok) {
    const body = await parseErrorBody(response);
    throw new ApiClientError(response.status, body.detail, body.code, body.raw);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export const apiClient = {
  get: <T>(path: string, headers?: Record<string, string>) =>
    request<T>({ method: 'GET', path, headers }),
  post: <T>(path: string, body?: unknown, opts?: { suppress401Redirect?: boolean }) =>
    request<T>({ method: 'POST', path, body, suppress401Redirect: opts?.suppress401Redirect }),
  put: <T>(path: string, body?: unknown) =>
    request<T>({ method: 'PUT', path, body }),
  patch: <T>(path: string, body?: unknown) =>
    request<T>({ method: 'PATCH', path, body }),
  delete: <T>(path: string) =>
    request<T>({ method: 'DELETE', path }),
};

export { ApiClientError, AuthRequiredError, RateLimitError } from './apiErrors';
