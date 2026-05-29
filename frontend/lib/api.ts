import type {
  Session, Driver, Lap, FastestLap, DriverComparison, HealthStatus
} from '@/types/f1'

const BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

class APIError extends Error {
  constructor(public status: number, message: string) {
    super(message)
    this.name = 'APIError'
  }
}

async function get<T>(path: string, serverOnly = false): Promise<T> {
  const options: RequestInit = {
    headers: { 'Content-Type': 'application/json' },
    // Only add next.revalidate in server context
    ...(serverOnly ? { next: { revalidate: 60 } } : { cache: 'no-store' }),
  }
  const res = await fetch(`${BASE}${path}`, options)
  if (!res.ok) {
    throw new APIError(res.status, `API ${res.status}: ${path}`)
  }
  return res.json() as Promise<T>
}

// server = true for Server Components, false (default) for Client Components
export const api = {
  health: {
    get: () => get<HealthStatus>('/health'),
  },
  sessions: {
    list: (server = false) => get<Session[]>('/api/v1/sessions', server),
    get: (key: number, server = false) => get<Session>(`/api/v1/sessions/${key}`, server),
  },
  laps: {
    list: (key: number, driver?: number) =>
      get<Lap[]>(`/api/v1/sessions/${key}/laps${driver ? `?driver=${driver}` : ''}`),
    driver: (key: number, num: number) =>
      get<{ laps: Lap[]; theoretical_best: Record<string, number> | null }>(
        `/api/v1/sessions/${key}/drivers/${num}/laps`
      ),
    fastest: (key: number, server = false) =>
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      get<{ laps: FastestLap[], fastest_s1: any, fastest_s2: any, fastest_s3: any }>(`/api/v1/sessions/${key}/fastest`, server),
  },
  drivers: {
    list: (key: number, server = false) =>
      get<Driver[]>(`/api/v1/sessions/${key}/drivers`, server),
    compare: (key: number, drivers: number[]) =>
      get<DriverComparison[]>(
        `/api/v1/sessions/${key}/drivers/compare?drivers=${drivers.join(',')}`
      ),
  },
}

export { APIError }

// Add these inside the api object — paste after drivers block:
export const strategyApi = {
  stints: (key: number) => get<import('@/types/f1').Stint[]>(`/api/v1/sessions/${key}/strategy`),
  raceOrder: (key: number) => get<import('@/types/f1').RacePosition[]>(`/api/v1/sessions/${key}/race-order`),
}

export const telemetryApi = {
  driver: (key: number, num: number) =>
    get<{ driver_number: number; lap_number: number; samples: import('@/types/f1').TelemetrySample[] }>(
      `/api/v1/sessions/${key}/telemetry/${num}`
    ),
  compare: (key: number, drivers: number[]) =>
    get<Record<string, { lap_number: number; samples: import('@/types/f1').TelemetrySample[] }>>(
      `/api/v1/sessions/${key}/telemetry/compare?drivers=${drivers.join(',')}`
    ),
  stats: (key: number, drivers?: number[]) => {
    const q = drivers?.length ? `?drivers=${drivers.join(',')}` : ''
    return get<import('@/types/f1').DriverTelemetryStats[]>(
      `/api/v1/sessions/${key}/telemetry/stats${q}`
    )
  },

}

export const predictionsApi = {
  predict: (qualiKey: number) =>
    get<import('@/types/f1').PredictionResponse>(
      `/api/v1/sessions/${qualiKey}/predict`
    ),
}