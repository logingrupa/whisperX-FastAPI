/**
 * Regression tests for useFileQueue.addHistoricTasks (Plan 15-ux).
 *
 * Coverage:
 *   - Historic items prepend to existing live items (refresh ordering)
 *   - taskId-based de-dup: re-seeding same taskIds is a no-op
 *   - isFileReady remains false for historic items even with language set
 *   - Live + historic items co-exist without status interference
 */
import { describe, it, expect } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import { useFileQueue } from '@/hooks/useFileQueue';
import type { FileQueueItem } from '@/types/upload';

function makeHistoric(overrides: Partial<FileQueueItem> = {}): FileQueueItem {
  return {
    id: crypto.randomUUID(),
    kind: 'historic',
    file: null,
    fileName: 'historic.mp3',
    fileSize: 0,
    detectedLanguage: null,
    selectedLanguage: 'en',
    selectedModel: 'large-v3',
    status: 'complete',
    taskId: 'task-h-1',
    progressPercentage: 100,
    progressStage: 'complete',
    ...overrides,
  };
}

describe('useFileQueue.addHistoricTasks — queue-merge regression', () => {
  it('prepends historic items to existing live items', () => {
    const { result } = renderHook(() => useFileQueue());

    // Add a live file first
    act(() => {
      result.current.addFiles([
        new File(['x'], 'live.mp3', { type: 'audio/mpeg' }),
      ]);
    });
    expect(result.current.queue).toHaveLength(1);
    expect(result.current.queue[0].kind).toBe('live');

    // Seed historic — should land in front of the live row
    act(() => {
      result.current.addHistoricTasks([makeHistoric({ taskId: 'h-1' })]);
    });

    expect(result.current.queue).toHaveLength(2);
    expect(result.current.queue[0].kind).toBe('historic');
    expect(result.current.queue[0].taskId).toBe('h-1');
    expect(result.current.queue[1].kind).toBe('live');
  });

  it('de-duplicates by taskId when seeded twice', () => {
    const { result } = renderHook(() => useFileQueue());
    const item = makeHistoric({ taskId: 'h-dup' });

    act(() => {
      result.current.addHistoricTasks([item]);
    });
    expect(result.current.queue).toHaveLength(1);

    // Re-seeding the same taskId must NOT add a duplicate row
    act(() => {
      result.current.addHistoricTasks([makeHistoric({ taskId: 'h-dup' })]);
    });
    expect(result.current.queue).toHaveLength(1);
  });

  it('isFileReady returns false for historic items even with language set', () => {
    const { result } = renderHook(() => useFileQueue());
    const historic = makeHistoric({
      taskId: 'h-not-ready',
      status: 'pending',
      selectedLanguage: 'en',
    });
    act(() => {
      result.current.addHistoricTasks([historic]);
    });
    const seededItem = result.current.queue[0];
    // Historic items must never be considered ready for upload — they
    // have no File object.
    expect(result.current.isFileReady(seededItem)).toBe(false);
  });

  it('a no-op when called with empty array', () => {
    const { result } = renderHook(() => useFileQueue());
    act(() => {
      result.current.addHistoricTasks([]);
    });
    expect(result.current.queue).toHaveLength(0);
  });

  it('readyCount excludes historic items', () => {
    const { result } = renderHook(() => useFileQueue());

    act(() => {
      result.current.addFiles([
        new File(['x'], 'live.mp3', { type: 'audio/mpeg' }),
      ]);
    });
    // After detectLanguageFromFilename, live item may or may not have
    // language preset — force a known-ready state explicitly.
    const liveId = result.current.queue[0].id;
    act(() => {
      result.current.updateFileSettings(liveId, { selectedLanguage: 'en' });
    });

    act(() => {
      result.current.addHistoricTasks([
        makeHistoric({
          taskId: 'h',
          status: 'pending',
          selectedLanguage: 'en',
        }),
      ]);
    });

    // Only the live item counts as ready
    expect(result.current.readyCount).toBe(1);
  });
});
