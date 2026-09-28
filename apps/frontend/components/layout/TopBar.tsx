'use client'

import React from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useTheme } from 'next-themes'
import { Volume2, Volume1, VolumeX, Sun, Moon, Menu, X } from 'lucide-react'
import { useMusic } from '@/components/layout/AudioProvider'

export default function TopBar() {
  const pathname = usePathname()
  const { theme, setTheme } = useTheme()
  const { isPlaying, volume, toggleMusic } = useMusic()
  const [mounted, setMounted] = React.useState(false)
  const [menuOpen, setMenuOpen] = React.useState(false)

  React.useEffect(() => {
    setMounted(true)
  }, [])

  React.useEffect(() => {
    setMenuOpen(false)
  }, [pathname])

  React.useEffect(() => {
    if (!menuOpen) return
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setMenuOpen(false)
    }
    window.addEventListener('keydown', onKeyDown)
    return () => {
      document.body.style.overflow = previousOverflow
      window.removeEventListener('keydown', onKeyDown)
    }
  }, [menuOpen])

  const navItems = [
    {
      name: 'Home',
      href: '/',
      active: pathname === '/',
      isHome: true,
    },
    {
      name: 'Dashboard',
      href: '/dashboard',
      active: pathname === '/dashboard',
    },
    {
      name: 'Sessions',
      href: '/sessions',
      active:
        pathname === '/sessions' ||
        pathname.startsWith('/sessions/'),
    },
    {
      name: 'Season Calendar',
      href: '/schedule',
      active: pathname === '/schedule',
    },
    {
      name: 'Standings',
      href: '/dashboard#standings',
      active: pathname === '/dashboard#standings',
    },
  ]

  const mobileNavItems = [
    ...navItems,
    {
      name: 'Predictions',
      href: '/predictions',
      active: pathname === '/predictions' || pathname.startsWith('/predictions'),
      isHome: false,
    },
  ]

  const isDark = mounted ? theme === 'dark' : true

  const volumeIcon = volume === 0 ? VolumeX : volume <= 0.5 ? Volume1 : Volume2
  const VolumeIcon = volumeIcon

  return (
    <header className="topbar-wrapper">
      <Link href="/" className="corner-brand" aria-label="BoxUp Home">
        BoxUp
      </Link>
      <nav className="topbar-tube">
        <div className="topbar-nav-links">
          {navItems.map((item) => {
            const isActive = item.active
            return (
              <Link
                key={item.name}
                href={item.href}
                className={`topbar-link ${isActive ? 'active' : ''} ${item.isHome ? 'home-tab' : ''}`}
              >
                {item.name}
              </Link>
            )
          })}
        </div>

        <div className="topbar-controls">
          <button
            type="button"
            className="topbar-menu-btn"
            aria-label={menuOpen ? 'Close menu' : 'Open menu'}
            aria-expanded={menuOpen}
            aria-controls="mobile-nav-drawer"
            onClick={() => setMenuOpen((open) => !open)}
          >
            {menuOpen ? <X size={18} strokeWidth={2.2} /> : <Menu size={18} strokeWidth={2.2} />}
          </button>

          <button
            type="button"
            onClick={toggleMusic}
            aria-label={isPlaying ? 'Cycle sound volume' : 'Play sound at 50%'}
            title={isPlaying ? 'Cycle sound volume' : 'Play sound at 50%'}
            className={`tube-control-btn sound-toggle ${isPlaying ? 'playing' : ''}`}
          >
            <VolumeIcon size={15} strokeWidth={2.2} />
          </button>

          <button
            type="button"
            onClick={() => setTheme(isDark ? 'light' : 'dark')}
            aria-label={isDark ? 'Switch to Light Mode' : 'Switch to Dark Mode'}
            title={isDark ? 'Light Mode' : 'Dark Mode'}
            className="tube-control-btn theme-toggle"
          >
            {isDark ? (
              <Moon size={15} strokeWidth={2.2} />
            ) : (
              <Sun size={15} strokeWidth={2.2} />
            )}
          </button>
        </div>
      </nav>

      {menuOpen ? (
        <div className="mobile-nav-overlay" onClick={() => setMenuOpen(false)}>
          <div
            id="mobile-nav-drawer"
            className="mobile-nav-drawer"
            role="dialog"
            aria-modal="true"
            aria-label="Site navigation"
            onClick={(event) => event.stopPropagation()}
          >
            {mobileNavItems.map((item) => (
              <Link
                key={item.name}
                href={item.href}
                className={`mobile-nav-link ${item.active ? 'active' : ''}`}
                onClick={() => setMenuOpen(false)}
              >
                {item.name}
              </Link>
            ))}
          </div>
        </div>
      ) : null}
    </header>
  )
}
