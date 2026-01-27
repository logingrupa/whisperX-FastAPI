import { X, Play, AlertCircle } from 'lucide-react';
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
 */
export function FileQueueItem({
  item,
  onRemove,
  onUpdateSettings,
  onStart,
}: FileQueueItemProps) {
  const isPending = item.status === 'pending';
  const isReady = isPending && item.selectedLanguage !== '';

  return (
    <Card className={cn(
      'transition-colors',
      item.status === 'error' && 'border-destructive',
      item.status === 'complete' && 'border-green-500',
    )}>
      <CardContent className="p-4">
        <div className="flex items-center gap-4">
          {/* File info */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <p className="font-medium truncate" title={item.file.name}>
                {item.file.name}
              </p>
              {/* Detected language badge */}
              {item.detectedLanguage && (
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
              {/* Warning if no language selected */}
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
              {item.status !== 'pending' && (
                <span className="ml-2 capitalize">
                  - {item.status}
                  {item.errorMessage && `: ${item.errorMessage}`}
                </span>
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
            {/* Start button (per-file) */}
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
      </CardContent>
    </Card>
  );
}
