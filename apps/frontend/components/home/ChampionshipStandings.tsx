'use client'

import { useMemo, useState } from 'react'

type Driver = {
  position?: number
  code?: string
  abbreviation?: string
  full_name?: string
  driver_name?: string
  team_name?: string
  points?: number
}

type Constructor = {
  position?: number
  team_name?: string
  name?: string
  points?: number
}

export default function ChampionshipStandings({
  drivers,
  constructors,
}: {
  drivers: Driver[]
  constructors: Constructor[]
  currentYear?: number
  round?: number
  images?: Record<string, string>
}) {
  const [view, setView] = useState<'drivers' | 'constructors'>('drivers')
  const entries = useMemo(
    () => view === 'drivers' ? drivers : constructors,
    [constructors, drivers, view],
  )

  return (
    <section>
      <div style={{ display: 'flex', gap: 20, marginBottom: 16, borderBottom: '1px solid #E2E8F0' }}>
        {(['drivers', 'constructors'] as const).map((item) => (
          <button
            key={item}
            type="button"
            onClick={() => setView(item)}
            style={{
              border: 0,
              borderBottom: view === item ? '2px solid #E8002D' : '2px solid transparent',
              background: 'transparent',
              color: view === item ? '#E8002D' : '#64748B',
              cursor: 'pointer',
              fontSize: 11,
              fontWeight: 800,
              letterSpacing: '.08em',
              padding: '10px 2px',
              textTransform: 'uppercase',
            }}
          >
            {item}
          </button>
        ))}
      </div>
      <div style={{ display: 'grid', gap: 8 }}>
        {entries.slice(0, 10).map((entry, index) => {
          const driver = entry as Driver
          const constructor = entry as Constructor
          const name = view === 'drivers'
            ? driver.full_name ?? driver.driver_name ?? driver.code ?? driver.abbreviation ?? 'Driver'
            : constructor.team_name ?? constructor.name ?? 'Constructor'
          const team = view === 'drivers' ? driver.team_name : undefined
          const points = entry.points ?? 0
          const position = entry.position ?? index + 1
          return (
            <div key={`${name}-${position}`} style={{ alignItems: 'center', background: '#F8FAFC', borderRadius: 12, display: 'grid', gap: 12, gridTemplateColumns: '34px 1fr auto', padding: '12px 16px' }}>
              <strong style={{ color: '#94A3B8', fontFamily: 'monospace', fontSize: 12 }}>{String(position).padStart(2, '0')}</strong>
              <span style={{ color: '#0F172A', fontSize: 13, fontWeight: 750 }}>
                {name}
                {team ? <small style={{ color: '#64748B', display: 'block', fontSize: 10, fontWeight: 600, marginTop: 2 }}>{team}</small> : null}
              </span>
              <strong style={{ color: '#0F172A', fontSize: 14 }}>{points} <small style={{ color: '#94A3B8', fontSize: 9 }}>PTS</small></strong>
            </div>
          )
        })}
      </div>
    </section>
  )
}
