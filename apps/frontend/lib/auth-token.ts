/**
 * Client-side Clerk JWT holder.
 *
 * Clerk tokens live on the browser only; Server Components must obtain their
 * own token via `auth()` from `@clerk/nextjs/server`. This module is imported
 * by both runtimes, but only the client ever populates it — server code falls
 * back to an explicit `token` argument passed into the api helpers.
 */
let authToken: string | null = null

let waiters: Array<(t: string) => void> = []

export function setAuthToken(token: string | null): void {
  authToken = token
  if (token) {
    waiters.forEach((w) => w(token))
    waiters = []
  }
}

/** Resolves once a token exists (or null after the timeout), so early requests do not 401. */
export function whenAuthToken(timeoutMs = 4000): Promise<string | null> {
  if (authToken) return Promise.resolve(authToken)
  return new Promise((resolve) => {
    const timer = setTimeout(() => resolve(null), timeoutMs)
    waiters.push((t) => {
      clearTimeout(timer)
      resolve(t)
    })
  })
}

export function getAuthToken(): string | null {
  return authToken
}

export function authHeaders(): Record<string, string> {
  const token = getAuthToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}