import type { Metadata } from 'next'
import { Analytics } from '@vercel/analytics/next'
import { SpeedInsights } from '@vercel/speed-insights/next'
import { ClerkProvider } from '@clerk/nextjs'
import './globals.css'
import AppShell from '@/components/layout/AppShell'
import AuthTokenSync from '@/components/auth/AuthTokenSync'
import { ThemeProvider } from '@/components/layout/ThemeProvider'
import { AudioProvider } from '@/components/layout/AudioProvider'
import { CLERK_ENABLED } from '@/lib/clerk'

export const metadata: Metadata = {
  title: 'BoxUp | F1 Race Analytics',
  description: 'Formula 1 telemetry, tyre strategy, driver profiles and race predictions.',
}

function Document({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body suppressHydrationWarning>
        <ThemeProvider>
          <AudioProvider>
            {CLERK_ENABLED && <AuthTokenSync />}
            <AppShell>{children}</AppShell>
            <Analytics />
            <SpeedInsights />
          </AudioProvider>
        </ThemeProvider>
      </body>
    </html>
  )
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  if (!CLERK_ENABLED) return <Document>{children}</Document>
  return (
    <ClerkProvider appearance={{ variables: { colorPrimary: '#E8002D' } }}>
      <Document>{children}</Document>
    </ClerkProvider>
  )
}
