import type { DriverProfile } from '@/types/f1'

/**
 * PLACEHOLDER DATA. Used only where the API returned nothing, so the page can be
 * designed and reviewed before history is ingested. Delete this file (and the
 * withSample call in DriverHero) once real data flows.
 */
const YEARS = [2021, 2022, 2023, 2024, 2025]
const POINTS = [25, 18, 15, 12, 10, 8, 6, 4, 2, 1, 0]

const grid: DriverProfile['results_grid'] = YEARS.flatMap((year, yi) =>
  Array.from({ length: 22 }, (_, i) => {
    const dnf = (i + yi * 2) % 11 === 0
    const gridPos = 1 + ((i * 7 + yi * 2) % 14)
    const position = dnf ? null : Math.max(1, Math.min(20, gridPos + ((i * 3 + yi) % 5) - 2))
    return {
      year, round: i + 1, race_name: `Round ${i + 1}`, grid: gridPos, position,
      points: position ? (POINTS[position - 1] ?? 0) : 0,
      status: dnf ? 'Retired' : 'Finished',
    }
  }),
)

const seasons: DriverProfile['seasons'] = YEARS.map((year, i) => ({
  year, races: 22, wins: [0, 1, 0, 2, 1][i], podiums: [5, 9, 6, 12, 8][i],
  points: [164, 246, 200, 290, 235][i], avg_finish: [7.6, 6.1, 7.4, 5.2, 6.4][i],
  avg_grid: [7.9, 6.3, 7.1, 5.6, 6.9][i], team: ['Ferrari', 'Ferrari', 'Ferrari', 'Ferrari', 'Williams'][i],
}))

const styleHistory: DriverProfile['style_history'] = YEARS.map((season, i) => ({
  season,
  braking_aggression: [0.55, 0.62, 0.7, 0.74, 0.8][i],
  drs_usage_pct: [0.6, 0.58, 0.64, 0.7, 0.66][i],
  max_speed_capability: [0.5, 0.55, 0.52, 0.6, 0.62][i],
  lap_time_consistency: [0.72, 0.78, 0.7, 0.82, 0.85][i],
  avg_positions_gained: [0.45, 0.6, 0.5, 0.68, 0.72][i],
  podium_rate: [0.35, 0.55, 0.4, 0.7, 0.58][i],
  dnf_rate: [0.8, 0.9, 0.7, 0.85, 0.92][i],
}))

export type SampleFlags = { career: boolean; races: boolean; seasons: boolean; style: boolean }

export function withSample(p: DriverProfile): { profile: DriverProfile; sampled: SampleFlags } {
  const sampled: SampleFlags = {
    career: !p.career,
    races: p.results_grid.length === 0,
    seasons: p.seasons.length === 0,
    style: p.style_history.length === 0,
  }
  const profile: DriverProfile = {
    ...p,
    career: p.career ?? {
      grands_prix: 185, wins: 4, podiums: 29, poles: 6, career_points: 1300,
      seasons: 11, first_season: 2015, last_season: 2025,
    },
    recent_races: p.recent_races.length ? p.recent_races : grid.slice(-5).reverse().map(r => ({
      year: r.year, round: r.round, race_name: r.race_name, race_date: null,
      constructor_name: 'Williams', grid: r.grid, position: r.position,
      position_text: r.position ? String(r.position) : 'R', points: r.points, status: r.status,
    })),
    style: p.style ?? { season: 2025, archetype: 'Late Braker' },
    results_grid: sampled.races ? grid : p.results_grid,
    seasons: sampled.seasons ? seasons : p.seasons,
    style_history: sampled.style ? styleHistory : p.style_history,
  }
  return { profile, sampled }
}
