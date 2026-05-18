/**
 * Tests for the centralised toast facade.
 *
 * The facade decides which sonner variant fires for each thrown value,
 * so we mock ``sonner`` and assert which method was called with which
 * arguments. Asserting on sonner's DOM output instead would force a
 * real <Toaster /> render and slow down the suite for no extra coverage.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const toastSuccess = vi.fn();
const toastInfo = vi.fn();
const toastWarning = vi.fn();
const toastError = vi.fn();

vi.mock('sonner', () => ({
  toast: {
    success: (...args: unknown[]) => toastSuccess(...args),
    info: (...args: unknown[]) => toastInfo(...args),
    warning: (...args: unknown[]) => toastWarning(...args),
    error: (...args: unknown[]) => toastError(...args),
  },
}));

import {
  showError,
  showInfo,
  showSuccess,
  showWarning,
  toastFromError,
} from '@/lib/toast';
import {
  ApiClientError,
  AuthRequiredError,
  RateLimitError,
} from '@/lib/apiErrors';

beforeEach(() => {
  toastSuccess.mockReset();
  toastInfo.mockReset();
  toastWarning.mockReset();
  toastError.mockReset();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('toast facade — semantic helpers', () => {
  it('showSuccess delegates to toast.success', () => {
    showSuccess('Saved', { description: 'Settings updated' });
    expect(toastSuccess).toHaveBeenCalledWith('Saved', {
      description: 'Settings updated',
    });
  });

  it('showInfo delegates to toast.info', () => {
    showInfo('Heads up');
    expect(toastInfo).toHaveBeenCalledWith('Heads up', undefined);
  });

  it('showWarning delegates to toast.warning', () => {
    showWarning('Careful');
    expect(toastWarning).toHaveBeenCalledWith('Careful', undefined);
  });

  it('showError delegates to toast.error', () => {
    showError('Boom');
    expect(toastError).toHaveBeenCalledWith('Boom', undefined);
  });
});

describe('toastFromError — error -> variant mapping', () => {
  it('swallows AuthRequiredError (apiClient already redirects)', () => {
    toastFromError(new AuthRequiredError());
    expect(toastError).not.toHaveBeenCalled();
    expect(toastWarning).not.toHaveBeenCalled();
  });

  it('renders RateLimitError as a warning with retry-after countdown', () => {
    toastFromError(new RateLimitError(42));
    expect(toastWarning).toHaveBeenCalledWith('Rate limited', {
      description: 'Try again in 42s.',
      duration: undefined,
    });
  });

  it('renders 4xx ApiClientError with the parsed detail as description', () => {
    const err = new ApiClientError(
      400,
      "Invalid file extension for file song.flac. Allowed: {'.mp3', '.wav'}",
      'UNSUPPORTED_FILE_EXTENSION',
    );
    toastFromError(err);
    expect(toastError).toHaveBeenCalledWith('Request failed', {
      description:
        "Invalid file extension for file song.flac. Allowed: {'.mp3', '.wav'}",
      duration: undefined,
    });
  });

  it('uses status-specific title for 415 (unsupported file)', () => {
    toastFromError(new ApiClientError(415, 'nope'));
    expect(toastError).toHaveBeenCalledWith(
      'Unsupported file',
      expect.objectContaining({ description: 'nope' }),
    );
  });

  it('uses "Server error" title for 5xx', () => {
    toastFromError(new ApiClientError(503, 'down'));
    expect(toastError).toHaveBeenCalledWith(
      'Server error',
      expect.objectContaining({ description: 'down' }),
    );
  });

  it('suppresses NETWORK_ERROR by default but allows opt-in', () => {
    const netErr = new ApiClientError(0, 'fetch failed', 'NETWORK_ERROR');

    toastFromError(netErr);
    expect(toastError).not.toHaveBeenCalled();

    toastFromError(netErr, { includeNetworkErrors: true });
    expect(toastError).toHaveBeenCalledWith(
      'Network error',
      expect.objectContaining({ description: 'fetch failed' }),
    );
  });

  it('appends correlation-id slice to description when available', () => {
    const err = new ApiClientError(
      500,
      'boom',
      'INTERNAL_ERROR',
      undefined,
      '01234567-89ab-cdef-0123-456789abcdef',
    );
    toastFromError(err);
    expect(toastError).toHaveBeenCalledWith(
      'Server error',
      expect.objectContaining({ description: 'boom (ref 01234567)' }),
    );
  });

  it('falls back to error.message for plain Error', () => {
    toastFromError(new Error('crashed'));
    expect(toastError).toHaveBeenCalledWith('Something went wrong', {
      description: 'crashed',
      duration: undefined,
    });
  });

  it('stringifies non-Error throws as a last resort', () => {
    toastFromError({ unexpected: 'object' });
    expect(toastError).toHaveBeenCalledWith('Something went wrong', {
      description: '[object Object]',
      duration: undefined,
    });
  });
});
