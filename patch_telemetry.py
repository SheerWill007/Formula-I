#!/usr/bin/env python3
"""
Patches apps/frontend/app/sessions/[key]/telemetry/page.tsx
to add Q1/Q2/Q3 qualifying segment leaderboard.

Makes 3 surgical edits:
  1. Add types before export default
  2. Add state + useEffect after existing state declarations  
  3. Add Q1/Q2/Q3 panel in the JSX (after sector times panel)

Run from your Slipstream root:
  python3 patch_telemetry.py
"""
import sys
import os

FILE = "apps/frontend/app/sessions/[key]/telemetry/page.tsx"

if not os.path.exists(FILE):
    print(f"❌ File not found: {FILE}")
    print("   Run this script from your Slipstream root directory.")
    sys.exit(1)

with open(FILE, "r") as f:
    content = f.read()

# ── Edit 1: Add types before export default function ─────────────────────────

TYPES = '''
// ── Q1/Q2/Q3 segment types ───────────────────────────────────────────────────
type QualiSegmentEntry = {
  driver_number: number
  abbreviation: string
  team_name: string
  team_colour: string
  lap_number: number
  lap_time_ms: number
  s1_ms: number | null
  s2_ms: number | null
  s3_ms: number | null
  gap_ms: number
  position: number
  eliminated: boolean
}

type QualiSegmentsData = {
  segments: { Q1: QualiSegmentEntry[]; Q2: QualiSegmentEntry[]; Q3: QualiSegmentEntry[] }
  boundaries: { Q2_start_lap: number | null; Q3_start_lap: number | null }
}

'''

TARGET_1 = "export default function TelemetryPage"
if TARGET_1 not in content:
    print("❌ Edit 1 failed: could not find 'export default function TelemetryPage'")
    sys.exit(1)
content = content.replace(TARGET_1, TYPES + TARGET_1)
print("✅ Edit 1: types added")

# ── Edit 2: Add state + useEffect after telLapNumbers state ──────────────────

OLD_STATE = "  const [telLapNumbers, setTelLapNumbers] = useState<Map<number, number>>(new Map())"

NEW_STATE = """  const [telLapNumbers, setTelLapNumbers] = useState<Map<number, number>>(new Map())
  const [qualiSegments, setQualiSegments] = useState<QualiSegmentsData | null>(null)
  const [activeSegment, setActiveSegment] = useState<'Q1' | 'Q2' | 'Q3'>('Q1')"""

if OLD_STATE not in content:
    print("❌ Edit 2 failed: could not find telLapNumbers state declaration")
    sys.exit(1)
content = content.replace(OLD_STATE, NEW_STATE)
print("✅ Edit 2: state added")

# ── Edit 3: Add useEffect for quali segments fetch ───────────────────────────
# Insert after the sector times useEffect block — find its closing comment

QUALI_EFFECT = """
  // Fetch Q1/Q2/Q3 segment leaderboards for qualifying sessions
  useEffect(() => {
    if (!sessionType || isRaceSession(sessionType) || isPracticeSession(sessionType)) return
    fetch(`${BASE}/api/v1/sessions/${sessionKey}/analysis/quali-segments`)
      .then(r => r.json())
      .then((data: QualiSegmentsData) => {
        setQualiSegments(data)
      })
      .catch(() => {})
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionKey, sessionType])

"""

# Insert after the sector times useEffect (find its eslint-disable comment)
TARGET_3 = "  // Build driver render data (qualifying canvas)"
if TARGET_3 not in content:
    print("❌ Edit 3 failed: could not find render data comment")
    sys.exit(1)
content = content.replace(TARGET_3, QUALI_EFFECT + TARGET_3)
print("✅ Edit 3: useEffect added")

# ── Edit 4: Add Q1/Q2/Q3 panel in JSX after the sector times panel ───────────

