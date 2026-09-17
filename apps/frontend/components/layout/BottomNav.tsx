'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { Home, Flag, Zap, LayoutDashboard } from 'lucide-react'

const NAV = [
  { href: '/', label: 'Home', icon: Home },
  { href: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { href: '/sessions', label: 'Sessions', icon: Flag },
  { href: '/predictions', label: 'Predictions', icon: Zap },
]

export default function BottomNav() {
  const pathname = usePathname()

  return (
    <nav className="bottom-nav-shell">
      <div className="bottom-nav-inner">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = href === '/' ? pathname === '/' : pathname.startsWith(href)
          return (
            <Link key={href} href={href} className="bottom-nav-link" style={{
              color: active ? '#E8002D' : '#94A3B8',
              background: active ? '#FEE2E7' : 'transparent',
              textDecoration: 'none',
            }}>
              <Icon size={18} strokeWidth={active ? 2.5 : 1.8} />
              <span className="bottom-nav-label" style={{
                color: active ? '#E8002D' : '#94A3B8',
                fontWeight: active ? 600 : 400,
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