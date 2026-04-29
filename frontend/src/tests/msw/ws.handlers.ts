import { http, HttpResponse } from 'msw';

export const wsHandlers = [
  http.post('/api/ws/ticket', async () =>
    HttpResponse.json(
      { ticket: 'mock-ticket-32chars', expires_at: '2099-01-01T00:00:00Z' },
      { status: 201 },
    ),
  ),
];
