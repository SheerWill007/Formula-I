import { redirect } from 'next/navigation'

import { api } from '@/lib/api'
import { getLatestWeekendOverviewRoute } from '@/lib/session-weekends'

export const revalidate = 60

export default async function LatestWeekendPage() {
  const sessions = await api.sessions.list(true).catch(() => [])
  const route = getLatestWeekendOverviewRoute(sessions)

  redirect(route ?? '/sessions')
}
