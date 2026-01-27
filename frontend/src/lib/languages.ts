import type { Language, LanguageCode } from '@/types/upload';

/** Core languages (pinned at top of dropdown per user decision) */
export const CORE_LANGUAGES: Language[] = [
  { code: 'lv', name: 'Latvian', nativeName: 'Latvieski' },
  { code: 'ru', name: 'Russian', nativeName: 'Russkiy' },
  { code: 'en', name: 'English', nativeName: 'English' },
];

/** Additional common languages */
export const OTHER_LANGUAGES: Language[] = [
  { code: 'de', name: 'German', nativeName: 'Deutsch' },
  { code: 'fr', name: 'French', nativeName: 'Francais' },
  { code: 'es', name: 'Spanish', nativeName: 'Espanol' },
  { code: 'it', name: 'Italian', nativeName: 'Italiano' },
  { code: 'pt', name: 'Portuguese', nativeName: 'Portugues' },
  { code: 'nl', name: 'Dutch', nativeName: 'Nederlands' },
  { code: 'pl', name: 'Polish', nativeName: 'Polski' },
  { code: 'ja', name: 'Japanese', nativeName: 'Nihongo' },
  { code: 'ko', name: 'Korean', nativeName: 'Hangugeo' },
  { code: 'zh', name: 'Chinese', nativeName: 'Zhongwen' },
  { code: 'ar', name: 'Arabic', nativeName: 'Arabiyya' },
  { code: 'hi', name: 'Hindi', nativeName: 'Hindi' },
  { code: 'tr', name: 'Turkish', nativeName: 'Turkce' },
];

/** All languages combined */
export const ALL_LANGUAGES: Language[] = [...CORE_LANGUAGES, ...OTHER_LANGUAGES];

/** Language lookup by code */
export const LANGUAGE_BY_CODE: Record<LanguageCode, Language> = Object.fromEntries(
  ALL_LANGUAGES.map(lang => [lang.code, lang])
) as Record<LanguageCode, Language>;

/** Get language name by code */
export function getLanguageName(code: LanguageCode): string {
  return LANGUAGE_BY_CODE[code]?.name ?? code;
}
