'use client'

import React from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useTheme } from 'next-themes'
import { Volume2, VolumeX, Sun, Moon } from 'lucide-react'
import { useMusic } from '@/components/layout/AudioProvider'

export default function TopBar() {
  const pathname = usePathname()
  const { theme, setTheme } = useTheme()
  const { isPlaying, toggleMusic } = useMusic()
  const [mounted, setMounted] = React.useState(false)

  React.useEffect(() => {
    setMounted(true)
  }, [])

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

  const isDark = mounted ? theme === 'dark' : true

  return (
    <header className="topbar-wrapper">
      <nav className="topbar-tube">
        {/* Left Section: Logo with Live Dot */}
        <div className="topbar-brand-section">
          <Link href="/" className="topbar-brand-capsule" aria-label="BoxUp Home">
            <span className="live-indicator-dot" />
            <span className="brand-wordmark">BOXUP</span>
          </Link>
          <div className="brand-divider" />
        </div>

        {/* Center Section: Navigation Links */}
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

        {/* Right Section: Sound Toggle & Theme Toggle */}
        <div className="topbar-controls">
          {/* Sound / Music Toggle */}
          <button
            type="button"
            onClick={toggleMusic}
            aria-label={isPlaying ? 'Mute sound' : 'Play sound'}
            title={isPlaying ? 'Mute atmospheric sound' : 'Play atmospheric sound'}
            className={`tube-control-btn sound-toggle ${isPlaying ? 'playing' : ''}`}
          >
            {isPlaying ? (
              <Volume2 size={15} strokeWidth={2.2} />
            ) : (
              <VolumeX size={15} strokeWidth={2.2} />
            )}
          </button>

          {/* Theme Toggle */}
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
    </header>
  )
}
