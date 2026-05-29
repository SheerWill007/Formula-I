'use client'

import { useMemo, useState } from 'react'
import Image from 'next/image'
import { UserCircle } from 'lucide-react'

type DriverStanding = {
  position: number
  code: string
  full_name: string
  team_name: string
  points: number
  wins: number
  nationality?: string
}

type ConstructorStanding = {
  position: number
  team_name: string
  points: number
  wins: number
}

function constructorColour(name: string): string {
  const colours: Record<string, string> = {
    Mercedes: '#27F4D2',
    'Red Bull': '#3671C6',
    Ferrari: '#E8002D',
    McLaren: '#FF8000',
    'Aston Martin': '#229971',
    Alpine: '#FF87BC',
    Williams: '#64C4FF',
    'Haas F1 Team': '#B6BABD',
    'Kick Sauber': '#52E252',
    RB: '#6692FF',
    'Racing Bulls': '#6692FF',
  }

  for (const [key, value] of Object.entries(colours)) {
    if (name?.toLowerCase().includes(key.toLowerCase())) return value
  }
  return '#64748B'
}

export default function ChampionshipStandings({
  drivers,
  constructors,
  images = {}
}: {
  drivers: DriverStanding[]
  constructors: ConstructorStanding[]
  currentYear: number
  round: number
  images?: Record<string, string>
}) {
  const [activeTab, setActiveTab] = useState<'drivers' | 'constructors'>('drivers')
  const [isExpanded, setIsExpanded] = useState(false)

  const visibleDrivers = useMemo(() => isExpanded ? drivers : drivers.slice(0, 10), [drivers, isExpanded])
  // In 2026 there are 11 teams, so we show 11 by default for constructors
  const visibleConstructors = useMemo(() => isExpanded ? constructors : constructors.slice(0, 11), [constructors, isExpanded])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
      {/* Tab Switcher */}
      <div style={{ display: 'flex', gap: 24, marginBottom: 24, borderBottom: '1px solid #F1F5F9' }}>
        <button
          onClick={() => setActiveTab('drivers')}
          style={{
            background: 'none',
            border: 'none',
            padding: '12px 0',
            fontSize: 12,
            fontWeight: 800,
            color: activeTab === 'drivers' ? '#E8002D' : '#94A3B8',
            cursor: 'pointer',
            position: 'relative',
            textTransform: 'uppercase',
            letterSpacing: '0.05em'
          }}
        >
          DRIVERS
          {activeTab === 'drivers' && <div style={{ position: 'absolute', bottom: -1, left: 0, right: 0, height: 2, background: '#E8002D' }} />}
        </button>
        <button
          onClick={() => setActiveTab('constructors')}
          style={{
            background: 'none',
            border: 'none',
            padding: '12px 0',
            fontSize: 12,
            fontWeight: 800,
            color: activeTab === 'constructors' ? '#E8002D' : '#94A3B8',
            cursor: 'pointer',
            position: 'relative',
            textTransform: 'uppercase',
            letterSpacing: '0.05em'
          }}
        >
          CONSTRUCTORS
          {activeTab === 'constructors' && <div style={{ position: 'absolute', bottom: -1, left: 0, right: 0, height: 2, background: '#E8002D' }} />}
        </button>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {activeTab === 'drivers' ? (
          visibleDrivers.map((driver) => (
            <DriverRow key={driver.code} driver={driver} imageUrl={images[driver.code]} />
          ))
        ) : (
          visibleConstructors.map((constructor) => (
            <ConstructorRow key={constructor.team_name} constructor={constructor} />
          ))
        )}
      </div>

      {/* See More Toggle */}
      <div style={{ display: 'flex', justifyContent: 'center', marginTop: 24 }}>
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          style={{
            background: '#FFFFFF',
            border: '1px solid #E2E8F0',
            padding: '10px 24px',
            borderRadius: 12,
            fontSize: 11,
            fontWeight: 800,
            color: '#64748B',
            cursor: 'pointer',
            textTransform: 'uppercase',
            letterSpacing: '0.05em',
            transition: 'all 0.2s ease',
            display: 'flex',
            alignItems: 'center',
            gap: 8
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = '#F8FAFC';
            e.currentTarget.style.borderColor = '#CBD5E1';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = '#FFFFFF';
            e.currentTarget.style.borderColor = '#E2E8F0';
          }}
        >
          {isExpanded ? 'Show Less' : 'See More Standings'}
        </button>
      </div>
    </div>
  )
}

