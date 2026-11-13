import { describe, expect, it } from 'vitest'
import { buildHeatRows, cellIntensity, radarData } from './driver-insights'

const r = (o: Partial<Parameters<typeof cellIntensity>[1]> = {}) => ({
  year: 2024, round: 1, race_name: 'X GP', grid: 5, position: 1, points: 25, status: 'Finished', ...o,
})

describe('driver insights', () => {
  it('scores a win highest and a DNF as empty', () => {
    expect(cellIntensity('finish', r())).toBe(1)
    expect(cellIntensity('finish', r({ position: null }))).toBeNull()
    expect(cellIntensity('finish', r({ position: 20 }))).toBeCloseTo(0.05)
  })
  it('centres positions gained at 0.5', () => {
    expect(cellIntensity('gained', r({ grid: 5, position: 5 }))).toBe(0.5)
    expect(cellIntensity('gained', r({ grid: 0, position: 5 }))).toBeNull()
  })
  it('builds newest-first rows padded to the longest season', () => {
    const { rows, rounds } = buildHeatRows([r({ year: 2023, round: 2 }), r({ year: 2024, round: 1 }), r({ year: 2024, round: 3 })])
    expect(rounds).toBe(3)
    expect(rows.map(x => x.year)).toEqual([2024, 2023])
    expect(rows[1].cells.map(c => c?.round ?? null)).toEqual([null, 2, null])
  })
  it('builds radar data with an optional comparison', () => {
    const h = [{ season: 2023, braking_aggression: 0.5 }, { season: 2024, braking_aggression: 1 }]
    const d = radarData(h, 2024, 2023)
    expect(d[0]).toEqual({ axis: 'Braking', current: 100, compare: 50 })
    expect(radarData(h, 2024)[0]).not.toHaveProperty('compare')
  })
})
