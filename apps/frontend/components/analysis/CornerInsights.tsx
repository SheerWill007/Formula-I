'use client'

// ── Design tokens (matching telemetry page) ──────────────────────────────────
const C = {
  bg: '#F8F9FC',
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
  purple: '#6E56CF',
  gold: '#F59E0B',
} as const

// ── Types ────────────────────────────────────────────────────────────────────
export type Insight = {
  id: string
  tier: 'CRITICAL' | 'NOTABLE' | 'INFO'
  category: 'BRAKING' | 'THROTTLE' | 'STRATEGY'
  title: string
  detail: string
  metric: string
  drivers: string[]
  winner: string
  corner?: number
}

export type DriverProfile = {
  style: 'ENTRY-FOCUSED' | 'EXIT-FOCUSED' | 'BALANCED'
  description: string
  entry_score: number
  exit_score: number
}

export type InsightsData = {
  headline: string
  insights: Insight[]
  driver_profiles: Record<string, DriverProfile>
  key_corner: number | null
}

// ── Tier styling ─────────────────────────────────────────────────────────────
const TIER_STYLE: Record<string, { accent: string; bg: string; border: string; label: string }> = {
  CRITICAL: { accent: C.red, bg: 'rgba(232,0,45,0.04)', border: 'rgba(232,0,45,0.14)', label: 'CRITICAL' },
  NOTABLE:  { accent: C.gold, bg: 'rgba(245,158,11,0.04)', border: 'rgba(245,158,11,0.14)', label: 'NOTABLE' },
  INFO:     { accent: C.textDim, bg: C.surfaceAlt, border: C.border, label: 'INFO' },
}

const CATEGORY_ICON: Record<string, string> = {
  BRAKING:  '⬇',
  THROTTLE: '⬆',
  STRATEGY: '◆',
}

const STYLE_CONFIG: Record<string, { colour: string; icon: string }> = {
  'ENTRY-FOCUSED': { colour: C.red, icon: '⬇' },
  'EXIT-FOCUSED':  { colour: C.green, icon: '⬆' },
  'BALANCED':      { colour: C.purple, icon: '◎' },
}

