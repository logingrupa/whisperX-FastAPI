/**
 * tusUpload — verifies CSRF + credentials wiring via onBeforeRequest.
 *
 * Phase 13 atomic-cutover gates TUS POST/PATCH/DELETE behind CsrfMiddleware.
 * tus-js-client v4 does NOT include credentials by default and does NOT
 * attach the csrf_token cookie as X-CSRF-Token unless we wire it ourselves.
 * These tests pin both behaviours so any regression fails CI loudly.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';

// Mock tus-js-client BEFORE importing the SUT so we can capture the
// options object passed to the Upload constructor.
const uploadCtorSpy = vi.fn();
vi.mock('tus-js-client', () => {
  class FakeUpload {
    public url: string | null = null;
    public options: unknown;
    public file: unknown;
    constructor(file: unknown, options: unknown) {
      this.file = file;
      this.options = options;
      uploadCtorSpy(file, options);
    }
    start(): void {}
    abort(): Promise<void> { return Promise.resolve(); }
    findPreviousUploads(): Promise<never[]> { return Promise.resolve([]); }
    resumeFromPreviousUpload(): void {}
  }
  return {
    Upload: FakeUpload,
    isSupported: true,
  };
});

import { createTusUpload } from '@/lib/upload/tusUpload';

interface CapturedOptions {
  onBeforeRequest?: (req: unknown) => void | Promise<void>;
  endpoint?: string;
  metadata?: Record<string, string>;
}

function buildFakeFile(): File {
  return new File([new Uint8Array([1, 2, 3])], 'test.aac', {
    type: 'audio/aac',
  });
}

function buildFakeRequest() {
  const xhr = {} as XMLHttpRequest;
  const setHeader = vi.fn();
  return {
    xhr,
    setHeader,
    req: {
      getUnderlyingObject: () => xhr,
      setHeader,
    },
  };
}

function clearCookies(): void {
  document.cookie.split(';').forEach((c) => {
    const eq = c.indexOf('=');
    const name = (eq > -1 ? c.slice(0, eq) : c).trim();
    document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT`;
  });
}

function lastCapturedOptions(): CapturedOptions {
  const calls = uploadCtorSpy.mock.calls;
  return calls[calls.length - 1][1] as CapturedOptions;
}

describe('createTusUpload — CSRF + credentials wiring', () => {
  beforeEach(() => {
    uploadCtorSpy.mockClear();
    clearCookies();
  });

  it('registers an onBeforeRequest hook on the tus.Upload config', () => {
    createTusUpload(buildFakeFile(), { filename: 'test.aac' }, {
      onProgress: () => {},
      onSuccess: () => {},
      onError: () => {},
    });

    const opts = lastCapturedOptions();
    expect(typeof opts.onBeforeRequest).toBe('function');
  });

  it('onBeforeRequest sets xhr.withCredentials = true', () => {
    createTusUpload(buildFakeFile(), { filename: 'test.aac' }, {
      onProgress: () => {},
      onSuccess: () => {},
      onError: () => {},
    });

    const opts = lastCapturedOptions();
    const fake = buildFakeRequest();
    opts.onBeforeRequest!(fake.req);

    expect((fake.xhr as XMLHttpRequest & { withCredentials: boolean }).withCredentials).toBe(true);
  });

  it('onBeforeRequest attaches X-CSRF-Token from csrf_token cookie', () => {
    document.cookie = 'csrf_token=tus-csrf-value; path=/';

    createTusUpload(buildFakeFile(), { filename: 'test.aac' }, {
      onProgress: () => {},
      onSuccess: () => {},
      onError: () => {},
    });

    const opts = lastCapturedOptions();
    const fake = buildFakeRequest();
    opts.onBeforeRequest!(fake.req);

    expect(fake.setHeader).toHaveBeenCalledWith('X-CSRF-Token', 'tus-csrf-value');
  });

  it('onBeforeRequest skips X-CSRF-Token when csrf_token cookie absent (fail-loud)', () => {
    // No cookie set — caller will 403 from server, surfaced via classifier.
    createTusUpload(buildFakeFile(), { filename: 'test.aac' }, {
      onProgress: () => {},
      onSuccess: () => {},
      onError: () => {},
    });

    const opts = lastCapturedOptions();
    const fake = buildFakeRequest();
    opts.onBeforeRequest!(fake.req);

    // withCredentials still flipped — only the CSRF header is conditional
    expect((fake.xhr as XMLHttpRequest & { withCredentials: boolean }).withCredentials).toBe(true);
    expect(fake.setHeader).not.toHaveBeenCalled();
  });

  it('re-evaluates the cookie on every request (rotation-safe)', () => {
    document.cookie = 'csrf_token=token-v1; path=/';

    createTusUpload(buildFakeFile(), { filename: 'test.aac' }, {
      onProgress: () => {},
      onSuccess: () => {},
      onError: () => {},
    });

    const opts = lastCapturedOptions();

    // First request — token v1
    const first = buildFakeRequest();
    opts.onBeforeRequest!(first.req);
    expect(first.setHeader).toHaveBeenCalledWith('X-CSRF-Token', 'token-v1');

    // Cookie rotates mid-upload
    document.cookie = 'csrf_token=token-v2; path=/';

    const second = buildFakeRequest();
    opts.onBeforeRequest!(second.req);
    expect(second.setHeader).toHaveBeenCalledWith('X-CSRF-Token', 'token-v2');
  });
});
