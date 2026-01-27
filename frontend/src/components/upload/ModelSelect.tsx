import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { WHISPER_MODELS } from '@/lib/whisperModels';
import type { WhisperModel } from '@/types/upload';

interface ModelSelectProps {
  value: WhisperModel;
  onValueChange: (value: WhisperModel) => void;
  disabled?: boolean;
}

/**
 * Whisper model selection dropdown
 *
 * Shows all available model sizes with their labels
 * Default: large-v3 (per user preference for accuracy)
 */
export function ModelSelect({
  value,
  onValueChange,
  disabled = false,
}: ModelSelectProps) {
  return (
    <Select
      value={value}
      onValueChange={onValueChange as (value: string) => void}
      disabled={disabled}
    >
      <SelectTrigger className="w-[130px]">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {WHISPER_MODELS.map(model => (
          <SelectItem key={model.value} value={model.value}>
            {model.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
