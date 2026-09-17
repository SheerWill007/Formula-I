export function isPracticeSessionType(sessionType: string): boolean {
  return sessionType.startsWith('FP')
}

export function getSessionRoute(sessionKey: number, sessionType: string): string {
  return isPracticeSessionType(sessionType)
    ? `/sessions/${sessionKey}/telemetry`
    : `/sessions/${sessionKey}`
}

export function getSessionOverviewRoute(sessionKey: number): string {
  return `/sessions/${sessionKey}/overview`
}

export function getSessionTelemetryRoute(sessionKey: number): string {
  return `/sessions/${sessionKey}/telemetry`
}
