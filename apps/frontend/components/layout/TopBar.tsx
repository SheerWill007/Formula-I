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
      name: 'Dashboard',
      href: '/dashboard',
      active: pathname === '/dashboard',
    },
    {
      name: 'Latest Weekend',
      href: '/sessions/latest',
      active: pathname === '/sessions/latest' || pathname.endsWith('/overview'),
    },
    {
      name: 'Season Calendar',
      href: '/schedule',
      active: pathname === '/schedule',
    },
    {
      name: 'Archive',
      href: '/sessions',
      active:
        pathname === '/sessions' ||
        (pathname.startsWith('/sessions/') &&
          pathname !== '/sessions/latest' &&
          !pathname.endsWith('/overview')),
    },
  ]

  const isDark = mounted ? theme === 'dark' : true

  return (
    <header className="topbar-wrapper">
      <nav className="topbar-tube">
        {/* Left Section: Nav Links */}
        <div className="topbar-left">
          <div className="topbar-nav-links">
            {navItems.map((item) => {
              const isActive = item.active
              return (
                <Link
                  key={item.name}
                  href={item.href}
                  className={`topbar-link ${isActive ? 'active' : ''}`}
                >
                  {item.name}
                </Link>
              )
            })}
          </div>
        </div>

        {/* Center Section: Italicized BoxUp Brand */}
        <div className="topbar-center">
          <Link href="/" className="topbar-brand" aria-label="BoxUp Home">
            <span className="brand-italic">BOXUP</span>
          </Link>
        </div>

        {/* Right Section: Music & Theme Toggles */}
        <div className="topbar-right">
          {/* Music Toggle */}
          <button
            type="button"
            onClick={toggleMusic}
            aria-label={isPlaying ? 'Pause music' : 'Play music'}
            title={isPlaying ? 'Mute ambient sound' : 'Play ambient audio'}
            className={`tube-icon-button ${isPlaying ? 'active' : ''}`}
          >
            {isPlaying ? (
              <Volume2 size={16} strokeWidth={2.2} />
            ) : (
              <VolumeX size={16} strokeWidth={2.2} />
            )}
            {isPlaying && <span className="music-pulse-dot" />}
          </button>

          {/* Theme Toggle */}
          <button
            type="button"
            onClick={() => setTheme(isDark ? 'light' : 'dark')}
            aria-label={isDark ? 'Switch to Light Mode' : 'Switch to Dark Mode'}
            title={isDark ? 'Light Mode' : 'Dark Mode'}
            className="tube-icon-button theme-toggle"
          >
            {isDark ? (
              <Sun size={16} strokeWidth={2.2} className="theme-icon sun" />
            ) : (
              <Moon size={16} strokeWidth={2.2} className="theme-icon moon" />
            )}
          </button>
        </div>
      </nav>
    </header>
  )
}
