/**
 * Read a non-httpOnly cookie value from document.cookie.
 * Returns null if the cookie is not present.
 *
 * Used exclusively for the csrf_token cookie (intentionally non-httpOnly
 * per CONTEXT §94-98) — apiClient attaches it as the X-CSRF-Token header
 * on every state-mutating request to satisfy the backend's double-submit
 * pattern (MID-04).
 */
export function readCookie(name: string): string | null {
  const cookies = document.cookie ? document.cookie.split('; ') : [];
  const prefix = `${encodeURIComponent(name)}=`;
  for (const c of cookies) {
    if (c.startsWith(prefix)) {
      return decodeURIComponent(c.slice(prefix.length));
    }
  }
  return null;
}
