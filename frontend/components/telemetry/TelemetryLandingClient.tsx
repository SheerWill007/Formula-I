'use client'

import { useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import { Activity, ChevronRight, Gauge, Network, Clock } from 'lucide-react'
import type { Session } from '@/types/f1'

type Props = {
  initialSessions: Session[]
}

const C = {
  bg: '#080A0E',
  surface: '#0D1117',
  surfaceHover: '#131924',
  border: '#1A2030',
  borderMid: '#242D3E',
  borderLight: '#2E3A52',
  textDim: '#364155',
  textMid: '#5A6A82',
  textSub: '#8A9BB5',
  textPrime: '#C8D8F0',
  textBright: '#E8F0FF',
  red: '#E8002D',
  redHover: '#ff0a3b',
  gold: '#FFD700',
} as const

export default function TelemetryLandingClient({ initialSessions }: Props) {
  const router = useRouter()
  const [selectedYear, setSelectedYear] = useState<number | null>(initialSessions[0]?.year ?? null)

  const years = useMemo(
    () => Array.from(new Set(initialSessions.map(s => s.year))).sort((a, b) => b - a),
    [initialSessions],
  )

  const gpsForYear = useMemo(() => {
    if (!selectedYear) return []
    return initialSessions
      .filter(s => s.year === selectedYear)
      .sort((a, b) => new Date(a.date_start ?? 0).getTime() - new Date(b.date_start ?? 0).getTime())
  }, [initialSessions, selectedYear])

  const recentSessions = useMemo(() => initialSessions.slice(0, 4), [initialSessions])

  const handleLaunch = (sessionKey: number) => {
    router.push(`/sessions/${sessionKey}/telemetry`)
  }

  return (
    <>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;600;700&display=swap');

        .tl-root {
          background: ${C.bg};
          min-height: 100vh;
          font-family: 'JetBrains Mono', monospace;
          color: ${C.textPrime};
          padding: 80px 24px;
        }

        .tl-container {
          max-width: 1200px;
          margin: 0 auto;
        }

        /* Hero */
        .tl-hero {
          margin-bottom: 60px;
        }

        .tl-eyebrow {
          display: inline-flex;
          align-items: center;
          gap: 12px;
          margin-bottom: 24px;
        }

        .tl-eyebrow-line {
          width: 24px;
          height: 2px;
          background: ${C.red};
        }

        .tl-eyebrow-text {
          font-size: 11px;
          letter-spacing: 0.24em;
          color: ${C.textDim};
          text-transform: uppercase;
          font-weight: 600;
        }

        .tl-title {
          font-family: 'Barlow Condensed', sans-serif;
          font-size: 84px;
          font-weight: 800;
          color: ${C.textBright};
          letter-spacing: 0.02em;
          text-transform: uppercase;
          line-height: 0.9;
          margin: 0 0 16px 0;
        }

        .tl-title em {
          font-style: normal;
          color: ${C.red};
        }

        .tl-subtitle {
          font-size: 14px;
          color: ${C.textMid};
          max-width: 600px;
          line-height: 1.6;
          letter-spacing: 0.02em;
        }

        /* Stats Row */
        .tl-stats-row {
          display: flex;
          gap: 32px;
          margin-top: 48px;
          padding-top: 32px;
          border-top: 1px solid ${C.border};
        }

        .tl-stat-box {
          display: flex;
          flex-direction: column;
          gap: 8px;
        }

        .tl-stat-label {
          font-size: 9px;
          letter-spacing: 0.16em;
          color: ${C.textDim};
          text-transform: uppercase;
        }

        .tl-stat-value {
          font-family: 'Barlow Condensed', sans-serif;
          font-size: 32px;
          font-weight: 700;
          color: ${C.textPrime};
          line-height: 1;
        }

        .tl-stat-value span {
          font-size: 16px;
          color: ${C.textMid};
          margin-left: 4px;
        }

        /* Main Grid */
        .tl-main-grid {
          display: grid;
          grid-template-columns: 3fr 1.2fr;
          gap: 40px;
        }

        @media (max-width: 900px) {
          .tl-main-grid {
            grid-template-columns: 1fr;
          }
        }

        /* Selector Panel */
        .tl-panel {
          background: ${C.surface};
          border: 1px solid ${C.border};
          border-radius: 12px;
          padding: 32px;
          position: relative;
          overflow: hidden;
        }

        .tl-panel-title {
          font-family: 'Barlow Condensed', sans-serif;
          font-size: 24px;
          font-weight: 700;
          color: ${C.textBright};
          text-transform: uppercase;
          margin-bottom: 24px;
          display: flex;
          align-items: center;
          gap: 12px;
        }

        /* Years */
        .tl-year-bar {
          display: flex;
          gap: 8px;
          margin-bottom: 32px;
          padding-bottom: 24px;
          border-bottom: 1px solid ${C.border};
        }

        .tl-year-btn {
          font-size: 16px;
          font-family: 'Barlow Condensed', sans-serif;
          font-weight: 700;
          color: ${C.textMid};
          padding: 8px 20px;
          border-radius: 6px;
          cursor: pointer;
          transition: all 0.2s ease;
          border: 1px solid transparent;
          background: transparent;
        }

        .tl-year-btn:hover {
          color: ${C.textPrime};
          background: ${C.surfaceHover};
        }

        .tl-year-btn.active {
          color: ${C.textBright};
          background: ${C.border};
          border-color: ${C.borderMid};
        }

        /* GPs */
        .tl-gp-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
          gap: 16px;
        }

        .tl-gp-btn {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 16px 20px;
          background: ${C.bg};
          border: 1px solid ${C.border};
          border-radius: 8px;
          cursor: pointer;
          transition: all 0.2s ease;
          text-align: left;
          position: relative;
          overflow: hidden;
        }

        .tl-gp-btn:hover {
          border-color: ${C.borderMid};
          background: ${C.surfaceHover};
          transform: translateY(-2px);
          box-shadow: 0 8px 24px rgba(0,0,0,0.4);
        }

        .tl-gp-indicator {
          width: 3px;
          position: absolute;
          left: 0;
          top: 0;
          bottom: 0;
          background: ${C.red};
          opacity: 0;
          transition: opacity 0.2s;
        }

        .tl-gp-btn:hover .tl-gp-indicator {
          opacity: 1;
        }

        .tl-gp-name {
          font-family: 'Barlow Condensed', sans-serif;
          font-size: 20px;
          font-weight: 700;
          color: ${C.textPrime};
          margin-bottom: 4px;
          text-transform: uppercase;
        }

        .tl-gp-meta {
          font-size: 10px;
          color: ${C.textDim};
          letter-spacing: 0.1em;
          display: flex;
          gap: 8px;
          align-items: center;
        }

        .tl-gp-launch {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 32px;
          height: 32px;
          border-radius: 50%;
          background: ${C.border};
          color: ${C.textMid};
          transition: all 0.2s;
        }

        .tl-gp-btn:hover .tl-gp-launch {
          background: ${C.red};
          color: ${C.textBright};
          transform: scale(1.1);
        }

        /* Recent */
        .tl-recent {
          display: flex;
          flex-direction: column;
          gap: 12px;
        }

        .tl-recent-card {
          padding: 20px;
          background: ${C.surface};
          border: 1px solid ${C.border};
          border-radius: 8px;
          cursor: pointer;
          transition: all 0.2s;
          display: flex;
          flex-direction: column;
          gap: 12px;
        }

        .tl-recent-card:hover {
          border-color: ${C.borderMid};
          background: ${C.surfaceHover};
        }

        .tl-recent-header {
          display: flex;
          justify-content: space-between;
          align-items: flex-start;
        }

        .tl-recent-tag {
          font-size: 8px;
          padding: 4px 8px;
          background: ${C.red}15;
          color: ${C.red};
          border-radius: 4px;
          letter-spacing: 0.1em;
          text-transform: uppercase;
          font-weight: 600;
        }

        .tl-recent-title {
          font-family: 'Barlow Condensed', sans-serif;
          font-size: 24px;
          font-weight: 700;
          color: ${C.textBright};
          text-transform: uppercase;
          line-height: 1;
        }
      `}</style>

      <div className="tl-root">
        <div className="tl-container">

          {/* Hero Section */}
          <header className="tl-hero">
            <div className="tl-eyebrow">
              <div className="tl-eyebrow-line" />
              <span className="tl-eyebrow-text">Data Architecture</span>
            </div>

            <h1 className="tl-title">
              Telemetry <em>Engine</em>
            </h1>

            <p className="tl-subtitle">
              High-fidelity velocity vectors, multispectral pedal application, and dynamic gear shift mapping. Access raw telemetry sequences mapped to the 0.001s for every qualifying session across the hybrid era.
            </p>

            <div className="tl-stats-row">
              <div className="tl-stat-box">
                <div className="tl-stat-label">Indexed Sessions</div>
                <div className="tl-stat-value">{initialSessions.length}</div>
              </div>
              <div className="tl-stat-box">
                <div className="tl-stat-label">Refresh Rate</div>
                <div className="tl-stat-value">60<span>Hz</span></div>
              </div>
              <div className="tl-stat-box">
                <div className="tl-stat-label">Latency</div>
                <div className="tl-stat-value">&lt;20<span>ms</span></div>
              </div>
            </div>
          </header>

          {/* Main Layout */}
          <div className="tl-main-grid">

            {/* Left: Interactive Browser */}
            <div className="tl-panel">
              <h2 className="tl-panel-title">
                <Activity size={24} style={{ color: C.red }} />
                Session Explorer
              </h2>

              <div className="tl-year-bar">
                {years.map(y => (
                  <button
                    key={y}
                    className={`tl-year-btn ${selectedYear === y ? 'active' : ''}`}
                    onClick={() => setSelectedYear(y)}
                  >
                    {y}
                  </button>
                ))}
              </div>

              <div className="tl-gp-grid">
                {gpsForYear.map(s => (
                  <button
                    key={s.session_key}
                    className="tl-gp-btn"
                    onClick={() => handleLaunch(s.session_key)}
                  >
                    <div className="tl-gp-indicator" />
                    <div>
                      <div className="tl-gp-name">{s.gp_name.replace(' Grand Prix', '')}</div>
                      <div className="tl-gp-meta">
                        <span>{s.year}</span>
                        <div style={{ width: 3, height: 3, borderRadius: '50%', background: C.borderMid }} />
                        <span>QUALIFYING</span>
                      </div>
                    </div>
                    <div className="tl-gp-launch">
                      <ChevronRight size={16} />
                    </div>
                  </button>
                ))}
              </div>
            </div>

            {/* Right: Shortcuts / Recent */}
            <div>
              <h2 className="tl-panel-title" style={{ fontSize: '18px', marginBottom: '20px' }}>
                <Clock size={16} style={{ color: C.textMid }} />
                Recent Snapshots
              </h2>

              <div className="tl-recent">
                {recentSessions.map((s, i) => (
                  <div key={s.session_key} className="tl-recent-card" onClick={() => handleLaunch(s.session_key)}>
                    <div className="tl-recent-header">
                      <div className="tl-recent-title">{s.gp_name.replace(' Grand Prix', '')}</div>
                      {i === 0 && <span className="tl-recent-tag">LATEST</span>}
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                      <div style={{ padding: '6px 10px', background: C.bg, borderRadius: 4, display: 'flex', alignItems: 'center', gap: 6, border: `1px solid ${C.border}` }}>
                        <Gauge size={12} style={{ color: C.textDim }} />
                        <span style={{ fontSize: 9, color: C.textMid }}>QUALIFYING</span>
                      </div>
                      <div style={{ padding: '6px 10px', background: C.bg, borderRadius: 4, display: 'flex', alignItems: 'center', gap: 6, border: `1px solid ${C.border}` }}>
                        <Network size={12} style={{ color: C.textDim }} />
                        <span style={{ fontSize: 9, color: C.textMid }}>{s.year}</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

          </div>
        </div>
      </div>
    </>
  )
}
