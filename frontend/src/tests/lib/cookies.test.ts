import { describe, it, expect, beforeEach } from 'vitest';
import { readCookie } from '@/lib/cookies';

describe('readCookie', () => {
  beforeEach(() => {
    // Clear document.cookie between tests (jsdom)
    document.cookie.split(';').forEach((c) => {
      const eq = c.indexOf('=');
      const name = (eq > -1 ? c.slice(0, eq) : c).trim();
      document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT`;
    });
  });

  it('returns null for missing cookie', () => {
    expect(readCookie('absent')).toBe(null);
  });

  it('returns the value for present cookie', () => {
    document.cookie = 'csrf_token=abc-123; path=/';
    expect(readCookie('csrf_token')).toBe('abc-123');
  });

  it('decodes URL-encoded values', () => {
    document.cookie = 'csrf_token=a%2Bb; path=/';
    expect(readCookie('csrf_token')).toBe('a+b');
  });

  it('does not match cookies with name as suffix', () => {
    document.cookie = 'xcsrf_token=should-not-match; path=/';
    expect(readCookie('csrf_token')).toBe(null);
  });
});