function DriverRow({ driver, imageUrl }: { driver: DriverStanding, imageUrl?: string }) {
  const colour = constructorColour(driver.team_name)
  const [imgError, setImgError] = useState(false)

  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: '40px 64px 1.5fr 1.2fr 100px 80px',
      alignItems: 'center',
      padding: '16px 20px',
      background: '#FFFFFF',
      borderRadius: 16,
      border: '1px solid #F1F5F9',
      transition: 'transform 0.2s ease, box-shadow 0.2s ease',
      cursor: 'pointer',
    }} className="standing-row standing-row-driver">
      {/* Position */}
      <span style={{ fontSize: 18, fontWeight: 900, color: '#0F172A', fontFamily: 'Inter, sans-serif' }}>
        {String(driver.position).padStart(2, '0')}
      </span>

      {/* Avatar Container */}
      <div style={{
        width: 48,
        height: 48,
        borderRadius: '50%',
        background: '#F8FAFC',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        border: '1px solid #E2E8F0',
        overflow: 'hidden',
        position: 'relative'
      }}>
        {imageUrl && !imgError ? (
          <Image
            src={imageUrl}
            alt={driver.full_name}
            fill
            style={{ objectFit: 'cover' }}
            unoptimized
            onError={() => setImgError(true)}
          />
        ) : (
          <UserCircle size={52} color="#CBD5E1" strokeWidth={1} style={{ marginTop: 8 }} />
        )}
      </div>

      {/* Driver Info */}
      <div style={{ display: 'flex', flexDirection: 'column' }}>
        <span style={{ fontSize: 14, fontWeight: 800, color: '#0F172A', textTransform: 'uppercase' }}>{driver.full_name}</span>
        <span style={{ fontSize: 10, fontWeight: 600, color: '#94A3B8', textTransform: 'uppercase' }}>{driver.nationality || 'F1 DRIVER'}</span>
      </div>

      {/* Team Info */}
      <div className="standing-hide-mobile" style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <div style={{ width: 3, height: 24, background: colour, borderRadius: 2 }} />
        <span style={{ fontSize: 12, fontWeight: 700, color: '#64748B' }}>{driver.team_name}</span>
      </div>

      {/* Points */}
      <div style={{ textAlign: 'right' }}>
        <span style={{ fontSize: 16, fontWeight: 700, color: '#0F172A', letterSpacing: '-0.02em' }}>{driver.points}</span>
      </div>

      <style jsx>{`
        .standing-row:hover {
          transform: translateY(-2px);
          box-shadow: 0 4px 12px rgba(0,0,0,0.05);
          border-color: #E2E8F0;
        }
      `}</style>
    </div>
  )
}

function ConstructorRow({ constructor }: { constructor: ConstructorStanding }) {
  const colour = constructorColour(constructor.team_name)

  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: '40px 1.5fr 1fr 80px',
      alignItems: 'center',
      padding: '16px 20px',
      background: '#FFFFFF',
      borderRadius: 16,
      border: '1px solid #F1F5F9',
      cursor: 'pointer',
    }} className="standing-row standing-row-constructor">
      <span style={{ fontSize: 18, fontWeight: 900, color: '#0F172A' }}>
        {String(constructor.position).padStart(2, '0')}
      </span>

      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <div style={{ width: 3, height: 24, background: colour, borderRadius: 2 }} />
        <span style={{ fontSize: 14, fontWeight: 800, color: '#0F172A', textTransform: 'uppercase' }}>{constructor.team_name}</span>
      </div>
      <div style={{ textAlign: 'right' }}>
        <span style={{ fontSize: 16, fontWeight: 700, color: '#0F172A', letterSpacing: '-0.02em' }}>{constructor.points}</span>
      </div>
    </div>
  )
}
