'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useEffect, useRef, useState } from 'react'
import { Home, LayoutDashboard, Flag, Zap } from 'lucide-react'

const NAV = [
  { href: '/', label: 'Home', icon: Home },
  { href: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { href: '/sessions', label: 'Sessions', icon: Flag },
  { href: '/predictions', label: 'Predictions', icon: Zap },
]

export default function BottomNav() {
  const pathname = usePathname()
  const [isVisible, setIsVisible] = useState(false)
  const lastScrollY = useRef(0)
  const hideTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    const hideNavigation = () => {
      if (hideTimer.current) clearTimeout(hideTimer.current)
      hideTimer.current = setTimeout(() => setIsVisible(false), 700)
    }

    const handleScroll = () => {
      const currentScrollY = window.scrollY
      const isScrollingDown = currentScrollY > lastScrollY.current

      if (isScrollingDown && currentScrollY > 4) setIsVisible(true)
      hideNavigation()
      lastScrollY.current = currentScrollY
    }

    window.addEventListener('scroll', handleScroll, { passive: true })
    return () => {
      window.removeEventListener('scroll', handleScroll)
      if (hideTimer.current) clearTimeout(hideTimer.current)
    }
  }, [])

  return (
    <nav
      className={`bottom-nav-shell ${isVisible ? 'is-visible' : ''}`}
      aria-label="Bottom Navigation"
      aria-hidden={!isVisible}
    >
      <div className="bottom-nav-inner">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = href === '/' ? pathname === '/' : pathname.startsWith(href)
          return (
            <Link
              key={href}
              href={href}
              tabIndex={isVisible ? 0 : -1}
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