// ── Component ────────────────────────────────────────────────────────────────
export default function CornerInsights({
  data,
  driverColours,
}: {
  data: InsightsData
  driverColours: Record<string, string>
}) {
  if (!data || !data.insights?.length) return null

  const profileEntries = Object.entries(data.driver_profiles ?? {})

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>

      {/* ── Headline banner ────────────────────────────────────────────────── */}
      <div style={{
        background: 'linear-gradient(135deg, #1E293B 0%, #162033 55%, #24324A 100%)',
        borderRadius: 18,
        padding: '20px 22px',
        boxShadow: '0 16px 34px rgba(19,35,61,0.16)',
        position: 'relative',
        overflow: 'hidden',
      }}>
        <div style={{ position: 'absolute', inset: 0, background: 'radial-gradient(circle at top right, rgba(255,255,255,0.08), transparent 34%)' }} />
        <div style={{ position: 'relative' }}>
          <div style={{ fontSize: 9, letterSpacing: '0.18em', color: 'rgba(255,255,255,0.45)', fontFamily: 'Space Grotesk, sans-serif', fontWeight: 600, textTransform: 'uppercase', marginBottom: 8 }}>
            CORNER ANALYSIS DEBRIEF
          </div>
          <div style={{ fontSize: 20, fontFamily: 'Inter, sans-serif', fontWeight: 900, color: '#fff', lineHeight: 1.25, letterSpacing: '-0.02em' }}>
            {data.headline}
          </div>
          <div style={{ display: 'flex', gap: 8, marginTop: 12, flexWrap: 'wrap' }}>
            {data.insights.filter(i => i.tier === 'CRITICAL').length > 0 && (
              <span style={{
                fontSize: 9, fontFamily: 'JetBrains Mono, monospace', fontWeight: 700,
                padding: '4px 10px', borderRadius: 999,
                background: 'rgba(232,0,45,0.18)', color: '#FF6B8A', border: '1px solid rgba(232,0,45,0.25)',
              }}>
                {data.insights.filter(i => i.tier === 'CRITICAL').length} CRITICAL
              </span>
            )}
            {data.insights.filter(i => i.tier === 'NOTABLE').length > 0 && (
              <span style={{
                fontSize: 9, fontFamily: 'JetBrains Mono, monospace', fontWeight: 700,
                padding: '4px 10px', borderRadius: 999,
                background: 'rgba(245,158,11,0.15)', color: '#FBBF24', border: '1px solid rgba(245,158,11,0.22)',
              }}>
                {data.insights.filter(i => i.tier === 'NOTABLE').length} NOTABLE
              </span>
            )}
            <span style={{
              fontSize: 9, fontFamily: 'JetBrains Mono, monospace',
              padding: '4px 10px', borderRadius: 999,
              background: 'rgba(255,255,255,0.06)', color: 'rgba(255,255,255,0.5)', border: '1px solid rgba(255,255,255,0.1)',
            }}>
              {data.insights.length} insights · {Object.keys(data.driver_profiles).length} drivers
            </span>
          </div>
        </div>
      </div>

      {/* ── Insight cards ──────────────────────────────────────────────────── */}
      <div style={{
        background: C.surface,
        border: `1px solid ${C.border}`,
        borderRadius: 18,
        overflow: 'hidden',
        boxShadow: '0 8px 24px rgba(19,35,61,0.04)',
      }}>
        <div style={{
          padding: '14px 18px',
          borderBottom: `1px solid ${C.border}`,
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}>
          <div>
            <div style={{ fontSize: 12, fontFamily: 'Space Grotesk, sans-serif', fontWeight: 700, letterSpacing: '0.08em', color: C.textBright, textTransform: 'uppercase' }}>
              Engineering Insights
            </div>
            <div style={{ fontSize: 10, fontFamily: 'Inter, sans-serif', color: C.textDim, marginTop: 2 }}>
              Rules-based analysis from corner telemetry data
            </div>
          </div>
        </div>

        <div style={{ padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 10 }}>
          {data.insights.map(insight => {
            const tier = TIER_STYLE[insight.tier] ?? TIER_STYLE.INFO
            const catIcon = CATEGORY_ICON[insight.category] ?? '●'
            const winnerColour = driverColours[insight.winner] ?? C.textBright

            return (
              <div key={insight.id} style={{
                background: tier.bg,
                border: `1px solid ${tier.border}`,
                borderRadius: 14,
                padding: '14px 16px',
                position: 'relative',
                overflow: 'hidden',
              }}>
                {/* Left accent bar */}
                <div style={{
                  position: 'absolute', left: 0, top: 0, bottom: 0, width: 3,
                  background: tier.accent, borderRadius: '3px 0 0 3px',
                }} />

                {/* Header row: tier + category + winner */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8, paddingLeft: 6 }}>
                  <span style={{
                    fontSize: 8, fontFamily: 'Space Grotesk, sans-serif', fontWeight: 700,
                    letterSpacing: '0.14em', textTransform: 'uppercase',
                    color: tier.accent, padding: '2px 7px', borderRadius: 4,
                    background: `${tier.accent}12`, border: `1px solid ${tier.accent}20`,
                  }}>
                    {tier.label}
                  </span>
                  <span style={{
                    fontSize: 8, fontFamily: 'Space Grotesk, sans-serif', fontWeight: 600,
                    letterSpacing: '0.12em', textTransform: 'uppercase', color: C.textDim,
                  }}>
                    {catIcon} {insight.category}
                  </span>
                  <div style={{ flex: 1 }} />
                  <span style={{
                    fontSize: 9, fontFamily: 'JetBrains Mono, monospace', fontWeight: 700,
                    color: winnerColour, padding: '2px 8px', borderRadius: 999,
                    background: `${winnerColour}12`, border: `1px solid ${winnerColour}22`,
                  }}>
                    {insight.winner}
                  </span>
                </div>

                {/* Title */}
                <div style={{
                  fontSize: 13, fontFamily: 'Inter, sans-serif', fontWeight: 700,
                  color: C.textBright, marginBottom: 6, paddingLeft: 6, lineHeight: 1.3,
                }}>
                  {insight.title}
                </div>

                {/* Detail */}
                <div style={{
                  fontSize: 12, fontFamily: 'Inter, sans-serif', fontWeight: 400,
                  color: C.textMid, lineHeight: 1.65, paddingLeft: 6,
                }}>
                  {insight.detail}
                </div>

                {/* Metric bar */}
                <div style={{
                  marginTop: 10, paddingLeft: 6, display: 'flex', alignItems: 'center', gap: 8,
                }}>
                  <span style={{
                    fontSize: 9, fontFamily: 'Space Grotesk, sans-serif', fontWeight: 600,
                    letterSpacing: '0.1em', textTransform: 'uppercase', color: C.textDim,
                  }}>
                    METRIC
                  </span>
                  <span style={{
                    fontSize: 11, fontFamily: 'JetBrains Mono, monospace', fontWeight: 600,
                    color: C.textSub, padding: '3px 10px', borderRadius: 8,
                    background: C.surfaceAlt, border: `1px solid ${C.border}`,
                  }}>
                    {insight.metric}
                  </span>
                  {insight.corner && (
                    <span style={{
                      fontSize: 9, fontFamily: 'JetBrains Mono, monospace', fontWeight: 600,
                      color: C.red, padding: '3px 8px', borderRadius: 8,
                      background: 'rgba(232,0,45,0.06)', border: '1px solid rgba(232,0,45,0.12)',
                    }}>
                      C{insight.corner}
                    </span>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* ── Driver style profiles ─────────────────────────────────────────── */}
      {profileEntries.length >= 2 && (
        <div style={{
          background: C.surface,
          border: `1px solid ${C.border}`,
          borderRadius: 18,
          overflow: 'hidden',
          boxShadow: '0 8px 24px rgba(19,35,61,0.04)',
        }}>
          <div style={{
            padding: '14px 18px',
            borderBottom: `1px solid ${C.border}`,
          }}>
            <div style={{ fontSize: 12, fontFamily: 'Space Grotesk, sans-serif', fontWeight: 700, letterSpacing: '0.08em', color: C.textBright, textTransform: 'uppercase' }}>
              Driver Corner Profiles
            </div>
            <div style={{ fontSize: 10, fontFamily: 'Inter, sans-serif', color: C.textDim, marginTop: 2 }}>
              Driving style characterisation from braking and throttle data
            </div>
          </div>

          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
            gap: 12,
            padding: '14px 16px',
          }}>
            {profileEntries.map(([abbr, profile]) => {
              const styleCfg = STYLE_CONFIG[profile.style] ?? STYLE_CONFIG['BALANCED']
              const driverColour = driverColours[abbr] ?? C.textBright
              const maxScore = Math.max(profile.entry_score + profile.exit_score, 1)
              const entryPct = Math.round((profile.entry_score / maxScore) * 100)
              const exitPct = Math.round((profile.exit_score / maxScore) * 100)

              return (
                <div key={abbr} style={{
                  border: `1px solid ${C.border}`,
                  borderRadius: 14,
                  padding: '16px 14px',
                  background: C.surfaceAlt,
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 12,
                }}>
                  {/* Driver name + style badge */}
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <div style={{ width: 4, height: 20, borderRadius: 2, background: driverColour }} />
                      <span style={{ fontSize: 16, fontFamily: 'Inter, sans-serif', fontWeight: 900, color: C.textBright }}>
                        {abbr}
                      </span>
                    </div>
                    <span style={{
                      fontSize: 8, fontFamily: 'Space Grotesk, sans-serif', fontWeight: 700,
                      letterSpacing: '0.12em', textTransform: 'uppercase',
                      color: styleCfg.colour, padding: '4px 10px', borderRadius: 999,
                      background: `${styleCfg.colour}12`, border: `1px solid ${styleCfg.colour}22`,
                    }}>
                      {styleCfg.icon} {profile.style}
                    </span>
                  </div>

                  {/* Description */}
                  <div style={{
                    fontSize: 11.5, fontFamily: 'Inter, sans-serif', fontWeight: 400,
                    color: C.textMid, lineHeight: 1.55,
                  }}>
                    {profile.description}
                  </div>

                  {/* Entry vs Exit score bars */}
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    <div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                        <span style={{ fontSize: 9, fontFamily: 'Space Grotesk, sans-serif', fontWeight: 600, letterSpacing: '0.1em', textTransform: 'uppercase', color: C.textDim }}>
                          ENTRY
                        </span>
                        <span style={{ fontSize: 9, fontFamily: 'JetBrains Mono, monospace', fontWeight: 700, color: C.red }}>
                          {profile.entry_score}
                        </span>
                      </div>
                      <div style={{ height: 5, background: C.border, borderRadius: 3, overflow: 'hidden' }}>
                        <div style={{
                          height: '100%', width: `${entryPct}%`,
                          background: C.red, borderRadius: 3,
                          transition: 'width 0.5s ease',
                        }} />
                      </div>
                    </div>

                    <div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                        <span style={{ fontSize: 9, fontFamily: 'Space Grotesk, sans-serif', fontWeight: 600, letterSpacing: '0.1em', textTransform: 'uppercase', color: C.textDim }}>
                          EXIT
                        </span>
                        <span style={{ fontSize: 9, fontFamily: 'JetBrains Mono, monospace', fontWeight: 700, color: C.green }}>
                          {profile.exit_score}
                        </span>
                      </div>
                      <div style={{ height: 5, background: C.border, borderRadius: 3, overflow: 'hidden' }}>
                        <div style={{
                          height: '100%', width: `${exitPct}%`,
                          background: C.green, borderRadius: 3,
                          transition: 'width 0.5s ease',
                        }} />
                      </div>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* ── Key corner highlight ──────────────────────────────────────────── */}
      {data.key_corner && (() => {
        const cornerInsight = data.insights.find(i => i.corner === data.key_corner)
        if (!cornerInsight) return null
        const winnerColour = driverColours[cornerInsight.winner] ?? C.textBright

        return (
          <div style={{
            background: C.surface,
            border: `1px solid ${C.border}`,
            borderRadius: 18,
            padding: '16px 18px',
            boxShadow: '0 8px 24px rgba(19,35,61,0.04)',
            display: 'flex',
            alignItems: 'center',
            gap: 16,
          }}>
            {/* Corner number badge */}
            <div style={{
              width: 52, height: 52, borderRadius: 14,
              background: 'linear-gradient(135deg, #1E293B, #24324A)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              flexShrink: 0,
              boxShadow: '0 8px 18px rgba(19,35,61,0.12)',
            }}>
              <div>
                <div style={{ fontSize: 7, fontFamily: 'Space Grotesk, sans-serif', fontWeight: 700, color: 'rgba(255,255,255,0.45)', letterSpacing: '0.14em', textAlign: 'center' }}>
                  CORNER
                </div>
                <div style={{ fontSize: 20, fontFamily: 'Inter, sans-serif', fontWeight: 900, color: '#fff', textAlign: 'center', lineHeight: 1 }}>
                  {data.key_corner}
                </div>
              </div>
            </div>

            {/* Info */}
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 9, fontFamily: 'Space Grotesk, sans-serif', fontWeight: 700, letterSpacing: '0.14em', textTransform: 'uppercase', color: C.red, marginBottom: 4 }}>
                HIGHEST LAP TIME IMPACT
              </div>
              <div style={{ fontSize: 12, fontFamily: 'Inter, sans-serif', fontWeight: 500, color: C.textMid, lineHeight: 1.5 }}>
                {cornerInsight.detail.split('.').slice(0, 2).join('.') + '.'}
              </div>
            </div>

            {/* Winner badge */}
            <div style={{
              display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4, flexShrink: 0,
            }}>
              <div style={{ width: 6, height: 6, borderRadius: '50%', background: winnerColour }} />
              <span style={{
                fontSize: 11, fontFamily: 'JetBrains Mono, monospace', fontWeight: 800,
                color: winnerColour,
              }}>
                {cornerInsight.winner}
              </span>
              <span style={{ fontSize: 8, fontFamily: 'Space Grotesk, sans-serif', color: C.textDim, fontWeight: 600 }}>
                ADVANTAGE
              </span>
            </div>
          </div>
        )
      })()}
    </div>
  )
}
