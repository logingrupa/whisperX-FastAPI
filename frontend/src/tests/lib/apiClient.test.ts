import { describe, it, expect, beforeEach } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '../setup';
import {
  apiClient,
  ApiClientError,
  AuthRequiredError,
  RateLimitError,
} from '@/lib/apiClient';

describe('apiClient', () => {
  beforeEach(() => {
    // Clear cookies between tests
    document.cookie.split(';').forEach((c) => {
      const eq = c.indexOf('=');
      const name = (eq > -1 ? c.slice(0, eq) : c).trim();
      document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT`;
    });
  });

  it('GET returns parsed JSON on 200', async () => {
    server.use(
      http.get('/api/test', () => HttpResponse.json({ ok: true, value: 42 })),
    );
    const result = await apiClient.get<{ ok: boolean; value: number }>('/api/test');
    expect(result).toEqual({ ok: true, value: 42 });
  });

  it('POST attaches X-CSRF-Token from csrf_token cookie', async () => {
    document.cookie = 'csrf_token=test-csrf-value; path=/';
    let capturedHeader: string | null = null;
    server.use(
      http.post('/api/test', ({ request }) => {
        capturedHeader = request.headers.get('X-CSRF-Token');
        return HttpResponse.json({ ok: true });
      }),
    );
    await apiClient.post('/api/test', { foo: 'bar' });
    expect(capturedHeader).toBe('test-csrf-value');
  });

  it('GET does NOT attach X-CSRF-Token (read-only request)', async () => {
    document.cookie = 'csrf_token=test-csrf-value; path=/';
    let capturedHeader: string | null = 'sentinel';
    server.use(
      http.get('/api/test', ({ request }) => {
        capturedHeader = request.headers.get('X-CSRF-Token');
        return HttpResponse.json({ ok: true });
      }),
    );
    await apiClient.get('/api/test');
    expect(capturedHeader).toBe(null);
  });

  it('401 triggers window.location.href redirect with ?next=', async () => {
    window.location.pathname = '/dashboard/keys';
    window.location.search = '?foo=bar';
    server.use(
      http.get('/api/test', () =>
        HttpResponse.json({ detail: 'Authentication required' }, { status: 401 }),
      ),
    );
    await expect(apiClient.get('/api/test')).rejects.toBeInstanceOf(AuthRequiredError);
    expect(window.location.href).toBe(
      '/login?next=' + encodeURIComponent('/dashboard/keys?foo=bar'),
    );
  });

  it('401 does NOT redirect when suppress401Redirect=true', async () => {
    const before = window.location.href;
    server.use(
      http.post('/api/test', () =>
        HttpResponse.json({ detail: 'Authentication required' }, { status: 401 }),
      ),
    );
    await expect(
      apiClient.post('/api/test', null, { suppress401Redirect: true }),
    ).rejects.toBeInstanceOf(AuthRequiredError);
    expect(window.location.href).toBe(before);
  });

  it('429 throws RateLimitError with parsed Retry-After', async () => {
    server.use(
      http.get('/api/test', () =>
        HttpResponse.json(
          { detail: 'Too many requests' },
          { status: 429, headers: { 'Retry-After': '42' } },
        ),
      ),
    );
    await expect(apiClient.get('/api/test')).rejects.toThrow(RateLimitError);
    try {
      await apiClient.get('/api/test');
    } catch (err) {
      expect(err).toBeInstanceOf(RateLimitError);
      expect((err as RateLimitError).retryAfterSeconds).toBe(42);
    }
  });

  it('429 falls back to 60s when Retry-After missing', async () => {
    server.use(
      http.get('/api/test', () =>
        HttpResponse.json({ detail: 'Too many requests' }, { status: 429 }),
      ),
    );
    try {
      await apiClient.get('/api/test');
    } catch (err) {
      expect((err as RateLimitError).retryAfterSeconds).toBe(60);
    }
  });

  it('non-401/429 4xx throws ApiClientError with detail+code', async () => {
    server.use(
      http.post('/api/test', () =>
        HttpResponse.json(
          { detail: 'Registration failed', code: 'REGISTRATION_FAILED' },
          { status: 422 },
        ),
      ),
    );
    try {
      await apiClient.post('/api/test', {});
    } catch (err) {
      expect(err).toBeInstanceOf(ApiClientError);
      expect((err as ApiClientError).status).toBe(422);
      expect((err as ApiClientError).code).toBe('REGISTRATION_FAILED');
    }
  });

  it('204 returns undefined (no body parse)', async () => {
    server.use(
      http.delete('/api/test', () => new HttpResponse(null, { status: 204 })),
    );
    const result = await apiClient.delete('/api/test');
    expect(result).toBeUndefined();
  });

  it('credentials: include is set on every request', async () => {
    let capturedCredentials: RequestCredentials | undefined;
    server.use(
      http.get('/api/test', ({ request }) => {
        capturedCredentials = request.credentials;
        return HttpResponse.json({ ok: true });
      }),
    );
    await apiClient.get('/api/test');
    expect(capturedCredentials).toBe('include');
  });
});
