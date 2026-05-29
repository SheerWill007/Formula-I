import React from 'react'
import Image from 'next/image'
import Link from 'next/link'
import {
  Thermometer,
  Wind,
  Droplets,
  Sun,
  Trophy,
  Clock,
  Zap,
  Flag
} from 'lucide-react'
import CountdownTimer from '@/components/schedule/CountdownTimer'
import ChampionshipStandings from '@/components/home/ChampionshipStandings'

export const revalidate = 60

const BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

// ── Data fetchers ─────────────────────────────────────────────────────────────

async function fetchStandings(year: number) {
  try {
    const [d, c] = await Promise.all([
      fetch(`${BASE}/api/v1/standings/drivers?year=${year}`, { next: { revalidate: 300 } }).then(r => r.json()),
      fetch(`${BASE}/api/v1/standings/constructors?year=${year}`, { next: { revalidate: 300 } }).then(r => r.json()),
    ])
    return { drivers: d.standings ?? [], constructors: c.standings ?? [], round: d.round ?? 0 }
  } catch {
    return { drivers: [], constructors: [], round: 0 }
  }
}

async function fetchDriverImages() {
  try {
    const data = await fetch('https://api.openf1.org/v1/drivers?session_key=latest', { next: { revalidate: 3600 } }).then(r => r.json())
    if (!Array.isArray(data)) return { acronymMap: {}, numberMap: {} }

    const acronymMap: Record<string, string> = {}
    const numberMap: Record<number, { full_name: string; headshot_url: string }> = {}
    data.forEach((d: { name_acronym: string; headshot_url: string; driver_number: number; full_name: string }) => {
      if (d.name_acronym && d.headshot_url) acronymMap[d.name_acronym] = d.headshot_url
      if (d.driver_number) numberMap[d.driver_number] = d
    })
    return { acronymMap, numberMap }
  } catch {
    return { acronymMap: {}, numberMap: {} }
  }
}

async function fetchDynamicFastestLap() {
  try {
    const now = new Date().toISOString()
    const sessions = await fetch('https://api.openf1.org/v1/sessions?year=2026&session_type=Race').then(r => r.json())
    if (!Array.isArray(sessions)) return { lap: null, gp: '---' }

    // Find last finished race
    const lastRace = sessions.filter(s => s.date_end < now && !s.is_cancelled).slice(-1)[0]
    if (!lastRace) return { lap: null, gp: '---' }

    const laps = await fetch(`https://api.openf1.org/v1/laps?session_key=${lastRace.session_key}`).then(r => r.json())
    if (!Array.isArray(laps)) return { lap: null, gp: lastRace.circuit_short_name }

    const bestLap = laps.reduce((min: { lap_duration: number } | null, lap: { lap_duration: number }) => {
      if (lap.lap_duration && (!min || lap.lap_duration < min.lap_duration)) return lap
      return min
    }, null)

    return { lap: bestLap, gp: lastRace.circuit_short_name }
  } catch {
    return { lap: null, gp: '---' }
  }
}

async function fetchLastFinishedSession() {
  try {
    const now = new Date().toISOString()
    const sessions = await fetch('https://api.openf1.org/v1/sessions?year=2026').then(r => r.json())
    if (!Array.isArray(sessions)) return null
    return sessions.filter(s => s.date_end < now && !s.is_cancelled).slice(-1)[0] ?? null
  } catch { return null }
}

async function fetchSessionWeather(sessionKey: number | string | undefined) {
  if (!sessionKey) return null
  try {
    const data = await fetch(`https://api.openf1.org/v1/weather?session_key=${sessionKey}`).then(r => r.json())
    return Array.isArray(data) && data.length > 0 ? data[data.length - 1] : null
  } catch { return null }
}

function formatLapTime(ms: number) {
  const mins = Math.floor(ms / 60000)
  const secs = ((ms % 60000) / 1000).toFixed(3)
  return `${mins}:${secs.padStart(6, '0')}`
}

// ── Dashboard Page ────────────────────────────────────────────────────────────

