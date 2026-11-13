import { describe, expect, it } from 'vitest'
import { driverImageCandidates, normaliseDriverCode, ordinal, teamColour } from './driver-image'

describe('driver image helpers', () => {
  it('rejects unsafe driver codes', () => {
    expect(normaliseDriverCode('../etc')).toBeNull()
    expect(normaliseDriverCode(' SAI ')).toBe('sai')
  })
  it('puts the private cutout before the headshot', () => {
    const c = driverImageCandidates('SAI', 'https://x.test/a.png')
    expect(c.map(i => i.kind)).toEqual(['cutout', 'headshot'])
    expect(c[0].src).toBe('/drivers/sai.png')
  })
  it('ignores non-http headshots', () => {
    expect(driverImageCandidates('ver', 'javascript:alert(1)')).toHaveLength(1)
  })
  it('normalises team colours', () => {
    expect(teamColour('3671C6')).toBe('#3671c6')
    expect(teamColour('nope')).toBe('#e8002d')
  })
  it('formats ordinals', () => {
    expect([1, 2, 3, 4, 11, 12, 21].map(ordinal)).toEqual(['1st', '2nd', '3rd', '4th', '11th', '12th', '21st'])
  })
})
