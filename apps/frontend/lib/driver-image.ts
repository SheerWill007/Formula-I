/** Ordered image sources for the driver hero. First entry that loads wins. */
export type DriverImage = { src: string; kind: 'cutout' | 'headshot' }

export function normaliseDriverCode(code: string): string | null {
  const c = code.trim().toLowerCase()
  return /^[a-z]{2,4}$/.test(c) ? c : null
}

export function driverImageCandidates(code: string, headshotUrl?: string | null): DriverImage[] {
  const c = normaliseDriverCode(code)
  const out: DriverImage[] = []
  if (c) out.push({ src: `/drivers/${c}.png`, kind: 'cutout' })
  if (headshotUrl && /^https?:\/\//i.test(headshotUrl)) out.push({ src: headshotUrl, kind: 'headshot' })
  return out
}

/** Accepts "#e8002d", "e8002d" or "E8002D"; anything else gives the fallback red. */
export function teamColour(raw?: string | null, fallback = '#e8002d'): string {
  const v = (raw ?? '').trim().replace(/^#/, '')
  return /^[0-9a-fA-F]{6}$/.test(v) ? `#${v.toLowerCase()}` : fallback
}

export function ordinal(n: number | null | undefined): string {
  if (n == null) return '-'
  const v = n % 100
  if (v >= 11 && v <= 13) return `${n}th`
  return `${n}${({ 1: 'st', 2: 'nd', 3: 'rd' } as Record<number, string>)[n % 10] ?? 'th'}`
}
