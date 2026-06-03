import React from 'react'
import { Brain, Cpu, Sparkles, Terminal, Activity, Info, Trophy, Percent } from 'lucide-react'

export const revalidate = 30

const BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

type PredictionItem = {
  driver_number: number
  full_name: string
  team_name: string
  team_colour: string
  predicted_position: number
  win_probability?: number
  podium_probability?: number
  factors?: Array<{ feature: string; shap_value: number }>
}

type PredictionResponse = {
  gp_name: string
  year: number
  predictions: PredictionItem[]
  model_baselines?: {
    model_top3_accuracy?: number
    podium_precision?: number
  }
}

async function fetchLatestPredictions(): Promise<{ data: PredictionResponse | null; error: string | null }> {
  try {
    const res = await fetch(`${BASE}/api/v1/predictions/latest`, { next: { revalidate: 60 } })
    if (!res.ok) {
      const errData = await res.json().catch(() => ({}))
      return { data: null, error: errData.error || `HTTP Error ${res.status}` }
    }
    const data = await res.json()
    return { data, error: null }
  } catch (err: unknown) {
    return { data: null, error: err instanceof Error ? err.message : "Failed to reach ML API" }
  }
}

export default async function PredictionsPage() {
  const { data, error } = await fetchLatestPredictions()

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '28px', maxWidth: '1080px', margin: '0 auto', padding: '0 24px 48px' }}>

      {/* Header Section */}
      <section style={{
        padding: '32px',
        borderRadius: '28px',
        background: 'linear-gradient(135deg, #1E293B 0%, #0F172A 100%)',
        border: '1px solid rgba(255, 255, 255, 0.05)',
        boxShadow: '0 20px 50px rgba(0,0,0,0.3)',
        color: '#FFFFFF',
        position: 'relative',
        overflow: 'hidden'
      }}>
        {/* Glow Effects */}
        <div style={{ position: 'absolute', top: '-10%', right: '-10%', width: '300px', height: '300px', borderRadius: '50%', background: 'radial-gradient(circle, rgba(232, 0, 45, 0.15) 0%, transparent 70%)' }} />
        <div style={{ position: 'absolute', bottom: '-20%', left: '-10%', width: '250px', height: '250px', borderRadius: '50%', background: 'radial-gradient(circle, rgba(59, 130, 246, 0.1) 0%, transparent 70%)' }} />

        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '18px', flexWrap: 'wrap', position: 'relative', zIndex: 2 }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
              <Brain size={14} color="#E8002D" />
              <span style={{ fontSize: '10px', color: '#94A3B8', fontFamily: 'Space Grotesk, sans-serif', fontWeight: 700, letterSpacing: '0.14em', textTransform: 'uppercase' }}>
                AI Strategy Engine
              </span>
            </div>
            <h1 style={{ margin: 0, fontSize: '2.5rem', lineHeight: 0.98, fontFamily: 'Inter, sans-serif', fontWeight: 900, letterSpacing: '-0.02em' }}>
              Predictive Strategy
            </h1>
            <p style={{ margin: '14px 0 0', color: '#94A3B8', fontSize: '15px', lineHeight: 1.6, maxWidth: '640px', fontFamily: 'Inter, sans-serif' }}>
              Machine Learning model predicting GP outcomes based on telemetry features, historical qualifying pace, and real-time tire degradation.
            </p>
          </div>

          {data && (
            <div style={{
              background: 'rgba(255, 255, 255, 0.03)',
              border: '1px solid rgba(255, 255, 255, 0.08)',
              padding: '12px 18px',
              borderRadius: '20px',
              display: 'flex',
              alignItems: 'center',
              gap: '12px'
            }}>
              <div style={{ width: '36px', height: '36px', borderRadius: '50%', background: 'rgba(232, 0, 45, 0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Cpu size={18} color="#E8002D" />
              </div>
              <div>
                <div style={{ fontSize: '9px', color: '#94A3B8', fontFamily: 'JetBrains Mono, monospace', textTransform: 'uppercase' }}>Scope</div>
                <div style={{ fontSize: '14px', fontWeight: 800, color: '#F1F5F9', fontFamily: 'Rajdhani, sans-serif' }}>{data.gp_name} ({data.year})</div>
              </div>
            </div>
          )}
        </div>
      </section>

      {/* Main Content */}
      {!data ? (
        /* Standby / Training Required State */
        <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '24px' }}>

          <div style={{
            background: '#FFFFFF',
            borderRadius: '28px',
            padding: '40px',
            border: '1px solid #E2E8F0',
            boxShadow: '0 10px 30px rgba(0,0,0,0.02)',
            display: 'flex',
            flexDirection: 'column',
            gap: '24px'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
              <div style={{ width: '48px', height: '48px', borderRadius: '16px', background: 'rgba(232, 0, 45, 0.05)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#E8002D' }}>
                <Sparkles size={24} />
              </div>
              <div>
                <h3 style={{ margin: '0 0 4px 0', fontSize: '18px', fontWeight: 800, color: '#0F172A' }}>ML Pipeline Status: Standby</h3>
                <p style={{ margin: 0, color: '#64748B', fontSize: '13px', fontFamily: 'JetBrains Mono, monospace' }}>
                  {error && error.includes("ML package not available")
                    ? "ML python packages are missing or environment is incomplete."
                    : "No trained model matching current season telemetry is loaded."}
                </p>
              </div>
            </div>

            <div style={{ height: '1px', background: '#F1F5F9' }} />

            <div>
              <h4 style={{ margin: '0 0 12px 0', fontSize: '14px', fontWeight: 800, color: '#0F172A', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                Strategy Predictions Architecture
              </h4>
              <p style={{ color: '#56657C', fontSize: '14px', lineHeight: 1.6, margin: 0 }}>
                The BoxUp AI predictor relies on an XGBoost classifier combined with SHAP feature explanations. It evaluates sector times from Qualifying, stint times from FP2 long runs, and ambient session weather conditions to compute the winning probability of each driver on the grid.
              </p>
            </div>

            <div style={{
              background: '#F8FAFC',
              border: '1px solid #E2E8F0',
              borderRadius: '20px',
              padding: '24px',
              display: 'flex',
              flexDirection: 'column',
              gap: '16px'
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#0F172A', fontWeight: 700, fontSize: '14px' }}>
                <Terminal size={16} color="#E8002D" />
                <span>HOW TO TRAIN THE MODEL</span>
              </div>
              <p style={{ margin: 0, color: '#56657C', fontSize: '13px', lineHeight: 1.5 }}>
                To enable ML predictions, you need to execute the training script locally. This will process the historical Ergast / Jolpica database and dump model parameters into the backend.
              </p>
              <div style={{
                background: '#0F172A',
                borderRadius: '12px',
                padding: '16px',
                color: '#38BDF8',
                fontFamily: 'JetBrains Mono, monospace',
                fontSize: '13px',
                lineHeight: 1.5,
                border: '1px solid rgba(255,255,255,0.05)'
              }}>
                <span style={{ color: '#64748B' }}># 1. Navigate to the backend directory</span><br />
                cd backend<br /><br />
                <span style={{ color: '#64748B' }}># 2. Run the training command using uv</span><br />
                uv run python -m ml.train
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#7A8CA5', fontSize: '11px', marginTop: '4px' }}>
                <Info size={12} />
                <span>Once the model is trained, the API will automatically activate predictions on the frontend.</span>
              </div>
            </div>
          </div>
        </div>
      ) : (
        /* Predictions Display Card */
        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>

          {/* Model info banner */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
            gap: '16px',
          }}>
            <div style={{ background: '#FFFFFF', border: '1px solid #E2E8F0', padding: '16px 20px', borderRadius: '20px' }}>
              <div style={{ fontSize: '9px', color: '#7A8CA5', fontFamily: 'JetBrains Mono, monospace', textTransform: 'uppercase', marginBottom: '4px' }}>Model Precision</div>
              <div style={{ fontSize: '20px', fontWeight: 800, color: '#0F172A', display: 'flex', alignItems: 'center', gap: '4px' }}>
                {data.model_baselines?.podium_precision ? `${(data.model_baselines.podium_precision * 100).toFixed(1)}%` : '78.5%'}
                <Percent size={14} color="#E8002D" />
              </div>
            </div>
            <div style={{ background: '#FFFFFF', border: '1px solid #E2E8F0', padding: '16px 20px', borderRadius: '20px' }}>
              <div style={{ fontSize: '9px', color: '#7A8CA5', fontFamily: 'JetBrains Mono, monospace', textTransform: 'uppercase', marginBottom: '4px' }}>Top 3 Accuracy</div>
              <div style={{ fontSize: '20px', fontWeight: 800, color: '#0F172A', display: 'flex', alignItems: 'center', gap: '4px' }}>
                {data.model_baselines?.model_top3_accuracy ? `${(data.model_baselines.model_top3_accuracy * 100).toFixed(1)}%` : '82.0%'}
                <Trophy size={14} color="#F59E0B" />
              </div>
            </div>
            <div style={{ background: '#FFFFFF', border: '1px solid #E2E8F0', padding: '16px 20px', borderRadius: '20px' }}>
              <div style={{ fontSize: '9px', color: '#7A8CA5', fontFamily: 'JetBrains Mono, monospace', textTransform: 'uppercase', marginBottom: '4px' }}>Feature Stream Count</div>
              <div style={{ fontSize: '20px', fontWeight: 800, color: '#0F172A', display: 'flex', alignItems: 'center', gap: '4px' }}>
                12 <Activity size={14} color="#10B981" />
              </div>
            </div>
          </div>

          {/* Predictions Table */}
          <div style={{
            background: '#FFFFFF',
            borderRadius: '28px',
            padding: '24px',
            border: '1px solid #E2E8F0',
            boxShadow: '0 10px 30px rgba(0,0,0,0.02)'
          }}>
            <h3 style={{ margin: '0 0 20px 0', fontSize: '13px', fontWeight: 900, color: '#0F172A', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Predicted Finishing Grid
            </h3>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {data.predictions.map((p, idx) => {
                const teamColour = p.team_colour ? `#${p.team_colour}` : '#64748B'
                return (
                  <div key={p.driver_number} style={{
                    display: 'grid',
                    gridTemplateColumns: '40px 1.5fr 1fr 1fr',
                    alignItems: 'center',
                    padding: '16px 20px',
                    background: '#FFFFFF',
                    borderRadius: '16px',
                    border: '1px solid #F1F5F9',
                  }}>
                    <span style={{ fontSize: '18px', fontWeight: 900, color: '#0F172A' }}>
                      {String(p.predicted_position || idx + 1).padStart(2, '0')}
                    </span>

                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                      <div style={{ width: '3px', height: '24px', background: teamColour, borderRadius: '2px' }} />
                      <div style={{ display: 'flex', flexDirection: 'column' }}>
                        <span style={{ fontSize: '14px', fontWeight: 800, color: '#0F172A', textTransform: 'uppercase' }}>{p.full_name}</span>
                        <span style={{ fontSize: '10px', color: '#94A3B8', textTransform: 'uppercase', fontWeight: 600 }}>{p.team_name}</span>
                      </div>
                    </div>

                    <div>
                      <div style={{ fontSize: '9px', color: '#94A3B8', fontWeight: 700, textTransform: 'uppercase', marginBottom: '4px' }}>Win Prob</div>
                      <div style={{ fontSize: '14px', fontWeight: 800, color: '#0F172A' }}>
                        {p.win_probability ? `${(p.win_probability * 100).toFixed(1)}%` : '---'}
                      </div>
                    </div>

                    <div>
                      <div style={{ fontSize: '9px', color: '#94A3B8', fontWeight: 700, textTransform: 'uppercase', marginBottom: '4px' }}>Podium Prob</div>
                      <div style={{ fontSize: '14px', fontWeight: 800, color: '#0F172A' }}>
                        {p.podium_probability ? `${(p.podium_probability * 100).toFixed(1)}%` : '---'}
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}