QUALI_PANEL = """
              {/* Q1 / Q2 / Q3 Segment Leaderboards */}
              {qualiSegments && (
                <div style={{
                  background: '#111111', border: '1px solid #2A2A2A',
                  borderRadius: '12px', padding: '12px 16px', marginBottom: '8px',
                }}>
                  {/* Header */}
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
                    <span style={{ fontSize: '10px', fontFamily: 'monospace', color: '#52525B', letterSpacing: '0.12em' }}>
                      QUALIFYING SEGMENTS
                    </span>
                    {/* Tab strip */}
                    <div style={{ display: 'flex', gap: '4px' }}>
                      {(['Q1', 'Q2', 'Q3'] as const).map(seg => {
                        const count = qualiSegments.segments[seg]?.length ?? 0
                        const isActive = activeSegment === seg
                        const segColour = seg === 'Q1' ? '#3671C6' : seg === 'Q2' ? '#FFD700' : '#E8002D'
                        return (
                          <button
                            key={seg}
                            onClick={() => setActiveSegment(seg)}
                            style={{
                              padding: '4px 12px', borderRadius: '6px', cursor: 'pointer',
                              border: isActive ? `1.5px solid ${segColour}` : '1.5px solid #2A2A2A',
                              background: isActive ? `${segColour}18` : 'transparent',
                              color: isActive ? '#fff' : '#52525B',
                              fontSize: '11px', fontFamily: 'monospace', fontWeight: isActive ? 700 : 400,
                              transition: 'all 0.12s',
                            }}
                          >
                            {seg}
                            {count > 0 && (
                              <span style={{ marginLeft: '5px', fontSize: '9px', color: isActive ? segColour : '#3F3F46' }}>
                                {count}
                              </span>
                            )}
                          </button>
                        )
                      })}
                    </div>
                  </div>

                  {/* Leaderboard */}
                  {(() => {
                    const entries = qualiSegments.segments[activeSegment] ?? []
                    const segColour = activeSegment === 'Q1' ? '#3671C6' : activeSegment === 'Q2' ? '#FFD700' : '#E8002D'
                    const cutLine = activeSegment === 'Q1' ? 15 : activeSegment === 'Q2' ? 10 : null

                    return (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
                        {/* Column headers */}
                        <div style={{
                          display: 'grid',
                          gridTemplateColumns: '28px 36px 1fr 80px 60px 60px 60px',
                          gap: '4px', paddingBottom: '6px',
                          borderBottom: '1px solid #1A1A1A', marginBottom: '4px',
                        }}>
                          {['P', 'DRV', 'TEAM', 'TIME', 'S1', 'S2', 'S3'].map(h => (
                            <span key={h} style={{ fontSize: '9px', fontFamily: 'monospace', color: '#3F3F46', textAlign: h === 'TIME' || h === 'S1' || h === 'S2' || h === 'S3' ? 'right' : 'left' }}>
                              {h}
                            </span>
                          ))}
                        </div>

                        {entries.map((entry, idx) => {
                          const isFastest = idx === 0
                          const isEliminated = entry.eliminated
                          const showCutLine = cutLine !== null && idx === cutLine - 1

                          const fmtMs = (ms: number | null) => {
                            if (ms === null) return '—'
                            const s = ms / 1000
                            const mins = Math.floor(s / 60)
                            const secs = (s % 60).toFixed(3).padStart(6, '0')
                            return mins > 0 ? `${mins}:${secs}` : `${secs}`
                          }

                          const fmtGap = (ms: number) => {
                            if (ms === 0) return ''
                            return `+${(ms / 1000).toFixed(3)}`
                          }

                          return (
                            <div key={entry.driver_number}>
                              {/* Cut line separator */}
                              {showCutLine && (
                                <div style={{
                                  height: '1px', background: '#E8002D33',
                                  margin: '4px 0', position: 'relative',
                                }}>
                                  <span style={{
                                    position: 'absolute', right: 0, top: '-8px',
                                    fontSize: '8px', fontFamily: 'monospace', color: '#E8002D66',
                                  }}>
                                    ELIMINATION LINE
                                  </span>
                                </div>
                              )}
                              <div style={{
                                display: 'grid',
                                gridTemplateColumns: '28px 36px 1fr 80px 60px 60px 60px',
                                gap: '4px', alignItems: 'center',
                                padding: '5px 4px', borderRadius: '6px',
                                background: isFastest ? `${segColour}0A` : 'transparent',
                                opacity: isEliminated ? 0.45 : 1,
                              }}>
                                {/* Position */}
                                <span style={{
                                  fontSize: '11px', fontFamily: 'monospace',
                                  color: isFastest ? segColour : '#52525B',
                                  fontWeight: isFastest ? 700 : 400,
                                }}>
                                  P{entry.position}
                                </span>

                                {/* Driver abbreviation */}
                                <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                                  <div style={{
                                    width: '3px', height: '14px', borderRadius: '2px',
                                    background: `#${entry.team_colour}`,
                                    flexShrink: 0,
                                  }} />
                                  <span style={{
                                    fontSize: '11px', fontFamily: 'monospace',
                                    color: isFastest ? '#fff' : '#A1A1AA',
                                    fontWeight: isFastest ? 700 : 500,
                                  }}>
                                    {entry.abbreviation}
                                  </span>
                                </div>

                                {/* Team */}
                                <span style={{
                                  fontSize: '10px', fontFamily: 'monospace',
                                  color: '#52525B', overflow: 'hidden',
                                  textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                                }}>
                                  {entry.team_name}
                                </span>

                                {/* Lap time + gap */}
                                <div style={{ textAlign: 'right' }}>
                                  <div style={{
                                    fontSize: '12px', fontFamily: 'monospace',
                                    color: isFastest ? '#fff' : '#A1A1AA',
                                    fontWeight: isFastest ? 700 : 400,
                                  }}>
                                    {fmtMs(entry.lap_time_ms)}
                                  </div>
                                  {entry.gap_ms > 0 && (
                                    <div style={{ fontSize: '9px', fontFamily: 'monospace', color: '#52525B' }}>
                                      {fmtGap(entry.gap_ms)}
                                    </div>
                                  )}
                                </div>

                                {/* S1 */}
                                <span style={{
                                  fontSize: '10px', fontFamily: 'monospace',
                                  color: '#52525B', textAlign: 'right',
                                }}>
                                  {entry.s1_ms ? (entry.s1_ms / 1000).toFixed(3) : '—'}
                                </span>

                                {/* S2 */}
                                <span style={{
                                  fontSize: '10px', fontFamily: 'monospace',
                                  color: '#52525B', textAlign: 'right',
                                }}>
                                  {entry.s2_ms ? (entry.s2_ms / 1000).toFixed(3) : '—'}
                                </span>

                                {/* S3 */}
                                <span style={{
                                  fontSize: '10px', fontFamily: 'monospace',
                                  color: '#52525B', textAlign: 'right',
                                }}>
                                  {entry.s3_ms ? (entry.s3_ms / 1000).toFixed(3) : '—'}
                                </span>
                              </div>
                            </div>
                          )
                        })}
                      </div>
                    )
                  })()}
                </div>
              )}

"""

# Insert before the track map panel
TARGET_4 = "              {/* Track Map */}"
if TARGET_4 not in content:
    print("❌ Edit 4 failed: could not find Track Map comment")
    sys.exit(1)
content = content.replace(TARGET_4, QUALI_PANEL + TARGET_4)
print("✅ Edit 4: Q1/Q2/Q3 panel added to JSX")

# ── Write the patched file ────────────────────────────────────────────────────
with open(FILE, "w") as f:
    f.write(content)

print()
print("✅ All edits applied successfully!")
print(f"   File written: {FILE}")
print()
print("Next: cd apps/frontend && pnpm dev")
print("      Open: http://localhost:3000 → any qualifying session → telemetry tab")
