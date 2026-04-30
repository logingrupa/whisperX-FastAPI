import { http, HttpResponse } from 'msw';

/**
 * MSW handlers for the transcription flow (TEST-06).
 *
 * Mirrors the backend contract used by:
 *   - frontend/src/lib/api/transcriptionApi.ts (POST /speech-to-text)
 *   - frontend/src/lib/api/taskApi.ts          (GET /task/:id)
 *   - frontend/src/hooks/useTaskProgress.ts    (GET /tasks/:id/progress)
 *
 * Returned shapes match Phase 13 backend so any test rendering the
 * full upload → transcribe → progress chain can rely on these mocks.
 */
export const transcribeHandlers = [
  http.post('/speech-to-text', () =>
    HttpResponse.json({ identifier: 'task-uuid-1', message: 'Task queued' }),
  ),
  http.get('/tasks/:id/progress', () =>
    HttpResponse.json({ stage: 'complete', percentage: 100, message: 'Done' }),
  ),
  // /task/all MUST come BEFORE /task/:id — MSW matches handlers in order
  // and ':id' would otherwise capture 'all' as a path param.
  //
  // Plan 15-ux: handler honours q/status/page/page_size so tests that
  // exercise pagination + search receive a deterministic slice.
  http.get('/task/all', ({ request }) => {
    const url = new URL(request.url);
    const q = url.searchParams.get('q');
    const status = url.searchParams.get('status');
    const page = Number.parseInt(url.searchParams.get('page') ?? '1', 10);
    const pageSize = Number.parseInt(
      url.searchParams.get('page_size') ?? '50',
      10,
    );
    return HttpResponse.json({
      tasks: [],
      total: 0,
      page: Number.isFinite(page) ? page : 1,
      page_size: Number.isFinite(pageSize) ? pageSize : 50,
      // Echoed back so tests can assert which params reached the handler.
      _echo: { q, status },
    });
  }),
  http.get('/task/:id', () =>
    HttpResponse.json({
      identifier: 'task-uuid-1',
      status: 'complete',
      result: {
        segments: [
          { start: 0, end: 1, text: 'hello', speaker: 'SPEAKER_00' },
        ],
      },
    }),
  ),
];
