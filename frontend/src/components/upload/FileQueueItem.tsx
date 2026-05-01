import { useState } from 'react';
import { X, Play, Square, AlertCircle, CheckCircle2, RotateCcw, ChevronDown, ChevronUp } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Collapsible, CollapsibleTrigger, CollapsibleContent } from '@/components/ui/collapsible';
import { TranscriptViewer } from '@/components/transcript/TranscriptViewer';
import { DownloadButtons } from '@/components/transcript/DownloadButtons';
import { fetchTaskResult } from '@/lib/api/taskApi';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { LanguageSelect } from './LanguageSelect';
import { ModelSelect } from './ModelSelect';
import { StageBadge } from './StageBadge';
import { FileProgress } from './FileProgress';
import { getLanguageName } from '@/lib/languages';
import type { FileQueueItem as FileQueueItemType, LanguageCode, WhisperModel } from '@/types/upload';
import type { TranscriptSegment, TaskMetadata } from '@/types/transcript';
import { cn } from '@/lib/utils';

interface FileQueueItemProps {
  item: FileQueueItemType;
  onRemove: (id: string) => void;
  onUpdateSettings: (
    id: string,
    updates: { selectedLanguage?: LanguageCode | ''; selectedModel?: WhisperModel }
  ) => void;
  onStart?: (id: string) => void;
  onRetry?: (id: string) => void;
  onCancel?: (id: string) => void;
  isRetrying?: boolean;
  onShowErrorDetails?: (errorMessage: string, technicalDetail?: string) => void;
}

/**
 * Format file size for display
 */
function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

/**
 * Resolve the status-border modifier class for the outer card.
 *
 * Flat lookup — DRY against `@layer components` modifiers, no nested-if.
 */
function statusBorderClass(item: FileQueueItemType): string {
  if (item.status === 'complete') return 'queue-card-complete';
  if (item.status === 'error') return 'queue-card-error';
  if (item.status === 'uploading' || item.status === 'processing') return 'queue-card-processing';
  return 'queue-card-pending';
}

/**
 * Individual file in the upload queue
 *
 * Displays:
 * - Filename and size
 * - Detected language badge (with tooltip explaining detection)
 * - Language selection dropdown
 * - Model selection dropdown
 * - Remove button (only when pending)
 * - Start button (only when pending and language selected)
 * - Progress bar and stage badge (when uploading/processing)
 * - Checkmark icon (when complete)
 * - Error state with retry button and details link
 */
