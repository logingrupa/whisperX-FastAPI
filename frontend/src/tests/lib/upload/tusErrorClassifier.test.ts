/**
 * Tests for the TUS error classifier — especially the JSON-detail
 * extraction added after the .flac regression where the backend message
 * ("Invalid file extension … Allowed: …") was silently replaced by a
 * generic "Upload failed" toast.
 */

import { describe, expect, it } from 'vitest';

import { classifyUploadError } from '@/lib/upload/tusErrorClassifier';

interface MockResponseInit {
  status: number;
  body: string;
}

/**
 * Build the duck-typed DetailedError that classifyUploadError expects.
 * tus-js-client v4 exposes ``originalResponse.getStatus()`` and
 * ``.getBody()`` — we mimic that surface area only.
 */
function buildTusError(init: MockResponseInit | null, message = 'tus error'): Error {
  const err = new Error(message);
  Object.assign(err, {
    originalResponse: init
      ? {
          getStatus: () => init.status,
          getBody: () => init.body,
        }
      : null,
  });
  return err;
}

describe('classifyUploadError — generic shape coverage', () => {
  it('network failure (no originalResponse) -> retryable', () => {
    const result = classifyUploadError(buildTusError(null));
    expect(result.isRetryable).toBe(true);
    expect(result.userMessage).toMatch(/network connection/i);
  });

  it('413 -> not retryable, file-too-large message', () => {
    const result = classifyUploadError(
      buildTusError({ status: 413, body: '' }),
    );
    expect(result.isRetryable).toBe(false);
    expect(result.userMessage).toMatch(/maximum upload size|too large/i);
  });

  it('5xx -> retryable, server-error message', () => {
    const result = classifyUploadError(
      buildTusError({ status: 503, body: '' }),
    );
    expect(result.isRetryable).toBe(true);
    expect(result.userMessage).toMatch(/server error/i);
  });
});

describe('classifyUploadError — server detail extraction', () => {
  it('surfaces FastAPI string detail on 4xx', () => {
    const body = JSON.stringify({
      detail:
        "Invalid file extension for file 1-gupsp.flac. Allowed: {'.mp3', '.wav'}",
    });
    const result = classifyUploadError(
      buildTusError({ status: 400, body }),
    );
    expect(result.userMessage).toContain('Invalid file extension');
    expect(result.userMessage).toContain('1-gupsp.flac');
    expect(result.isRetryable).toBe(false);
  });

  it('surfaces ApplicationError.to_dict() message on 422', () => {
    const body = JSON.stringify({
      error: {
        message: 'File audio.xyz has unsupported extension .xyz',
        user_message: 'Audio format .xyz is not supported.',
        code: 'UNSUPPORTED_FILE_EXTENSION',
        correlation_id: 'abc-123',
      },
    });
    const result = classifyUploadError(
      buildTusError({ status: 422, body }),
    );
    expect(result.userMessage).toBe('Audio format .xyz is not supported.');
  });

  it('surfaces HTTPException dict-detail message', () => {
    const body = JSON.stringify({
      detail: {
        message: 'Magic-byte mismatch',
        code: 'FILE_FORMAT_MISMATCH',
      },
    });
    const result = classifyUploadError(
      buildTusError({ status: 400, body }),
    );
    expect(result.userMessage).toBe('Magic-byte mismatch');
  });

  it('falls back to generic message when body is not JSON', () => {
    const result = classifyUploadError(
      buildTusError({ status: 400, body: '<html>oops</html>' }),
    );
    expect(result.userMessage).toMatch(/rejected by the server/i);
  });

  it('falls back when JSON has no recognised detail key', () => {
    const result = classifyUploadError(
      buildTusError({ status: 400, body: JSON.stringify({ foo: 'bar' }) }),
    );
    expect(result.userMessage).toMatch(/rejected by the server/i);
  });
});
