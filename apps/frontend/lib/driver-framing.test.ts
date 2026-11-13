import { describe, expect, it } from 'vitest'
import { DEFAULT_FRAMING, framingFor } from './driver-framing'

describe('framingFor', () => {
  it('returns per-driver framing case-insensitively', () => {
    expect(framingFor('LEC').kind).toBe('full')
    expect(framingFor('sai').kind).toBe('crop')
  })
  it('falls back to the default for unknown drivers', () => {
    expect(framingFor('zzz')).toEqual(DEFAULT_FRAMING)
  })
})
