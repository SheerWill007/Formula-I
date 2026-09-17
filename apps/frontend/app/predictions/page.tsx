'use client'

import { useEffect, useMemo, useState } from 'react'
import { Activity, BarChart3, Brain, CheckCircle2, ChevronDown, Cpu, Database, FlaskConical, GitBranch, Sigma, TrendingUp, AlertCircle, Trophy } from 'lucide-react'

const BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'
const HERO_IMAGE = 'https://images.unsplash.com/photo-1696178946280-776bfa09ba90?q=80&w=2232&auto=format&fit=crop&ixlib=rb-4.1.0&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D'

// ── Types ─────────────────────────────────────────────────────────────────────

type ShapFactor = {
  feature: string
  label: string
  positive: boolean
  shap_value: number
  stream?: string
  stream_label?: string
}

type FeatureStream = {
  stream: string
  label: string
  share: number
  score: number
}

type ValidationFeature = {
  feature: string
  stream_label?: string
  cohens_d?: number | null
  p_value?: number | null
  spearman_r?: number | null
  importance?: number | null
  vif?: number | null
}

type Prediction = {
  driver_number: number
  abbreviation: string
  team_name: string
  team_colour: string
  grid_position: number
  predicted_position: number
  p1_probability?: number
  p2_probability?: number
  p3_probability?: number
  win_probability: number
  podium_probability: number
  position_probabilities: Record<string, number>
  factors: ShapFactor[]
  feature_streams?: FeatureStream[]
}

type PredictionResponse = {
  session_key: number
  gp_name: string
  year: number
  predictions: Prediction[]
  validation_report?: {
    available: boolean
    caveat: string
    feature_tests: ValidationFeature[]
    vif: ValidationFeature[]
    permutation_importance: ValidationFeature[]
  }
  model_baselines?: {
    grid_top3_accuracy?: number | null
    model_top3_accuracy?: number | null
    podium_precision?: number | null
    podium_recall?: number | null
    podium_brier?: number | null
  }
  weekend_inputs_used?: Record<string, {
    available: boolean
    session_type: string
    session_key?: number
    lap_count: number
  }>
  model?: {
    scope?: 'global' | 'gp'
    best_estimator?: string | null
    cv_mae_mean?: number | null
    cv_mae_std?: number | null
    cv_top3_accuracy_mean?: number | null
    cv_podium_precision_mean?: number | null
    cv_podium_recall_mean?: number | null
    cv_podium_brier_mean?: number | null
    grid_baseline_top3_accuracy_mean?: number | null
    cv_folds?: number | null
    n_training_rows?: number | null
    years?: number[]
    gp_name?: string | null
  }
}

type QualiSession = {
  session_key: number
  gp_name: string
  year: number
  date_start: string
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function ProbBar({ value, colour, max }: { value: number; colour: string; max: number }) {
  const pct = max > 0 ? (value / max) * 100 : 0
  return (
    <div style={{ flex: 1, height: '6px', background: '#DCE6F5', borderRadius: '999px', overflow: 'hidden' }}>
      <div style={{ width: `${pct}%`, height: '100%', background: '#' + colour + 'AA', borderRadius: '3px', transition: 'width 0.5s ease' }} />
    </div>
  )
}

function PositionBadge({ pos }: { pos: number }) {
  const gold = pos === 1
  const silver = pos === 2
  const bronze = pos === 3
  const bg = gold ? '#FFD70022' : silver ? '#C0C0C022' : bronze ? '#CD7F3222' : '#1A1A1A'
  const col = gold ? '#FFD700' : silver ? '#C0C0C0' : bronze ? '#CD7F32' : '#52525B'
  return (
    <div style={{ width: '28px', height: '28px', borderRadius: '6px', background: bg, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
      <span style={{ fontSize: '11px', fontFamily: 'monospace', fontWeight: 700, color: col }}>P{pos}</span>
    </div>
  )
}

function pct(value?: number | null, digits = 0) {
  return value == null ? 'n/a' : `${(value * 100).toFixed(digits)}%`
}

function StreamBars({ streams }: { streams?: FeatureStream[] }) {
  const palette: Record<string, string> = {
    car_pace: '#2563EB',
    tyre_strategy: '#059669',
    driver_team_form: '#7C3AED',
    circuit_context: '#D97706',
    other: '#64748B',
  }
  const visible = (streams ?? []).filter(s => Number.isFinite(s.share)).slice(0, 4)
  if (!visible.length) {
    return <div style={{ fontSize: '12px', color: '#7A8CA5', fontFamily: 'JetBrains Mono, monospace' }}>No stream attribution available.</div>
  }
  return (
    <div style={{ display: 'grid', gap: '10px' }}>
      {visible.map(stream => {
        const colour = palette[stream.stream] ?? '#64748B'
        return (
          <div key={stream.stream}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: '10px', marginBottom: '5px' }}>
              <span style={{ fontSize: '11px', fontFamily: 'Inter, sans-serif', color: '#56657C', fontWeight: 700 }}>{stream.label}</span>
              <span style={{ fontSize: '10px', fontFamily: 'JetBrains Mono, monospace', color: '#14233C' }}>{pct(stream.share)}</span>
            </div>
            <div style={{ height: '8px', borderRadius: '999px', overflow: 'hidden', background: '#DCE6F5' }}>
              <div style={{ width: `${Math.max(4, stream.share * 100)}%`, height: '100%', background: colour, borderRadius: '999px' }} />
            </div>
          </div>
        )
      })}
    </div>
  )
}

function statusTone(status: 'accepted' | 'pending' | 'limited') {
  if (status === 'accepted') return { bg: '#ECFDF5', border: '#A7F3D0', text: '#047857' }
  if (status === 'limited') return { bg: '#FFFBEB', border: '#FDE68A', text: '#92400E' }
  return { bg: '#F8FAFC', border: '#E2E8F0', text: '#64748B' }
}

function StatusPill({ status }: { status: 'accepted' | 'pending' | 'limited' }) {
  const tone = statusTone(status)
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', height: '22px', padding: '0 8px', borderRadius: '999px', border: `1px solid ${tone.border}`, background: tone.bg, color: tone.text, fontSize: '9px', fontFamily: 'JetBrains Mono, monospace', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em' }}>
      {status}
    </span>
  )
}

