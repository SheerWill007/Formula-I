import { describe, expect, it } from 'vitest'
import { ageFromDob, flagEmoji, getDriverMeta } from './driver-meta'

describe('driver meta', () => {
  it('computes age around the birthday', () => {
    expect(ageFromDob('1994-09-01', new Date('2025-08-31T12:00:00Z'))).toBe(30)
    expect(ageFromDob('1994-09-01', new Date('2025-09-01T12:00:00Z'))).toBe(31)
  })
  it('builds flag emoji', () => {
    expect(flagEmoji('ES')).toBe('🇪🇸')
    expect(flagEmoji('x')).toBe('')
  })
  it('looks up drivers case-insensitively and returns null for unknown', () => {
    expect(getDriverMeta('sai')?.nationality).toBe('Spanish')
    expect(getDriverMeta('ZZZ')).toBeNull()
  })
})
