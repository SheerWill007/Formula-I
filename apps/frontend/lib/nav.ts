import type { LucideIcon } from 'lucide-react'
import { BookOpen, CalendarDays, Flag, Gauge, Home, LayoutDashboard, Trophy, Users } from 'lucide-react'

export type NavItem = {
  href: string
  label: string
  icon: LucideIcon
  /** Shown in the mobile bottom bar (max 5). */
  bottom?: boolean
}

export const NAV_ITEMS: NavItem[] = [
  { href: '/', label: 'Home', icon: Home, bottom: true },
  { href: '/dashboard', label: 'Dashboard', icon: LayoutDashboard, bottom: true },
  { href: '/sessions', label: 'Sessions', icon: Flag, bottom: true },
  { href: '/telemetry', label: 'Telemetry', icon: Gauge },
  { href: '/predictions', label: 'Predictions', icon: Trophy, bottom: true },
  { href: '/schedule', label: 'Calendar', icon: CalendarDays },
  { href: '/drivers', label: 'Drivers', icon: Users, bottom: true },
  { href: '/blog', label: 'Blog', icon: BookOpen },
]

export function isActive(pathname: string, href: string): boolean {
  if (href === '/') return pathname === '/'
  return pathname === href || pathname.startsWith(`${href}/`)
}
