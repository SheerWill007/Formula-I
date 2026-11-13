import { describe, expect, it } from 'vitest'

import { pct, ramp, teamHex } from '@/lib/viz-color'

describe('ramp', () => {
  it('starts at the lightest step and ends at the darkest', () => {
    expect(ramp(0)).toBe('rgb(205,226,251)')
    expect(ramp(1)).toBe('rgb(13,54,107)')
  })

  it('clamps out of range input', () => {
    expect(ramp(-5)).toBe(ramp(0))
    expect(ramp(9)).toBe(ramp(1))
  })

  it('gets darker as the value grows', () => {
    const lum = (c: string) => c.match(/\d+/g)!.map(Number).reduce((a, b) => a + b, 0)
    expect(lum(ramp(0.2))).toBeGreaterThan(lum(ramp(0.8)))
  })
})

describe('teamHex', () => {
  it('accepts six digit hex with or without a hash', () => {
    expect(teamHex('E8002D')).toBe('#E8002D')
    expect(teamHex('#27F4D2')).toBe('#27F4D2')
  })

  it('falls back to grey for missing or invalid colours', () => {
    expect(teamHex(null)).toBe('#737373')
    expect(teamHex('nope')).toBe('#737373')
  })
})

describe('pct', () => {
  it('formats a probability as a percentage', () => {
    expect(pct(0.1234)).toBe('12.3%')
    expect(pct(0.5, 0)).toBe('50%')
  })

  it('shows a dash for missing values', () => {
    expect(pct(null)).toBe('—')
    expect(pct(undefined)).toBe('—')
    expect(pct(Number.NaN)).toBe('—')
  })
})
