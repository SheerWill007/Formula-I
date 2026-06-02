'use client'

import Link from 'next/link'
import { useEffect, useState, useRef } from 'react'
import { Play, Volume2, VolumeX } from 'lucide-react'

export default function Hero() {
  const [isMuted, setIsMuted] = useState(true)
  const videoRef = useRef<HTMLVideoElement>(null)

  useEffect(() => {
    if (videoRef.current) {
      videoRef.current.muted = isMuted
    }
  }, [isMuted])

  const toggleMute = () => {
    setIsMuted(!isMuted)
  }

  return (
    <section
      style={{
        position: 'relative',
        width: '100%',
        height: '100vh',
        overflow: 'hidden',
        marginTop: -80, // Offset the layout padding to make it full-bleed
      }}
    >
      {/* Video Background */}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          zIndex: 0,
        }}
      >
        <video
          ref={videoRef}
          autoPlay
          loop
          muted={isMuted}
          playsInline
          style={{
            width: '100%',
            height: '100%',
            objectFit: 'cover',
            objectPosition: 'center',
          }}
        >
          <source src="/LiveHero.webm" type="video/webm" />
          Your browser does not support the video tag.
        </video>
      </div>

      {/* Gradient Overlay */}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          background: 'linear-gradient(to bottom, transparent 0%, transparent 40%, rgba(0, 0, 0, 0.72) 100%)',
          zIndex: 1,
        }}
      />

      {/* Music Toggle Button */}
      <button
        onClick={toggleMute}
        style={{
          position: 'absolute',
          top: 120,
          right: 40,
          zIndex: 3,
          width: 56,
          height: 56,
          borderRadius: '50%',
          background: 'rgba(0, 0, 0, 0.6)',
          backdropFilter: 'blur(8px)',
          border: '2px solid rgba(255, 255, 255, 0.2)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          cursor: 'pointer',
          transition: 'all 0.3s ease',
          color: '#FFFFFF',
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.background = 'rgba(225, 6, 0, 0.8)'
          e.currentTarget.style.borderColor = '#E10600'
          e.currentTarget.style.transform = 'scale(1.1)'
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.background = 'rgba(0, 0, 0, 0.6)'
          e.currentTarget.style.borderColor = 'rgba(255, 255, 255, 0.2)'
          e.currentTarget.style.transform = 'scale(1)'
        }}
        aria-label={isMuted ? 'Unmute video' : 'Mute video'}
      >
        {isMuted ? <VolumeX size={24} /> : <Volume2 size={24} />}
      </button>

      {/* Content */}
      <div
        style={{
          position: 'relative',
          zIndex: 2,
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'flex-end',
          alignItems: 'center',
          padding: '0 24px 120px',
          textAlign: 'center',
        }}
      >
        {/* Red Accent Line */}
        <div
          style={{
            width: 80,
            height: 2,
            background: '#E10600',
            marginBottom: 32,
          }}
        />

        {/* Headline */}
        <h1
          style={{
            fontFamily: "'Bebas Neue', 'Oswald', sans-serif",
            fontSize: 'clamp(48px, 8vw, 96px)',
            fontWeight: 400,
            lineHeight: 0.95,
            letterSpacing: '0.02em',
            color: '#FFFFFF',
            marginBottom: 24,
            textTransform: 'uppercase',
            textShadow: '0 4px 24px rgba(0, 0, 0, 0.5)',
          }}
        >
          Precision in
          <br />
          Every Millisecond
        </h1>

        {/* Subtitle */}
        <p
          style={{
            fontFamily: 'Inter, sans-serif',
            fontSize: 'clamp(16px, 2vw, 20px)',
            lineHeight: 1.6,
            color: 'rgba(255, 255, 255, 0.95)',
            marginBottom: 40,
            maxWidth: 600,
            textShadow: '0 2px 12px rgba(0, 0, 0, 0.6)',
            fontWeight: 500,
          }}
        >
          Unlock elite-level race analytics. From real-time telemetry to predictive race strategy,
          dominate the grid with advanced motorsport data.
        </p>

        {/* CTA Button */}
        <Link
          href="/dashboard"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 12,
            padding: '18px 40px',
            background: '#E10600',
            color: '#FFFFFF',
            fontFamily: 'Inter, sans-serif',
            fontSize: 16,
            fontWeight: 700,
            textDecoration: 'none',
            borderRadius: 4,
            textTransform: 'uppercase',
            letterSpacing: '0.05em',
            transition: 'all 0.3s ease',
            boxShadow: '0 8px 32px rgba(225, 6, 0, 0.4)',
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.transform = 'translateY(-2px)'
            e.currentTarget.style.boxShadow = '0 12px 40px rgba(225, 6, 0, 0.5)'
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.transform = 'translateY(0)'
            e.currentTarget.style.boxShadow = '0 8px 32px rgba(225, 6, 0, 0.4)'
          }}
        >
          <Play size={20} fill="#FFFFFF" />
          Enter BoxUp
        </Link>
      </div>

      {/* Video Styles */}
      <style jsx>{`
        @import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Oswald:wght@400;700&display=swap');

        @media (max-width: 768px) {
          h1 {
            font-size: 48px !important;
          }
        }
      `}</style>
    </section>
  )
}
