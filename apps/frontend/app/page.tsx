'use client'

import Link from 'next/link'
import { useEffect, useRef, useState } from 'react'
import { Zap, Brain, Globe, Activity, Play } from 'lucide-react'

function LandingHeroMedia() {
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const [shouldRenderVideo, setShouldRenderVideo] = useState(true)

  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
    const syncMotionPreference = () => setShouldRenderVideo(!mediaQuery.matches)
    syncMotionPreference()
    mediaQuery.addEventListener('change', syncMotionPreference)
    return () => mediaQuery.removeEventListener('change', syncMotionPreference)
  }, [])

  useEffect(() => {
    const video = videoRef.current
    if (!video || !shouldRenderVideo) return
    void video.play().catch(() => {})
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry?.isIntersecting) { void video.play().catch(() => {}); return }
        video.pause()
      },
      { threshold: 0.1 },
    )
    observer.observe(video)
    return () => { observer.disconnect(); video.pause() }
  }, [shouldRenderVideo])

  if (!shouldRenderVideo) {
    return (
      <div
        aria-hidden="true"
        style={{ position: 'absolute', inset: 0, background: '#050608' }}
      />
    )
  }

  return (
    <video
      ref={videoRef}
      autoPlay
      loop
      muted
      playsInline
      preload="auto"
      aria-hidden="true"
      style={{
        position: 'absolute',
        inset: 0,
        width: '100%',
        height: '100%',
        objectFit: 'cover',
        objectPosition: 'center 18%',
      }}
    >
      <source src="/LandingPage3.webm" type="video/webm" />
      <source src="/LandingPage3.mp4" type="video/mp4" />
    </video>
  )
}

