import { UploadDropzone } from '@/components/upload/UploadDropzone';
import { FileQueueList } from '@/components/upload/FileQueueList';
import { ConnectionStatus } from '@/components/upload/ConnectionStatus';
import { useUploadOrchestration } from '@/hooks/useUploadOrchestration';
import { useTaskHistory } from '@/hooks/useTaskHistory';
import { TopNav } from '@/components/layout/TopNav';

/**
 * Transcription page — UI-10.
 *
 * Moved verbatim from App.tsx during Phase 14 router cutover.
 * Existing UploadDropzone + FileQueueList + ConnectionStatus integration is
 * preserved 1:1 — no logic change, no styling change, no regression risk.
 *
 * Plan 15-ux: composes useTaskHistory once at mount so a refresh during
 * processing does not lose state — the in-flight task is re-seeded into
 * the queue and re-subscribes to WebSocket progress automatically.
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

  // Mount-time DB-driven history seed (Plan 15-ux).
  useTaskHistory({ addHistoricTasks, resumeProcessingTask });

  return (
    <>
      <TopNav />
      <UploadDropzone onFilesAdded={addFiles}>
        <ConnectionStatus
          connectionState={connectionState}
          onReconnect={reconnect}
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
