'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { Home, Flag, Zap, LayoutDashboard, Trophy } from 'lucide-react'
import { useTheme } from '@/app/layout'

const NAV = [
  { href: '/', label: 'Home', icon: Home },
  { href: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { href: '/sessions', label: 'Sessions', icon: Flag },
  { href: '/schedule', label: 'Calendar', icon: Zap },
  { href: '/standings', label: 'Standings', icon: Trophy },
]

export default function BottomNav() {
  const pathname = usePathname()
  const { theme } = useTheme()
  const dark = theme === 'dark'

  return (
    <nav style={{
      position: 'fixed',
      bottom: 0,
      left: 0,
      right: 0,
      zIndex: 50,
      background: dark ? 'rgba(0,0,0,0.85)' : 'rgba(255, 255, 255, 0.94)',
      borderTop: dark ? '1px solid rgba(16,185,129,0.15)' : '1px solid #E2E8F0',
      backdropFilter: 'blur(16px)',
      WebkitBackdropFilter: 'blur(16px)',
      padding: '8px 16px calc(8px + env(safe-area-inset-bottom, 0px))',
      transition: 'background 0.3s, border 0.3s',
    }}>
      <div style={{
        maxWidth: 600,
        margin: '0 auto',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-around',
        height: 60,
      }}>
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = href === '/' ? pathname === '/' : pathname.startsWith(href)
          return (
            <Link key={href} href={href} style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: 3,
              flex: 1,
              padding: '6px 4px',
              borderRadius: 12,
              textDecoration: 'none',
              color: active ? '#E10600' : dark ? '#94A3B8' : '#94A3B8',
              background: active ? 'rgba(225,6,0,0.12)' : 'transparent',
              transition: 'background 150ms ease, color 0.3s',
            }}>
              <Icon size={18} strokeWidth={active ? 2.5 : 1.8} />
              <span style={{
                fontSize: 10,
                fontWeight: active ? 600 : 400,
                fontFamily: 'Space Grotesk, sans-serif',
                letterSpacing: '0.04em',
              }}>
                {label}
              </span>
            </Link>
          )
        })}
      </div>
    </nav>
  )
}
