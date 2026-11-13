import { describe, expect, it } from 'vitest'
import { withSample } from './driver-sample'
import type { DriverProfile } from '@/types/f1'

const empty: DriverProfile = {
  code: 'SAI', identity: null, career: null, recent_races: [], style: null,
  seasons: [], results_grid: [], style_history: [],
}

describe('withSample', () => {
  it('fills every empty block and flags it', () => {
    const { profile, sampled } = withSample(empty)
    expect(sampled).toEqual({ career: true, races: true, seasons: true, style: true })
    expect(profile.results_grid.length).toBeGreaterThan(0)
    expect(profile.style_history[0]).toHaveProperty('braking_aggression')
  })
  it('keeps real data untouched', () => {
    const real = { ...empty, seasons: [{ year: 2024, races: 1, wins: 0, podiums: 0, points: 1, avg_finish: 9, avg_grid: 9, team: 'X' }] }
    const { profile, sampled } = withSample(real)
    expect(sampled.seasons).toBe(false)
    expect(profile.seasons).toBe(real.seasons)
  })
})
