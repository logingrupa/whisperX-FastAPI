/**
 * Typed wrapper over apiClient for /api/keys CRUD (UI-05, DRY).
 *
 * Single source of API key data shapes — KeysDashboardPage and tests
 * both import these types. NO direct fetch usage here — apiClient owns
 * credentials/CSRF/401-redirect/429-handling (UI-11).
 *
 * Backend contract (locked from app/api/key_routes.py + key_schemas.py):
 *   GET    /api/keys      -> 200 ApiKeyListItem[]
 *   POST   /api/keys      -> 201 CreatedApiKey  (key plaintext shown ONCE — KEY-04)
 *   DELETE /api/keys/:id  -> 204 (void)
 */

import { apiClient } from '@/lib/apiClient';

export interface ApiKeyListItem {
  id: number;
  name: string;
  prefix: string;
  created_at: string;
  last_used_at: string | null;
  status: 'active' | 'revoked';
}

export interface CreatedApiKey extends ApiKeyListItem {
  /** Plaintext — shown ONCE; unrecoverable after this response (KEY-04). */
  key: string;
}

export function fetchKeys(): Promise<ApiKeyListItem[]> {
  return apiClient.get<ApiKeyListItem[]>('/api/keys');
}

export function createKey(name: string): Promise<CreatedApiKey> {
  return apiClient.post<CreatedApiKey>('/api/keys', { name });
}

export function revokeKey(id: number): Promise<void> {
  return apiClient.delete<void>(`/api/keys/${id}`);
}
