import { useLanguage } from '@/i18n'

/* 提示后端提供、尚未随界面语言翻译的内容 — informational, non-dismissible, hidden under zh. */
export default function UntranslatedNotice() {
  const { lang, catalog } = useLanguage()
  if (lang === 'zh') return null
  return (
    <div className="rounded-lg border border-sky-500/20 bg-sky-500/10 px-4 py-3 text-sm text-[var(--text-secondary)]">
      {catalog.settings.untranslatedNotice}
    </div>
  )
}
