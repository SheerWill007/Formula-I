'use client'

import { Analytics } from '@vercel/analytics/next'
import { SpeedInsights } from '@vercel/speed-insights/next'
import './globals.css'
import BottomNav from '@/components/layout/BottomNav'
import SmoothScroll from '@/components/layout/SmoothScroll'
import TopBar from '@/components/layout/TopBar'
import { ThemeProvider } from '@/components/layout/ThemeProvider'
import { AudioProvider } from '@/components/layout/AudioProvider'

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body suppressHydrationWarning>
        <ThemeProvider>
          <AudioProvider>
            <SmoothScroll />
            <TopBar />
            <main>
              {children}
            </main>
            <BottomNav />
            <Analytics />
            <SpeedInsights />
          </AudioProvider>
        </ThemeProvider>
      </body>
    </html>
  )
}
