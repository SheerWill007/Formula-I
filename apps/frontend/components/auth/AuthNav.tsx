'use client'

import Link from 'next/link'
import { Show, UserButton } from '@clerk/nextjs'
import { LogIn } from 'lucide-react'

/** Sign-in button or account menu. Only rendered when Clerk is configured. */
export default function AuthNav({ compact = false }: { compact?: boolean }) {
  return (
    <>
      <Show when="signed-out">
        {compact ? (
          <Link href="/sign-in" className="tube-control-btn" aria-label="Sign in" title="Sign in">
            <LogIn size={16} strokeWidth={2.2} />
          </Link>
        ) : (
          <Link href="/sign-in" className="auth-pill">Sign in</Link>
        )}
      </Show>
      <Show when="signed-in">
        <span className={compact ? 'tube-control-btn' : 'auth-user'}>
          <UserButton />
        </span>
      </Show>
    </>
  )
}
