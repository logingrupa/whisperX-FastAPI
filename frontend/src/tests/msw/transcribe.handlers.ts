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
