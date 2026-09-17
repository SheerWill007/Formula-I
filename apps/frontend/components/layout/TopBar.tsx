'use client'

import React from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'


export default function TopBar() {
  const pathname = usePathname()

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
      active: pathname === '/sessions' || (pathname.startsWith('/sessions/') && pathname !== '/sessions/latest' && !pathname.endsWith('/overview')),
    },
  ]

  return (
    <nav style={{
      height: 60,
      background: '#FFFFFF',
      borderBottom: '1px solid #F1F5F9',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: '0 24px',
      position: 'fixed',
      top: 0,
      left: 0,
      right: 0,
      zIndex: 50,
    }}>
      {/* Logo Section */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 40 }}>
        <Link href="/" style={{ textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{
            fontSize: 14,
            fontWeight: 900,
            color: '#0F172A',
            letterSpacing: '0.05em',
            fontFamily: 'Inter, sans-serif'
          }}>
            SLIPSTREAM
          </span>
        </Link>

        {/* Desktop Nav */}
          <div className="topbar-nav-links" style={{ display: 'flex', gap: 32 }}>
          {navItems.map((item) => {
            const isActive = item.active
            return (
              <Link
                key={item.name}
                href={item.href}
                style={{
                  fontSize: 11,
                  fontWeight: isActive ? 800 : 600,
                  color: isActive ? '#E8002D' : '#64748B',
                  textDecoration: 'none',
                  letterSpacing: '0.01em',
                  position: 'relative',
                  padding: '21px 0',
                }}
              >
                {item.name}
                {isActive && (
                  <div style={{
                    position: 'absolute',
                    bottom: 0,
                    left: 0,
                    right: 0,
                    height: 2,
                    background: '#E8002D',
                    borderRadius: '2px 2px 0 0'
                  }} />
                )}
              </Link>
            )
          })}
        </div>
      </div>
    </nav>
  )
}
