import { UploadDropzone } from '@/components/upload/UploadDropzone';
import { FileQueueList } from '@/components/upload/FileQueueList';
import { ConnectionStatus } from '@/components/upload/ConnectionStatus';
import { useUploadOrchestration } from '@/hooks/useUploadOrchestration';

/**
 * Transcription page — UI-10.
 *
 * Moved verbatim from App.tsx during Phase 14 router cutover.
 * Existing UploadDropzone + FileQueueList + ConnectionStatus integration is
 * preserved 1:1 — no logic change, no styling change, no regression risk.
 */
export function TranscribePage() {
  const {
    queue,
    addFiles,
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
  } = useUploadOrchestration();

  return (
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
  );
}
