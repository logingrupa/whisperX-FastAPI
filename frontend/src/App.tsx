import { UploadDropzone } from '@/components/upload/UploadDropzone';
import { FileQueueList } from '@/components/upload/FileQueueList';
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
  } = useUploadOrchestration();

  return (
    <UploadDropzone onFilesAdded={addFiles}>
      {queue.length > 0 && (
        <FileQueueList
          queue={queue}
          onRemoveFile={removeFile}
          onUpdateSettings={updateFileSettings}
          onClearPending={clearPendingFiles}
          onStartAll={handleStartAll}
          onStartFile={handleStartFile}
          pendingCount={pendingCount}
          readyCount={readyCount}
        />
      )}
    </UploadDropzone>
  );
}

export default App;
