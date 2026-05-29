import { MapPin, CalendarDays } from 'lucide-react'
import Image from 'next/image'
import React from 'react'

export const revalidate = 60

const BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

// ── Components ───────────────────────────────────────────────────────────────



function HeroNextRace({ race }: { race: { round: number, event_name: string, event_date: string, circuit: string, country: string } }) {
  if (!race) return null

  return (
    <div className="schedule-hero" style={{
      position: 'relative',
      height: 480,
      borderRadius: 40,
      overflow: 'hidden',
      marginBottom: 40,
      background: '#0F172A',
      boxShadow: '0 20px 25px -5px rgb(0 0 0 / 0.1), 0 8px 10px -6px rgb(0 0 0 / 0.1)'
    }}>
      {/* Background Image */}
      <Image
        src="https://images.unsplash.com/photo-1699138346491-d6f4c7e04b85?q=80&w=2232&auto=format&fit=crop&ixlib=rb-4.1.0&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D"
        alt="F1 Car"
        fill
        style={{ objectFit: 'cover', opacity: 0.7 }}
      />

      {/* Gradient Overlay */}
      <div className="schedule-hero-content" style={{
        position: 'absolute',
        inset: 0,
        background: 'linear-gradient(to top, rgba(15, 23, 42, 0.95) 0%, rgba(15, 23, 42, 0.4) 40%, transparent 100%)',
        padding: '60px 80px',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'flex-end'
      }}>
        <div style={{ maxWidth: 800 }}>
          <div style={{
            display: 'inline-block',
            background: 'rgba(63, 55, 57, 0.15)',
            color: '#eee6e6ff',
            padding: '8px 16px',
            borderRadius: 8,
            fontSize: 12,
            fontWeight: 1000,
            letterSpacing: '0.08em',
            marginBottom: 20
          }}>
            NEXT UP • ROUND {String(race.round).padStart(2, '0')}
          </div>

          <h1 className="schedule-hero-title" style={{ fontSize: 'clamp(2.5rem, 6vw, 3rem)', fontWeight: 800, color: '#FFFFFF', margin: 0, letterSpacing: '-0.04em', lineHeight: 1.1 }}>
            {race.event_name}
          </h1>

          <div className="schedule-hero-meta" style={{ display: 'flex', gap: 32, marginTop: 32, color: '#CBD5E1' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <CalendarDays size={20} color="#E8002D" />
              <span style={{ fontSize: 16, fontWeight: 300 }}>{new Date(race.event_date).toLocaleDateString('en-US', { month: 'long', day: '2-digit', year: 'numeric' })}</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <MapPin size={20} color="#E8002D" />
              <span style={{ fontSize: 16, fontWeight: 300 }}>{race.circuit}, {race.country}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

function RaceCard({ race, isNext }: { race: { round: number, event_name: string, circuit: string, event_date: string, status: string, top_finishers?: string[] }, isNext?: boolean }) {
  const isPast = race.status === 'past'

  return (
    <div className="race-card" style={{
      background: '#FFFFFF',
      borderRadius: 24,
      padding: '40px 32px',
      border: isNext ? '2px solid #E8002D' : '1px solid #F1F5F9',
      position: 'relative',
      overflow: 'hidden',
      display: 'flex',
      flexDirection: 'column',
      justifyContent: 'center',
      gap: 4,
      transition: 'all 0.3s ease',
      cursor: 'pointer',
      opacity: isPast ? 0.75 : 1,
      minHeight: 160
    }}>
      <div className="race-card-number" style={{
        position: 'absolute',
        left: 16,
        top: '50%',
        transform: 'translateY(-50%)',
        fontSize: 100,
        fontWeight: 900,
        color: '#c4c9cdff',
        zIndex: 0,
        pointerEvents: 'none',
        lineHeight: 1
      }}>
        {String(race.round).padStart(2, '0')}
      </div>

      <div className="race-card-inner" style={{ position: 'relative', zIndex: 1, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div className="race-card-content" style={{ flex: 1, paddingLeft: 130 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 6 }}>
            <h3 style={{ fontSize: 26, fontWeight: 900, color: '#0F172A', margin: 0, letterSpacing: '-0.02em' }}>
              {race.event_name}
            </h3>
          </div>
          <p style={{ fontSize: 15, color: '#64748B', fontWeight: 500, margin: 0 }}>
            {race.circuit} • {new Date(race.event_date).toLocaleDateString('en-US', { month: 'short', day: '2-digit' })}
          </p>
        </div>

        {isNext && (
          <div style={{ background: '#E8002D15', padding: 12, borderRadius: 12, color: '#E8002D' }}>
            Next Up
          </div>
        )}

        {isPast && race.top_finishers && race.top_finishers.length > 0 && (
          <div className="race-card-finishers" style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
            {race.top_finishers.slice(0, 3).map((code: string, idx: number) => (
              <div key={idx} style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                <div style={{
                  width: 6,
                  height: 6,
                  borderRadius: '50%',
                  background: idx === 0 ? '#2DD4BF' : '#3B82F6'
                }} />
                <span style={{ fontSize: 10, fontWeight: 800, color: '#94A3B8' }}>• {code}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default async function SchedulePage() {
  const [nextRace, fullSchedule] = await Promise.all([
    fetch(`${BASE}/api/v1/schedule/next-race`, { next: { revalidate: 60 } }).then(r => r.json()).catch(() => null),
    fetch(`${BASE}/api/v1/schedule/2026`, { next: { revalidate: 3600 } }).then(r => r.json()).catch(() => null)
  ])

  const races = fullSchedule?.races ?? []

  return (
    <div className="schedule-container" style={{ padding: '20px 24px', maxWidth: 1200, margin: '0 auto' }}>

      {nextRace && (
        <HeroNextRace race={nextRace.race} />
      )}

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: 32 }}>
        <div>
          <h2 style={{ fontSize: 32, fontWeight: 900, color: '#0F172A', margin: 0, letterSpacing: '-0.04em' }}>
            2026 Season
          </h2>
          <p style={{ fontSize: 14, color: '#64748B', fontWeight: 500, marginTop: 4 }}>
            {races.length} Rounds this Season
          </p>
        </div>
      </div>

      <div className="schedule-grid" style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(2, 1fr)',
        gap: 24
      }}>
        {races.map((race: { round: number, event_name: string, circuit: string, event_date: string, status: string, top_finishers?: string[] }) => (
          <RaceCard
            key={race.round}
            race={race}
            isNext={nextRace?.race?.round === race.round}
          />
        ))}
      </div>
    </div>
  )
}