function ProcessFlow({ data, isMobile }: { data: PredictionResponse; isMobile: boolean }) {
  const validationAvailable = Boolean(data.validation_report?.available && data.validation_report.feature_tests?.length)
  const baselineAvailable = data.model_baselines?.model_top3_accuracy != null || data.model_baselines?.podium_brier != null
  const streamAvailable = Boolean(data.predictions[0]?.feature_streams?.length)
  const inputCount = Object.values(data.weekend_inputs_used ?? {}).filter(input => input.available).length
  const toolStack = [
    { label: 'FLAML AutoML', detail: 'model selection / tuning' },
    { label: data.model?.best_estimator ?? 'XGBoost', detail: 'race-order baseline' },
    { label: 'SHAP', detail: 'driver-level feature attribution' },
    { label: 'SciPy / sklearn', detail: 'effect sizes, p-tests, permutation' },
    { label: 'Monte Carlo', detail: 'P1/P2/P3 uncertainty' },
  ]
  const stages = [
    {
      title: 'Historical Extraction',
      icon: Database,
      status: (data.model?.n_training_rows || data.model?.years?.length) ? 'accepted' : 'limited',
      metric: data.model?.scope === 'gp' ? `${data.model.gp_name ?? data.gp_name}` : `${data.model?.n_training_rows ?? 0} rows`,
      detail: `${data.model?.years?.length ? data.model.years.join(', ') : 'Legacy metadata'} training coverage`,
    },
    {
      title: 'Weekend Streams',
      icon: GitBranch,
      status: inputCount >= 2 ? 'accepted' : inputCount === 1 ? 'limited' : 'pending',
      metric: `${inputCount}/4 live streams`,
      detail: 'FP1 race sim, SQ, Sprint, and Q availability are tracked separately.',
    },
    {
      title: 'Validation Gate',
      icon: Sigma,
      status: validationAvailable ? 'accepted' : 'pending',
      metric: validationAvailable ? `${data.validation_report?.feature_tests?.length ?? 0} feature tests` : 'metadata pending',
      detail: validationAvailable ? 'Cohen d, p-values, Spearman, VIF, and permutation checks are available.' : 'Retrain v1.5 to publish statistical acceptance artifacts.',
    },
    {
      title: 'Podium Simulator',
      icon: Cpu,
      status: baselineAvailable ? 'accepted' : 'limited',
      metric: `${pct(data.model_baselines?.model_top3_accuracy)} top-3 hit`,
      detail: `Compared against grid baseline ${pct(data.model_baselines?.grid_top3_accuracy)} with Brier ${data.model_baselines?.podium_brier?.toFixed(3) ?? 'n/a'}.`,
    },
    {
      title: 'XAI Output',
      icon: FlaskConical,
      status: streamAvailable ? 'accepted' : 'pending',
      metric: streamAvailable ? `${data.predictions[0]?.feature_streams?.length ?? 0} streams` : 'SHAP pending',
      detail: 'Driver explanations are grouped into car pace, tyre/strategy, form, and circuit context.',
    },
  ] as const

  return (
    <div style={{ background: '#fff', border: '1px solid rgba(204,218,236,0.95)', borderRadius: '22px', padding: '18px', boxShadow: '0 16px 42px rgba(24,39,75,0.10)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', alignItems: 'flex-start', marginBottom: '16px', flexWrap: 'wrap' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', fontFamily: 'Inter, sans-serif', fontWeight: 900, color: '#14233C' }}>
            <GitBranch size={15} style={{ color: '#E8002D' }} />
            Model Reasoning Flow
          </div>
          <div style={{ fontSize: '11px', fontFamily: 'JetBrains Mono, monospace', color: '#7A8CA5', marginTop: '5px', lineHeight: 1.5 }}>
            Data streams are normalized, tested, simulated, then explained per driver.
          </div>
        </div>
        <div style={{ display: 'flex', gap: '7px', flexWrap: 'wrap', justifyContent: 'flex-end' }}>
          {toolStack.map(tool => (
            <div key={tool.label} title={tool.detail} style={{ border: '1px solid #D7E2F1', background: '#F8FAFC', borderRadius: '10px', padding: '7px 9px' }}>
              <div style={{ fontSize: '10px', fontFamily: 'JetBrains Mono, monospace', fontWeight: 800, color: '#14233C' }}>{tool.label}</div>
              <div style={{ fontSize: '9px', fontFamily: 'JetBrains Mono, monospace', color: '#7A8CA5', marginTop: '3px' }}>{tool.detail}</div>
            </div>
          ))}
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(5, minmax(0, 1fr))', gap: '10px', alignItems: 'stretch' }}>
        {stages.map((stage, idx) => {
          const Icon = stage.icon
          const tone = statusTone(stage.status)
          return (
            <div key={stage.title} style={{ position: 'relative', border: `1px solid ${tone.border}`, borderRadius: '16px', padding: '13px', background: tone.bg, minHeight: '158px' }}>
              {!isMobile && idx < stages.length - 1 && (
                <div style={{ position: 'absolute', right: '-11px', top: '50%', width: '12px', height: '2px', background: '#CBD5E1' }} />
              )}
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', alignItems: 'center', marginBottom: '12px' }}>
                <div style={{ width: '28px', height: '28px', borderRadius: '9px', background: '#fff', border: `1px solid ${tone.border}`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <Icon size={14} style={{ color: tone.text }} />
                </div>
                <StatusPill status={stage.status} />
              </div>
              <div style={{ fontSize: '12px', fontFamily: 'Inter, sans-serif', fontWeight: 900, color: '#14233C', marginBottom: '7px' }}>{stage.title}</div>
              <div style={{ fontSize: '11px', fontFamily: 'JetBrains Mono, monospace', color: tone.text, fontWeight: 800, marginBottom: '8px' }}>{stage.metric}</div>
              <div style={{ fontSize: '10px', fontFamily: 'Inter, sans-serif', color: '#56657C', lineHeight: 1.45 }}>{stage.detail}</div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function ValidationDeepDive({ data, isMobile }: { data: PredictionResponse; isMobile: boolean }) {
  const tests = data.validation_report?.feature_tests ?? []
  const vif = data.validation_report?.vif ?? []
  const permutation = data.validation_report?.permutation_importance ?? []
  const accepted = tests.filter(f => Math.abs(f.cohens_d ?? 0) >= 0.5 && (f.p_value == null || f.p_value <= 0.05)).length
  const limited = tests.filter(f => Math.abs(f.cohens_d ?? 0) > 0 && Math.abs(f.cohens_d ?? 0) < 0.5).length

  const columns = [
    {
      title: 'Effect Size Gate',
      subtitle: `${accepted} accepted · ${limited} weak`,
      rows: tests.slice(0, 6).map(f => ({
        label: f.feature,
        left: f.stream_label ?? 'feature',
        right: `d=${f.cohens_d ?? 'n/a'} · p=${f.p_value ?? 'n/a'}`,
        status: Math.abs(f.cohens_d ?? 0) >= 0.5 ? 'accepted' : 'limited',
      })),
      empty: 'Train v1.5 metadata to show Cohen d and p-values.',
    },
    {
      title: 'Collinearity Gate',
      subtitle: 'VIF pressure check',
      rows: vif.slice(0, 6).map(f => ({
        label: f.feature,
        left: 'VIF',
        right: `${f.vif ?? 'n/a'}`,
        status: (f.vif ?? 0) > 10 ? 'limited' : 'accepted',
      })),
      empty: 'VIF report pending.',
    },
    {
      title: 'Permutation Gate',
      subtitle: 'Does shuffling hurt?',
      rows: permutation.slice(0, 6).map(f => ({
        label: f.feature,
        left: f.stream_label ?? 'feature',
        right: `${f.importance ?? 'n/a'}`,
        status: (f.importance ?? 0) > 0 ? 'accepted' : 'limited',
      })),
      empty: 'Permutation importance pending.',
    },
  ] as const

  return (
    <div style={{ background: '#fff', border: '1px solid rgba(204,218,236,0.95)', borderRadius: '22px', padding: '18px', boxShadow: '0 16px 42px rgba(24,39,75,0.10)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', fontFamily: 'Inter, sans-serif', fontWeight: 900, color: '#14233C', marginBottom: '8px' }}>
        <BarChart3 size={15} style={{ color: '#E8002D' }} />
        Statistical Acceptance Report
      </div>
      <div style={{ fontSize: '11px', fontFamily: 'JetBrains Mono, monospace', color: '#64748B', lineHeight: 1.55, marginBottom: '14px' }}>
        {data.validation_report?.caveat ?? 'Acceptance metadata appears after v1.5 training. Legacy models can still predict, but cannot claim validation gates were accepted.'}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(3, minmax(0, 1fr))', gap: '12px' }}>
        {columns.map(column => (
          <div key={column.title} style={{ border: '1px solid #D7E2F1', borderRadius: '16px', overflow: 'hidden', background: '#F8FAFC' }}>
            <div style={{ padding: '12px', borderBottom: '1px solid #D7E2F1', background: '#fff' }}>
              <div style={{ fontSize: '12px', fontFamily: 'Inter, sans-serif', fontWeight: 900, color: '#14233C' }}>{column.title}</div>
              <div style={{ fontSize: '10px', fontFamily: 'JetBrains Mono, monospace', color: '#7A8CA5', marginTop: '4px' }}>{column.subtitle}</div>
            </div>
            <div style={{ padding: '10px 12px', display: 'grid', gap: '8px' }}>
              {column.rows.length ? column.rows.map(row => {
                const tone = statusTone(row.status as 'accepted' | 'limited')
                return (
                  <div key={`${column.title}-${row.label}`} style={{ display: 'grid', gap: '4px', paddingBottom: '8px', borderBottom: '1px solid #E2E8F0' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px' }}>
                      <span style={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: '11px', fontFamily: 'Inter, sans-serif', fontWeight: 800, color: '#334155' }}>{row.label}</span>
                      <span style={{ fontSize: '9px', fontFamily: 'JetBrains Mono, monospace', color: tone.text, fontWeight: 800 }}>{row.status}</span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', fontSize: '10px', fontFamily: 'JetBrains Mono, monospace', color: '#64748B' }}>
                      <span>{row.left}</span>
                      <span>{row.right}</span>
                    </div>
                  </div>
                )
              }) : (
                <div style={{ fontSize: '11px', color: '#94A3B8', lineHeight: 1.5 }}>{column.empty}</div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function PredictionsPage() {
  const [sessions, setSessions] = useState<QualiSession[]>([])
  const [selectedKey, setSelectedKey] = useState<number | null>(null)
  const [data, setData] = useState<PredictionResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [sessionsLoading, setSessionsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sessionError, setSessionError] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<number | null>(null)
  const [dropOpen, setDropOpen] = useState(false)
  const [showAllGrid, setShowAllGrid] = useState(false)
  const [isMobile, setIsMobile] = useState(false)

  useEffect(() => {
    const handleResize = () => setIsMobile(window.innerWidth < 1024)
    handleResize()
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [])

  // Load qualifying sessions for the selector
  useEffect(() => {
    setSessionsLoading(true)
    setSessionError(null)
    fetch(`${BASE}/api/v1/sessions`)
      .then(r => {
        if (!r.ok) throw new Error(`API returned ${r.status}`)
        return r.json()
      })
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      .then((all: any[]) => {
        const quali = all
          .filter(s => s.session_type === 'Q' || s.session_type === 'SQ')
          .sort((a, b) => new Date(b.date_start).getTime() - new Date(a.date_start).getTime())
          .map(s => ({ session_key: s.session_key, gp_name: s.gp_name, year: s.year, date_start: s.date_start }))
        setSessions(quali)
        if (quali.length) setSelectedKey(quali[0].session_key)
      })
      .catch(() => {
        setSessionError(`Backend API is not reachable at ${BASE}. Start the Flask backend, then refresh this page.`)
      })
      .finally(() => setSessionsLoading(false))
  }, [])

  // Fetch predictions when session changes
  useEffect(() => {
    if (!selectedKey) return
    setLoading(true)
    setError(null)
    setData(null)
    setShowAllGrid(false)
    setExpanded(null)
    fetch(`${BASE}/api/v1/sessions/${selectedKey}/predictions`)
      .then(r => {
        if (!r.ok) throw new Error(`API returned ${r.status}`)
        return r.json()
      })
      .then(d => {
        if (d.error) { setError(d.error); return }
        const sorted = {
          ...d,
          predictions: [...(d.predictions || [])].sort((a, b) => b.podium_probability - a.podium_probability)
        }
        setData(sorted)
      })
      .catch(() => setError('Failed to load predictions'))
      .finally(() => setLoading(false))
  }, [selectedKey])

  const selected = sessions.find(s => s.session_key === selectedKey)
  const maxPodium = data ? Math.max(...data.predictions.map(p => p.podium_probability)) : 1
  const modelLabel = data?.model?.scope === 'gp' ? 'GP-specific model' : 'Global fallback model'
  const modelName = data?.model?.best_estimator ?? 'AutoML'
  const coverageLabel = data?.model?.scope === 'gp'
    ? `${data.model?.gp_name ?? data?.gp_name ?? 'Circuit'} · ${(data.model?.years?.length ?? 0)} season${(data.model?.years?.length ?? 0) === 1 ? '' : 's'}`
    : `${data?.model?.n_training_rows ?? 0} training rows`
  const maeLabel = data?.model?.cv_mae_mean != null
    ? `${data.model.cv_mae_mean}${data.model.cv_mae_std != null ? ` ± ${data.model.cv_mae_std}` : ''} pos`
    : 'n/a'
  const visiblePredictions = data ? (showAllGrid ? data.predictions : data.predictions.slice(0, 10)) : []
  const topFactors = useMemo(() => {
    if (!data?.predictions.length) return []
    return [...(data.predictions[0].factors ?? [])]
      .sort((a, b) => Math.abs(b.shap_value) - Math.abs(a.shap_value))
      .slice(0, 5)
  }, [data])
  const topStreams = data?.predictions[0]?.feature_streams ?? []
  const validationFeatures = data?.validation_report?.feature_tests?.slice(0, 5) ?? []
  const permutationFeatures = data?.validation_report?.permutation_importance?.slice(0, 5) ?? []
  const weekendInputs = data?.weekend_inputs_used ? Object.entries(data.weekend_inputs_used) : []

  return (
    <div className="predictions-container" style={{ display: 'flex', flexDirection: 'column', gap: '18px', maxWidth: '980px', margin: '0 auto', padding: isMobile ? '0 12px 32px' : '0 0 48px' }}>

      {/* Header */}
      <section className="fade-up" style={{
        padding: '18px',
        position: 'relative',
        zIndex: 5,
        overflow: 'visible',
        borderRadius: '24px',
        background: 'linear-gradient(180deg, rgba(248,250,255,0.98) 0%, rgba(243,247,252,0.98) 100%)',
        border: '1px solid rgba(207,219,235,0.95)',
        boxShadow: '0 16px 42px rgba(24,39,75,0.10)',
      }}>
        <div className="predictions-page-header" style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '12px', marginBottom: '16px' }}>
          <div>
            <div style={{ fontSize: '10px', color: '#7A8CA5', fontFamily: 'Space Grotesk, sans-serif', fontWeight: 700, letterSpacing: '0.14em', marginBottom: '8px', textTransform: 'uppercase' }}>
              Prediction Lab
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '8px' }}>
              <div style={{ width: '38px', height: '38px', borderRadius: '12px', background: '#E8002D16', border: '1px solid #E8002D28', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Brain size={17} style={{ color: '#E8002D' }} />
              </div>
              <h1 className="page-title" style={{ fontSize: isMobile ? '2.2rem' : 'clamp(2rem, 4vw, 2.9rem)', margin: 0, color: '#14233C', lineHeight: 0.95 }}>
                Race Predictions
              </h1>
            </div>
            <p className="page-subtitle" style={{ fontFamily: 'Inter, sans-serif', fontSize: '14px', margin: 0, color: '#56657C', maxWidth: '600px', lineHeight: 1.55 }}>
              Qualifying-led race forecasts with projected podium, model analysis, and full-grid probability views.
            </p>
          </div>

          {sessions.length > 0 && (
            <div className="predictions-dropdown-container" style={{ position: 'relative', flexShrink: 0, zIndex: 20 }}>
              <button className="predictions-dropdown-button" onClick={() => setDropOpen(o => !o)} style={{ display: 'flex', alignItems: 'center', gap: '6px', background: 'rgba(255,255,255,0.92)', border: '1px solid rgba(204,218,236,0.92)', color: '#14233C', fontSize: '12px', padding: '11px 14px', borderRadius: '999px', cursor: 'pointer', fontFamily: 'JetBrains Mono, monospace', whiteSpace: 'nowrap', position: 'relative', zIndex: 21, boxShadow: '0 8px 24px rgba(24,39,75,0.08)' }}>
                {selected ? `${selected.gp_name.replace(' Grand Prix', '')} ${selected.year} Q` : 'Select session'}
                <ChevronDown size={12} style={{ transform: dropOpen ? 'rotate(180deg)' : 'none', transition: '0.15s' }} />
              </button>
              {dropOpen && (
                <div className="predictions-dropdown-menu" style={{ position: 'absolute', right: 0, top: 'calc(100% + 8px)', background: 'rgba(248,250,255,0.99)', border: '1px solid rgba(204,218,236,0.95)', borderRadius: '18px', overflow: 'hidden', zIndex: 999, minWidth: '240px', maxHeight: '320px', overflowY: 'auto', boxShadow: '0 20px 48px rgba(24,39,75,0.18)' }}>
                  {sessions.map(s => (
                    <button key={s.session_key} onClick={() => { setSelectedKey(s.session_key); setDropOpen(false) }} style={{ display: 'block', width: '100%', textAlign: 'left', padding: '11px 14px', fontSize: '12px', cursor: 'pointer', background: selectedKey === s.session_key ? 'rgba(232,0,45,0.06)' : 'transparent', color: selectedKey === s.session_key ? '#14233C' : '#56657C', fontFamily: 'JetBrains Mono, monospace', border: 'none', borderBottom: '1px solid rgba(204,218,236,0.7)' }}>
                      {s.gp_name.replace(' Grand Prix', '')} {s.year}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        <div style={{
          position: 'relative',
          minHeight: isMobile ? '160px' : '270px',
          borderRadius: '18px',
          overflow: 'hidden',
          background: '#0F172A',
          border: '1px solid rgba(204,218,236,0.7)',
          boxShadow: '0 14px 36px rgba(15,23,42,0.16)',
        }}>
          <div style={{
            position: 'absolute',
            inset: 0,
            backgroundImage: `linear-gradient(180deg, rgba(7,12,20,0.16) 0%, rgba(7,12,20,0.72) 82%), url(${HERO_IMAGE})`,
            backgroundSize: 'cover',
            backgroundPosition: 'center',
          }} />
        </div>
      </section>

      {/* Model disclaimer */}
      <div className="fade-up-delay-1" style={{ display: 'flex', gap: '8px', padding: '14px 16px', alignItems: 'flex-start', background: 'rgba(255,250,236,0.96)', border: '1px solid rgba(242, 200, 121, 0.22)', borderRadius: '18px', boxShadow: '0 10px 24px rgba(24,39,75,0.06)' }}>
        <AlertCircle size={13} style={{ color: '#FFD700', flexShrink: 0, marginTop: '1px' }} />
        <span style={{ fontSize: '11px', fontFamily: 'JetBrains Mono, monospace', color: '#6A7485', lineHeight: 1.6 }}>
          Podium probabilities blend qualifying pace, weekend race-sim signals, driver/team form, and circuit priors. Missing FP1/Sprint/Q streams are shown explicitly instead of being hidden.
        </span>
      </div>

      {/* Loading */}
      {loading && (
        <div className="panel-soft" style={{ textAlign: 'center', padding: '48px', color: '#5e7289', fontFamily: 'monospace', fontSize: '13px' }}>
          Running model...
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="panel-soft" style={{ padding: '16px', background: '#E8002D11', borderColor: '#E8002D33', fontSize: '12px', fontFamily: 'monospace', color: '#E8002D' }}>
          {error}
        </div>
      )}

      {sessionsLoading && !data && (
        <div className="panel-soft" style={{ textAlign: 'center', padding: '28px', color: '#5e7289', fontFamily: 'monospace', fontSize: '12px' }}>
          Loading available qualifying sessions...
        </div>
      )}

      {sessionError && (
        <div className="panel-soft" style={{ padding: '16px', background: '#E8002D11', borderColor: '#E8002D33', fontSize: '12px', fontFamily: 'monospace', color: '#E8002D', lineHeight: 1.6 }}>
          {sessionError}
        </div>
      )}

      {!sessionsLoading && !sessionError && sessions.length === 0 && (
        <div className="panel-soft" style={{ padding: '18px', background: '#fff', borderColor: 'rgba(204,218,236,0.95)', fontSize: '12px', fontFamily: 'JetBrains Mono, monospace', color: '#64748B', lineHeight: 1.65 }}>
          No qualifying or sprint qualifying sessions found in this database. Ingest a Q or SQ session, or point `NEXT_PUBLIC_API_URL` and `DATABASE_URL` at a populated environment.
        </div>
      )}

      {/* Predictions */}
      {!loading && data && (
        <>
          {/* Podium highlight */}
          <div className="fade-up-delay-1" style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div style={{
              background: 'linear-gradient(180deg, rgba(248,250,255,0.98) 0%, rgba(242,246,252,0.98) 100%)',
              border: '1px solid rgba(204,218,236,0.95)',
              borderRadius: '22px',
              padding: '18px',
              boxShadow: '0 16px 42px rgba(24,39,75,0.10)',
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', alignItems: 'baseline', marginBottom: '14px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Trophy size={14} style={{ color: '#E8002D' }} />
                  <div style={{ fontSize: '13px', fontFamily: 'Inter, sans-serif', fontWeight: 800, color: '#14233C' }}>Projected Podium</div>
                </div>
              </div>

              <div className="podium-grid" style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr 1fr', gap: '12px' }}>
                {data.predictions.slice(0, 3).map((p, i) => {
                  const colour = '#' + p.team_colour
                  const labels = ['P1', 'P2', 'P3']
                  return (
                    <div key={p.driver_number} className="podium-card interactive-card" style={{ borderTop: `3px solid ${colour}`, borderRadius: '16px', padding: '16px', textAlign: 'center', background: '#fff', boxShadow: '0 10px 26px rgba(24,39,75,0.06)' }}>
                      <div style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', minWidth: '42px', height: '34px', padding: '0 12px', borderRadius: '12px', border: `1px solid ${colour}88`, color: colour, fontSize: '12px', fontFamily: 'JetBrains Mono, monospace', fontWeight: 700, marginBottom: '12px' }}>{labels[i]}</div>
                      <div style={{ fontSize: '19px', fontFamily: 'Rajdhani, sans-serif', fontWeight: 700, color: '#14233C' }}>{p.abbreviation}</div>
                      <div style={{ fontSize: '11px', color: '#56657C', fontFamily: 'Inter, sans-serif', marginTop: '4px', fontWeight: 600 }}>{p.team_name.split(' ')[0]}</div>
                      <div style={{ marginTop: '10px', display: 'flex', flexDirection: 'column', gap: '3px' }}>
                        <div style={{ fontSize: '22px', fontFamily: 'Rajdhani, sans-serif', fontWeight: 700, color: '#E8002D' }}>{(p.podium_probability * 100).toFixed(1)}%</div>
                        <div style={{ fontSize: '9px', fontFamily: 'JetBrains Mono, monospace', color: '#7A8CA5' }}>podium probability</div>
                        <div style={{ fontSize: '9px', fontFamily: 'JetBrains Mono, monospace', color: '#94A3B8', marginTop: '4px' }}>
                          P1 {pct(p.p1_probability)} · P2 {pct(p.p2_probability)} · P3 {pct(p.p3_probability)}
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>

            <ProcessFlow data={data} isMobile={isMobile} />

            <div className="predictions-model-grid" style={{
              background: 'linear-gradient(180deg, rgba(248,250,255,0.98) 0%, rgba(242,246,252,0.98) 100%)',
              border: '1px solid rgba(204,218,236,0.95)',
              borderRadius: '22px',
              padding: '18px',
              boxShadow: '0 16px 42px rgba(24,39,75,0.10)',
              display: 'grid',
              gridTemplateColumns: isMobile ? '1fr' : '0.95fr 1.05fr',
              gap: '14px',
            }}>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', fontFamily: 'Inter, sans-serif', fontWeight: 800, color: '#14233C', marginBottom: '12px' }}>
                  <Brain size={14} style={{ color: '#E8002D' }} />
                  Model Architecture & Analysis
                </div>
                <div style={{ display: 'grid', gap: '10px' }}>
                  {[
                    { label: 'Core Engine', value: modelName },
                    { label: 'Scope', value: modelLabel },
                    { label: 'Coverage', value: coverageLabel },
                    { label: 'CV MAE', value: maeLabel },
                    { label: 'Top-3 hit', value: pct(data.model_baselines?.model_top3_accuracy) },
                    { label: 'Grid baseline', value: pct(data.model_baselines?.grid_top3_accuracy) },
                    { label: 'Podium Brier', value: data.model_baselines?.podium_brier?.toFixed(3) ?? 'n/a' },
                  ].map(({ label, value }) => (
                    <div key={label} style={{ padding: '10px 12px', borderRadius: '14px', background: '#fff', border: '1px solid rgba(204,218,236,0.84)' }}>
                      <div style={{ fontSize: '9px', fontFamily: 'JetBrains Mono, monospace', color: '#7A8CA5', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: '5px' }}>{label}</div>
                      <div style={{ fontSize: '13px', fontFamily: 'Inter, sans-serif', color: '#14233C', fontWeight: 700 }}>{value}</div>
                    </div>
                  ))}
                </div>
              </div>

              <div>
                <div style={{ fontSize: '12px', fontFamily: 'Inter, sans-serif', fontWeight: 800, color: '#14233C', marginBottom: '12px' }}>
                  Leading Driver Stream Attribution
                </div>
                <StreamBars streams={topStreams} />
                <div style={{ fontSize: '12px', fontFamily: 'Inter, sans-serif', fontWeight: 800, color: '#14233C', margin: '16px 0 12px' }}>
                  Top SHAP Factors
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '11px' }}>
                  {topFactors.length ? topFactors.map((factor, idx) => {
                    const width = Math.max(24, Math.min(100, Math.abs(factor.shap_value) * 100))
                    return (
                      <div key={`${factor.feature}-${idx}`}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', gap: '10px', marginBottom: '5px' }}>
                          <span style={{ fontSize: '11px', fontFamily: 'Inter, sans-serif', color: '#56657C', fontWeight: 600 }}>{factor.label}</span>
                          <span style={{ fontSize: '10px', fontFamily: 'JetBrains Mono, monospace', color: factor.positive ? '#10B981' : '#E8002D' }}>
                            {factor.positive ? '+' : ''}{factor.shap_value.toFixed(2)}
                          </span>
                        </div>
                        <div style={{ height: '7px', background: '#DCE6F5', borderRadius: '999px', overflow: 'hidden' }}>
                          <div style={{ width: `${width}%`, height: '100%', borderRadius: '999px', background: factor.positive ? '#E8002D' : '#94A3B8' }} />
                        </div>
                      </div>
                    )
                  }) : (
                    <div style={{ fontSize: '12px', color: '#7A8CA5', fontFamily: 'JetBrains Mono, monospace' }}>No factor data available.</div>
                  )}
                </div>
              </div>
            </div>
          </div>

          <ValidationDeepDive data={data} isMobile={isMobile} />

          <div className="fade-up-delay-2" style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '0.9fr 1.1fr', gap: '14px' }}>
            <div style={{ background: '#fff', border: '1px solid rgba(204,218,236,0.95)', borderRadius: '18px', padding: '16px', boxShadow: '0 12px 30px rgba(24,39,75,0.08)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', fontFamily: 'Inter, sans-serif', fontWeight: 800, color: '#14233C', marginBottom: '12px' }}>
                <Activity size={14} style={{ color: '#E8002D' }} />
                Weekend Inputs Used
              </div>
              <div style={{ display: 'grid', gap: '8px' }}>
                {weekendInputs.map(([key, input]) => (
                  <div key={key} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '10px', padding: '9px 10px', borderRadius: '12px', background: input.available ? '#ECFDF5' : '#F8FAFC', border: `1px solid ${input.available ? '#A7F3D0' : '#E2E8F0'}` }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', minWidth: 0 }}>
                      <CheckCircle2 size={13} style={{ color: input.available ? '#059669' : '#94A3B8', flexShrink: 0 }} />
                      <span style={{ fontSize: '11px', fontFamily: 'Inter, sans-serif', color: '#14233C', fontWeight: 700 }}>{key.replaceAll('_', ' ')}</span>
                    </div>
                    <span style={{ fontSize: '10px', fontFamily: 'JetBrains Mono, monospace', color: '#64748B', whiteSpace: 'nowrap' }}>
                      {input.session_type} · {input.lap_count} laps
                    </span>
                  </div>
                ))}
              </div>
            </div>

            <div style={{ background: '#fff', border: '1px solid rgba(204,218,236,0.95)', borderRadius: '18px', padding: '16px', boxShadow: '0 12px 30px rgba(24,39,75,0.08)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', fontFamily: 'Inter, sans-serif', fontWeight: 800, color: '#14233C', marginBottom: '12px' }}>
                <BarChart3 size={14} style={{ color: '#E8002D' }} />
                Statistical Validation
              </div>
              <div style={{ fontSize: '10px', fontFamily: 'JetBrains Mono, monospace', color: '#64748B', lineHeight: 1.55, marginBottom: '12px' }}>
                {data.validation_report?.caveat ?? 'Validation artifacts appear after training the v1.5 model.'}
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr', gap: '12px' }}>
                <div>
                  <div style={{ fontSize: '10px', fontFamily: 'JetBrains Mono, monospace', color: '#7A8CA5', marginBottom: '8px', textTransform: 'uppercase' }}>Podium separators</div>
                  {(validationFeatures.length ? validationFeatures : []).map(f => (
                    <div key={f.feature} style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', fontSize: '11px', padding: '6px 0', borderBottom: '1px solid #E2E8F0' }}>
                      <span style={{ color: '#334155', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{f.feature}</span>
                      <span style={{ color: '#0F172A', fontFamily: 'JetBrains Mono, monospace' }}>d={f.cohens_d ?? 'n/a'}</span>
                    </div>
                  ))}
                  {!validationFeatures.length && <div style={{ fontSize: '11px', color: '#94A3B8' }}>Train metadata not available.</div>}
                </div>
                <div>
                  <div style={{ fontSize: '10px', fontFamily: 'JetBrains Mono, monospace', color: '#7A8CA5', marginBottom: '8px', textTransform: 'uppercase' }}>Permutation importance</div>
                  {(permutationFeatures.length ? permutationFeatures : []).map(f => (
                    <div key={f.feature} style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', fontSize: '11px', padding: '6px 0', borderBottom: '1px solid #E2E8F0' }}>
                      <span style={{ color: '#334155', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{f.feature}</span>
                      <span style={{ color: '#0F172A', fontFamily: 'JetBrains Mono, monospace' }}>{f.importance ?? 'n/a'}</span>
                    </div>
                  ))}
                  {!permutationFeatures.length && <div style={{ fontSize: '11px', color: '#94A3B8' }}>Run v1.5 training to populate.</div>}
                </div>
              </div>
            </div>
          </div>

          {/* Full grid */}
          <div className="fade-up-delay-2" style={{ borderRadius: '24px', overflow: 'hidden', background: 'linear-gradient(180deg, rgba(248,250,255,0.98) 0%, rgba(242,246,252,0.98) 100%)', border: '1px solid rgba(204,218,236,0.95)', boxShadow: '0 18px 46px rgba(24,39,75,0.10)' }}>
            {/* Column headers */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', padding: '18px 18px 10px', gap: '12px', flexWrap: 'wrap' }}>
              <div>
                <div style={{ fontSize: '13px', fontFamily: 'Inter, sans-serif', fontWeight: 800, color: '#14233C' }}>Full Grid Probabilities</div>
                <div style={{ fontSize: '11px', fontFamily: 'JetBrains Mono, monospace', color: '#7A8CA5', marginTop: '4px' }}>Podium-first probabilities with P1/P2/P3 uncertainty across the grid</div>
              </div>
            </div>
            <div className="predictions-header" style={{ display: 'grid', gridTemplateColumns: isMobile ? '32px 28px 1fr 48px' : '32px 28px 1fr 100px 110px 110px', gap: '8px', padding: '10px 16px', fontSize: '9px', color: '#7A8CA5', fontFamily: 'JetBrains Mono, monospace', letterSpacing: '0.1em', borderTop: '1px solid rgba(204,218,236,0.8)', borderBottom: '1px solid rgba(204,218,236,0.8)', background: 'rgba(255,255,255,0.76)' }}>
              <span>PRED</span><span>GRID</span><span>DRIVER</span><span>{isMobile ? 'POD' : 'PODIUM %'}</span>{!isMobile && <span>WIN %</span>}{!isMobile && <span>PROBABILITY</span>}
            </div>

            {visiblePredictions.map((p, i) => {
              const colour = '#' + p.team_colour
              const isExpand = expanded === p.driver_number
              const gridDiff = p.grid_position - (i + 1)  // positive = predicted better than grid

              return (
                <div key={p.driver_number}>
                  <div
                    onClick={() => setExpanded(isExpand ? null : p.driver_number)}
                    className="predictions-row"
                    style={{ display: 'grid', gridTemplateColumns: isMobile ? '32px 28px 1fr 48px' : '32px 28px 1fr 100px 110px 110px', gap: '8px', padding: '11px 16px', borderBottom: '1px solid rgba(204,218,236,0.7)', alignItems: 'center', cursor: 'pointer', transition: 'background 0.1s', background: isExpand ? 'rgba(232,0,45,0.045)' : 'transparent' }}
                    onMouseEnter={e => { if (!isExpand) e.currentTarget.style.background = 'rgba(20,35,60,0.025)' }}
                    onMouseLeave={e => { if (!isExpand) e.currentTarget.style.background = 'transparent' }}
                  >
                    {/* Predicted position */}
                    <PositionBadge pos={i + 1} />

                    {/* Grid position + delta */}
                    <div style={{ textAlign: 'center' }}>
                      <div style={{ fontSize: '11px', fontFamily: 'monospace', color: '#6A7485' }}>P{p.grid_position}</div>
                      {gridDiff !== 0 && (
                        <div style={{ fontSize: '8px', fontFamily: 'monospace', color: gridDiff > 0 ? '#2CF4C5' : '#E8002D' }}>
                          {gridDiff > 0 ? `+${gridDiff}` : gridDiff}
                        </div>
                      )}
                    </div>

                    {/* Driver */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', minWidth: 0 }}>
                      <div style={{ width: '3px', height: '20px', borderRadius: '2px', background: colour, flexShrink: 0 }} />
                      <div style={{ minWidth: 0 }}>
                        <div style={{ fontSize: '13px', fontFamily: 'monospace', fontWeight: 700, color: colour }}>{p.abbreviation}</div>
                        <div style={{ fontSize: '9px', color: '#6A7485', fontFamily: 'monospace', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{p.team_name}</div>
                      </div>
                    </div>

                    {/* Podium % (Mobile: just number) */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      {!isMobile && <ProbBar value={p.podium_probability} colour={p.team_colour} max={maxPodium} />}
                      <span style={{ fontSize: '11px', fontFamily: 'monospace', color: '#14233C', width: isMobile ? 'auto' : '32px', textAlign: 'right', flexShrink: 0, fontWeight: 700 }}>
                        {(p.podium_probability * 100).toFixed(0)}%
                      </span>
                    </div>

                    {/* Win % */}
                    <div className="predictions-hide-mobile" style={{ fontSize: '12px', fontFamily: 'monospace', color: p.podium_probability > 0.5 ? '#10B981' : '#6A7485', textAlign: 'center' }}>
                      {(p.win_probability * 100).toFixed(0)}%
                    </div>

                    {/* Mini position probability bars */}
                    <div className="predictions-hide-mobile" style={{ display: 'flex', gap: '1px', alignItems: 'flex-end', height: '20px' }}>
                      {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map(pos => {
                        const prob = p.position_probabilities[String(pos)] ?? 0
                        const h = Math.max(2, prob * 100)
                        return (
                          <div key={pos} style={{ flex: 1, height: `${h}%`, background: pos <= 3 ? colour + 'CC' : colour + '44', borderRadius: '1px', minHeight: '2px' }} />
                        )
                      })}
                    </div>
                  </div>

                  {/* Expanded SHAP factors */}
                  {isExpand && p.factors.length > 0 && (
                    <div style={{ padding: '12px 16px 16px', background: 'rgba(244,247,252,0.95)', borderBottom: '1px solid rgba(204,218,236,0.7)' }}>
                      <div style={{ fontSize: '9px', fontFamily: 'monospace', color: '#7A8CA5', letterSpacing: '0.1em', marginBottom: '8px' }}>
                        FEATURE STREAMS — XAI attribution
                      </div>
                      <StreamBars streams={p.feature_streams} />
                      <div style={{ fontSize: '9px', fontFamily: 'monospace', color: '#7A8CA5', letterSpacing: '0.1em', margin: '12px 0 8px' }}>
                        KEY FACTORS — SHAP explanation
                      </div>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
                        {p.factors.slice(0, 3).map((f, fi) => (
                          <div key={fi} style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <div style={{ width: '16px', height: '16px', borderRadius: '4px', background: f.positive ? '#2CF4C522' : '#E8002D22', border: `1px solid ${f.positive ? '#2CF4C544' : '#E8002D44'}`, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                              <TrendingUp size={9} style={{ color: f.positive ? '#2CF4C5' : '#E8002D', transform: f.positive ? 'none' : 'scaleY(-1)' }} />
                            </div>
                            <span style={{ fontSize: '11px', fontFamily: 'monospace', color: '#56657C' }}>
                              {f.stream_label ? `${f.stream_label}: ` : ''}{f.label}
                            </span>
                            <span style={{ marginLeft: 'auto', fontSize: '10px', fontFamily: 'monospace', color: '#14233C' }}>
                              {f.shap_value > 0 ? '+' : ''}{f.shap_value.toFixed(2)}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )
            })}

            {data.predictions.length > 10 && (
              <div style={{ display: 'flex', justifyContent: 'center', padding: '16px 18px 18px', background: 'rgba(255,255,255,0.58)', borderTop: '1px solid rgba(204,218,236,0.65)' }}>
                <button
                  onClick={() => setShowAllGrid(v => !v)}
                  style={{
                    border: '1px solid rgba(204,218,236,0.95)',
                    background: '#fff',
                    color: '#14233C',
                    borderRadius: '999px',
                    padding: '10px 16px',
                    fontSize: '12px',
                    fontFamily: 'JetBrains Mono, monospace',
                    fontWeight: 600,
                    cursor: 'pointer',
                    boxShadow: '0 10px 26px rgba(24,39,75,0.08)',
                  }}
                >
                  {showAllGrid ? 'Show top 10' : `+ Show ${data.predictions.length - 10} more`}
                </button>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}
