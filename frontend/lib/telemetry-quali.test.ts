import { describe, expect, it } from 'vitest'

import {
  getSegmentDriverNumbers,
  getSegmentEntries,
  getSegmentLapByDriver,
  getQualifyingAdvancePosition,
  getSegmentSummary,
  reconcileSelectedDrivers,
  type QualiSegmentsData,
} from '@/lib/telemetry-quali'

const qualiSegments: QualiSegmentsData = {
  segments: {
    Q1: [
      { driver_number: 12, abbreviation: 'ANT', team_name: 'Mercedes', team_colour: '27F4D2', lap_number: 2, lap_time_ms: 93305, s1_ms: 1, s2_ms: 1, s3_ms: 1, gap_ms: 130, position: 3, eliminated: false },
      { driver_number: 63, abbreviation: 'RUS', team_name: 'Mercedes', team_colour: '27F4D2', lap_number: 2, lap_time_ms: 93262, s1_ms: 1, s2_ms: 1, s3_ms: 1, gap_ms: 87, position: 2, eliminated: false },
      { driver_number: 55, abbreviation: 'SAI', team_name: 'Williams', team_colour: '64C4FF', lap_number: 9, lap_time_ms: 94317, s1_ms: 1, s2_ms: 1, s3_ms: 1, gap_ms: 1142, position: 17, eliminated: true },
    ],
    Q2: [
      { driver_number: 12, abbreviation: 'ANT', team_name: 'Mercedes', team_colour: '27F4D2', lap_number: 8, lap_time_ms: 92443, s1_ms: 1, s2_ms: 1, s3_ms: 1, gap_ms: 0, position: 1, eliminated: false },
      { driver_number: 63, abbreviation: 'RUS', team_name: 'Mercedes', team_colour: '27F4D2', lap_number: 5, lap_time_ms: 92523, s1_ms: 1, s2_ms: 1, s3_ms: 1, gap_ms: 80, position: 3, eliminated: false },
    ],
    Q3: [
      { driver_number: 12, abbreviation: 'ANT', team_name: 'Mercedes', team_colour: '27F4D2', lap_number: 14, lap_time_ms: 92064, s1_ms: 1, s2_ms: 1, s3_ms: 1, gap_ms: 0, position: 1, eliminated: false },
      { driver_number: 63, abbreviation: 'RUS', team_name: 'Mercedes', team_colour: '27F4D2', lap_number: 12, lap_time_ms: 92286, s1_ms: 1, s2_ms: 1, s3_ms: 1, gap_ms: 222, position: 2, eliminated: false },
    ],
  },
  boundaries: { Q2_start_lap: 5, Q3_start_lap: 11 },
}

describe('telemetry qualifying helpers', () => {
  it('returns the segment lap numbers by driver', () => {
    const entries = getSegmentEntries(qualiSegments, 'Q2')
    const lapByDriver = getSegmentLapByDriver(entries)

    expect(lapByDriver.get(12)).toBe(8)
    expect(lapByDriver.get(63)).toBe(5)
  })

  it('filters and refills selected drivers from the active segment', () => {
    const allowed = getSegmentDriverNumbers(getSegmentEntries(qualiSegments, 'Q2'))
    const next = reconcileSelectedDrivers(
      [12, 55],
      [{ driver_number: 12 }, { driver_number: 63 }, { driver_number: 55 }],
      allowed,
    )

    expect(next).toEqual([12, 63])
  })

  it('builds a summary with leader and cutoff context', () => {
    const summary = getSegmentSummary('Q1', getSegmentEntries(qualiSegments, 'Q1'), 2025)

    expect(summary.label).toBe('Full qualifying field')
    expect(summary.leader?.driver_number).toBe(12)
    expect(summary.cutoff).toBeNull()
  })

  it('uses the old qualifying cutoffs through 2025', () => {
    expect(getQualifyingAdvancePosition(2025, 'Q1')).toBe(15)
    expect(getQualifyingAdvancePosition(2025, 'Q2')).toBe(10)
    expect(getQualifyingAdvancePosition(2025, 'Q3')).toBeNull()
  })

  it('uses the expanded Q1 cutoff from 2026 onward', () => {
    expect(getQualifyingAdvancePosition(2026, 'Q1')).toBe(16)
    expect(getQualifyingAdvancePosition(2026, 'Q2')).toBe(10)
    expect(getQualifyingAdvancePosition(2026, 'Q3')).toBeNull()
  })
})
