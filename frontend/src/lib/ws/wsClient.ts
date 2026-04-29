/**
 * WebSocket ticket helper (MID-06 enforcement on the client).
 *
 * Backend Phase 13 rejects WS connections without a single-use 60-second
 * ticket. This module is the SINGLE source of WS-URL composition for the app:
 *
 *   - requestWsTicket(taskId) -> ticket string via apiClient.post('/api/ws/ticket')
 *   - buildTaskSocketUrl(taskId) -> `/ws/tasks/${taskId}?ticket=<encoded>`
 *
 * Tickets are single-use + 60s TTL. Callers MUST re-request on every
 * (auto-)reconnect; useTaskProgress wires that via onClose -> rebuild URL.
 *
 * Tiger-style: ticket is never logged; apiClient handles 401-redirect/429-typed
 * for the ticket-issue call itself; failures bubble up to the caller for UI.
 */

import { apiClient } from '@/lib/apiClient';

interface WsTicketResponse {
  ticket: string;
  expires_at: string;
}

/**
 * Request a single-use WebSocket ticket for the given task.
 *
 * Throws ApiClientError / AuthRequiredError / RateLimitError per apiClient
 * contract. Caller is responsible for surfacing connection failure to UI.
 */
export async function requestWsTicket(taskId: string): Promise<string> {
  const response = await apiClient.post<WsTicketResponse>('/api/ws/ticket', {
    task_id: taskId,
  });
  return response.ticket;
}

/**
 * Build the ticket-bearing WebSocket URL for a task.
 *
 * Returns a relative path — react-use-websocket / native WebSocket
 * will resolve scheme + host from window.location automatically.
 */
export async function buildTaskSocketUrl(taskId: string): Promise<string> {
  const ticket = await requestWsTicket(taskId);
  return `/ws/tasks/${taskId}?ticket=${encodeURIComponent(ticket)}`;
}
