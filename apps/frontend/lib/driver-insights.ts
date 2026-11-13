import type { DriverProfile } from '@/types/f1'

export type HeatMetric = 'finish' | 'gained' | 'points'
type Result = DriverProfile['results_grid'][number]

export const RADAR_AXES: { key: string; label: string }[] = [
  { key: 'braking_aggression', label: 'Braking' },
  { key: 'drs_usage_pct', label: 'DRS use' },
  { key: 'max_speed_capability', label: 'Top speed' },
  { key: 'lap_time_consistency', label: 'Consistency' },
  { key: 'avg_positions_gained', label: 'Overtaking' },
  { key: 'podium_rate', label: 'Podiums' },
  { key: 'dnf_rate', label: 'Reliability' },
]

/** Value in [0,1] where 1 is the strongest cell; null when there is nothing to show. */
export function cellIntensity(metric: HeatMetric, r: Result): number | null {
  if (metric === 'finish') {
    if (r.position == null) return null
    return Math.max(0, Math.min(1, (21 - r.position) / 20))
  }
  if (metric === 'gained') {
    if (r.position == null || !r.grid) return null
    return Math.max(0, Math.min(1, (r.grid - r.position + 10) / 20))
  }
  return Math.max(0, Math.min(1, r.points / 25))
}

export function cellLabel(metric: HeatMetric, r: Result): string {
  const base = `${r.year} ${r.race_name ?? `Round ${r.round}`}`
  if (metric === 'points') return `${base}: ${r.points} pts`
  if (r.position == null) return `${base}: did not finish${r.status ? ` (${r.status})` : ''}`
  if (metric === 'gained') return `${base}: ${r.grid ? `P${r.grid} to P${r.position}` : `P${r.position}`}`
  return `${base}: P${r.position}`
}

export type HeatRow = { year: number; cells: (Result | null)[] }

export function buildHeatRows(grid: Result[]): { rows: HeatRow[]; rounds: number } {
  const byYear = new Map<number, Result[]>()
  for (const r of grid) byYear.set(r.year, [...(byYear.get(r.year) ?? []), r])
  const rounds = Math.max(0, ...grid.map(r => r.round))
  const rows = [...byYear.entries()]
    .sort((a, b) => b[0] - a[0])
    .map(([year, rs]) => {
      const cells: (Result | null)[] = Array.from({ length: rounds }, () => null)
      for (const r of rs) if (r.round >= 1) cells[r.round - 1] = r
      return { year, cells }
    })
  return { rows, rounds }
}

/** Radar rows for one or two seasons; missing values plot as 0. */
export function radarData(
  history: DriverProfile['style_history'],
  season: number,
  compare?: number | null,
) {
  const a = history.find(h => h.season === season)
  const b = compare != null ? history.find(h => h.season === compare) : undefined
  return RADAR_AXES.map(ax => ({
    axis: ax.label,
    current: Math.round((a?.[ax.key] ?? 0) * 100),
    ...(b ? { compare: Math.round((b[ax.key] ?? 0) * 100) } : {}),
  }))
}
