'use client'

import React from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useTheme } from 'next-themes'
import { Volume2, Volume1, VolumeX, Sun, Moon } from 'lucide-react'
import { useMusic } from '@/components/layout/AudioProvider'

export default function TopBar() {
  const pathname = usePathname()
  const { theme, setTheme } = useTheme()
  const { isPlaying, volume, toggleMusic } = useMusic()
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
    </header>
  )
}