export default async function DashboardPage() {
  const currentYear = new Date().getFullYear()

  const [standings, nextRace, dData, dynamicFastest, lastSession] = await Promise.all([
    fetchStandings(currentYear),
    fetch(`${BASE}/api/v1/schedule/next-race`, { next: { revalidate: 300 } }).then(r => r.json()).catch(() => null),
    fetchDriverImages(),
    fetchDynamicFastestLap(),
    fetchLastFinishedSession()
  ])

  const sessionWeather = await fetchSessionWeather(lastSession?.session_key)
  const { acronymMap: driverImages, numberMap: driverByNum } = dData
  const topFastestLapData = dynamicFastest?.lap
  const fastestDriver = topFastestLapData ? driverByNum[topFastestLapData.driver_number] : null

  const heroRace = nextRace?.race
  const heroSession = nextRace?.next_session

  const heroImage = "https://images.unsplash.com/photo-1748465579870-d31c8d5ca7da?q=80&w=2070&auto=format&fit=crop&ixlib=rb-4.1.0&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D"

  const champLeader = standings.drivers[0]
  const constructorLeader = standings.constructors[0]

  const eventDateRaw = heroRace?.event_date?.split(' ')[0]
  const formattedEventDate = eventDateRaw ? new Date(eventDateRaw).toLocaleDateString('en-US', { month: 'short', day: '2-digit', year: 'numeric' }) : 'Next Event Scheduled'

  return (
    <div className="dashboard-container" style={{ display: 'flex', flexDirection: 'column', gap: 32, padding: '24px 24px 40px', maxWidth: 1200, margin: '0 auto' }}>

      <div className="dashboard-top-grid" style={{ display: 'grid', gridTemplateColumns: '1fr 300px', gap: 24, alignItems: 'stretch' }}>

        <div style={{
          position: 'relative',
          minHeight: 400,
          borderRadius: 24,
          overflow: 'hidden',
          boxShadow: '0 20px 40px -12px rgba(0,0,0,0.1)'
        }}>
          <Image
            src={heroImage}
            alt="Circuit Hero"
            fill
            style={{ objectFit: 'cover' }}
            priority
          />
          <div style={{
            position: 'absolute', inset: 0,
            background: 'linear-gradient(220deg, rgba(15, 23, 42, 0) 20%, rgba(15, 23, 42, 0.8) 100%)'
          }} />

          <div className="dashboard-hero-content" style={{ position: 'absolute', inset: 0, padding: 40, display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
            <div style={{
              background: '#E8002D',
              color: '#FFFFFF',
              fontSize: 10,
              fontWeight: 900,
              padding: '6px 12px',
              borderRadius: 4,
              width: 'fit-content',
              marginBottom: 24,
              letterSpacing: '0.05em'
            }}> NEXT RACE </div>

            <h1 className="dashboard-hero-title" style={{
              fontFamily: 'Inter, sans-serif',
              fontWeight: 900,
              fontSize: 'clamp(2.5rem, 8vw, 3rem)',
              color: '#FFFFFF',
              letterSpacing: '-0.04em',
              lineHeight: 1,
              marginBottom: 8,
              textTransform: 'uppercase'
            }}>
              {heroRace?.event_name ?? 'F1 SEASON ACTIVE'}
            </h1>
            <p style={{ color: '#CBD5E1', fontSize: 14, fontWeight: 500, marginBottom: 40 }}>
              {heroRace?.circuit ?? 'Awaiting official schedule'} • {formattedEventDate}
            </p>

            <div style={{ display: 'flex', alignItems: 'center', gap: 24 }}>
              {heroSession?.date_utc ? (
                <CountdownTimer targetDate={heroSession.date_utc} sessionName={heroSession.name} />
              ) : (
                <div style={{ color: '#94A3B8', fontSize: 12, fontWeight: 700 }}>SESSION TIMES PENDING</div>
              )}
            </div>
          </div>
        </div>

        <div style={{ background: '#FFFFFF', borderRadius: 24, padding: 24, border: '1px solid #F1F5F9', display: 'flex', flexDirection: 'column' }}>
          <h3 style={{ fontSize: 13, fontWeight: 900, color: '#0F172A', marginBottom: 24, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            SESSION CONDITIONS
          </h3>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
            <ConditionCard icon={Thermometer} label="TRACK TEMP" value={sessionWeather?.track_temperature ? `${sessionWeather.track_temperature}°C` : 'N/A'} color="#E8002D" />
            <ConditionCard icon={Wind} label="AIR TEMP" value={sessionWeather?.air_temperature ? `${sessionWeather.air_temperature}°C` : 'N/A'} color="#10B981" />
            <ConditionCard icon={Droplets} label="HUMIDITY" value={sessionWeather?.humidity ? `${sessionWeather.humidity}%` : 'N/A'} color="#0EA5E9" />
            <ConditionCard icon={Sun} label="RAINFALL" value={sessionWeather?.rainfall ? 'WET' : 'DRY'} color="#F59E0B" />
          </div>

          <div style={{
            marginTop: 18,
            paddingTop: 18,
            borderTop: '1px solid #F1F5F9',
            display: 'flex',
            flexDirection: 'column',
            gap: 12,
          }}>
            <div>
              <div style={{ fontSize: 10, fontWeight: 800, color: '#94A3B8', letterSpacing: '0.06em', textTransform: 'uppercase' }}>
                Quick Access
              </div>
            </div>
            <Link
              href="/sessions/latest"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: 12,
                textDecoration: 'none',
                background: 'linear-gradient(180deg, rgba(248,250,255,0.98) 0%, rgba(241,245,251,0.98) 100%)',
                border: '1px solid rgba(226,232,240,0.92)',
                borderRadius: 16,
                padding: '14px 16px',
                color: '#0F172A',
                boxShadow: '0 10px 28px rgba(24,39,75,0.06)',
              }}
            >
              <div>
                <div style={{ fontSize: 13, fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                  Open Latest Weekend
                </div>
                <div style={{ marginTop: 4, color: '#64748B', fontSize: 12 }}>
                  Race, quali, and practice summary with direct analysis actions.
                </div>
              </div>
              <span style={{ fontSize: 18, color: '#94A3B8' }}>→</span>
            </Link>
          </div>
        </div>
      </div>

      <div className="dashboard-stats-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 20 }}>
        <StatCard
          label="CHAMPIONSHIP LEADER" value={champLeader?.full_name ?? 'PENDING'} sub={champLeader?.team_name ?? '---'}
          points={champLeader?.points} icon={Trophy} color="#E8002D"
        />
        <StatCard
          label="QUICKEST PACE"
          value={topFastestLapData ? formatLapTime(topFastestLapData.lap_duration * 1000) : 'NO DATA'}
          sub={fastestDriver ? fastestDriver.full_name : 'Session Best'}
          subLabel={dynamicFastest?.gp ? `Fastest Lap: ${dynamicFastest.gp}` : '---'}
          icon={Clock} color="#E8002D"
        />
        <StatCard
          label="LEADING CONSTRUCTOR" value={constructorLeader?.team_name ?? '---'} sub="Team Standings" points={constructorLeader?.points} icon={Zap} color="#E8002D"
        />
        <StatCard
          label="RECENT SESSION"
          value={lastSession?.circuit_short_name ?? '---'}
          sub={lastSession ? `${lastSession.session_type} Session` : '---'}
          icon={Flag} color="#E8002D"
        />
      </div>

      <div style={{ background: '#FFFFFF', borderRadius: 24, padding: '24px 16px', border: '1px solid #F1F5F9', overflowX: 'auto' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 32 }}>
          <div>
            <h2 style={{ fontSize: 24, fontWeight: 900, color: '#0F172A', letterSpacing: '-0.03em', textTransform: 'uppercase' }}>
              {currentYear} STANDINGS
            </h2>
            <p style={{ fontSize: 12, color: '#94A3B8', fontWeight: 500, marginTop: 4 }}>Updated after Round {standings.round}</p>
          </div>
        </div>

        <ChampionshipStandings
          drivers={standings.drivers}
          constructors={standings.constructors}
          currentYear={currentYear}
          round={standings.round}
          images={driverImages}
        />
      </div>

    </div>
  )
}

// ── Shared Sub-components ─────────────────────────────────────────────────────

function ConditionCard({ icon: Icon, label, value, color }: { icon: React.ElementType, label: string, value: string, color: string }) {
  return (
    <div style={{ background: '#F8FAFC', borderRadius: 16, padding: 16, display: 'flex', flexDirection: 'column', gap: 12 }}>
      <Icon size={18} color={color} style={{ opacity: 0.8 }} />
      <div>
        <div style={{ fontSize: 9, fontWeight: 800, color: '#94A3B8', letterSpacing: '0.05em' }}>{label}</div>
        <div style={{ fontSize: 18, fontWeight: 900, color: '#0F172A', letterSpacing: '-0.02em', marginTop: 2 }}>{value}</div>
      </div>
    </div>
  )
}

function StatCard({ label, value, sub, subLabel, points, timer, icon: Icon }: { label: string, value: string, sub: string, subLabel?: string, points?: number, timer?: string, icon: React.ElementType, color: string }) {
  return (
    <div style={{ background: '#FFFFFF', borderRadius: 20, padding: 24, border: '1px solid #F1F5F9', position: 'relative', display: 'flex', flexDirection: 'column' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 16 }}>
        <div style={{ fontSize: 9, fontWeight: 800, color: '#94A3B8', letterSpacing: '0.05em', maxWidth: '70%', textTransform: 'uppercase' }}>{label}</div>
        <div style={{ width: 24, height: 24, background: '#FEE2E2', borderRadius: 6, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <Icon size={14} color="#E8002D" />
        </div>
      </div>

      <div style={{ fontSize: points ? 24 : 28, fontWeight: 900, color: '#0F172A', letterSpacing: '-0.04em', lineHeight: 1, textTransform: 'uppercase' }}>
        {value}
      </div>

      {subLabel && (
        <div style={{ fontSize: 9, fontWeight: 700, color: '#94A3B8', marginTop: 8, textTransform: 'uppercase', letterSpacing: '0.02em' }}>
          {subLabel}
        </div>
      )}

      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: subLabel ? 4 : 12 }}>
        <span style={{ fontSize: 12, fontWeight: 500, color: '#64748B' }}>{sub}</span>
        {points && <span style={{ fontSize: 14, fontWeight: 800, color: '#0F172A' }}>{points} <span style={{ fontSize: 10, color: '#94A3B8' }}>PTS</span></span>}
        {timer && <span style={{ fontSize: 18, fontWeight: 900, color: '#0F172A', fontFamily: 'monospace' }}>{timer}</span>}
      </div>
    </div>
  )
}
