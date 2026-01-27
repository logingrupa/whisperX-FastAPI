import { Badge } from '@/components/ui/badge';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import {
  FRIENDLY_STAGE_NAMES,
  STAGE_COLORS,
  STAGE_STEPS,
  TOTAL_STEPS,
  getStageTooltip,
} from '@/lib/progressStages';
import type { ProgressStage } from '@/types/websocket';

interface StageBadgeProps {
  stage: ProgressStage | 'error';
  className?: string;
}

/**
 * Stage indicator badge showing current processing stage
 *
 * Per CONTEXT.md:
 * - Badge/chip showing current stage name
 * - Step counter in badge (1/5, 2/5, etc.)
 * - Tooltip reveals remaining stages
 * - Different badge color per stage (Upload=blue, Processing=yellow, Complete=green, Error=red)
 */
export function StageBadge({ stage, className }: StageBadgeProps) {
  const isError = stage === 'error';
  const label = isError ? 'Error' : FRIENDLY_STAGE_NAMES[stage];
  const color = STAGE_COLORS[stage];
  const step = isError ? 0 : STAGE_STEPS[stage];

  // Show step counter for processing stages (not for error, complete, or uploading)
  const showStepCounter =
    !isError && stage !== 'complete' && stage !== 'uploading' && step > 0;

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Badge
          className={cn('border-transparent cursor-help', color, className)}
        >
          {label}
          {showStepCounter && ` (${step}/${TOTAL_STEPS})`}
        </Badge>
      </TooltipTrigger>
      <TooltipContent>
        <p>{getStageTooltip()}</p>
      </TooltipContent>
    </Tooltip>
  );
}
