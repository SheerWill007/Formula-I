'use client'

import React from 'react'

interface SectorCardProps {
  label: string
  time: string | number
  delta?: number | string | null
  color: string
}

const C = {
  textDim: '#7D8BA2',
  textSub: '#293A52',
  textBright: '#13233D',
  border: '#D9E3EF',
  surface: '#FFFFFF',
  green: '#10B981',
  red: '#E8002D',
} as const

export default function SectorCard({ label, time, delta, color }: SectorCardProps) {
  const isNegative = typeof delta === 'number' ? delta < 0 : String(delta).startsWith('-')
  const deltaValue = typeof delta === 'number' ? (delta / 1000).toFixed(3) : delta

  return (
    <div style={{
      background: C.surface,
      border: `1px solid ${C.border}`,
      borderRadius: '20px',
      padding: '20px',
      position: 'relative',
      overflow: 'hidden',
      boxShadow: '0 8px 30px rgba(0,0,0,0.03)',
      flex: 1,
      minWidth: '200px'
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '12px' }}>
        <span style={{ 
          fontSize: '10px', 
          fontFamily: 'Space Grotesk, sans-serif', 
          fontWeight: 700, 
          letterSpacing: '0.12em', 
          textTransform: 'uppercase', 
          color: C.textDim 
        }}>
          {label}
        </span>
        {delta != null && (
          <div style={{
            background: isNegative ? `${C.green}15` : `${C.red}15`,
            color: isNegative ? C.green : C.red,
            padding: '2px 8px',
            borderRadius: '6px',
            fontSize: '10px',
            fontFamily: 'JetBrains Mono, monospace',
            fontWeight: 700
          }}>
            {isNegative ? '' : '+'}{deltaValue}s
          </div>
        )}
      </div>

      <div style={{ 
        fontSize: '24px', 
        fontFamily: 'Inter, sans-serif', 
        fontWeight: 900, 
        color: C.textBright, 
        letterSpacing: '-0.03em', 
        lineHeight: 1 
      }}>
        {typeof time === 'number' ? (time / 1000).toFixed(3) : time}
      </div>

      <div style={{ 
        marginTop: '20px', 
        height: '4px', 
        background: `${color}20`, 
        borderRadius: '2px',
        overflow: 'hidden'
      }}>
        <div style={{ 
          width: '40%', // Decorative progress
          height: '100%', 
          background: color,
          borderRadius: '2px'
        }} />
      </div>
    </div>
  )
}
