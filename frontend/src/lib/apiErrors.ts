/**
 * Typed error hierarchy for apiClient (tiger-style — callers
 * narrow on instanceof rather than parsing strings).
 *
 * Locked dispositions (CONTEXT §76-79):
 *   401 -> AuthRequiredError (apiClient redirects, never thrown to caller
 *          unless suppress401Redirect=true)
 *   429 -> RateLimitError    (THROWN to caller; surface as inline countdown)
 *   other 4xx/5xx -> ApiClientError
 *   network failure -> ApiClientError(0, ...)
 */

export class ApiClientError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly code?: string,
    public readonly body?: unknown,
  ) {
    super(message);
    this.name = 'ApiClientError';
  }
}

export class AuthRequiredError extends ApiClientError {
  constructor(body?: unknown) {
    super(401, 'Authentication required', 'AUTH_REQUIRED', body);
    this.name = 'AuthRequiredError';
  }
}

export class RateLimitError extends ApiClientError {
  constructor(
    public readonly retryAfterSeconds: number,
    body?: unknown,
  ) {
    super(429, `Rate limited — retry in ${retryAfterSeconds}s`, 'RATE_LIMITED', body);
    this.name = 'RateLimitError';
  }
}
