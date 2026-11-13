import Link from 'next/link'
import { SignIn, SignUp } from '@clerk/nextjs'
import { CLERK_ENABLED } from '@/lib/clerk'

export default function AuthPage({ mode }: { mode: 'sign-in' | 'sign-up' }) {
  return (
    <div className="layout-wrapper" style={{ display: 'grid', placeItems: 'center', minHeight: '70vh' }}>
      {CLERK_ENABLED ? (
        mode === 'sign-in'
          ? <SignIn routing="path" path="/sign-in" signUpUrl="/sign-up" fallbackRedirectUrl="/predictions" />
          : <SignUp routing="path" path="/sign-up" signInUrl="/sign-in" fallbackRedirectUrl="/predictions" />
      ) : (
        <div style={{ textAlign: 'center', maxWidth: 420, color: 'var(--text-3)' }}>
          <h1 style={{ fontSize: 26, fontWeight: 800, color: 'var(--text)', marginBottom: 10 }}>Sign-in is not switched on yet</h1>
          <p style={{ lineHeight: 1.6 }}>Everything except predictions is open without an account.</p>
          <Link href="/dashboard" className="bx-btn-primary" style={{ marginTop: 20, display: 'inline-flex' }}>Go to dashboard</Link>
        </div>
      )}
    </div>
  )
}
