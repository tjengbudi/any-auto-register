import { useEffect, useRef, useState } from 'react'

export function useSaveNotice() {
  const [saved, setSaved] = useState(false)
  const [ignoredNotice, setIgnoredNotice] = useState('')
  const savedTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const ignoredTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => () => {
    if (savedTimer.current) clearTimeout(savedTimer.current)
    if (ignoredTimer.current) clearTimeout(ignoredTimer.current)
  }, [])

  const showSaved = () => {
    if (savedTimer.current) clearTimeout(savedTimer.current)
    setIgnoredNotice('')
    setSaved(true)
    savedTimer.current = setTimeout(() => setSaved(false), 2000)
  }
  const showIgnored = (text: string) => {
    if (ignoredTimer.current) clearTimeout(ignoredTimer.current)
    setSaved(false)
    setIgnoredNotice(text)
    ignoredTimer.current = setTimeout(() => setIgnoredNotice(''), 4000)
  }
  const reset = () => {
    if (savedTimer.current) clearTimeout(savedTimer.current)
    if (ignoredTimer.current) clearTimeout(ignoredTimer.current)
    setSaved(false)
    setIgnoredNotice('')
  }
  return { saved, ignoredNotice, showSaved, showIgnored, reset }
}
