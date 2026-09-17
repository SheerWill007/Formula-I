'use client'

import React from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { 
  LayoutDashboard, 
  User, 
  Sliders, 
  Brain, 
  Headphones, 
  HelpCircle, 
  Sparkles,
  Flag
} from 'lucide-react'

export default function Sidebar() {
  const pathname = usePathname()

  const navItems = [
    { name: 'RACE OVERVIEW', icon: LayoutDashboard, href: '/dashboard', active: pathname === '/dashboard' },
    { name: 'LATEST WEEKEND', icon: Flag, href: '/sessions/latest', active: pathname === '/sessions/latest' || pathname.endsWith('/overview') },
    { name: 'DRIVER ANALYSIS', icon: User, href: '/analysis', active: pathname === '/analysis' },
    { name: 'CAR SETUP', icon: Sliders, href: '/setup', active: pathname === '/setup' },
    { name: 'STRATEGY TOOL', icon: Brain, href: '/predictions', active: pathname === '/predictions' },
    { name: 'PIT WALL', icon: Headphones, href: '/pitwall', active: pathname === '/pitwall' },
  ]

  return (
    <aside style={{
      width: 240,
      height: 'calc(100vh - 60px)',
      background: '#FAFAFA',
      borderRight: '1px solid #F1F5F9',
      padding: '24px 16px',
      display: 'flex',
      flexDirection: 'column',
      position: 'fixed',
      top: 60,
      left: 0,
      zIndex: 40,
    }}>
      {/* Team / Profile Card */}
      <div style={{
        background: '#FFFFFF',
        borderRadius: 12,
        padding: '12px',
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        marginBottom: 32,
        boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
        border: '1px solid #F1F5F9',
      }}>
        <div style={{
          width: 36,
          height: 36,
          background: '#0B1B34', // Red Bull Navy
          borderRadius: 8,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: '#FFFFFF',
          fontSize: 10,
          fontWeight: 900,
        }}> RB </div>
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          <span style={{ fontSize: 12, fontWeight: 800, color: '#0F172A' }}>Red Bull Racing</span>
          <span style={{ fontSize: 9, fontWeight: 700, color: '#E8002D', letterSpacing: '0.05em' }}>LIVE SESSION: MONZA</span>
        </div>
      </div>

      {/* Navigation Links */}
      <nav style={{ display: 'flex', flexDirection: 'column', gap: 4, flex: 1 }}>
        {navItems.map((item) => {
          const isActive = item.active
          return (
            <Link 
              key={item.name} 
              href={item.href}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 12,
                padding: '12px 14px',
                borderRadius: 8,
                textDecoration: 'none',
                background: isActive ? '#FFFFFF' : 'transparent',
                boxShadow: isActive ? '0 1px 3px rgba(0,0,0,0.05)' : 'none',
                border: isActive ? '1px solid #F1F5F9' : '1px solid transparent',
                transition: 'all 0.2s ease',
              }}
              className="nav-link"
            >
              <item.icon 
                size={16} 
                color={isActive ? '#E8002D' : '#94A3B8'} 
                strokeWidth={isActive ? 2.5 : 2}
              />
              <span style={{ 
                fontSize: 11, 
                fontWeight: isActive ? 800 : 600, 
                color: isActive ? '#0F172A' : '#64748B',
                letterSpacing: '0.02em',
              }}>
                {item.name}
              </span>
            </Link>
          )
        })}
      </nav>

      {/* Footer Links */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4, paddingTop: 24, borderTop: '1px solid #F1F5F9' }}>
        <button style={{
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          padding: '12px 14px',
          borderRadius: 8,
          background: '#E8002D',
          border: 'none',
          cursor: 'pointer',
          width: '100%',
        }}>
          <Sparkles size={16} color="#FFFFFF" />
          <span style={{ fontSize: 11, fontWeight: 800, color: '#FFFFFF', letterSpacing: '0.02em' }}>UPGRADE TO PRO</span>
        </button>
        <Link 
          href="/help"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 12,
            padding: '12px 14px',
            borderRadius: 8,
            textDecoration: 'none',
            color: '#64748B',
          }}
        >
          <HelpCircle size={16} color="#94A3B8" />
          <span style={{ fontSize: 11, fontWeight: 600 }}>HELP CENTER</span>
        </Link>
      </div>

      <style jsx>{`
        .nav-link:hover {
          background: #FFFFFF !important;
          border-color: #F1F5F9 !important;
        }
      `}</style>
    </aside>
  )
}
