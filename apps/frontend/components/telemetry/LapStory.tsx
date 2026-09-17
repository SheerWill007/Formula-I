'use client'

// ── "Where the lap was won" ───────────────────────────────────────────────────
// Distance-aligned story of a qualifying duel: real per-sector deltas, a
// telemetry-derived mini-sector dominance strip, Monaco-relevant skill metrics
// (slowest-corner apex speed, top speed, full-throttle share), and an
// auto-generated verdict. Pure frontend — consumes the interpolated telemetry
// the page already holds, so it needs no extra API call.

const C = {
  surface: '#FFFFFF',
  surfaceAlt: '#F5F7FB',
  border: '#D9E3EF',
  borderMid: '#C5D2E3',
  textDim: '#7D8BA2',
  textMid: '#56657C',
  textSub: '#293A52',
  textBright: '#13233D',
  red: '#E8002D',
  green: '#10B981',
  gold: '#F59E0B',
} as const

export type LapStoryDriver = {
  abbr: string
  colour: string
  speed: number[]
  dist: number[]
  throttle?: number[]
  s1_ms: number | null
  s2_ms: number | null
  s3_ms: number | null
  lapNumber?: number | null
}

const MINI_SECTORS = 24

function fmtDelta(ms: number): string {
  const s = Math.abs(ms) / 1000
  return `${ms <= 0 ? '−' : '+'}${s.toFixed(3)}`
}

function fmtSeconds(ms: number): string {
  return `${(ms / 1000).toFixed(3)}s`
}

/** Cumulative lap time (ms) from a distance-aligned speed trace. */
function cumulativeTimeMs(speed: number[], dist: number[]): number[] {
  const n = Math.min(speed.length, dist.length)
  const cum = new Array(n).fill(0)
  for (let i = 1; i < n; i++) {
    const segM = Math.max(0, dist[i] - dist[i - 1])
    const vMs = Math.max((speed[i] + speed[i - 1]) / 2 / 3.6, 0.5) // avg speed, floor to avoid /0
    cum[i] = cum[i - 1] + (segM / vMs) * 1000
  }
  return cum
}

function fullThrottlePct(throttle?: number[]): number | null {
  if (!throttle || !throttle.length) return null
  const open = throttle.filter(t => t >= 98).length
  return (open / throttle.length) * 100
}

