import { UploadDropzone } from '@/components/upload/UploadDropzone';
import { FileQueueList } from '@/components/upload/FileQueueList';
import { useFileQueue } from '@/hooks/useFileQueue';

/**
 * Main upload page
 *
 * Integrates:
 * - UploadDropzone for drag-drop and file selection
 * - FileQueueList for queue display and management
 * - useFileQueue for state management
 *
 * Note: Start functionality is stubbed (Phase 5 will add actual upload)
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
  } = useFileQueue();

  // Stub for start functionality (implemented in Phase 5)
  const handleStartAll = () => {
    console.log('Start all clicked - will be implemented in Phase 5');
  };

  const handleStartFile = (id: string) => {
    console.log(`Start file ${id} clicked - will be implemented in Phase 5`);
  };

  return (
    <UploadDropzone onFilesAdded={addFiles}>
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
    </UploadDropzone>
  );
}

export default App;
