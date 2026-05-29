'use client'

import Image from 'next/image'
import Link from 'next/link'
import { useEffect, useState } from 'react'
import { Play } from 'lucide-react'

const HERO_IMAGES = [

  //vids On Here!
  
  '/Picture1.jpg',
  '/Picture2.jpg',
  '/Picture3.jpg',
  '/Picture4.jpg',
  '/Picture5.jpg',
  '/Picture6.jpg',
]

export default function Hero() {
  const [currentIndex, setCurrentIndex] = useState(0)
  const [isAnimating, setIsAnimating] = useState(false)

  useEffect(() => {
    const interval = setInterval(() => {
      setIsAnimating(true)
      setTimeout(() => {
        setCurrentIndex((prev) => (prev + 1) % HERO_IMAGES.length)
        setIsAnimating(false)
      }, 1000)
    }, 6000)

    return () => clearInterval(interval)
  }, [])

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
      {/* Image Slideshow */}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          zIndex: 0,
        }}
      >
        {HERO_IMAGES.map((src, index) => (
          <div
            key={src}
            style={{
              position: 'absolute',
              inset: 0,
              opacity: index === currentIndex ? 1 : 0,
              transition: 'opacity 1s ease-in-out',
              animation: index === currentIndex && !isAnimating ? 'kenBurns 10s ease-out forwards' : 'none',
            }}
          >
            <Image
              src={src}
              alt={`F1 Racing ${index + 1}`}
              fill
              priority={index === 0}
              sizes="100vw"
              style={{
                objectFit: 'cover',
                objectPosition: 'center',
              }}
              quality={90}
            />
          </div>
        ))}
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
          Enter Pitwall
        </Link>

        {/* Slideshow Indicators */}
        <div
          style={{
            display: 'flex',
            gap: 8,
            marginTop: 48,
          }}
        >
          {HERO_IMAGES.map((_, index) => (
            <button
              key={index}
              onClick={() => {
                setIsAnimating(true)
                setTimeout(() => {
                  setCurrentIndex(index)
                  setIsAnimating(false)
                }, 500)
              }}
              style={{
                width: index === currentIndex ? 32 : 8,
                height: 8,
                background: index === currentIndex ? '#E10600' : 'rgba(255, 255, 255, 0.4)',
                border: 'none',
                borderRadius: 4,
                cursor: 'pointer',
                transition: 'all 0.3s ease',
              }}
              aria-label={`Go to slide ${index + 1}`}
            />
          ))}
        </div>
      </div>

      {/* Ken Burns Animation */}
      <style jsx>{`
        @import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Oswald:wght@400;700&display=swap');

        @keyframes kenBurns {
          0% {
            transform: scale(1.06);
          }
          100% {
            transform: scale(1.0);
          }
        }

        @media (max-width: 768px) {
          h1 {
            font-size: 48px !important;
          }
        }
      `}</style>
    </section>
  )
}
