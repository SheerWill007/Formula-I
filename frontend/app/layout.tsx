'use client'

import { Analytics } from '@vercel/analytics/next'
import { SpeedInsights } from '@vercel/speed-insights/next'
import './globals.css'
import ErrorBoundary from '@/components/ErrorBoundary'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { createContext, useContext, useEffect, useRef, useState } from 'react'

/* ─────────────────────────────────────────────
   THEME CONTEXT
───────────────────────────────────────────── */
type Theme = 'light' | 'dark'
interface ThemeCtx { theme: Theme; toggle: () => void }
export const ThemeContext = createContext<ThemeCtx>({ theme: 'dark', toggle: () => { } })
export const useTheme = () => useContext(ThemeContext)

/* ─────────────────────────────────────────────
   MUSIC CONTEXT
───────────────────────────────────────────── */
type VolumeLevel = 'mute' | 'low' | 'max'
interface MusicCtx { 
  volume: VolumeLevel
  setVolume: (v: VolumeLevel) => void
}
export const MusicContext = createContext<MusicCtx>({ 
  volume: 'mute', 
  setVolume: () => { } 
})
export const useMusic = () => useContext(MusicContext)

/* ─────────────────────────────────────────────
   TUBE NAV BAR  (logo left, nav center, controls right)
───────────────────────────────────────────── */
function TubeNavBar() {
  const pathname = usePathname()
  const { theme, toggle: toggleTheme } = useTheme()
  const { volume, setVolume } = useMusic()
  const dark = theme === 'dark'

  const cycleVolume = () => {
    if (volume === 'mute') setVolume('low')
    else if (volume === 'low') setVolume('max')
    else setVolume('mute')
  }

  const navItems = [
    { name: 'Home', href: '/', active: pathname === '/' },
    { name: 'Dashboard', href: '/dashboard', active: pathname === '/dashboard' },
    { name: 'Sessions', href: '/sessions', active: pathname === '/sessions' || (pathname.startsWith('/sessions/') && pathname !== '/sessions/latest' && !pathname.endsWith('/overview')) },
    { name: 'Season Calendar', href: '/schedule', active: pathname === '/schedule' },
    { name: 'Standings', href: '/standings', active: pathname === '/standings' },
  ]

  return (
    <nav style={{
      height: 70,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: '0 40px',
      position: 'fixed',
      top: 0,
      left: 0,
      right: 0,
      zIndex: 1000,
      pointerEvents: 'none',
    }}>
      {/* Left Tube: Formula 1 Logo - TRANSPARENT */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 4,
        background: 'transparent',
        border: 'none',
        borderRadius: 999,
        padding: '8px 16px',
        transition: 'all 0.3s ease',
        pointerEvents: 'auto',
      }}>
        <Link href="/" style={{ 
          textDecoration: 'none', 
          display: 'flex', 
          alignItems: 'center', 
          gap: 8,
          padding: '4px 8px',
          borderRadius: 999,
          transition: 'background 0.2s',
        }}>
          <span 
            data-music-dot
            style={{
              width: 6,
              height: 6,
              borderRadius: '50%',
              background: '#E10600',
              boxShadow: '0 0 8px #E10600',
            }} 
          />
          <span style={{
            fontSize: 14,
            fontWeight: 900,
            color: dark ? '#F1F5F9' : '#0F172A',
            letterSpacing: '-0.02em',
            fontFamily: 'Inter, sans-serif',
            textTransform: 'uppercase',
            fontStyle: 'italic',
          }}>
            Formula 1
          </span>
        </Link>
      </div>

      {/* Center Tube: Nav Items */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 4,
        background: dark
          ? 'rgba(0,0,0,0.5)'
          : 'rgba(255,255,255,0.5)',
        border: dark
          ? '1px solid rgba(16,185,129,0.2)'
          : '1px solid rgba(15,23,42,0.1)',
        borderRadius: 999,
        padding: '8px 16px',
        backdropFilter: 'blur(20px) saturate(180%)',
        WebkitBackdropFilter: 'blur(20px) saturate(180%)',
        boxShadow: dark
          ? '0 8px 32px rgba(0,0,0,0.3), inset 0 1px 0 rgba(16,185,129,0.08)'
          : '0 8px 32px rgba(15,23,42,0.1), inset 0 1px 0 rgba(255,255,255,0.6)',
        transition: 'all 0.3s ease',
        pointerEvents: 'auto',
      }}>
        {/* Nav Items */}
        <div style={{ display: 'flex', gap: 2 }}>
          {navItems.map((item) => {
            const isActive = item.active
            return (
              <Link
                key={item.name}
                href={item.href}
                style={{
                  fontSize: 11,
                  fontWeight: isActive ? 700 : 600,
                  color: isActive ? '#E10600' : dark ? '#94A3B8' : '#64748B',
                  textDecoration: 'none',
                  letterSpacing: '0.02em',
                  padding: '8px 16px',
                  borderRadius: 999,
                  background: isActive 
                    ? 'rgba(225,6,0,0.12)' 
                    : 'transparent',
                  transition: 'all 0.2s ease',
                  whiteSpace: 'nowrap',
                }}
                onMouseEnter={(e) => {
                  if (!isActive) {
                    e.currentTarget.style.background = dark 
                      ? 'rgba(255,255,255,0.06)' 
                      : 'rgba(15,23,42,0.05)'
                  }
                }}
                onMouseLeave={(e) => {
                  if (!isActive) {
                    e.currentTarget.style.background = 'transparent'
                  }
                }}
              >
                {item.name}
              </Link>
            )
          })}
        </div>
      </div>

      {/* Right Tube: Music & Theme Controls - TRANSPARENT */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 6,
        background: 'transparent',
        border: 'none',
        borderRadius: 999,
        padding: '8px 12px',
        transition: 'all 0.3s ease',
        pointerEvents: 'auto',
      }}>
        {/* Music Control */}
        <TubeButton
          onClick={cycleVolume}
          active={volume !== 'mute'}
          dark={dark}
          title={`Volume: ${volume.toUpperCase()} - Click to cycle`}
        >
          {volume === 'mute' ? (
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
              <line x1="23" y1="9" x2="17" y2="15" />
              <line x1="17" y1="9" x2="23" y2="15" />
            </svg>
          ) : volume === 'low' ? (
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
              <path d="M15.54 8.46a5 5 0 0 1 0 7.07" />
            </svg>
          ) : (
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
              <path d="M15.54 8.46a5 5 0 0 1 0 7.07" />
              <path d="M19.07 4.93a10 10 0 0 1 0 14.14" />
            </svg>
          )}
        </TubeButton>

        {/* Theme Control */}
        <TubeButton
          onClick={toggleTheme}
          active={false}
          dark={dark}
          title={dark ? 'Switch to light mode' : 'Switch to dark mode'}
        >
          {dark ? (
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
            </svg>
          ) : (
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="5" />
              <line x1="12" y1="1" x2="12" y2="3" />
              <line x1="12" y1="21" x2="12" y2="23" />
              <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
              <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
              <line x1="1" y1="12" x2="3" y2="12" />
              <line x1="21" y1="12" x2="23" y2="12" />
              <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
              <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
            </svg>
          )}
        </TubeButton>
      </div>
    </nav>
  )
}