export function FileQueueItem({
  item,
  onRemove,
  onUpdateSettings,
  onStart,
  onRetry,
  onCancel,
  isRetrying,
  onShowErrorDetails,
}: FileQueueItemProps) {
  const isPending = item.status === 'pending';
  const isProcessing = item.status === 'uploading' || item.status === 'processing';
  const isComplete = item.status === 'complete';
  const isError = item.status === 'error';
  const isReady = isPending && item.selectedLanguage !== '';

  // Transcript state (for completed files)
  const [isTranscriptOpen, setIsTranscriptOpen] = useState(false);
  const [transcriptSegments, setTranscriptSegments] = useState<TranscriptSegment[] | null>(null);
  const [transcriptMetadata, setTranscriptMetadata] = useState<TaskMetadata | null>(null);
  const [isLoadingTranscript, setIsLoadingTranscript] = useState(false);
  const [transcriptError, setTranscriptError] = useState<string | null>(null);

  /**
   * Handle transcript viewer toggle with lazy loading
   * Fetches transcript data on first expand only
   */
  const handleToggleTranscript = async () => {
    // If opening and no data yet, fetch it
    if (!isTranscriptOpen && !transcriptSegments && item.taskId) {
      setIsLoadingTranscript(true);
      setTranscriptError(null);

      const result = await fetchTaskResult(item.taskId);

      if (result.success && result.data.result?.segments) {
        setTranscriptSegments(result.data.result.segments);
        setTranscriptMetadata({
          fileName: result.data.fileName,
          language: result.data.language,
          audioDuration: result.data.audioDuration,
        });
      } else {
        setTranscriptError(
          result.success
            ? 'No transcript data available'
            : result.error.detail
        );
      }

      setIsLoadingTranscript(false);
    }

    setIsTranscriptOpen(!isTranscriptOpen);
  };

  return (
    <Card className={cn('queue-card', statusBorderClass(item))}>
      <CardContent className="queue-card-content">
        <div className="flex flex-col gap-3">
          {/* Top row: File info and actions */}
          <div className="queue-card-row">
            {/* Status icon for complete/error */}
            {isComplete && (
              <CheckCircle2 className="h-5 w-5 text-green-500 shrink-0" />
            )}
            {isError && (
              <AlertCircle className="h-5 w-5 text-destructive shrink-0" />
            )}

            {/* File info */}
            <div className="queue-card-filename">
              <div className="flex flex-wrap items-center gap-2">
                <p className="font-medium truncate" title={item.fileName}>
                  {item.fileName}
                </p>
                {/* Detected language badge (only when pending) */}
                {item.detectedLanguage && isPending && (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Badge variant="secondary" className="shrink-0">
                        {getLanguageName(item.detectedLanguage)}
                      </Badge>
                    </TooltipTrigger>
                    <TooltipContent>
                      <p>Detected from filename pattern</p>
                    </TooltipContent>
                  </Tooltip>
                )}
                {/* Stage badge (when processing) */}
                {isProcessing && item.progressStage && (
                  <StageBadge stage={item.progressStage} />
                )}
                {/* Complete badge */}
                {isComplete && (
                  <StageBadge stage="complete" />
                )}
                {/* Error badge */}
                {isError && (
                  <StageBadge stage="error" />
                )}
                {/* Warning if no language selected (pending only) */}
                {!item.selectedLanguage && isPending && (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <AlertCircle className="h-4 w-4 text-amber-500 shrink-0" />
                    </TooltipTrigger>
                    <TooltipContent>
                      <p>Please select a language</p>
                    </TooltipContent>
                  </Tooltip>
                )}
              </div>
              <p className="text-sm text-muted-foreground break-words">
                {item.kind === 'historic' && item.fileSize === 0
                  ? '—'
                  : formatFileSize(item.fileSize)}
                {/* Error message with "Show details" link */}
                {isError && item.errorMessage && (
                  <>
                    <span className="ml-2">- {item.errorMessage}</span>
                    {item.technicalDetail && onShowErrorDetails && (
                      <button
                        type="button"
                        className="ml-2 text-primary hover:underline"
                        onClick={() =>
                          onShowErrorDetails(item.errorMessage!, item.technicalDetail)
                        }
                      >
                        Show details
                      </button>
                    )}
                  </>
                )}
              </p>
            </div>

            {/* Settings (only when pending) */}
            {isPending && (
              <>
                <LanguageSelect
                  value={item.selectedLanguage}
                  onValueChange={(value) =>
                    onUpdateSettings(item.id, { selectedLanguage: value })
                  }
                />
                <ModelSelect
                  value={item.selectedModel}
                  onValueChange={(value) =>
                    onUpdateSettings(item.id, { selectedModel: value })
                  }
                />
                {item.selectedLanguage === 'lv' && (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Badge variant="outline" className="shrink-0 text-xs border-blue-400 text-blue-600">
                        LV model
                      </Badge>
                    </TooltipTrigger>
                    <TooltipContent>
                      <p>Whisper large-v3 (full) will be used for better Latvian accuracy</p>
                    </TooltipContent>
                  </Tooltip>
                )}
                {item.selectedLanguage === 'ru' && (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Badge variant="outline" className="shrink-0 text-xs border-blue-400 text-blue-600">
                        RU model
                      </Badge>
                    </TooltipTrigger>
                    <TooltipContent>
                      <p>Fine-tuned Russian model (whisper-large-v3-russian) will be used automatically</p>
                    </TooltipContent>
                  </Tooltip>
                )}
              </>
            )}

            {/* Actions */}
            <div className="queue-card-actions">
              {/* Start button (per-file, pending only) */}
              {onStart && isPending && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => onStart(item.id)}
                  disabled={!isReady}
                  title={isReady ? 'Start processing' : 'Select language first'}
                >
                  <Play className="h-4 w-4" />
                </Button>
              )}

              {/* Cancel button (uploading stage only) */}
              {onCancel && item.progressStage === 'uploading' && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => onCancel(item.id)}
                  title="Cancel upload"
                >
                  <Square className="h-4 w-4" />
                </Button>
              )}

              {/* Retry button (error only) */}
              {onRetry && isError && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => onRetry(item.id)}
                  title="Retry processing"
                >
                  <RotateCcw className="h-4 w-4" />
                </Button>
              )}

              {/* Remove button (only when pending) */}
              {isPending && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => onRemove(item.id)}
                  className="text-muted-foreground hover:text-destructive"
                >
                  <X className="h-4 w-4" />
                </Button>
              )}
            </div>
          </div>

          {/* Progress bar row (when uploading or processing) */}
          {isProcessing && item.progressPercentage !== undefined && (
            <FileProgress
              percentage={item.progressPercentage}
              showSpinner={true}
              uploadSpeed={item.uploadSpeed}
              uploadEta={item.uploadEta}
              isRetrying={isRetrying}
            />
          )}

          {/* Transcript viewer (completed files only) */}
          {isComplete && item.taskId && (
            <Collapsible open={isTranscriptOpen} onOpenChange={setIsTranscriptOpen}>
              <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-border">
                <CollapsibleTrigger asChild>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={handleToggleTranscript}
                    className="gap-1"
                  >
                    {isTranscriptOpen ? (
                      <ChevronUp className="h-4 w-4" />
                    ) : (
                      <ChevronDown className="h-4 w-4" />
                    )}
                    {isLoadingTranscript ? 'Loading...' : 'View Transcript'}
                  </Button>
                </CollapsibleTrigger>

                {/* Download buttons (visible once transcript is loaded) */}
                {transcriptSegments && (
                  <DownloadButtons
                    segments={transcriptSegments}
                    filename={item.fileName.replace(/\.[^/.]+$/, '')}
                    metadata={transcriptMetadata ?? undefined}
                  />
                )}
              </div>

              <CollapsibleContent>
                <div className="pt-3">
                  {isLoadingTranscript && (
                    <div className="text-center py-4 text-muted-foreground">
                      Loading transcript...
                    </div>
                  )}

                  {transcriptError && (
                    <div className="text-center py-4 text-destructive">
                      {transcriptError}
                    </div>
                  )}

                  {transcriptSegments && !isLoadingTranscript && (
                    <TranscriptViewer segments={transcriptSegments} />
                  )}
                </div>
              </CollapsibleContent>
            </Collapsible>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
