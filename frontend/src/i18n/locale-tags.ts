import type { Lang } from './LanguageContext'

const LOCALE_TAGS: Record<Lang, string> = { zh: 'zh-CN', en: 'en-US', vi: 'vi-VN' }

export function getLocaleTag(lang: Lang): string {
  return LOCALE_TAGS[lang] ?? LOCALE_TAGS.zh
}
