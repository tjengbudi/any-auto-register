import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { getConfig, invalidateAppDataCaches } from '@/lib/app-data'
import { apiFetch } from '@/lib/utils'
import { catalogZh, type Catalog } from './zh'
import { catalogEn } from './en'
import { catalogViRaw } from './vi'

/* 这是本项目对“零 Context / 零 Store”标准规则的唯一、有意例外（AD-15）。
   仅持有 { lang, catalog, setLang }：只由语言选择器写入，其余各处只读。 */
/* This is the project's one deliberate exception to the "zero Context / zero Store" standard
   rule (AD-15). It holds only { lang, catalog, setLang }: written only by the language
   selector; everywhere else it's read-only. */

export type Lang = 'zh' | 'en' | 'vi'

// 选择器自身固定两个选项，永远不从目录 key 或后端可接受值集合派生；
// 每个选项名固定用其自身语言书写，不随当前语言变化。
// The selector itself always has exactly these two fixed options; they are never
// derived from catalog keys or the backend's set of acceptable values. Each option's
// label is always written in its own language and never changes with the current language.
export const LANGUAGE_OPTIONS: { value: 'zh' | 'en'; label: string }[] = [
  { value: 'zh', label: '中文' },
  { value: 'en', label: 'English' },
]

// 构建期合并：vi 目录中留空的值回退到 zh 对应值，避免任何界面渲染出空字符串。
// 仅在构建 catalogs.vi 时运行一次；zh 与 en 原样直通，不做任何合并。
// Build-time merge: values left blank in the vi catalog fall back to the corresponding
// zh value, so the UI never renders an empty string. Runs once, only when building
// catalogs.vi; zh and en pass through unchanged, with no merging.
function withZhFallback(raw: Catalog, zh: Catalog): Catalog {
  const merged: any = {}
  for (const owner of Object.keys(zh)) {
    merged[owner] = {}
    for (const key of Object.keys((zh as any)[owner])) {
      const value = (raw as any)[owner][key]
      merged[owner][key] = value !== '' ? value : (zh as any)[owner][key]
    }
  }
  return merged
}

const catalogVi = withZhFallback(catalogViRaw, catalogZh)

const catalogs: Record<Lang, Catalog> = {
  zh: catalogZh,
  en: catalogEn,
  vi: catalogVi,
}

type LanguageContextValue = {
  lang: Lang
  catalog: Catalog
  setLang: (next: Lang) => Promise<boolean>
}

const LanguageContext = createContext<LanguageContextValue>({
  lang: 'zh',
  catalog: catalogZh,
  setLang: async () => false,
})

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>('zh')

  // 初始语言只来自 /api/config（story 2.1），从不读写 localStorage。
  // 请求解析前，或请求失败（例如设置了 APP_PASSWORD 且尚无 token 的登录页），
  // 保持默认的 'zh'——这是已知且被接受的空档。
  // Initial language comes only from /api/config (story 2.1); localStorage is never
  // read or written. Before the request resolves, or if it fails (e.g. the login page
  // when APP_PASSWORD is set and there's no token yet), it stays at the default 'zh' —
  // this is a known, accepted gap.
  useEffect(() => {
    let cancelled = false
    getConfig()
      .then((cfg) => {
        if (cancelled) return
        const value = cfg?.ui_language
        if (value === 'zh' || value === 'en' || value === 'vi') {
          setLangState(value)
        }
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [])

  // 写入失败时保留当前语言，不向上抛出未处理的 rejection，改为返回 false 让调用方决定如何提示用户 —
  // On a failed write, keep the current language and return false instead of throwing,
  // so the caller decides how to surface the failure to the user.
  const setLang = async (next: Lang): Promise<boolean> => {
    try {
      await apiFetch('/config', { method: 'PUT', body: JSON.stringify({ data: { ui_language: next } }) })
      invalidateAppDataCaches()
      setLangState(next)
      return true
    } catch {
      // selector visually stays on the previous language; caller decides how to surface the failure
      return false
    }
  }

  return (
    <LanguageContext.Provider value={{ lang, catalog: catalogs[lang], setLang }}>
      {children}
    </LanguageContext.Provider>
  )
}

export function useLanguage() {
  return useContext(LanguageContext)
}
