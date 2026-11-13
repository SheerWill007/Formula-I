'use client'

import React from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useTheme } from 'next-themes'
import { Menu, Moon, Sun, Volume1, Volume2, VolumeX, X } from 'lucide-react'
import { useMusic } from '@/components/layout/AudioProvider'
import AuthNav from '@/components/auth/AuthNav'
import { CLERK_ENABLED } from '@/lib/clerk'
import { NAV_ITEMS, isActive } from '@/lib/nav'
import './nav.css'

export default function TopBar() {
  const pathname = usePathname()
  const { theme, setTheme } = useTheme()
  const { isPlaying, volume, toggleMusic } = useMusic()
  const [mounted, setMounted] = React.useState(false)
  const [menuOpen, setMenuOpen] = React.useState(false)

  React.useEffect(() => {
    setMounted(true)
  }, [])

  // Close the menu whenever the route changes.
  React.useEffect(() => {
    setMenuOpen(false)
  }, [pathname])

  React.useEffect(() => {
    if (!menuOpen) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setMenuOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [menuOpen])

  const isDark = mounted ? theme === 'dark' : true
  const VolumeIcon = volume === 0 ? VolumeX : volume <= 0.5 ? Volume1 : Volume2
  const links = NAV_ITEMS.filter(item => item.href !== '/')

  return (
    <>
      <header className="topbar-wrapper">
        <Link href="/" className="corner-brand" aria-label="BoxUp home">
          Box<span>Up</span>
        </Link>

        <nav className="topbar-tube" aria-label="Main navigation">
          <div className="topbar-nav-links">
            {links.map(item => (
              <Link
                key={item.href}
                href={item.href}
                className={`topbar-link ${isActive(pathname, item.href) ? 'active' : ''}`}
                aria-current={isActive(pathname, item.href) ? 'page' : undefined}
              >
                {item.label}
              </Link>
            ))}
          </div>

          <span className="topbar-divider" aria-hidden />

          <div className="topbar-controls">
            <button
              type="button"
              onClick={toggleMusic}
              aria-label={isPlaying ? 'Change sound volume' : 'Play sound at 50%'}
              title={isPlaying ? 'Change sound volume' : 'Play sound at 50%'}
              className={`tube-control-btn ${isPlaying ? 'playing' : ''}`}
            >
              <VolumeIcon size={16} strokeWidth={2.2} />
            </button>

            <button
              type="button"
              onClick={() => setTheme(isDark ? 'light' : 'dark')}
              aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
              title={isDark ? 'Light mode' : 'Dark mode'}
              className="tube-control-btn"
            >
              {isDark ? <Moon size={16} strokeWidth={2.2} /> : <Sun size={16} strokeWidth={2.2} />}
            </button>

            {CLERK_ENABLED && (
              <span className="auth-slot">
                <AuthNav compact />
              </span>
            )}

            <button
              type="button"
              className="tube-control-btn menu-toggle"
              aria-label={menuOpen ? 'Close menu' : 'Open menu'}
              aria-expanded={menuOpen}
              aria-controls="nav-sheet"
              onClick={() => setMenuOpen(open => !open)}
            >
              {menuOpen ? <X size={18} strokeWidth={2.4} /> : <Menu size={18} strokeWidth={2.4} />}
            </button>
          </div>
        </nav>

        <div className="topbar-actions">
          {CLERK_ENABLED && <AuthNav />}
        </div>
      </header>

      {menuOpen && (
        <>
          <div className="nav-sheet-backdrop" onClick={() => setMenuOpen(false)} aria-hidden />
          <nav id="nav-sheet" className="nav-sheet" aria-label="All sections">
            {NAV_ITEMS.map(({ href, label, icon: Icon }) => (
              <Link
                key={href}
                href={href}
                className={`nav-sheet-link ${isActive(pathname, href) ? 'active' : ''}`}
                aria-current={isActive(pathname, href) ? 'page' : undefined}
                onClick={() => setMenuOpen(false)}
              >
                <Icon size={18} strokeWidth={2} />
                {label}
              </Link>
            ))}
          </nav>
        </>
      )}
    </>
  )
}
