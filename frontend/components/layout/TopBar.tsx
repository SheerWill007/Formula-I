'use client'

import React from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useTheme } from '@/app/layout'


export default function TopBar() {
  const pathname = usePathname()
  const { theme } = useTheme()
  const dark = theme === 'dark'

  const navItems = [
    {
      name: 'Home',
      href: '/',
      active: pathname === '/',
    },
    {
      name: 'Dashboard',
      href: '/dashboard',
      active: pathname === '/dashboard',
    },
    {
      name: 'Sessions',
      href: '/sessions',
      active: pathname === '/sessions' || (pathname.startsWith('/sessions/') && pathname !== '/sessions/latest' && !pathname.endsWith('/overview')),
    },
    {
      name: 'Season Calendar',
      href: '/schedule',
      active: pathname === '/schedule',
    },
    {
      name: 'Standings',
      href: '/standings',
      active: pathname === '/standings',
    },
  ]

  return (
    <nav style={{
      height: 70,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '0 24px',
      position: 'fixed',
      top: 0,
      left: 0,
      right: 0,
      zIndex: 50,
      pointerEvents: 'none',
    }}>
      {/* Centered Tube Navigation */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 4,
        background: dark
          ? 'rgba(0,0,0,0.88)'
          : 'rgba(255,255,255,0.90)',
        border: dark
          ? '1px solid rgba(16,185,129,0.25)'
          : '1px solid rgba(15,23,42,0.15)',
        borderRadius: 999,
        padding: '8px 16px',
        backdropFilter: 'blur(20px) saturate(180%)',
        WebkitBackdropFilter: 'blur(20px) saturate(180%)',
        boxShadow: dark
          ? '0 8px 32px rgba(0,0,0,0.6), inset 0 1px 0 rgba(16,185,129,0.1)'
          : '0 8px 32px rgba(15,23,42,0.15), inset 0 1px 0 rgba(255,255,255,0.8)',
        transition: 'all 0.3s ease',
        pointerEvents: 'auto',
      }}>
        {/* Logo */}
        <Link href="/" style={{ 
          textDecoration: 'none', 
          display: 'flex', 
          alignItems: 'center', 
          gap: 6,
          padding: '6px 12px',
          borderRadius: 999,
          transition: 'background 0.2s',
        }}>
          <span style={{
            width: 6,
            height: 6,
            borderRadius: '50%',
            background: '#E10600',
            boxShadow: '0 0 8px #E10600',
          }} />
          <span style={{
            fontSize: 12,
            fontWeight: 900,
            color: dark ? '#F1F5F9' : '#0F172A',
            letterSpacing: '0.08em',
            fontFamily: 'Inter, sans-serif',
            transition: 'color 0.3s',
          }}>
            F1
          </span>
        </Link>

        {/* Divider */}
        <span style={{
          width: 1,
          height: 20,
          background: dark ? 'rgba(16,185,129,0.25)' : 'rgba(15,23,42,0.15)',
          margin: '0 4px',
        }} />

        {/* Nav Items */}
        <div className="topbar-nav-links" style={{ display: 'flex', gap: 2 }}>
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
    </nav>
  )
}
