// ── Core F1 types — mirror your Flask API response shapes exactly ──────────

export interface Session {
  session_key: number
  year: number
  gp_name: string
  country: string | null
  session_type: 'R' | 'Q' | 'FP1' | 'FP2' | 'FP3' | 'SS' | 'SQ' | 'S'
  session_name: string
  date_start: string | null
  drivers?: Driver[]
  track_temp_c?: number | null
  air_temp_c?: number | null
  humidity_pct?: number | null
  rainfall?: boolean | null
}

export interface Driver {
  driver_number: number
  full_name: string
  abbreviation: string
  team_name: string | null
  team_colour: string | null
  best_lap_ms?: number | null
  total_laps?: number
}

export interface Lap {
  driver_number: number
  abbreviation: string
  team_name: string | null
  team_colour: string | null
  lap_number: number
  lap_time_ms: number | null
  s1_ms: number | null
  s2_ms: number | null
  s3_ms: number | null
  compound: 'SOFT' | 'MEDIUM' | 'HARD' | 'INTER' | 'INTERMEDIATE' | 'WET' | null
  tyre_life_laps: number | null
  is_personal_best: boolean
  track_status: string | null
  deleted: boolean
}

export interface FastestLap {
  driver_number: number
  abbreviation: string
  team_name: string | null
  team_colour: string | null
  lap_number: number
  lap_time_ms: number
  compound: string | null
}

export interface DriverComparison {
  driver_number: number
  abbreviation: string
  team_name: string | null
  team_colour: string | null
  best_lap_ms: number | null
  best_s1_ms: number | null
  best_s2_ms: number | null
  best_s3_ms: number | null
  theoretical_best_ms: number | null
  lap_time_stddev: number | null
  total_laps: number
  gap_to_fastest_ms: number | null
}

export interface HealthStatus {
  status: 'ok' | 'degraded'
  database: 'ok' | 'unreachable'
  version: string
}

export interface Stint {
  driver_number: number
  abbreviation:  string
  team_colour:   string | null
  compound:      string | null
  stint_num:     number
  lap_start:     number
  lap_end:       number
  lap_count:     number
}

export interface RacePosition {
  driver_number: number
  abbreviation:  string
  team_colour:   string | null
  team_name:     string | null
  position:      number | null
}

// Column names match the actual DB schema (renamed from generic speed/throttle)
export interface TelemetrySample {
  speed_kmh:    number | null   // km/h
  throttle_pct: number | null   // 0–100
  rpm:          number | null   // added
  brake:        boolean | null
  gear:         number | null   // 1–8
  drs:          number | null   // 0/8/10/12/14 — >8 means DRS open
  distance_m:   number | null   // metres into lap — used for spatial alignment
  driver_number?: number        // added for multi-driver comparison
  x_pos:        number | null   // track map X coordinate
  y_pos:        number | null   // track map Y coordinate
  distance_pct?: number         // computed by API: 0–100
  // Compatibility aliases
  speed?:       number | null
  throttle?:    number | null
}

export interface ShapFactor {
  feature:    string
  label:      string
  shap_value: number
  positive:   boolean
}

export interface DriverPrediction {
  driver_number:           number
  abbreviation:            string
  team_name:               string | null
  grid_position:           number
  predicted_position:      number
  win_probability:         number
  podium_probability:      number
  position_probabilities:  Record<string, number>
  shap_factors:            ShapFactor[]
}

export interface PredictionResponse {
  quali_session_key: number
  predictions:       DriverPrediction[]
  model_info:        { name: string; version: string }
}

export interface CornerStat {
  corner_num:       number
  distance_m:       number
  min_speed_kmh:    number
  entry_speed_kmh:  number
  exit_speed_kmh:   number
  brake_point_m:    number | null
  throttle_point_m: number | null
  min_gear:         number
  apex_rpm:         number | null
}

export interface DriverTelemetryStats {
  driver_number:       number
  abbreviation:        string
  team_colour:         string | null
  lap_number:          number
  corners:             CornerStat[]
  speed_trap_1_kmh:    number | null
  speed_trap_2_kmh:    number | null
  max_speed_kmh:       number
  max_rpm:             number | null
  avg_rpm_pct:         number | null
  avg_brake_point_pct: number | null
  drs_open_pct:        number | null
}

export interface RaceIntelligenceSession {
  session_key: number
  year: number
  gp_name: string
  session_type: string
  session_name: string
}

export interface DriverState{
  driver_number: number
  abbreviation: string
  team_name: string | null
  team_color: string | null
  clean_laps: number
  avg_clean_ms: number | null
  pace_stddev_ms: number | null
  first_position: number | null
  final_position: number | null
  positions_gained: number | null
  pit_stops: number
  compounds: string[]
}
export interface StintSummary{
  driver_number: number
  abbreviation: string
  team_name: string | null
  team_colour: string | null
  stint: number
  compound: string
  start_lap: number
  end_lap: number
  lap_count: number
  avg_lap_ms: number
  best_lap_ms: number
  degradation_ms_per_lap: number | null
}
export interface CompoundPace{
  compound: string
  lap_count: number
  avg_lap_ms: number | null
  median_lap_ms: number | null
  best_lap_ms: number | null
}

export interface BattleGap {
  lap_number: number
  ahead: string
  behind: string
  ahead_driver_number: number
  behind_driver_number: number
  position_ahead: number
  gap_ms: number
  gap_s: number
  behind_compound: string | null
  behind_tyre_life_laps: number | null
}

export interface UndercutCandidate {
  lap_number: number
  ahead: string
  behind: string
  gap_s: number
  pace_advantage_ms: number
  signal: string
}

export interface DriverScore {
  driver_number: number
  abbreviation: string
  team_colour: string | null
  score: number
  inputs: {
    avg_clean_ms: number | null
    pace_stddev_ms: number | null
    positions_gained: number | null
    pit_stops: number
  }
}
export interface RaceInsight {
  id: string
  tier: 'CRITICAL' | 'NOTABLE' | 'INFO'
  category: string
  title: string
  detail: string
  evidence: Record<string, unknown>
}

export interface RaceIntelligenceMetadata {
  source: string
  method: string
  llm_used: boolean
  features: string[]
}

export interface RaceIntelligenceResponse {
  session: RaceIntelligenceSession
  driver_states: DriverState[]
  stint_summaries: StintSummary[]
  compound_pace: CompoundPace[]
  stint_phase_summaries: StintPhaseSummary[]
  battle_gaps: BattleGap[]
  undercut_candidates: UndercutCandidate[]
  driver_scores: DriverScore[]
  insights: RaceInsight[]
  metadata: RaceIntelligenceMetadata
}
export interface StintPhaseSummary {
  driver_number: number
  abbreviation: string
  team_colour: string | null
  stint: number
  compound: string
  phase: string
  lap_count: number
  avg_lap_ms: number | null
}

export interface RaceIntelligenceEvent {
  id: number
  session_key: number
  event_type: string
  event_key: string
  driver_number: number | null
  lap_number: number | null
  payload: Record<string, unknown>
  created_at: string | null
  updated_at: string | null
}

export interface RaceIntelligenceEventsResponse {
  session_key: number
  event_count: number
  events: RaceIntelligenceEvent[]
}