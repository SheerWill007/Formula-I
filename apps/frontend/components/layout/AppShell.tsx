'use client'

import { usePathname } from 'next/navigation'
import BottomNav from '@/components/layout/BottomNav'
import SmoothScroll from '@/components/layout/SmoothScroll'
import TopBar from '@/components/layout/TopBar'

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const isLanding = pathname === '/'

  return (
    <>
      <SmoothScroll />
      <TopBar />
      <main className={isLanding ? 'landing' : undefined}>{children}</main>
      <BottomNav />
    </>
  )
}
