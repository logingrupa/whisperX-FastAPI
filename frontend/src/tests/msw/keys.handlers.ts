import { http, HttpResponse } from 'msw';

export const keysHandlers = [
  http.get('/api/keys', () =>
    HttpResponse.json([
      {
        id: 1,
        name: 'default',
        prefix: 'whsk_abc1',
        created_at: '2026-04-29T12:00:00Z',
        last_used_at: null,
        status: 'active',
      },
    ]),
  ),
  http.post('/api/keys', async ({ request }) => {
    const body = (await request.json()) as { name: string };
    return HttpResponse.json(
      {
        id: 2,
        name: body.name,
        prefix: 'whsk_xyz2',
        key: 'whsk_xyz2_thisisthe22charplaintext',
        created_at: '2026-04-29T13:00:00Z',
        status: 'active',
      },
      { status: 201 },
    );
  }),
  http.delete('/api/keys/:id', () => new HttpResponse(null, { status: 204 })),
];
