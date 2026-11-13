import { whenAuthToken } from '@/lib/auth-token'

export class HttpError extends Error {
  constructor(public status: number, message: string) {
    super(message)
    this.name = 'HttpError'
  }
}

const cache = new Map<string, { at: number; promise: Promise<unknown> }>()

/** GET JSON with a short in-memory cache, request de-duplication and real HTTP errors. */
export function getJson<T>(url: string, ttlMs = 60_000): Promise<T> {
  const hit = cache.get(url)
  if (hit && Date.now() - hit.at < ttlMs) return hit.promise as Promise<T>
  const promise = whenAuthToken()
    .then((token) => fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} }))
    .then((res) => {
      if (!res.ok) throw new HttpError(res.status, `Request failed (${res.status})`)
      return res.json() as Promise<T>
    })
  cache.set(url, { at: Date.now(), promise })
  promise.catch(() => cache.delete(url))
  return promise
}
