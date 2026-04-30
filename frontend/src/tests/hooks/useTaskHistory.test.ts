/**
 * Unit tests for useTaskHistory (Plan 15-ux).
 *
 * Coverage:
 *   - taskToQueueItem maps backend statuses correctly
 *     (completed -> 'complete', failed -> 'error', processing -> 'processing')
 *   - taskToQueueItem rejects rows with empty identifier (boundary assertion)
 *   - seedQueueFromTasks filters malformed rows + preserves order
 *   - useTaskHistory hook fetches /task/all on mount, seeds queue,
 *     and re-binds WS for the first in-flight task
 *   - Hook is StrictMode-safe (no double-seed on remount)
 *   - Hook swallows fetch errors (uploads must keep working)
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { StrictMode, createElement, type ReactNode } from 'react';
import { server } from '@/tests/setup';
import {
  useTaskHistory,
  taskToQueueItem,
  seedQueueFromTasks,
  __resetTaskHistoryCacheForTests,
} from '@/hooks/useTaskHistory';
import type { TaskListItem } from '@/lib/api/taskApi';

const StrictWrapper = ({ children }: { children: ReactNode }) =>
  createElement(StrictMode, null, children);

function makeTask(overrides: Partial<TaskListItem> = {}): TaskListItem {
  return {
    identifier: 'task-1',
    status: 'completed',
    task_type: 'transcribe',
    file_name: 'sample.mp3',
    url: null,
    audio_duration: 12.5,
    language: 'en',
    error: null,
    duration: 4.2,
    start_time: null,
    end_time: null,
    ...overrides,
  };
}

describe('taskToQueueItem — pure mapper', () => {
  it('maps completed -> complete with progress 100 + complete stage', () => {
    const item = taskToQueueItem(makeTask({ status: 'completed' }));
    expect(item).not.toBeNull();
    expect(item!.status).toBe('complete');
    expect(item!.progressPercentage).toBe(100);
    expect(item!.progressStage).toBe('complete');
    expect(item!.kind).toBe('historic');
    expect(item!.file).toBeNull();
    expect(item!.fileName).toBe('sample.mp3');
    expect(item!.fileSize).toBe(0);
    expect(item!.taskId).toBe('task-1');
  });

  it('maps failed -> error and surfaces error message', () => {
    const item = taskToQueueItem(
      makeTask({ status: 'failed', error: 'CUDA OOM' }),
    );
    expect(item).not.toBeNull();
    expect(item!.status).toBe('error');
    expect(item!.errorMessage).toBe('CUDA OOM');
  });

  it('maps processing -> processing without progress fields preset', () => {
    const item = taskToQueueItem(makeTask({ status: 'processing' }));
    expect(item).not.toBeNull();
    expect(item!.status).toBe('processing');
    expect(item!.progressPercentage).toBeUndefined();
    expect(item!.progressStage).toBeUndefined();
  });

  it('rejects rows with empty identifier (boundary assertion)', () => {
    expect(taskToQueueItem(makeTask({ identifier: '' }))).toBeNull();
  });

  it('uses placeholder when file_name is null (no nested-if surfaces)', () => {
    const item = taskToQueueItem(makeTask({ file_name: null }));
    expect(item!.fileName).toBe('(unnamed task)');
  });
});

describe('seedQueueFromTasks — filters + ordering', () => {
  it('filters out malformed rows and preserves order', () => {
    const tasks: TaskListItem[] = [
      makeTask({ identifier: 'a', status: 'completed' }),
      makeTask({ identifier: '', status: 'completed' }), // dropped
      makeTask({ identifier: 'b', status: 'processing' }),
    ];
    const result = seedQueueFromTasks(tasks);
    expect(result.map(item => item.taskId)).toEqual(['a', 'b']);
  });

  it('returns empty array for empty input', () => {
    expect(seedQueueFromTasks([])).toEqual([]);
  });
});

describe('useTaskHistory — mount-time seed', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    __resetTaskHistoryCacheForTests();
  });

  it('fetches /task/all on mount and seeds historic items', async () => {
    server.use(
      http.get('/task/all', () =>
        HttpResponse.json({
          tasks: [
            makeTask({ identifier: 'hist-1', status: 'completed', file_name: 'old.mp3' }),
            makeTask({ identifier: 'hist-2', status: 'processing', file_name: 'new.mp3' }),
          ],
        }),
      ),
    );

    const addHistoricTasks = vi.fn();
    const resumeProcessingTask = vi.fn();

    renderHook(() =>
      useTaskHistory({ addHistoricTasks, resumeProcessingTask }),
    );

    await waitFor(() => expect(addHistoricTasks).toHaveBeenCalledTimes(1));
    const seeded = addHistoricTasks.mock.calls[0][0];
    expect(seeded).toHaveLength(2);
    expect(seeded[0].taskId).toBe('hist-1');
    expect(seeded[0].status).toBe('complete');
    expect(seeded[1].taskId).toBe('hist-2');
    expect(seeded[1].status).toBe('processing');
  });

  it('re-binds WS for the first processing historic task', async () => {
    server.use(
      http.get('/task/all', () =>
        HttpResponse.json({
          tasks: [
            makeTask({ identifier: 'hist-done', status: 'completed' }),
            makeTask({ identifier: 'hist-live', status: 'processing' }),
          ],
        }),
      ),
    );

    const addHistoricTasks = vi.fn();
    const resumeProcessingTask = vi.fn();

    renderHook(() =>
      useTaskHistory({ addHistoricTasks, resumeProcessingTask }),
    );

    await waitFor(() => expect(resumeProcessingTask).toHaveBeenCalledTimes(1));
    const [, taskIdArg] = resumeProcessingTask.mock.calls[0];
    expect(taskIdArg).toBe('hist-live');
  });

  it('does NOT call resumeProcessingTask when no processing tasks exist', async () => {
    server.use(
      http.get('/task/all', () =>
        HttpResponse.json({
          tasks: [makeTask({ identifier: 'done', status: 'completed' })],
        }),
      ),
    );

    const addHistoricTasks = vi.fn();
    const resumeProcessingTask = vi.fn();

    renderHook(() =>
      useTaskHistory({ addHistoricTasks, resumeProcessingTask }),
    );

    await waitFor(() => expect(addHistoricTasks).toHaveBeenCalledTimes(1));
    expect(resumeProcessingTask).not.toHaveBeenCalled();
  });

  it('swallows network errors and never blocks (uploads keep working)', async () => {
    server.use(http.get('/task/all', () => HttpResponse.error()));
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const addHistoricTasks = vi.fn();
    const resumeProcessingTask = vi.fn();

    renderHook(() =>
      useTaskHistory({ addHistoricTasks, resumeProcessingTask }),
    );

    await waitFor(() => expect(warnSpy).toHaveBeenCalled());
    expect(addHistoricTasks).not.toHaveBeenCalled();
    expect(resumeProcessingTask).not.toHaveBeenCalled();
  });

  it('swallows non-OK responses and never seeds', async () => {
    server.use(
      http.get('/task/all', () =>
        HttpResponse.json({ detail: 'boom' }, { status: 500 }),
      ),
    );
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const addHistoricTasks = vi.fn();
    const resumeProcessingTask = vi.fn();

    renderHook(() =>
      useTaskHistory({ addHistoricTasks, resumeProcessingTask }),
    );

    await waitFor(() => expect(warnSpy).toHaveBeenCalled());
    expect(addHistoricTasks).not.toHaveBeenCalled();
  });

  it('is idempotent across re-renders (StrictMode-safe)', async () => {
    server.use(
      http.get('/task/all', () =>
        HttpResponse.json({
          tasks: [makeTask({ identifier: 'only', status: 'completed' })],
        }),
      ),
    );

    const addHistoricTasks = vi.fn();
    const resumeProcessingTask = vi.fn();

    const { rerender } = renderHook(() =>
      useTaskHistory({ addHistoricTasks, resumeProcessingTask }),
    );

    await waitFor(() => expect(addHistoricTasks).toHaveBeenCalledTimes(1));
    rerender();
    rerender();
    // Still only one seed despite multiple renders
    expect(addHistoricTasks).toHaveBeenCalledTimes(1);
  });

  // Regression test for the bug where StrictMode's mount→unmount→remount
  // cycle interacted destructively with a `hasRunRef` guard + per-mount
  // `cancelled` flag, causing addHistoricTasks to NEVER be called in dev.
  // Wrapping the hook in <StrictMode> simulates the real dev environment
  // (main.tsx wraps the app in <StrictMode>) and was missing from the
  // original idempotency check (rerender() does not exercise lifecycle).
  it('seeds the queue under StrictMode (regression: empty queue on /ui/)', async () => {
    server.use(
      http.get('/task/all', () =>
        HttpResponse.json({
          tasks: [
            makeTask({ identifier: 'strict-1', status: 'completed' }),
            makeTask({ identifier: 'strict-2', status: 'processing' }),
          ],
        }),
      ),
    );

    const addHistoricTasks = vi.fn();
    const resumeProcessingTask = vi.fn();

    renderHook(
      () => useTaskHistory({ addHistoricTasks, resumeProcessingTask }),
      { wrapper: StrictWrapper },
    );

    await waitFor(() => expect(addHistoricTasks).toHaveBeenCalledTimes(1));
    const seeded = addHistoricTasks.mock.calls[0][0];
    expect(seeded).toHaveLength(2);
    expect(seeded[0].taskId).toBe('strict-1');
    expect(seeded[1].taskId).toBe('strict-2');
    // Re-bind WS still fires for the in-flight task
    await waitFor(() =>
      expect(resumeProcessingTask).toHaveBeenCalledTimes(1),
    );
    expect(resumeProcessingTask.mock.calls[0][1]).toBe('strict-2');
  });

  it('skips seeding entirely when /task/all returns malformed payload', async () => {
    server.use(
      http.get('/task/all', () => HttpResponse.json({ wrong: 'shape' })),
    );
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const addHistoricTasks = vi.fn();
    const resumeProcessingTask = vi.fn();

    renderHook(() =>
      useTaskHistory({ addHistoricTasks, resumeProcessingTask }),
    );

    await waitFor(() => expect(warnSpy).toHaveBeenCalled());
    expect(addHistoricTasks).not.toHaveBeenCalled();
  });
});

describe('useTaskHistory — query state + re-fetch (Plan 15-ux)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    __resetTaskHistoryCacheForTests();
  });

  it('forwards q/status/page/pageSize to /task/all', async () => {
    const observedUrls: string[] = [];
    server.use(
      http.get('/task/all', ({ request }) => {
        observedUrls.push(request.url);
        return HttpResponse.json({
          tasks: [],
          total: 0,
          page: 2,
          page_size: 50,
        });
      }),
    );

    const setHistoricTasks = vi.fn();
    renderHook(() =>
      useTaskHistory({
        addHistoricTasks: vi.fn(),
        resumeProcessingTask: vi.fn(),
        setHistoricTasks,
        replaceOnFetch: true,
        query: { q: 'meeting', status: 'completed', page: 2, pageSize: 50 },
      }),
    );

    await waitFor(() => expect(observedUrls.length).toBeGreaterThan(0));
    const url = new URL(observedUrls[0]);
    expect(url.searchParams.get('q')).toBe('meeting');
    expect(url.searchParams.get('status')).toBe('completed');
    expect(url.searchParams.get('page')).toBe('2');
    expect(url.searchParams.get('page_size')).toBe('50');
  });

  it('re-fetches when query.q changes', async () => {
    let callCount = 0;
    server.use(
      http.get('/task/all', () => {
        callCount += 1;
        return HttpResponse.json({
          tasks: [],
          total: 0,
          page: 1,
          page_size: 50,
        });
      }),
    );

    const setHistoricTasks = vi.fn();
    const { rerender } = renderHook(
      ({ q }: { q: string }) =>
        useTaskHistory({
          addHistoricTasks: vi.fn(),
          resumeProcessingTask: vi.fn(),
          setHistoricTasks,
          replaceOnFetch: true,
          query: { q, page: 1, pageSize: 50 },
        }),
      { initialProps: { q: 'first' } },
    );

    await waitFor(() => expect(callCount).toBe(1));
    rerender({ q: 'second' });
    await waitFor(() => expect(callCount).toBe(2));
  });

  it('re-fetches when query.page changes', async () => {
    const pageHits: string[] = [];
    server.use(
      http.get('/task/all', ({ request }) => {
        pageHits.push(new URL(request.url).searchParams.get('page') ?? '');
        return HttpResponse.json({
          tasks: [],
          total: 0,
          page: 1,
          page_size: 50,
        });
      }),
    );

    const setHistoricTasks = vi.fn();
    const { rerender } = renderHook(
      ({ page }: { page: number }) =>
        useTaskHistory({
          addHistoricTasks: vi.fn(),
          resumeProcessingTask: vi.fn(),
          setHistoricTasks,
          replaceOnFetch: true,
          query: { page, pageSize: 50 },
        }),
      { initialProps: { page: 1 } },
    );

    await waitFor(() => expect(pageHits.length).toBe(1));
    rerender({ page: 2 });
    await waitFor(() => expect(pageHits.length).toBe(2));
    expect(pageHits).toEqual(['1', '2']);
  });

  it('re-fetches when query.status changes', async () => {
    const statusHits: (string | null)[] = [];
    server.use(
      http.get('/task/all', ({ request }) => {
        statusHits.push(new URL(request.url).searchParams.get('status'));
        return HttpResponse.json({
          tasks: [],
          total: 0,
          page: 1,
          page_size: 50,
        });
      }),
    );

    const setHistoricTasks = vi.fn();
    const { rerender } = renderHook(
      ({ status }: { status?: string }) =>
        useTaskHistory({
          addHistoricTasks: vi.fn(),
          resumeProcessingTask: vi.fn(),
          setHistoricTasks,
          replaceOnFetch: true,
          query: { status, page: 1, pageSize: 50 },
        }),
      { initialProps: { status: undefined as string | undefined } },
    );

    await waitFor(() => expect(statusHits.length).toBe(1));
    rerender({ status: 'failed' });
    await waitFor(() => expect(statusHits.length).toBe(2));
    expect(statusHits[1]).toBe('failed');
  });

  it('returns meta with total/page/pageSize from envelope', async () => {
    server.use(
      http.get('/task/all', () =>
        HttpResponse.json({
          tasks: [],
          total: 461,
          page: 1,
          page_size: 50,
        }),
      ),
    );

    const { result } = renderHook(() =>
      useTaskHistory({
        addHistoricTasks: vi.fn(),
        resumeProcessingTask: vi.fn(),
        setHistoricTasks: vi.fn(),
        replaceOnFetch: true,
        query: { page: 1, pageSize: 50 },
      }),
    );

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.total).toBe(461);
    expect(result.current.page).toBe(1);
    expect(result.current.pageSize).toBe(50);
  });

  it('replaces historic queue on each fetch when replaceOnFetch=true', async () => {
    server.use(
      http.get('/task/all', ({ request }) => {
        const page = new URL(request.url).searchParams.get('page');
        const tasks =
          page === '2'
            ? [{
                identifier: 'page2-1',
                status: 'completed',
                task_type: 'transcribe',
                file_name: 'p2.mp3',
                url: null,
                audio_duration: null,
                language: null,
                error: null,
                duration: null,
                start_time: null,
                end_time: null,
              }]
            : [{
                identifier: 'page1-1',
                status: 'completed',
                task_type: 'transcribe',
                file_name: 'p1.mp3',
                url: null,
                audio_duration: null,
                language: null,
                error: null,
                duration: null,
                start_time: null,
                end_time: null,
              }];
        return HttpResponse.json({
          tasks,
          total: 2,
          page: page === '2' ? 2 : 1,
          page_size: 1,
        });
      }),
    );

    const setHistoricTasks = vi.fn();
    const { rerender } = renderHook(
      ({ page }: { page: number }) =>
        useTaskHistory({
          addHistoricTasks: vi.fn(),
          resumeProcessingTask: vi.fn(),
          setHistoricTasks,
          replaceOnFetch: true,
          query: { page, pageSize: 1 },
        }),
      { initialProps: { page: 1 } },
    );

    await waitFor(() => expect(setHistoricTasks).toHaveBeenCalledTimes(1));
    rerender({ page: 2 });
    await waitFor(() => expect(setHistoricTasks).toHaveBeenCalledTimes(2));
    const firstCallTaskIds = setHistoricTasks.mock.calls[0][0].map(
      (item: { taskId?: string }) => item.taskId,
    );
    const secondCallTaskIds = setHistoricTasks.mock.calls[1][0].map(
      (item: { taskId?: string }) => item.taskId,
    );
    expect(firstCallTaskIds).toEqual(['page1-1']);
    expect(secondCallTaskIds).toEqual(['page2-1']);
  });
});
