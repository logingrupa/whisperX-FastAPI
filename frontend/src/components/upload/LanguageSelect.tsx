import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { CORE_LANGUAGES, OTHER_LANGUAGES } from '@/lib/languages';
import type { LanguageCode } from '@/types/upload';

interface LanguageSelectProps {
  value: LanguageCode | '';
  onValueChange: (value: LanguageCode) => void;
  disabled?: boolean;
}

/**
 * Language selection dropdown with grouped options
 *
 * Groups:
 * - Primary: Core 3 languages (Latvian, Russian, English) pinned at top
 * - Other: Additional common languages
 *
 * Per CONTEXT.md: "Core 3 languages pinned at top of dropdown"
 */
export function LanguageSelect({
  value,
  onValueChange,
  disabled = false,
}: LanguageSelectProps) {
  return (
    <Select
      value={value}
      onValueChange={onValueChange as (value: string) => void}
      disabled={disabled}
    >
      <SelectTrigger className="w-[140px]">
        <SelectValue placeholder="Select language" />
      </SelectTrigger>
      <SelectContent>
        <SelectGroup>
          <SelectLabel>Primary</SelectLabel>
          {CORE_LANGUAGES.map(language => (
            <SelectItem key={language.code} value={language.code}>
              {language.name}
            </SelectItem>
          ))}
        </SelectGroup>
        <SelectGroup>
          <SelectLabel>Other</SelectLabel>
          {OTHER_LANGUAGES.map(language => (
            <SelectItem key={language.code} value={language.code}>
              {language.name}
            </SelectItem>
          ))}
        </SelectGroup>
      </SelectContent>
    </Select>
  );
}
