import type { WhisperModel, WhisperModelInfo } from '@/types/upload';

/**
 * Available Whisper models with their specifications
 * Source: https://github.com/openai/whisper
 *
 * User preference: large-v3 as default (accuracy over speed)
 */
export const WHISPER_MODELS: WhisperModelInfo[] = [
  {
    value: 'tiny',
    label: 'Tiny',
    description: '39M params, ~1GB VRAM, fastest'
  },
  {
    value: 'base',
    label: 'Base',
    description: '74M params, ~1GB VRAM'
  },
  {
    value: 'small',
    label: 'Small',
    description: '244M params, ~2GB VRAM'
  },
  {
    value: 'medium',
    label: 'Medium',
    description: '769M params, ~5GB VRAM'
  },
  {
    value: 'large-v3',
    label: 'Large v3',
    description: '1.5B params, ~10GB VRAM, most accurate'
  },
  {
    value: 'turbo',
    label: 'Turbo',
    description: '809M params, ~6GB VRAM, fast + accurate'
  },
];

/** Default model (user preference: accuracy over speed) */
export const DEFAULT_MODEL: WhisperModel = 'large-v3';

/** Get model info by value */
export function getModelInfo(value: WhisperModel): WhisperModelInfo | undefined {
  return WHISPER_MODELS.find(model => model.value === value);
}
