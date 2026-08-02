import { apiFetch } from '@/lib/utils'
import type { ConfigUpdateResponse } from '@/lib/config-options'

type CacheEntry<T> = {
  value: T | null
  promise: Promise<T> | null
  expiresAt: number
  generation: number
}

function createCacheEntry<T>(): CacheEntry<T> {
  return {
    value: null,
    promise: null,
    expiresAt: 0,
    generation: 0,
  }
}

function loadCached<T>(
  entry: CacheEntry<T>,
  loader: () => Promise<T>,
  options: {
    force?: boolean
    ttlMs?: number
  } = {},
): Promise<T> {
  const force = Boolean(options.force)
  const ttlMs = options.ttlMs ?? 30_000
  const now = Date.now()
  if (!force && entry.value !== null && entry.expiresAt > now) {
    return Promise.resolve(entry.value)
  }
  if (!force && entry.promise) {
    return entry.promise
  }
  const generation = entry.generation
  const pending: Promise<T> = loader()
    .then((value) => {
      if (entry.generation === generation) {
        entry.value = value
        entry.expiresAt = Date.now() + ttlMs
      }
      if (entry.promise === pending) entry.promise = null
      return value
    })
    .catch((error) => {
      if (entry.promise === pending) entry.promise = null
      throw error
    })
  entry.promise = pending
  return pending
}

const platformsCache = createCacheEntry<any[]>()
const configCache = createCacheEntry<Record<string, any>>()
const configOptionsCache = createCacheEntry<any>()

export function invalidatePlatformsCache() {
  platformsCache.value = null
  platformsCache.promise = null
  platformsCache.expiresAt = 0
  platformsCache.generation += 1
}

export function invalidateConfigCache() {
  configCache.value = null
  configCache.promise = null
  configCache.expiresAt = 0
  configCache.generation += 1
}

export function invalidateConfigOptionsCache() {
  configOptionsCache.value = null
  configOptionsCache.promise = null
  configOptionsCache.expiresAt = 0
  configOptionsCache.generation += 1
}

export function invalidateAppDataCaches() {
  invalidatePlatformsCache()
  invalidateConfigCache()
  invalidateConfigOptionsCache()
}

export function getPlatforms(options?: { force?: boolean }) {
  return loadCached(platformsCache, async () => {
    const data = await apiFetch('/platforms')
    return Array.isArray(data) ? data : []
  }, { force: options?.force })
}

export function getConfig(options?: { force?: boolean }) {
  return loadCached(configCache, async () => {
    const data = await apiFetch('/config')
    return data && typeof data === 'object' ? data : {}
  }, { force: options?.force })
}

export function getConfigOptions(options?: { force?: boolean }) {
  return loadCached(configOptionsCache, async () => {
    return apiFetch('/config/options')
  }, { force: options?.force })
}

export async function updateConfig(data: Record<string, string>): Promise<ConfigUpdateResponse> {
  const response = await apiFetch('/config', { method: 'PUT', body: JSON.stringify({ data }) }) as ConfigUpdateResponse
  invalidateConfigCache()
  return response
}