/* ─────────────────────────────────────────────
   TUBE BUTTON  (pill segment)
───────────────────────────────────────────── */
function TubeButton({
  children,
  onClick,
  active,
  dark,
  title,
}: {
  children: React.ReactNode
  onClick: () => void
  active: boolean
  dark: boolean
  title: string
}) {
  const [hovered, setHovered] = useState(false)

  return (
    <button
      onClick={onClick}
      title={title}
      aria-label={title}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 5,
        background: active
          ? 'rgba(225,6,0,0.15)'
          : hovered
            ? dark
              ? 'rgba(255,255,255,0.08)'
              : 'rgba(15,23,42,0.07)'
            : 'transparent',
        border: 'none',
        borderRadius: 999,
        padding: '8px 10px',
        cursor: 'pointer',
        color: active
          ? '#E10600'
          : dark
            ? 'rgba(255,255,255,0.75)'
            : 'rgba(15,23,42,0.70)',
        fontSize: 11,
        fontWeight: 600,
        letterSpacing: '0.04em',
        textTransform: 'uppercase',
        fontFamily: 'inherit',
        transition: 'background 0.18s, color 0.18s, transform 0.12s',
        transform: hovered ? 'scale(1.08)' : 'scale(1)',
        userSelect: 'none',
        whiteSpace: 'nowrap',
      }}
    >
      {children}
    </button>
  )
}

