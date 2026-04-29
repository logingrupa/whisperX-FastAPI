import { http, HttpResponse } from 'msw';

export const authHandlers = [
  http.post('/auth/login', async ({ request }) => {
    const body = (await request.json()) as { email: string; password: string };
    if (body.password === 'wrong') {
      return HttpResponse.json(
        { detail: 'Invalid credentials', code: 'INVALID_CREDENTIALS' },
        { status: 401 },
      );
    }
    return HttpResponse.json(
      { user_id: 1, plan_tier: 'trial' },
      {
        status: 200,
        headers: {
          'Set-Cookie': 'session=fake.jwt.token; Path=/; HttpOnly, csrf_token=fake-csrf-123; Path=/',
        },
      },
    );
  }),
  http.post('/auth/register', async () =>
    HttpResponse.json(
      { user_id: 1, plan_tier: 'trial' },
      {
        status: 201,
        headers: {
          'Set-Cookie': 'session=fake.jwt.token; Path=/; HttpOnly, csrf_token=fake-csrf-123; Path=/',
        },
      },
    ),
  ),
  http.post('/auth/logout', () => new HttpResponse(null, { status: 204 })),
];
