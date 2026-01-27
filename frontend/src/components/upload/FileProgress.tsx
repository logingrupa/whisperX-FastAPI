import { Loader2 } from 'lucide-react';
import { Progress } from '@/components/ui/progress';
import { cn } from '@/lib/utils';

interface FileProgressProps {
  /** Progress percentage 0-100 */
  percentage: number;
  /** Show spinner alongside progress */
  showSpinner?: boolean;
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
  className,
}: FileProgressProps) {
  return (
    <div className={cn('flex items-center gap-2', className)}>
      {showSpinner && (
        <Loader2 className="h-4 w-4 animate-spin text-muted-foreground shrink-0" />
      )}
      <Progress value={percentage} className="flex-1 h-2" />
      <span className="text-sm text-muted-foreground w-10 text-right shrink-0">
        {percentage}%
      </span>
    </div>
  );
}
