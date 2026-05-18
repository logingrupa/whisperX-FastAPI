/**
 * Centralised toast facade — SOLE entry point for surfacing
 * user-visible notifications across the app (DRY).
 *
 * SRP: this module owns *presentation* of error/success/info/warning
 * states. Callers stay thin — they hand us an Error or a string and
 * the right sonner variant (with the right icon and colour) fires.
 *
 * Why a wrapper instead of importing sonner directly:
 * - Keeps the ApiClientError / RateLimitError / AuthRequiredError
 *   knowledge in ONE place. A new error subtype only needs a branch
 *   here — every existing caller picks up nicer messages for free.
 * - Suppresses 401 toasts: AuthRequiredError already triggers a hard
 *   redirect to /login from apiClient, so a stale toast is just noise.
 * - Suppresses generic NETWORK_ERROR toasts during navigation/teardown
 *   (caller may opt-in via ``options.includeNetworkErrors``).
 *
 * Tiger-style: this module never reads global state; every helper is
 * a pure function of its arguments + ``toast`` from sonner.
 */

import { toast } from 'sonner';

import {
  ApiClientError,
  AuthRequiredError,
  RateLimitError,
} from '@/lib/apiErrors';

interface ToastOptions {
  /** Optional secondary line shown beneath the title. */
  description?: string;
  /** Override sonner's default auto-dismiss (ms). Pass ``Infinity`` to pin. */
  duration?: number;
}

interface ErrorToastOptions extends ToastOptions {
  /** Prepended to the rendered title (e.g. "Upload failed"). */
  title?: string;
  /** Surface NETWORK_ERROR / status=0 (default: false — usually transient). */
  includeNetworkErrors?: boolean;
}

export function showSuccess(message: string, options?: ToastOptions): void {
  toast.success(message, options);
}

export function showInfo(message: string, options?: ToastOptions): void {
  toast.info(message, options);
}

export function showWarning(message: string, options?: ToastOptions): void {
  toast.warning(message, options);
}

export function showError(message: string, options?: ToastOptions): void {
  toast.error(message, options);
}

/**
 * Render an arbitrary thrown value as the appropriate toast.
 *
 * Selection rules:
 * - ``AuthRequiredError``     -> swallowed (apiClient redirects to /login).
 * - ``RateLimitError``        -> warning toast with retry-after countdown.
 * - ``ApiClientError`` (5xx)  -> error toast tagged "Server error".
 * - ``ApiClientError`` (4xx)  -> error toast with the parsed detail.
 * - generic ``Error``         -> error toast with ``error.message``.
 * - anything else             -> error toast with String(err) (last resort).
 */
export function toastFromError(
  err: unknown,
  options: ErrorToastOptions = {},
): void {
  if (err instanceof AuthRequiredError) {
    return;
  }

  if (err instanceof RateLimitError) {
    showWarning('Rate limited', {
      description: `Try again in ${err.retryAfterSeconds}s.`,
      duration: options.duration,
    });
    return;
  }

  if (err instanceof ApiClientError) {
    if (err.code === 'NETWORK_ERROR' && !options.includeNetworkErrors) {
      return;
    }
    const title = options.title ?? defaultTitleForStatus(err.status);
    const description = buildDescription(err, options.description);
    showError(title, {
      description,
      duration: options.duration,
    });
    return;
  }

  if (err instanceof Error) {
    showError(options.title ?? 'Something went wrong', {
      description: options.description ?? err.message,
      duration: options.duration,
    });
    return;
  }

  showError(options.title ?? 'Something went wrong', {
    description: options.description ?? String(err),
    duration: options.duration,
  });
}

function defaultTitleForStatus(status: number): string {
  if (status === 0) return 'Network error';
  if (status === 402) return 'Upgrade required';
  if (status === 403) return 'Not permitted';
  if (status === 404) return 'Not found';
  if (status === 413) return 'File too large';
  if (status === 415) return 'Unsupported file';
  if (status === 422) return 'Invalid input';
  if (status >= 500) return 'Server error';
  return 'Request failed';
}

function buildDescription(
  err: ApiClientError,
  override: string | undefined,
): string {
  if (override !== undefined) return override;
  if (err.correlationId) {
    return `${err.message} (ref ${err.correlationId.slice(0, 8)})`;
  }
  return err.message;
}
