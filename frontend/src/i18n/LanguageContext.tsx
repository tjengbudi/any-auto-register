import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { getConfig } from '@/lib/app-data'
import { apiFetch } from '@/lib/utils'
import { catalogZh, type Catalog } from './zh'
import { catalogEn } from './en'
import { catalogViRaw } from './vi'

/* 这是本项目对“零 Context / 零 Store”标准规则的唯一、有意例外（AD-15）。
   仅持有 { lang, catalog, setLang }：只由语言选择器写入，其余各处只读。 */

export type Lang = 'zh' | 'en' | 'vi'

// 选择器自身固定两个选项，永远不从目录 key 或后端可接受值集合派生；
// 每个选项名固定用其自身语言书写，不随当前语言变化。
export const LANGUAGE_OPTIONS: { value: 'zh' | 'en'; label: string }[] = [
  { value: 'zh', label: '中文' },
  { value: 'en', label: 'English' },
]

// 构建期合并：vi 目录中留空的值回退到 zh 对应值，避免任何界面渲染出空字符串。
// 仅在构建 catalogs.vi 时运行一次；zh 与 en 原样直通，不做任何合并。
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
  setLang: (next: Lang) => Promise<void>
}

const LanguageContext = createContext<LanguageContextValue>({
  lang: 'zh',
  catalog: catalogZh,
  setLang: async () => {},
})

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>('zh')

  // 初始语言只来自 /api/config（story 2.1），从不读写 localStorage。
  // 请求解析前，或请求失败（例如设置了 APP_PASSWORD 且尚无 token 的登录页），
  // 保持默认的 'zh'——这是已知且被接受的空档。
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

  // 写入失败时静默保留当前语言，不向上抛出未处理的 rejection —
  // On a failed write, silently keep the current language rather than
  // letting the rejection go unhandled at the caller.
  const setLang = async (next: Lang) => {
    try {
      await apiFetch('/config', { method: 'PUT', body: JSON.stringify({ data: { ui_language: next } }) })
      setLangState(next)
    } catch {
      // no-op: selector visually stays on the previous language
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
