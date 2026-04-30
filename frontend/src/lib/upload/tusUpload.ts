/**
 * TUS upload wrapper around tus-js-client.
 *
 * Provides a factory function that creates a configured tus.Upload instance
 * with project-standard defaults (chunk size, retry, metadata).
 * The caller is responsible for calling `.start()` on the returned instance.
 *
 * This module has NO React dependency -- it is a pure library utility.
 *
 * Auth/CSRF (Phase 13 atomic-cutover): TUS POST/PATCH/DELETE are state-mutating
 * and gated by CsrfMiddleware. Cookies are not sent on XHR by default in
 * tus-js-client v4, so we use `onBeforeRequest` to (a) flip
 * `xhr.withCredentials = true` and (b) attach the `X-CSRF-Token` header
 * from the `csrf_token` cookie on every request. Re-evaluating per-request
 * means a mid-upload token rotation is picked up automatically (vs. the
 * static `headers` config option, which is read once at construction).
 */

import * as tus from 'tus-js-client';
import type { DetailedError, HttpRequest } from 'tus-js-client';

import { readCookie } from '@/lib/cookies';
import { TUS_CHUNK_SIZE, TUS_ENDPOINT, TUS_RETRY_DELAYS } from './constants';

const CSRF_COOKIE_NAME = 'csrf_token';
const CSRF_HEADER_NAME = 'X-CSRF-Token';

/**
 * Per-request hook: enable cookie-credentials on the XHR and attach the
 * CSRF double-submit header from the csrf_token cookie.
 *
 * If the cookie is missing we deliberately do NOT synthesize a placeholder —
 * the request will 403 and surface as a fail-loud auth error (tiger-style).
 */
function applyCsrfAndCredentials(req: HttpRequest): void {
  const xhr = req.getUnderlyingObject() as XMLHttpRequest;
  xhr.withCredentials = true;

  const csrf = readCookie(CSRF_COOKIE_NAME);
  if (csrf) {
    req.setHeader(CSRF_HEADER_NAME, csrf);
  }
}

/** Callbacks for upload lifecycle events. */
export interface TusUploadCallbacks {
  onProgress(bytesSent: number, bytesTotal: number): void;
  onSuccess(tusUrl: string): void;
  onError(error: Error): void;
  /** Fires when a retry is about to happen (before the delay). */
  onBeforeRetry?: () => void;
}

/**
 * Create a configured TUS upload instance.
 *
 * @param file      - The file to upload.
 * @param metadata  - Key-value metadata sent via TUS Upload-Metadata header.
 * @param callbacks - Lifecycle callbacks for progress, success, and error.
 * @returns A tus.Upload instance. Call `.start()` to begin uploading.
 */
export function createTusUpload(
  file: File,
  metadata: Record<string, string>,
  callbacks: TusUploadCallbacks,
): tus.Upload {
  /** HTTP status codes that indicate permanent failure -- never retry. */
  const PERMANENT_STATUSES = new Set([413, 415, 410, 403]);

  /** HTTP status codes that are always worth retrying. */
  const TRANSIENT_STATUSES = new Set([0, 408, 429, 502, 503, 504]);

  const upload = new tus.Upload(file, {
    endpoint: TUS_ENDPOINT,
    chunkSize: TUS_CHUNK_SIZE,
    retryDelays: TUS_RETRY_DELAYS,
    metadata,
    storeFingerprintForResuming: true,
    removeFingerprintOnSuccess: true,
    onBeforeRequest: applyCsrfAndCredentials,
    onProgress: callbacks.onProgress,
    onSuccess: () => {
      callbacks.onSuccess(upload.url ?? '');
    },
    onError: (error) => {
      callbacks.onError(error instanceof Error ? error : new Error(String(error)));
    },
    onShouldRetry: (err: DetailedError, _retryAttempt: number, _options) => {
      const status = err.originalResponse?.getStatus() ?? 0;

      if (PERMANENT_STATUSES.has(status)) return false;

      if (TRANSIENT_STATUSES.has(status)) {
        callbacks.onBeforeRetry?.();
        return true;
      }

      // Default: retry non-4xx errors, plus 409 (conflict) and 423 (locked)
      const shouldRetry =
        !(status >= 400 && status < 500) || status === 409 || status === 423;

      if (shouldRetry) {
        callbacks.onBeforeRetry?.();
      }

      return shouldRetry;
    },
  });

  return upload;
}

/** Check whether the current browser supports TUS uploads. */
export function isTusSupported(): boolean {
  return tus.isSupported;
}
