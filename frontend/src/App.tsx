import { UploadDropzone } from '@/components/upload/UploadDropzone';
import { FileQueueList } from '@/components/upload/FileQueueList';
import { ConnectionStatus } from '@/components/upload/ConnectionStatus';
import { useUploadOrchestration } from '@/hooks/useUploadOrchestration';

/**
 * Main upload page
 *
 * Integrates:
 * - UploadDropzone for drag-drop and file selection
 * - FileQueueList for queue display and management
 * - useUploadOrchestration for upload -> transcribe -> progress flow
 */
function App() {
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
          pendingCount={pendingCount}
          readyCount={readyCount}
        />
      )}
    </UploadDropzone>
  );
}

export default App;
