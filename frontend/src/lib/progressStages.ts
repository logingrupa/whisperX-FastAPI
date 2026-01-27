import type { ProgressStage } from '@/types/websocket';

/** Friendly stage names per CONTEXT.md decisions */
export const FRIENDLY_STAGE_NAMES: Record<ProgressStage, string> = {
  uploading: 'Uploading',
  queued: 'Queued',
  transcribing: 'Converting Speech',
  aligning: 'Syncing Timing',
  diarizing: 'Identifying Speakers',
  complete: 'Done',
};

/** Stage step numbers (out of 5 total processing stages, excluding upload) */
export const STAGE_STEPS: Record<ProgressStage, number> = {
  uploading: 0,  // Not counted in processing steps
  queued: 1,
  transcribing: 2,
  aligning: 3,
  diarizing: 4,
  complete: 5,
};

/** Total number of processing steps (excluding upload) */
export const TOTAL_STEPS = 5;

/** Stage color classes per CONTEXT.md: Upload=blue, Processing=yellow, Complete=green, Error=red */
export const STAGE_COLORS: Record<ProgressStage | 'error', string> = {
  uploading: 'bg-blue-500 text-white',
  queued: 'bg-blue-500 text-white',
  transcribing: 'bg-yellow-500 text-black',
  aligning: 'bg-yellow-500 text-black',
  diarizing: 'bg-yellow-500 text-black',
  complete: 'bg-green-500 text-white',
  error: 'bg-red-500 text-white',
};

/** Stage configuration combining all stage metadata */
export interface StageConfig {
  label: string;
  step: number;
  color: string;
}

export function getStageConfig(stage: ProgressStage): StageConfig {
  return {
    label: FRIENDLY_STAGE_NAMES[stage],
    step: STAGE_STEPS[stage],
    color: STAGE_COLORS[stage],
  };
}

/** Get tooltip text listing all stages */
export function getStageTooltip(): string {
  return 'Queued -> Converting Speech -> Syncing Timing -> Identifying Speakers -> Done';
}
