'use client'

import { useAuth } from '@clerk/nextjs'
import { useEffect } from 'react'
import { setAuthToken } from '@/lib/auth-token'

/**
 * Syncs the signed-in user's Clerk JWT into the shared client token holder so
 * api.ts and raw fetches can attach `Authorization` to protected product APIs.
 * Mounted once inside ClerkProvider in the root layout.
 *
 * Clerk session JWTs expire; if we only fetch the token at mount the page ends
 * up sending a stale, expired JWT ("Signature has expired"). So we re-fetch the
 * token on a short interval AND whenever the tab regains focus/visibility so a
 * long-idle tab still refreshes right before the next API call.
 */
const REFRESH_MS = 4 * 60 * 1000

export default function AuthTokenSync() {
  const { getToken, isLoaded } = useAuth()

  useEffect(() => {
    if (!isLoaded) return
    let active = true

    const refresh = () => {
      // Clerk's cached token is refreshed by Clerk itself shortly before it
      // expires, and the 4 minute interval plus focus handlers below re-read it,
      // so no forced network round trip is needed on every call.
      getToken()
        .then(token => {
          if (active) setAuthToken(token)
        })
        .catch(() => {})
    }

    // Immediate sync on mount/sign-in, then keep the JWT fresh:
    refresh()
    const interval = window.setInterval(refresh, REFRESH_MS)

    const refreshWhenVisible = () => {
      if (document.visibilityState === 'visible') refresh()
    }
    document.addEventListener('visibilitychange', refreshWhenVisible)
    window.addEventListener('focus', refreshWhenVisible)

    return () => {
      active = false
      window.clearInterval(interval)
      document.removeEventListener('visibilitychange', refreshWhenVisible)
      window.removeEventListener('focus', refreshWhenVisible)
    }
  }, [getToken, isLoaded])

  return null
}