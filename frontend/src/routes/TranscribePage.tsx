import { useMemo, useState } from 'react';
import { UploadDropzone } from '@/components/upload/UploadDropzone';
import { FileQueueList } from '@/components/upload/FileQueueList';
import { ConnectionStatus } from '@/components/upload/ConnectionStatus';
import {
  ALL_STATUSES,
  QueueFilterBar,
  type StatusFilter,
} from '@/components/upload/QueueFilterBar';
import { useUploadOrchestration } from '@/hooks/useUploadOrchestration';
import { useTaskHistory } from '@/hooks/useTaskHistory';
import { TopNav } from '@/components/layout/TopNav';
import type { FetchAllTasksOptions } from '@/lib/api/taskApi';

const PAGE_SIZE = 50;

/**
 * Transcription page — UI-10.
 *
 * Owns the query state (Plan 15-ux pagination): searchQuery / statusFilter
 * / currentPage. The QueueFilterBar receives them as props (SRP — page is
 * the orchestrator, bar is dumb input UI), and useTaskHistory consumes
 * them as a single ``query`` object so re-fetch fires only when the
 * serialised key changes.
 *
 * <TopNav> renders as a SIBLING above the dropzone (not wrapped in AppShell)
 * so the dropzone stays full-bleed per Plan 14-04 lock. Same nav as
 * /dashboard/* routes — single source of truth.
 */
export function TranscribePage() {
  const {
    queue,
    addFiles,
    addHistoricTasks,
    setHistoricTasks,
    removeFile,
    clearPendingFiles,
    updateFileSettings,
    pendingCount,
    readyCount,
    handleStartAll,
    handleStartFile,
    handleRetry,
    handleCancel,
    retryingFileId,
    connectionState,
    reconnect,
    resumeProcessingTask,
  } = useUploadOrchestration();

  // Single source of truth for queue query state (Plan 15-ux).
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>(ALL_STATUSES);
  const [currentPage, setCurrentPage] = useState<number>(1);

  // Reset to page 1 whenever filters change so an empty page-2 query
  // does not show "no results" when results exist on page 1.
  function applySearchQuery(value: string): void {
    setSearchQuery(value);
    setCurrentPage(1);
  }
  function applyStatusFilter(value: StatusFilter): void {
    setStatusFilter(value);
    setCurrentPage(1);
  }

  const query = useMemo<FetchAllTasksOptions>(() => {
    const opts: FetchAllTasksOptions = {
      page: currentPage,
      pageSize: PAGE_SIZE,
    };
    if (searchQuery.length > 0) opts.q = searchQuery;
    if (statusFilter !== ALL_STATUSES) opts.status = statusFilter;
    return opts;
  }, [searchQuery, statusFilter, currentPage]);

  const meta = useTaskHistory({
    addHistoricTasks,
    resumeProcessingTask,
    query,
    replaceOnFetch: true,
    setHistoricTasks,
  });

  const totalPages = Math.max(1, Math.ceil(meta.total / PAGE_SIZE));

  return (
    <>
      <TopNav />
      <UploadDropzone onFilesAdded={addFiles}>
        <ConnectionStatus
          connectionState={connectionState}
          onReconnect={reconnect}
        />
        <QueueFilterBar
          searchQuery={searchQuery}
          onSearchQueryChange={applySearchQuery}
          statusFilter={statusFilter}
          onStatusFilterChange={applyStatusFilter}
          currentPage={currentPage}
          totalPages={totalPages}
          onPageChange={setCurrentPage}
        />
        {queue.length > 0 && (
          <FileQueueList
            queue={queue}
            onRemoveFile={removeFile}
            onUpdateSettings={updateFileSettings}
            onClearPending={clearPendingFiles}
            onStartAll={handleStartAll}
            onStartFile={handleStartFile}
            onRetry={handleRetry}
            onCancel={handleCancel}
            retryingFileId={retryingFileId}
            pendingCount={pendingCount}
            readyCount={readyCount}
          />
        )}
      </UploadDropzone>
    </>
  );
}