export default function LapStory({
  drivers,
  isMobile,
}: {
  drivers: LapStoryDriver[]
  isMobile: boolean
}) {
  if (drivers.length < 2) return null

  // ── Pick the two fastest of the selected drivers (the headline duel) ──────────
  const withTotals = drivers
    .map(d => {
      const cum = cumulativeTimeMs(d.speed, d.dist)
      const telTotal = cum[cum.length - 1] ?? 0
      const sectorTotal =
        d.s1_ms != null && d.s2_ms != null && d.s3_ms != null
          ? d.s1_ms + d.s2_ms + d.s3_ms
          : null
      return { ...d, cum, telTotal, sectorTotal }
    })
    .sort((a, b) => (a.sectorTotal ?? a.telTotal) - (b.sectorTotal ?? b.telTotal))

  const [fast, slow] = withTotals
  const haveSectors =
    fast.sectorTotal != null && slow.sectorTotal != null

  // ── Real per-sector deltas (positive = fast driver gains in that sector) ──────
  const sectorRows = (['s1_ms', 's2_ms', 's3_ms'] as const).map((k, i) => {
    const fastMs = fast[k]
    const slowMs = slow[k]
    const delta = fastMs != null && slowMs != null ? slowMs - fastMs : null // +ve → fast gains
    return { label: `S${i + 1}`, fastMs, slowMs, delta }
  })

  const totalGapMs = haveSectors
    ? (slow.sectorTotal as number) - (fast.sectorTotal as number)
    : slow.telTotal - fast.telTotal

  // Sector where the fast driver banks the most time
  const decisiveSector = sectorRows
    .filter(r => r.delta != null)
    .sort((a, b) => (b.delta as number) - (a.delta as number))[0]

  // ── Mini-sector dominance from distance-aligned telemetry ─────────────────────
  const n = Math.min(fast.cum.length, slow.cum.length)
  const miniSectors = Array.from({ length: MINI_SECTORS }, (_, b) => {
    const start = Math.floor((b * (n - 1)) / MINI_SECTORS)
    const end = Math.floor(((b + 1) * (n - 1)) / MINI_SECTORS)
    const fastDt = fast.cum[end] - fast.cum[start]
    const slowDt = slow.cum[end] - slow.cum[start]
    const diff = slowDt - fastDt // +ve → fast quicker in this mini-sector
    const winner = diff >= 0 ? fast : slow
    const distMid = (fast.dist[start] + fast.dist[end]) / 2
    return { winner: winner.abbr, colour: winner.colour, diff, distMid }
  })
  const fastWins = miniSectors.filter(m => m.diff >= 0).length

  // ── Monaco skill metrics ──────────────────────────────────────────────────────
  const skill = withTotals.slice(0, 2).map(d => ({
    abbr: d.abbr,
    colour: d.colour,
    minSpeed: Math.round(Math.min(...d.speed)), // slowest corner apex (the hairpin)
    topSpeed: Math.round(Math.max(...d.speed)), // tunnel
    fullThrottle: fullThrottlePct(d.throttle),
  }))
  const apexLeader = [...skill].sort((a, b) => b.minSpeed - a.minSpeed)[0]

  const lapLen = Math.round(Math.max(...fast.dist))

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      {/* ── Verdict banner ───────────────────────────────────────────────────── */}
      <div style={{
        background: 'linear-gradient(135deg, #1E293B 0%, #162033 55%, #24324A 100%)',
        borderRadius: 18,
        padding: isMobile ? '18px 18px' : '22px 24px',
        boxShadow: '0 16px 34px rgba(19,35,61,0.16)',
        position: 'relative',
        overflow: 'hidden',
      }}>
        <div style={{ position: 'absolute', inset: 0, background: 'radial-gradient(circle at top right, rgba(255,255,255,0.08), transparent 34%)' }} />
        <div style={{ position: 'relative' }}>
          <div style={{ fontSize: 9, letterSpacing: '0.18em', color: 'rgba(255,255,255,0.45)', fontFamily: 'Space Grotesk, sans-serif', fontWeight: 600, textTransform: 'uppercase', marginBottom: 8 }}>
            Where the lap was won
          </div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, flexWrap: 'wrap' }}>
            <span style={{ fontSize: isMobile ? 22 : 28, fontFamily: 'Inter, sans-serif', fontWeight: 900, color: '#fff', letterSpacing: '-0.02em', lineHeight: 1 }}>
              {fast.abbr}
            </span>
            <span style={{ fontSize: 12, color: 'rgba(255,255,255,0.55)', fontFamily: 'JetBrains Mono, monospace' }}>beats</span>
            <span style={{ fontSize: isMobile ? 18 : 22, fontFamily: 'Inter, sans-serif', fontWeight: 800, color: 'rgba(255,255,255,0.85)', letterSpacing: '-0.02em', lineHeight: 1 }}>
              {slow.abbr}
            </span>
            <span style={{ marginLeft: 'auto', padding: '5px 12px', background: 'rgba(232,0,45,0.16)', border: '1px solid rgba(232,0,45,0.35)', borderRadius: 999, fontSize: isMobile ? 16 : 20, color: '#fff', fontFamily: 'JetBrains Mono, monospace', fontWeight: 800 }}>
              {fmtSeconds(totalGapMs)}
            </span>
          </div>
          <div style={{ marginTop: 12, fontSize: 13, lineHeight: 1.6, color: 'rgba(255,255,255,0.78)', fontFamily: 'Inter, sans-serif', maxWidth: 680 }}>
            {decisiveSector && decisiveSector.delta != null && decisiveSector.delta > 0 ? (
              <>
                The lap is won in <strong style={{ color: '#fff' }}>{decisiveSector.label}</strong>, where {fast.abbr} banks{' '}
                <strong style={{ color: '#fff' }}>{fmtSeconds(decisiveSector.delta)}</strong>.{' '}
              </>
            ) : (
              <>{fast.abbr} controls {fastWins}/{MINI_SECTORS} mini-sectors across the lap.{' '}</>
            )}
            {apexLeader && (
              <>
                {apexLeader.abbr} also carries the higher minimum speed through the slowest corner
                {' '}(<strong style={{ color: '#fff' }}>{apexLeader.minSpeed} km/h</strong>) — the clearest read on Monaco commitment.
              </>
            )}
          </div>
        </div>
      </div>

      {/* ── Mini-sector dominance strip ──────────────────────────────────────── */}
      <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 18, overflow: 'hidden', boxShadow: '0 8px 24px rgba(19,35,61,0.03)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '14px 16px', borderBottom: `1px solid ${C.border}` }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
            <span style={{ fontSize: 12, fontFamily: 'Space Grotesk, sans-serif', fontWeight: 700, letterSpacing: '0.08em', color: C.textBright, textTransform: 'uppercase' }}>Mini-Sector Dominance</span>
            <span style={{ fontSize: 10, fontFamily: 'JetBrains Mono, monospace', color: C.textDim }}>{MINI_SECTORS} segments · {lapLen} m lap</span>
          </div>
          <div style={{ display: 'flex', gap: 12 }}>
            {[fast, slow].map(d => (
              <div key={d.abbr} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                <div style={{ width: 10, height: 10, borderRadius: 3, background: d.colour }} />
                <span style={{ fontSize: 10, fontFamily: 'JetBrains Mono, monospace', fontWeight: 700, color: C.textMid }}>
                  {d.abbr} {d.abbr === fast.abbr ? fastWins : MINI_SECTORS - fastWins}
                </span>
              </div>
            ))}
          </div>
        </div>
        <div style={{ padding: '16px 16px 14px' }}>
          <div style={{ display: 'flex', gap: 2, height: 46 }}>
            {miniSectors.map((m, i) => {
              const intensity = Math.min(1, Math.abs(m.diff) / 60) // 60ms = strong margin
              return (
                <div
                  key={i}
                  title={`${m.winner} fastest here · ${fmtDelta(-Math.abs(m.diff))}s · ~${Math.round(m.distMid)}m`}
                  style={{
                    flex: 1,
                    borderRadius: 3,
                    background: m.colour,
                    opacity: 0.35 + intensity * 0.65,
                  }}
                />
              )
            })}
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 8, fontSize: 9, fontFamily: 'JetBrains Mono, monospace', color: C.textDim }}>
            <span>START / S1</span>
            <span>S2</span>
            <span>S3</span>
            <span>FINISH</span>
          </div>
        </div>
      </div>

      {/* ── Real per-sector deltas + skill metrics ───────────────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr', gap: 14 }}>
        {/* Sector deltas */}
        <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 18, padding: '16px 18px', boxShadow: '0 8px 24px rgba(19,35,61,0.03)' }}>
          <div style={{ fontSize: 11, fontFamily: 'Space Grotesk, sans-serif', fontWeight: 700, letterSpacing: '0.08em', color: C.textBright, textTransform: 'uppercase', marginBottom: 14 }}>
            Sector Gains · {fast.abbr} vs {slow.abbr}
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            {sectorRows.map(row => {
              const maxAbs = Math.max(...sectorRows.map(r => Math.abs(r.delta ?? 0)), 1)
              const fastGains = (row.delta ?? 0) >= 0
              const widthPct = row.delta != null ? (Math.abs(row.delta) / maxAbs) * 50 : 0
              return (
                <div key={row.label}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 5 }}>
                    <span style={{ fontSize: 11, fontFamily: 'JetBrains Mono, monospace', fontWeight: 700, color: C.textSub }}>{row.label}</span>
                    <span style={{ fontSize: 11, fontFamily: 'JetBrains Mono, monospace', fontWeight: 700, color: fastGains ? fast.colour : slow.colour }}>
                      {row.delta != null ? `${fmtDelta(-Math.abs(row.delta))}s → ${fastGains ? fast.abbr : slow.abbr}` : '—'}
                    </span>
                  </div>
                  {/* diverging bar: centre line, fast grows left, slow grows right */}
                  <div style={{ position: 'relative', height: 10, background: C.surfaceAlt, borderRadius: 999, overflow: 'hidden' }}>
                    <div style={{ position: 'absolute', left: '50%', top: 0, bottom: 0, width: 1, background: C.borderMid }} />
                    {row.delta != null && (
                      <div style={{
                        position: 'absolute',
                        top: 0, bottom: 0,
                        ...(fastGains
                          ? { right: '50%', width: `${widthPct}%`, background: fast.colour }
                          : { left: '50%', width: `${widthPct}%`, background: slow.colour }),
                        opacity: 0.85,
                        borderRadius: 999,
                      }} />
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        {/* Monaco skill metrics */}
        <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 18, padding: '16px 18px', boxShadow: '0 8px 24px rgba(19,35,61,0.03)' }}>
          <div style={{ fontSize: 11, fontFamily: 'Space Grotesk, sans-serif', fontWeight: 700, letterSpacing: '0.08em', color: C.textBright, textTransform: 'uppercase', marginBottom: 4 }}>
            Skill Read-Out
          </div>
          <div style={{ fontSize: 10, fontFamily: 'Inter, sans-serif', color: C.textDim, marginBottom: 14 }}>
            Slowest-corner apex, tunnel top speed, and lap spent flat-out.
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr auto auto', gap: '10px 14px', alignItems: 'center' }}>
            <span style={{ fontSize: 9, fontFamily: 'Space Grotesk, sans-serif', fontWeight: 600, letterSpacing: '0.1em', color: C.textDim, textTransform: 'uppercase' }}>Driver</span>
            <span style={{ fontSize: 9, fontFamily: 'Space Grotesk, sans-serif', fontWeight: 600, letterSpacing: '0.1em', color: C.textDim, textTransform: 'uppercase', textAlign: 'right' }}>Apex</span>
            <span style={{ fontSize: 9, fontFamily: 'Space Grotesk, sans-serif', fontWeight: 600, letterSpacing: '0.1em', color: C.textDim, textTransform: 'uppercase', textAlign: 'right' }}>Top</span>
            {skill.map(s => (
              <Row key={s.abbr} s={s} apexLeaderAbbr={apexLeader?.abbr} />
            ))}
          </div>
          {skill.some(s => s.fullThrottle != null) && (
            <div style={{ marginTop: 14, paddingTop: 12, borderTop: `1px solid ${C.border}`, display: 'flex', flexDirection: 'column', gap: 8 }}>
              {skill.map(s => s.fullThrottle == null ? null : (
                <div key={s.abbr}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                    <span style={{ fontSize: 10, fontFamily: 'JetBrains Mono, monospace', color: C.textMid }}>{s.abbr} · full throttle</span>
                    <span style={{ fontSize: 10, fontFamily: 'JetBrains Mono, monospace', fontWeight: 700, color: C.textSub }}>{s.fullThrottle.toFixed(1)}%</span>
                  </div>
                  <div style={{ height: 6, background: C.surfaceAlt, borderRadius: 999, overflow: 'hidden' }}>
                    <div style={{ height: '100%', width: `${s.fullThrottle}%`, background: s.colour, borderRadius: 999, opacity: 0.8 }} />
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function Row({
  s,
  apexLeaderAbbr,
}: {
  s: { abbr: string; colour: string; minSpeed: number; topSpeed: number }
  apexLeaderAbbr?: string
}) {
  const isApexLeader = s.abbr === apexLeaderAbbr
  return (
    <>
      <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
        <div style={{ width: 8, height: 8, borderRadius: '50%', background: s.colour }} />
        <span style={{ fontSize: 12, fontFamily: 'JetBrains Mono, monospace', fontWeight: 700, color: '#13233D' }}>{s.abbr}</span>
      </div>
      <span style={{ fontSize: 13, fontFamily: 'JetBrains Mono, monospace', fontWeight: isApexLeader ? 800 : 500, color: isApexLeader ? '#10B981' : '#56657C', textAlign: 'right' }}>
        {s.minSpeed}
      </span>
      <span style={{ fontSize: 13, fontFamily: 'JetBrains Mono, monospace', fontWeight: 500, color: '#56657C', textAlign: 'right' }}>
        {s.topSpeed}
      </span>
    </>
  )
}