/* ─────────────────────────────────────────────
   BACKGROUND MUSIC PLAYER  (plays MP3 on all pages except home)
───────────────────────────────────────────── */
function BackgroundMusicPlayer({ volume }: { volume: VolumeLevel }) {
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const pathname = usePathname()
  const isHomePage = pathname === '/'

  useEffect(() => {
    // Create audio element if it doesn't exist
    if (!audioRef.current) {
      audioRef.current = new Audio('/baakipageOG.mp3')
      audioRef.current.loop = true
      audioRef.current.preload = 'auto'
    }

    const audio = audioRef.current

    // Only play on non-home pages
    if (!isHomePage && volume !== 'mute') {
      // Set volume based on level
      const targetVolume = volume === 'low' ? 0.3 : 0.6
      audio.volume = targetVolume
      
      // Play the audio
      audio.play().catch((err) => {
        console.log('Audio playback failed:', err)
      })
    } else {
      // Pause on home page or when muted
      audio.pause()
    }

    return () => {
      // Don't destroy the audio element, just pause it
      // This keeps it ready for the next page
    }
  }, [volume, isHomePage])

  // Update volume when it changes (without restarting playback)
  useEffect(() => {
    if (audioRef.current && !isHomePage && volume !== 'mute') {
      const targetVolume = volume === 'low' ? 0.3 : 0.6
      audioRef.current.volume = targetVolume
    }
  }, [volume, isHomePage])

  return null
}

/* ─────────────────────────────────────────────
   CSS VARIABLE INJECTION  (theme-aware)
───────────────────────────────────────────── */
const lightVars = `
  :root {
    --bg: #F8FAFC;
    --surface: #FFFFFF;
    --text: #0F172A;
    --text-muted: #64748B;
    --border: rgba(15,23,42,0.10);
    --accent: #E10600;
    --accent-glow: rgba(225,6,0,0.20);
    --accent-green: #10B981;
  }
`
const darkVars = `
  :root {
    --bg: #000000;
    --surface: #0F0F0F;
    --text: #F1F5F9;
    --text-muted: #64748B;
    --border: rgba(16,185,129,0.15);
    --accent: #E10600;
    --accent-glow: rgba(225,6,0,0.30);
    --accent-green: #10B981;
  }
`

/* ─────────────────────────────────────────────
   ROOT LAYOUT
───────────────────────────────────────────── */
export default function RootLayout({ children }: { children: React.ReactNode }) {
  const [theme, setTheme] = useState<Theme>('dark')
  const [volume, setVolume] = useState<VolumeLevel>('mute')

  const toggleTheme = () =>
    setTheme((t) => (t === 'dark' ? 'light' : 'dark'))

  const dark = theme === 'dark'

  return (
    <ThemeContext.Provider value={{ theme, toggle: toggleTheme }}>
      <MusicContext.Provider value={{ volume, setVolume }}>
        <html lang="en" suppressHydrationWarning data-theme={theme} data-scroll-behavior="smooth">
          <head>
            <title>Formula 1 - F1 Race Analytics & Telemetry</title>
            <meta
              name="description"
              content="Elite-level Formula 1 race analytics, real-time telemetry, and predictive race strategy. Dominate the grid with advanced motorsport data."
            />
            <link rel="icon" href="/favicon.ico" />
            {/* Theme CSS variables */}
            <style>{dark ? darkVars : lightVars}</style>
            {/* Global tube-nav & transition styles */}
            <style>{`
              *, *::before, *::after { box-sizing: border-box; }
              html { }
              body {
                margin: 0;
                transition: background 0.35s ease, color 0.35s ease;
              }
              /* Tube nav entrance animation */
              @keyframes tubeSlideIn {
                from { opacity: 0; transform: translateY(-12px) scale(0.94); }
                to   { opacity: 1; transform: translateY(0) scale(1); }
              }
              [data-tube-nav] {
                animation: tubeSlideIn 0.4s cubic-bezier(0.34,1.56,0.64,1) both;
              }
              /* Music pulse ring */
              @keyframes musicPulse {
                0%   { box-shadow: 0 0 0 0 rgba(225,6,0,0.45); }
                70%  { box-shadow: 0 0 0 8px rgba(225,6,0,0); }
                100% { box-shadow: 0 0 0 0 rgba(225,6,0,0); }
              }
              [data-music-active="true"] [data-music-dot] {
                animation: musicPulse 1.6s ease-out infinite;
              }
            `}</style>
          </head>
          <body
            style={{
              background: dark ? '#000000' : '#F8FAFC',
              color: dark ? '#F1F5F9' : '#0F172A',
              minHeight: '100vh',
              transition: 'background 0.35s ease, color 0.35s ease',
            }}
            suppressHydrationWarning
            data-music-active={String(volume !== 'mute')}
          >
            {/* Tube navigation bar */}
            <TubeNavBar />

            {/* Background music player */}
            <BackgroundMusicPlayer volume={volume} />

            {/* Main app layout */}
            <main
              style={{
                paddingTop: 80,
                minHeight: '100vh',
              }}
            >
              <ErrorBoundary>
                {children}
              </ErrorBoundary>
            </main>

            <Analytics />
            <SpeedInsights />
          </body>
        </html>
      </MusicContext.Provider>
    </ThemeContext.Provider>
  )
}