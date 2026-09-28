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
  const { isPlaying, volume, setVolume } = useMusic()
  const [mounted, setMounted] = React.useState(false)
  const [audioMenuOpen, setAudioMenuOpen] = React.useState(false)

  React.useEffect(() => {
    setMounted(true)
  }, [])

  React.useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as HTMLElement | null
      if (!target?.closest('.music-volume-menu') && !target?.closest('.sound-toggle')) {
        setAudioMenuOpen(false)
      }
    }

    document.addEventListener('click', handleClickOutside)
    return () => document.removeEventListener('click', handleClickOutside)
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

  const volumeOptions = [
    { label: '0% (Mute)', value: 0 },
    { label: '50%', value: 0.5 },
    { label: '100%', value: 1 },
  ]

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
          <div className="music-volume-wrapper">
            <button
              type="button"
              onClick={() => setAudioMenuOpen((open) => !open)}
              aria-label={isPlaying ? 'Adjust sound volume' : 'Sound is muted'}
              title="Adjust sound volume"
              className={`tube-control-btn sound-toggle ${isPlaying ? 'playing' : ''}`}
            >
              <VolumeIcon size={15} strokeWidth={2.2} />
            </button>

            {audioMenuOpen && (
              <div className="music-volume-menu" role="menu" aria-label="Music volume options">
                {volumeOptions.map((option) => (
                  <button
                    key={option.label}
                    type="button"
                    className={`music-volume-option ${volume === option.value ? 'active' : ''}`}
                    onClick={() => {
                      setVolume(option.value)
                      setAudioMenuOpen(false)
                    }}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            )}
          </div>

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
