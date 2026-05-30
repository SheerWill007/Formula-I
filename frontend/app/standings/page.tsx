import React from 'react'
import ChampionshipStandings from '@/components/home/ChampionshipStandings'
import { Trophy, ShieldAlert } from 'lucide-react'

export const revalidate = 60

const BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

async function fetchStandings(year: number) {
  try {
    const [d, c] = await Promise.all([
      fetch(`${BASE}/api/v1/standings/drivers?year=${year}`, { next: { revalidate: 300 } }).then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      }),
      fetch(`${BASE}/api/v1/standings/constructors?year=${year}`, { next: { revalidate: 300 } }).then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      }),
    ])
    return { drivers: d.standings ?? [], constructors: c.standings ?? [], round: d.round ?? 0, error: null }
  } catch (err: any) {
    console.error("Failed to fetch standings:", err)
    return { drivers: [], constructors: [], round: 0, error: err.message || "Failed to load standings" }
  }
}

async function fetchDriverImages() {
  try {
    const data = await fetch('https://api.openf1.org/v1/drivers?session_key=latest', { next: { revalidate: 3600 } }).then(r => r.json())
    if (!Array.isArray(data)) return { acronymMap: {} }

    const acronymMap: Record<string, string> = {}
    data.forEach((d: { name_acronym: string; headshot_url: string }) => {
      if (d.name_acronym && d.headshot_url) acronymMap[d.name_acronym] = d.headshot_url
    })
    return { acronymMap }
  } catch {
    return { acronymMap: {} }
  }
}

export default async function StandingsPage() {
  const currentYear = new Date().getFullYear()

  const [standings, dData] = await Promise.all([
    fetchStandings(currentYear),
    fetchDriverImages()
  ])

  const { acronymMap: driverImages } = dData
  const hasData = standings.drivers.length > 0 || standings.constructors.length > 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px', maxWidth: '1080px', margin: '0 auto', padding: '0 24px 48px' }}>
      
      {/* Header Section */}
      <section style={{
        padding: '32px',
        borderRadius: '28px',
        background: 'linear-gradient(180deg, rgba(248,250,255,0.98) 0%, rgba(242,246,252,0.98) 100%)',
        border: '1px solid rgba(207,219,235,0.92)',
        boxShadow: '0 18px 48px rgba(24,39,75,0.08)',
      }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '18px', flexWrap: 'wrap' }}>
          <div>
            <div style={{ fontSize: '10px', color: '#7A8CA5', fontFamily: 'Space Grotesk, sans-serif', fontWeight: 700, letterSpacing: '0.14em', textTransform: 'uppercase', marginBottom: '10px' }}>
              Championship Standings
            </div>
            <h1 style={{ margin: 0, color: '#14233C', fontSize: '2.5rem', lineHeight: 0.98, fontFamily: 'Inter, sans-serif', fontWeight: 800 }}>
              {currentYear} Season Standings
            </h1>
            <p style={{ margin: '12px 0 0', color: '#56657C', fontSize: '15px', lineHeight: 1.6, maxWidth: '640px', fontFamily: 'Inter, sans-serif' }}>
              Keep track of the official driver and constructor championship standings throughout the {currentYear} Formula 1 campaign.
            </p>
          </div>

          <div style={{
            background: '#fff',
            border: '1px solid rgba(204,218,236,0.92)',
            padding: '12px 18px',
            borderRadius: '20px',
            boxShadow: '0 10px 24px rgba(24,39,75,0.06)',
            display: 'flex',
            alignItems: 'center',
            gap: '12px'
          }}>
            <div style={{ width: '36px', height: '36px', borderRadius: '50%', background: '#FEE2E2', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Trophy size={18} color="#E8002D" />
            </div>
            <div>
              <div style={{ fontSize: '10px', color: '#7A8CA5', fontFamily: 'JetBrains Mono, monospace', textTransform: 'uppercase' }}>Current Round</div>
              <div style={{ fontSize: '16px', fontWeight: 800, color: '#14233C', fontFamily: 'Rajdhani, sans-serif' }}>Round {standings.round || '---'}</div>
            </div>
          </div>
        </div>
      </section>

      {/* Main Content */}
      {standings.error || !hasData ? (
        <div style={{
          textAlign: 'center',
          padding: '64px 24px',
          borderRadius: '28px',
          background: 'linear-gradient(180deg, rgba(248,250,255,0.98) 0%, rgba(242,246,252,0.98) 100%)',
          border: '1px solid rgba(207,219,235,0.92)',
          boxShadow: '0 18px 48px rgba(24,39,75,0.08)',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          gap: '16px'
        }}>
          <div style={{ width: '48px', height: '48px', borderRadius: '50%', background: 'rgba(232, 0, 45, 0.08)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#E8002D' }}>
            <ShieldAlert size={24} />
          </div>
          <div>
            <h3 style={{ margin: '0 0 8px 0', fontSize: '18px', fontWeight: 800, color: '#14233C' }}>Standings Unavailable</h3>
            <p style={{ margin: 0, color: '#7A8CA5', fontSize: '14px', maxWidth: '480px', lineHeight: 1.5 }}>
              {standings.error ? `Failed to connect to the API: ${standings.error}` : "Standings data is currently not loaded. Please ensure the Flask API is running and connected."}
            </p>
          </div>
        </div>
      ) : (
        <div style={{
          background: '#FFFFFF',
          borderRadius: '28px',
          padding: '24px',
          border: '1px solid #F1F5F9',
          boxShadow: '0 18px 48px rgba(24,39,75,0.04)',
        }}>
          <ChampionshipStandings
            drivers={standings.drivers}
            constructors={standings.constructors}
            currentYear={currentYear}
            round={standings.round}
            images={driverImages}
          />
        </div>
      )}
    </div>
  )
}
