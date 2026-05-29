export type TelemetrySegment = 'Q1' | 'Q2' | 'Q3'

export type QualiSegmentEntry = {
  driver_number: number
  abbreviation: string
  team_name: string
  team_colour: string
  lap_number: number
  lap_time_ms: number
  s1_ms: number | null
  s2_ms: number | null
  s3_ms: number | null
  gap_ms: number
  position: number
  eliminated: boolean
}

export type QualiSegmentsData = {
  segments: { Q1: QualiSegmentEntry[]; Q2: QualiSegmentEntry[]; Q3: QualiSegmentEntry[] }
  boundaries: { Q2_start_lap: number | null; Q3_start_lap: number | null }
}

export type DriverOption = {
  driver_number: number
}

export function getQualifyingAdvancePosition(
  sessionYear: number | null | undefined,
  segment: TelemetrySegment,
): number | null {
  if (segment === 'Q3') return null
  if (segment === 'Q2') return 10
  return (sessionYear ?? 0) >= 2026 ? 16 : 15
}

export function getSegmentEntries(
  qualiSegments: QualiSegmentsData | null,
  segment: TelemetrySegment,
): QualiSegmentEntry[] {
  return qualiSegments?.segments[segment] ?? []
}

export function getSegmentDriverNumbers(entries: QualiSegmentEntry[]): Set<number> {
  return new Set(entries.map(entry => entry.driver_number))
}

export function getSegmentLapByDriver(entries: QualiSegmentEntry[]): Map<number, number> {
  return new Map(entries.map(entry => [entry.driver_number, entry.lap_number]))
}

export function reconcileSelectedDrivers(
  selected: number[],
  drivers: DriverOption[],
  allowedDrivers: Set<number>,
  preferredCount = 2,
  maxCount = 4,
): number[] {
  const kept = selected.filter(dn => allowedDrivers.has(dn)).slice(0, maxCount)
  const next = [...kept]

  for (const driver of drivers) {
    if (!allowedDrivers.has(driver.driver_number)) continue
    if (next.length >= Math.min(preferredCount, maxCount)) break
    if (!next.includes(driver.driver_number)) next.push(driver.driver_number)
  }

  return next
}

export function getSegmentSummary(
  segment: TelemetrySegment,
  entries: QualiSegmentEntry[],
  sessionYear?: number | null,
) {
  const leader = entries[0] ?? null
  const cutoffPosition = getQualifyingAdvancePosition(sessionYear, segment)
  const cutoff = cutoffPosition !== null
    ? (entries.find(entry => entry.position === cutoffPosition) ?? entries[cutoffPosition - 1] ?? null)
    : null

  return {
    leader,
    cutoff,
    count: entries.length,
    label:
      segment === 'Q3'
        ? 'Pole shootout'
        : segment === 'Q2'
          ? 'Fight for the top 10'
          : 'Full qualifying field',
  }
}
