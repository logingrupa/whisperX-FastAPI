import { X, Play, AlertCircle, CheckCircle2, RotateCcw } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
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
  onShowErrorDetails,
}: FileQueueItemProps) {
  const isPending = item.status === 'pending';
  const isProcessing = item.status === 'uploading' || item.status === 'processing';
  const isComplete = item.status === 'complete';
  const isError = item.status === 'error';
  const isReady = isPending && item.selectedLanguage !== '';

  return (
    <Card className={cn(
      'transition-colors',
      isError && 'border-destructive',
      isComplete && 'border-green-500',
    )}>
      <CardContent className="p-4">
        <div className="flex flex-col gap-3">
          {/* Top row: File info and actions */}
          <div className="flex items-center gap-4">
            {/* Status icon for complete/error */}
            {isComplete && (
              <CheckCircle2 className="h-5 w-5 text-green-500 shrink-0" />
            )}
            {isError && (
              <AlertCircle className="h-5 w-5 text-destructive shrink-0" />
            )}

            {/* File info */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <p className="font-medium truncate" title={item.file.name}>
                  {item.file.name}
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
              <p className="text-sm text-muted-foreground">
                {formatFileSize(item.file.size)}
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
              </>
            )}

            {/* Actions */}
            <div className="flex items-center gap-2">
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
            />
          )}
        </div>
      </CardContent>
    </Card>
  );
}
