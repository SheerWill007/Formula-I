import TelemetryLandingClient from '@/components/telemetry/TelemetryLandingClient'
import { api } from '@/lib/api'

export const revalidate = 300

export default async function TelemetryLandingPage() {
  const sessions = await api.sessions.list(true).catch(() => [])
  const qualiSessions = sessions
    .filter(session => session.session_type === 'Q')
    .sort((a, b) => new Date(b.date_start ?? 0).getTime() - new Date(a.date_start ?? 0).getTime())

  return <TelemetryLandingClient initialSessions={qualiSessions} />
}
