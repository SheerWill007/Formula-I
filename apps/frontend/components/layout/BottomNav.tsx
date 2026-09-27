'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { Home, LayoutDashboard, Flag, Calendar, Trophy } from 'lucide-react'

const NAV = [
  { href: '/', label: 'Home', icon: Home },
  { href: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { href: '/sessions', label: 'Sessions', icon: Flag },
  { href: '/schedule', label: 'Calendar', icon: Calendar },
  { href: '/dashboard#standings', label: 'Standings', icon: Trophy },
]

export default function BottomNav() {
  const pathname = usePathname()

  return (
    <nav className="bottom-nav-shell" aria-label="Bottom Navigation">
      <div className="bottom-nav-inner">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = href === '/' ? pathname === '/' : pathname.startsWith(href)
          return (
            <Link
              key={href}
              href={href}
              className={`bottom-nav-link ${active ? 'active' : ''}`}
            >
              <Icon size={16} strokeWidth={active ? 2.5 : 1.9} />
              <span className="bottom-nav-label">
                {label}
              </span>
            </Link>
          )
        })}
      </div>
    </nav>
  )
}