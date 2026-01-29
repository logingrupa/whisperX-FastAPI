import { Loader2 } from 'lucide-react';
import { Progress } from '@/components/ui/progress';
import { cn } from '@/lib/utils';

interface FileProgressProps {
  /** Progress percentage 0-100 */
  percentage: number;
  /** Show spinner alongside progress */
  showSpinner?: boolean;
  /** Upload speed display (e.g., "12.3 MB/s") */
  uploadSpeed?: string;
  /** Estimated time remaining (e.g., "2m 15s") */
  uploadEta?: string;
  className?: string;
}

/**
 * Progress bar with percentage and optional spinner
 *
 * Per CONTEXT.md:
 * - Progress bar with percentage (horizontal bar, percentage text alongside)
 * - Smooth animation between percentage updates (via CSS)
 * - Spinner icon alongside progress bar during active processing
 */
export function FileProgress({
  percentage,
  showSpinner = true,
  uploadSpeed,
  uploadEta,
  className,
}: FileProgressProps) {
  return (
    <div className={cn('space-y-0', className)}>
      <div className="flex items-center gap-2">
        {showSpinner && (
          <Loader2 className="h-4 w-4 animate-spin text-muted-foreground shrink-0" />
        )}
        <Progress value={percentage} className="flex-1 h-2" />
        <span className="text-sm text-muted-foreground w-10 text-right shrink-0">
          {percentage}%
        </span>
      </div>
      {(uploadSpeed || uploadEta) && (
        <div className="flex justify-between text-xs text-muted-foreground mt-1">
          <span>{uploadSpeed || ''}</span>
          <span>{uploadEta || ''}</span>
        </div>
      )}
    </div>
  );
}
