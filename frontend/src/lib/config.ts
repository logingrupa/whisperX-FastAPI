/**
 * Application configuration from environment variables
 *
 * In development: Vite injects VITE_ prefixed env vars
 * In production: Same vars are baked in at build time
 */

/**
 * Backend API base URL
 *
 * Development: Vite proxy handles requests, so we use relative URLs
 * Production: Direct API calls to the configured backend
 */
export function getApiBaseUrl(): string {
  // In production (served by FastAPI), use relative URLs
  // The frontend is served from the same origin as the API
  if (import.meta.env.PROD) {
    return '';
  }

  // In development, Vite proxy handles /api/* routes
  // So we still use relative URLs - the proxy does the work
  return '';
}

/**
 * WebSocket base URL for real-time progress
 *
 * Constructs ws:// or wss:// URL based on current protocol
 */
export function getWebSocketBaseUrl(): string {
  // In production, derive from current page location
  if (import.meta.env.PROD) {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${protocol}//${window.location.host}`;
  }

  // In development, Vite proxy handles WebSocket upgrade
  // Use relative URL - proxy config in vite.config.ts does the rest
  return '';
}

/**
 * Full API URL from environment (used by Vite proxy config)
 * This is only used in vite.config.ts, not in runtime code
 */
export const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
