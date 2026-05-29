'use client'

import React from 'react'

interface PerformanceMatrixProps {
  bestLap: string | number
  theoBest: string | number
  topSpeed: number
  s1Best: string | number
  s2Best: string | number
  s3Best: string | number
  accentColor: string
}

const C = {
  textDim: '#7D8BA2',
  textSub: '#293A52',
  textBright: '#13233D',
  border: '#D9E3EF',
  surface: '#FFFFFF',
  red: '#E8002D',
  gold: '#C98A27',
  purple: '#6E56CF',
  green: '#10B981',
} as const

export default function PerformanceMatrix({
  bestLap,
  theoBest,
  topSpeed,
  s1Best,
  s2Best,
  s3Best
}: PerformanceMatrixProps) {
  const formatTime = (t: string | number) => typeof t === 'number' ? (t / 1000).toFixed(3) : t

  const rows = [
    { label: 'BEST LAP', value: formatTime(bestLap), color: C.textBright, bold: true },
    { label: 'THEORETICAL BEST', value: formatTime(theoBest), color: C.red, bold: true },
    { label: 'TOP SPEED', value: `${topSpeed} KM/H`, color: C.textBright },
    { label: 'S1 BEST', value: formatTime(s1Best), color: C.green },
    { label: 'S2 BEST', value: formatTime(s2Best), color: C.textBright },
    { label: 'S3 BEST', value: formatTime(s3Best), color: C.textBright },
  ]

  return (
    <div style={{
      background: C.surface,
      border: `1px solid ${C.border}`,
      borderRadius: '24px',
      padding: '24px',
      boxShadow: '0 8px 30px rgba(0,0,0,0.03)',
      width: '100%',
      maxWidth: '340px',
      display: 'flex',
      flexDirection: 'column',
      gap: '20px'
    }}>
      <h3 style={{ 
        fontSize: '14px', 
        fontFamily: 'Space Grotesk, sans-serif', 
        fontWeight: 800, 
        color: C.textBright,
        margin: 0,
        marginBottom: '4px'
      }}>
        Performance Matrix
      </h3>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '1px' }}>
        {rows.map((row, i) => (
          <div key={row.label} style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            padding: '14px 0',
            borderBottom: i === rows.length - 1 ? 'none' : `1px solid ${C.border}40`
          }}>
            <span style={{ 
              fontSize: '11px', 
              fontFamily: 'Space Grotesk, sans-serif', 
              fontWeight: 600, 
              color: C.textDim,
              letterSpacing: '0.05em'
            }}>
              {row.label}
            </span>
            <span style={{ 
              fontSize: '15px', 
              fontFamily: 'JetBrains Mono, monospace', 
              fontWeight: row.bold ? 800 : 500, 
              color: row.color,
              letterSpacing: '-0.02em'
            }}>
              {row.value}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
