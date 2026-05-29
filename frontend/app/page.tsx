'use client'

import Link from 'next/link'
import { Zap, Brain, Globe, Activity } from 'lucide-react'
import Hero from '@/components/home/Hero'

export default function LandingPage() {
  return (
    <div style={{ background: '#FAFAFA', overflowX: 'hidden', width: '100%' }}>

      {/*  HERO SECTION ─────────────────────────────────────────────────── */}
      <Hero />

      {/* ── FEATURES SECTION ─────────────────────────────────────────────── */}
      <section style={{ padding: '120px 5vw', width: '100%', background: '#F4F6F8', borderTop: '1px solid #E2E8F0' }}>

        {/* Section header */}
        <div style={{ marginBottom: 64, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', flexWrap: 'wrap', gap: 24 }}>
          <div style={{ maxWidth: 500 }}>
            <h2 style={{
              fontFamily: 'Inter, sans-serif',
              fontWeight: 900,
              fontSize: 'clamp(2rem, 4vw, 2.8rem)',
              letterSpacing: '-0.04em',
              color: '#0F172A',
              lineHeight: 1.1,
              marginBottom: 16,
              textTransform: 'uppercase',
            }}>
              TECHNICAL MASTERY
            </h2>
            <p style={{
              fontFamily: 'Inter, sans-serif',
              fontSize: 16, color: '#64748B', lineHeight: 1.6,
            }}>
              Strip away the drag from your decision-making process with high-fidelity telemetry architecture.
            </p>
          </div>
        </div>

        {/* Feature grid */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(12, 1fr)',
          gap: 16,
        }}>

          {/* TELEMETRY — large, spans 8 cols */}
          <div style={{
            gridColumn: 'span 8',
            background: '#FAFAFA',
            borderRadius: 24,
            overflow: 'hidden',
            display: 'flex',
            minHeight: 460,
            boxShadow: '0 4px 20px rgba(0,0,0,0.03)',
          }}>
            <div style={{ padding: 48, flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
                <Activity size={18} color="#E8002D" />
                <span style={{
                  fontFamily: 'Space Grotesk, sans-serif', fontSize: 11,
                  fontWeight: 800, letterSpacing: '0.12em', color: '#E8002D', textTransform: 'uppercase',
                }}>Telemetry</span>
              </div>
              <p style={{ fontFamily: 'Inter, sans-serif', fontSize: 15, color: '#64748B', lineHeight: 1.6, maxWidth: 320, marginBottom: 24 }}>
                Distributed data streaming via Apache Kafka. Processed with sub-millisecond latency for instant technical insight from over 300 sensors.
              </p>
              <div style={{ display: 'flex', gap: 8 }}>
                {['KAFKA-DRIVEN', '2.4GB/S', 'DIST-ALIGNED'].map(t => (
                  <span key={t} style={{
                    fontFamily: 'Space Grotesk, sans-serif', fontSize: 10,
                    padding: '6px 12px', borderRadius: 4,
                    background: '#F8FAFC', color: '#0F172A', fontWeight: 700,
                    border: '1px solid #E2E8F0',
                  }}>{t}</span>
                ))}
              </div>
            </div>
            <div style={{ flex: 1, position: 'relative', background: '#0F172A' }}>
              <div style={{
                position: 'absolute', inset: 0,
                backgroundImage: `url('https://images.unsplash.com/photo-1522519972666-d8677d9d3e67?q=80&w=988&auto=format&fit=crop&ixlib=rb-4.1.0&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D')`,
                backgroundSize: 'cover',
                backgroundPosition: 'center',
                opacity: 0.6,
              }} />
              <div style={{
                position: 'absolute', inset: 0,
                background: 'linear-gradient(90deg, #FFFFFF 0%, rgba(255, 255, 255, 0) 40%)',
              }} />
            </div>
          </div>

          {/* STRATEGY — 4 cols */}
          <div style={{
            gridColumn: 'span 4',
            background: '#FFFFFF',
            borderRadius: 24,
            padding: 48,
            display: 'flex', flexDirection: 'column',
            boxShadow: '0 4px 20px rgba(0,0,0,0.03)',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
              <Zap size={18} color="#E8002D" />
              <span style={{
                fontFamily: 'Space Grotesk, sans-serif', fontSize: 11,
                fontWeight: 800, letterSpacing: '0.12em', color: '#E8002D', textTransform: 'uppercase',
              }}>Strategy</span>
            </div>
            <p style={{ fontFamily: 'Inter, sans-serif', fontSize: 15, color: '#64748B', lineHeight: 1.6, marginBottom: 32 }}>
              Monte Carlo simulations running on TimescaleDB hypertables to provide optimal pit-stop windows and compound degradation models.
            </p>
            <div style={{ marginTop: 'auto', display: 'flex', alignItems: 'flex-end', gap: 6, height: 100 }}>
              {[40, 60, 100, 80, 50].map((h, i) => (
                <div key={i} style={{ flex: 1, height: `${h}%`, background: h === 100 ? '#E8002D' : '#FEE2E7', borderRadius: 4 }} />
              ))}
            </div>
          </div>

          {/* PREDICTIONS — 4 cols */}
          <div style={{
            gridColumn: 'span 4',
            background: '#FFFFFF',
            borderRadius: 24,
            padding: 40,
            minHeight: 240,
            boxShadow: '0 4px 20px rgba(0,0,0,0.03)',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
              <Brain size={18} color="#E8002D" />
              <span style={{
                fontFamily: 'Space Grotesk, sans-serif', fontSize: 11,
                fontWeight: 800, letterSpacing: '0.12em', color: '#E8002D', textTransform: 'uppercase',
              }}>AutoML Inference</span>
            </div>
            <p style={{ fontFamily: 'Inter, sans-serif', fontSize: 15, color: '#64748B', lineHeight: 1.6 }}>
              Neural networks and FLAML ensembles trained on 70 years of race data to predict overtaking probability and engine fatigue with SHAP interpretability.
            </p>
          </div>

          {/* GLOBAL SYNC — 8 cols, dark */}
          <div className="landing-global-sync" style={{
            gridColumn: 'span 8',
            background: '#0F172A',
            borderRadius: 24,
            padding: 48,
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            minHeight: 240,
          }}>
            <div style={{ maxWidth: 400 }}>
              <h3 style={{
                fontFamily: 'Inter, sans-serif', fontSize: 18, fontWeight: 800,
                color: '#FFFFFF', marginBottom: 12, textTransform: 'uppercase',
              }}>Ingestion Pipeline</h3>
              <p style={{ fontFamily: 'Inter, sans-serif', fontSize: 15, color: '#94A3B8', lineHeight: 1.6 }}>
                Automated data ingestion from FastF1, OpenF1, and Jolpica. Zero-config synchronization between the track and your local archive.
              </p>
            </div>
            <div className="landing-global-sync-right" style={{ textAlign: 'right' }}>
              <div style={{
                fontFamily: 'Inter, sans-serif', fontWeight: 900,
                fontSize: 56, color: '#10B981',
                letterSpacing: '-0.04em', lineHeight: 1,
              }}>
                99.9%
              </div>
              <div style={{
                fontFamily: 'Space Grotesk, sans-serif', fontSize: 10,
                fontWeight: 700, color: '#10B981', opacity: 0.8,
                letterSpacing: '0.15em', textTransform: 'uppercase', marginTop: 8,
              }}>
                Ingestion Accuracy
              </div>
            </div>
          </div>

        </div>
      </section>

      {/* ── COMMUNITY & CONTRIBUTION ─────────────────────────────────────────── */}
      <section style={{ padding: '120px 5vw', textAlign: 'center', background: '#FFFFFF' }}>
        <div style={{ maxWidth: 800, margin: '0 auto' }}>
          <h2 style={{
            fontFamily: 'Inter, sans-serif', fontWeight: 900,
            fontSize: 'clamp(2rem, 4vw, 3rem)',
            letterSpacing: '-0.05em', color: '#0F172A',
            lineHeight: 1.1, marginBottom: 24,
            textTransform: 'uppercase',
          }}>
            Built by the community,<br />for the community.
          </h2>
          <p style={{
            fontFamily: 'Inter, sans-serif', fontSize: 18,
            color: '#64748B', lineHeight: 1.6, marginBottom: 48,
            maxWidth: 600, margin: '0 auto 48px'
          }}>
            Formula 1 is 100% open-source. Join 1,200+ engineers and F1 fans building the future of accessible motorsport analytics.
          </p>
          <div style={{ display: 'flex', gap: 16, justifyContent: 'center', flexWrap: 'wrap' }}>
            <Link href="https://github.com/SheerWill007/Formula-I" target="_blank" style={{
              display: 'inline-flex', alignItems: 'center', gap: 12,
              padding: '16px 36px',
              background: '#0F172A', color: '#fff',
              fontFamily: 'Inter, sans-serif', fontSize: 14, fontWeight: 800,
              borderRadius: 12, textDecoration: 'none',
              textTransform: 'uppercase', letterSpacing: '0.05em',
              transition: 'transform 0.2s ease',
            }} onMouseEnter={e => e.currentTarget.style.transform = 'translateY(-2px)'} onMouseLeave={e => e.currentTarget.style.transform = 'translateY(0)'}>
              <Globe size={18} /> View Code on GitHub
            </Link>
          </div>
        </div>
      </section>

      {/* ── FOOTER ───────────────────────────────────────────────────────── */}
      <footer style={{
        background: '#F4F6F8',
        borderTop: '1px solid #E2E8F0',
        padding: '60px 5vw 40px',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 40,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{
            fontFamily: 'Inter, sans-serif', fontWeight: 900, fontSize: 18,
            color: '#0F172A', letterSpacing: '-0.04em', textTransform: 'uppercase', fontStyle: 'italic',
          }}>
            Formula 1
          </span>
        </div>
        <div style={{ display: 'flex', gap: 40, flexWrap: 'wrap', justifyContent: 'center' }}>
          {['LATEST WEEKEND', 'TELEMETRY', 'SESSIONS', 'PREDICTIONS', 'GITHUB'].map(l => {
            const href = l === 'GITHUB'
              ? 'https://github.com/SheerWill007/Formula-I'
              : l === 'LATEST WEEKEND'
                ? '/sessions/latest'
                : `/${l.toLowerCase()}`
            return (
              <Link key={l} href={href} target={l === 'GITHUB' ? '_blank' : undefined} style={{
                fontFamily: 'Inter, sans-serif', fontSize: 12, fontWeight: 700,
                color: '#94A3B8', textDecoration: 'none', letterSpacing: '0.05em',
              }}>{l}</Link>
            )
          })}
        </div>
        <div style={{ fontFamily: 'Inter, sans-serif', fontSize: 12, color: '#CBD5E1', fontWeight: 500 }}>
          © 2026 FORMULA 1  · APACHE 2.0
        </div>
      </footer>

      {/* Mobile responsiveness & Hover effects */}
      <style>{`
        .play-btn:hover { transform: scale(1.1); }
        @media (max-width: 1024px) {
          [style*="span 8"], [style*="span 4"] {
            grid-column: span 12 !important;
          }
        }
        @media (max-width: 768px) {
          .landing-global-sync {
            flex-direction: column !important;
            align-items: flex-start !important;
            gap: 32px;
            padding: 32px 24px !important;
          }
          .landing-global-sync-right {
            text-align: left !important;
          }
        }
      `}</style>
    </div>
  )
}