export default function LandingPage() {
  return (
    <div style={{ background: 'var(--bg)', color: 'var(--text)', overflowX: 'hidden', width: '100%' }}>

      {/* ── FULLSCREEN HERO ─────────────────────────────────────────────────── */}
      <section style={{
        position: 'relative',
        width: '100%',
        height: '100vh',
        minHeight: 560,
        overflow: 'hidden',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}>
        {/* Video / Poster fill */}
        <LandingHeroMedia />

        {/* Dark gradient overlay — keep the video readable, not covered */}
        <div style={{
          position: 'absolute',
          inset: 0,
          background: 'linear-gradient(to top, rgba(5,6,8,0.78) 0%, rgba(5,6,8,0.18) 38%, rgba(5,6,8,0.04) 100%)',
          zIndex: 1,
          pointerEvents: 'none',
        }} />

        {/* Hero Text — small, italic, anchored low so the video stays visible */}
        <div style={{
          position: 'absolute',
          left: 0,
          right: 0,
          bottom: 40,
          zIndex: 2,
          textAlign: 'center',
          padding: '0 24px',
          pointerEvents: 'none',
        }}>
          <h1 style={{
            fontFamily: 'Inter, sans-serif',
            fontWeight: 800,
            fontStyle: 'italic',
            fontSize: 'clamp(1.1rem, 2.2vw, 1.6rem)',
            lineHeight: 1.2,
            letterSpacing: '0.08em',
            color: 'rgba(255,255,255,0.92)',
            marginBottom: 12,
            textTransform: 'uppercase',
            textShadow: '0 1px 12px rgba(0,0,0,0.55)',
          }}>
            Precision in every millisecond
          </h1>

          <p style={{
            fontFamily: 'Inter, sans-serif',
            fontSize: 13,
            lineHeight: 1.55,
            color: 'rgba(255,255,255,0.72)',
            maxWidth: 420,
            margin: '0 auto 20px',
            textShadow: '0 1px 8px rgba(0,0,0,0.4)',
          }}>
            Unlock elite-level race analytics. From real-time telemetry to
            predictive race strategy, dominate the grid with advanced motorsport data.
          </p>

          <div style={{ display: 'flex', justifyContent: 'center', pointerEvents: 'auto' }}>
            <Link
              href="/dashboard"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 10,
                background: '#E8002D',
                color: '#FFFFFF',
                padding: '14px 36px',
                borderRadius: 8,
                fontFamily: 'Inter, sans-serif',
                fontSize: 14,
                fontWeight: 800,
                letterSpacing: '0.06em',
                textDecoration: 'none',
                boxShadow: '0 8px 32px rgba(232, 0, 45, 0.45)',
                transition: 'transform 160ms ease, box-shadow 160ms ease',
                textTransform: 'uppercase',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.transform = 'translateY(-2px)'
                e.currentTarget.style.boxShadow = '0 12px 36px rgba(232, 0, 45, 0.55)'
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.transform = 'translateY(0)'
                e.currentTarget.style.boxShadow = '0 8px 32px rgba(232, 0, 45, 0.45)'
              }}
            >
              <Play size={16} fill="#FFFFFF" strokeWidth={0} />
              ENTER BOXUP
            </Link>
          </div>
        </div>
      </section>

      {/* Partners strip */}
      <section style={{ padding: '28px 5vw', background: 'var(--bg)', borderBottom: '1px solid var(--border)', textAlign: 'center' }}>
        <p style={{
          fontFamily: 'Space Grotesk, sans-serif', fontSize: 10, fontWeight: 700,
          letterSpacing: '0.16em', textTransform: 'uppercase', color: 'var(--text-4)', marginBottom: 14,
        }}>DATA FROM</p>
        <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 40, flexWrap: 'wrap' }}>
          {['FastF1', 'OpenF1', 'Jolpica'].map(name => (
            <span key={name} style={{ fontFamily: 'Inter, sans-serif', fontSize: 15, fontWeight: 600, color: 'var(--text-3)', letterSpacing: '-0.01em' }}>
              {name}
            </span>
          ))}
        </div>
      </section>

      {/* ── FEATURES ─────────────────────────────────────────────────────── */}
      <section style={{ padding: '100px 5vw', width: '100%', background: 'var(--bg-deep)', borderTop: '1px solid var(--border)' }}>

        <div style={{ marginBottom: 64, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', flexWrap: 'wrap', gap: 24 }}>
          <div style={{ maxWidth: 500 }}>
            <h2 style={{
              fontFamily: 'Inter, sans-serif', fontWeight: 900,
              fontSize: 'clamp(2rem, 4vw, 2.8rem)', letterSpacing: '-0.04em',
              color: 'var(--text)', lineHeight: 1.1, marginBottom: 16, textTransform: 'uppercase',
            }}>TECHNICAL MASTERY</h2>
            <p style={{ fontFamily: 'Inter, sans-serif', fontSize: 16, color: 'var(--text-3)', lineHeight: 1.6 }}>
              Strip away the drag from your decision-making process with high-fidelity telemetry architecture.
            </p>
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(12, 1fr)', gap: 16 }}>

          {/* TELEMETRY — 8 cols */}
          <div style={{ gridColumn: 'span 8', background: 'var(--surface)', borderRadius: 24, overflow: 'hidden', display: 'flex', minHeight: 460, border: '1px solid var(--border)' }}>
            <div style={{ padding: 48, flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
                <Activity size={18} color="#E8002D" />
                <span style={{ fontFamily: 'Space Grotesk, sans-serif', fontSize: 11, fontWeight: 800, letterSpacing: '0.12em', color: '#E8002D', textTransform: 'uppercase' }}>Telemetry</span>
              </div>
              <p style={{ fontFamily: 'Inter, sans-serif', fontSize: 15, color: 'var(--text-3)', lineHeight: 1.6, maxWidth: 320, marginBottom: 24 }}>
                Distributed data streaming via Apache Kafka. Processed with sub-millisecond latency for instant technical insight from over 300 sensors.
              </p>
              <div style={{ display: 'flex', gap: 8 }}>
                {['KAFKA-DRIVEN', '2.4GB/S', 'DIST-ALIGNED'].map(t => (
                  <span key={t} style={{ fontFamily: 'Space Grotesk, sans-serif', fontSize: 10, padding: '6px 12px', borderRadius: 4, background: 'var(--surface-2)', color: 'var(--text-2)', fontWeight: 700, border: '1px solid var(--border)' }}>{t}</span>
                ))}
              </div>
            </div>
            <div style={{ flex: 1, position: 'relative', background: '#0F172A' }}>
              <div style={{ position: 'absolute', inset: 0, backgroundImage: `url('https://images.unsplash.com/photo-1522519972666-d8677d9d3e67?q=80&w=988&auto=format&fit=crop')`, backgroundSize: 'cover', backgroundPosition: 'center', opacity: 0.6 }} />
              <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(90deg, var(--surface) 0%, transparent 40%)' }} />
            </div>
          </div>

          {/* STRATEGY — 4 cols */}
          <div style={{ gridColumn: 'span 4', background: 'var(--surface)', borderRadius: 24, padding: 48, display: 'flex', flexDirection: 'column', border: '1px solid var(--border)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
              <Zap size={18} color="#E8002D" />
              <span style={{ fontFamily: 'Space Grotesk, sans-serif', fontSize: 11, fontWeight: 800, letterSpacing: '0.12em', color: '#E8002D', textTransform: 'uppercase' }}>Strategy</span>
            </div>
            <p style={{ fontFamily: 'Inter, sans-serif', fontSize: 15, color: 'var(--text-3)', lineHeight: 1.6, marginBottom: 32 }}>
              Monte Carlo simulations running on TimescaleDB hypertables to provide optimal pit-stop windows and compound degradation models.
            </p>
            <div style={{ marginTop: 'auto', display: 'flex', alignItems: 'flex-end', gap: 6, height: 100 }}>
              {[40, 60, 100, 80, 50].map((h, i) => (
                <div key={i} style={{ flex: 1, height: `${h}%`, background: h === 100 ? '#E8002D' : 'var(--surface-3)', borderRadius: 4 }} />
              ))}
            </div>
          </div>

          {/* PREDICTIONS — 4 cols */}
          <div style={{ gridColumn: 'span 4', background: 'var(--surface)', borderRadius: 24, padding: 40, minHeight: 240, border: '1px solid var(--border)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
              <Brain size={18} color="#E8002D" />
              <span style={{ fontFamily: 'Space Grotesk, sans-serif', fontSize: 11, fontWeight: 800, letterSpacing: '0.12em', color: '#E8002D', textTransform: 'uppercase' }}>AutoML Inference</span>
            </div>
            <p style={{ fontFamily: 'Inter, sans-serif', fontSize: 15, color: 'var(--text-3)', lineHeight: 1.6 }}>
              Neural networks and FLAML ensembles trained on 70 years of race data to predict overtaking probability and engine fatigue with SHAP interpretability.
            </p>
          </div>

          {/* INGESTION — 8 cols */}
          <div className="landing-global-sync" style={{ gridColumn: 'span 8', background: 'var(--navy)', borderRadius: 24, padding: 48, display: 'flex', justifyContent: 'space-between', alignItems: 'center', minHeight: 240, border: '1px solid var(--border)' }}>
            <div style={{ maxWidth: 400 }}>
              <h3 style={{ fontFamily: 'Inter, sans-serif', fontSize: 18, fontWeight: 800, color: '#FFFFFF', marginBottom: 12, textTransform: 'uppercase' }}>Ingestion Pipeline</h3>
              <p style={{ fontFamily: 'Inter, sans-serif', fontSize: 15, color: '#94A3B8', lineHeight: 1.6 }}>
                Automated data ingestion from FastF1, OpenF1, and Jolpica. Zero-config synchronization between the track and your local archive.
              </p>
            </div>
            <div className="landing-global-sync-right" style={{ textAlign: 'right' }}>
              <div style={{ fontFamily: 'Inter, sans-serif', fontWeight: 900, fontSize: 56, color: '#10B981', letterSpacing: '-0.04em', lineHeight: 1 }}>99.9%</div>
              <div style={{ fontFamily: 'Space Grotesk, sans-serif', fontSize: 10, fontWeight: 700, color: '#10B981', opacity: 0.8, letterSpacing: '0.15em', textTransform: 'uppercase', marginTop: 8 }}>Ingestion Accuracy</div>
            </div>
          </div>

        </div>
      </section>

      {/* ── COMMUNITY ─────────────────────────────────────────────────────── */}
      <section style={{ padding: '120px 5vw', textAlign: 'center', background: 'var(--bg)', borderTop: '1px solid var(--border)' }}>
        <div style={{ maxWidth: 800, margin: '0 auto' }}>
          <h2 style={{ fontFamily: 'Inter, sans-serif', fontWeight: 900, fontSize: 'clamp(2rem, 4vw, 3rem)', letterSpacing: '-0.05em', color: 'var(--text)', lineHeight: 1.1, marginBottom: 24, textTransform: 'uppercase' }}>
            Built by the community,<br />for the community.
          </h2>
          <p style={{ fontFamily: 'Inter, sans-serif', fontSize: 18, color: 'var(--text-3)', lineHeight: 1.6, maxWidth: 600, margin: '0 auto 48px' }}>
            BoxUp is built for engineers and F1 fans shaping the future of accessible motorsport analytics.
          </p>
          <div style={{ display: 'flex', gap: 16, justifyContent: 'center', flexWrap: 'wrap' }}>
            <a href="https://github.com/SheerWill007/Formula-I" style={{
              display: 'inline-flex', alignItems: 'center', gap: 12,
              padding: '16px 36px', background: 'var(--surface-2)', color: 'var(--text)',
              border: '1px solid var(--border-2)',
              fontFamily: 'Inter, sans-serif', fontSize: 14, fontWeight: 800,
              borderRadius: 12, textDecoration: 'none',
              textTransform: 'uppercase', letterSpacing: '0.05em',
              transition: 'transform 0.2s ease',
            }}
              onMouseEnter={e => e.currentTarget.style.transform = 'translateY(-2px)'}
              onMouseLeave={e => e.currentTarget.style.transform = 'translateY(0)'}>
              <Globe size={18} /> Contribute to the Project.
            </a>
          </div>
        </div>
      </section>

      {/* ── FOOTER ───────────────────────────────────────────────────────── */}
      <footer style={{ background: 'var(--bg-deep)', borderTop: '1px solid var(--border)', padding: '60px 5vw 40px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 40 }}>
        <span style={{ fontFamily: 'Inter, sans-serif', fontWeight: 900, fontSize: 18, color: 'var(--text)', letterSpacing: '-0.04em', textTransform: 'uppercase', fontStyle: 'italic' }}>BoxUp</span>
        <div style={{ display: 'flex', gap: 40, flexWrap: 'wrap', justifyContent: 'center' }}>
          {['LATEST WEEKEND', 'TELEMETRY', 'SESSIONS', 'PREDICTIONS', 'LIVE DATA'].map(l => {
            const href = l === 'LIVE DATA' || l === 'LATEST WEEKEND' ? '/sessions/latest' : `/${l.toLowerCase()}`
            return (
              <Link key={l} href={href} style={{ fontFamily: 'Inter, sans-serif', fontSize: 12, fontWeight: 700, color: 'var(--text-4)', textDecoration: 'none', letterSpacing: '0.05em' }}>{l}</Link>
            )
          })}
        </div>
        <div style={{ fontFamily: 'Inter, sans-serif', fontSize: 12, color: 'var(--text-4)', fontWeight: 500 }}>
          © 2026 BOXUP · MOTORSPORT ANALYTICS
        </div>
      </footer>

      <style>{`
        @media (max-width: 1024px) {
          [style*="span 8"], [style*="span 4"] { grid-column: span 12 !important; }
        }
        @media (max-width: 768px) {
          .landing-global-sync { flex-direction: column !important; align-items: flex-start !important; gap: 32px; padding: 32px 24px !important; }
          .landing-global-sync-right { text-align: left !important; }
        }
      `}</style>
    </div>
  )
}
