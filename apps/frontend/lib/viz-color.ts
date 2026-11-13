/* Pure colour and number helpers for the prediction charts. */

const RAMP = ['#cde2fb', '#86b6ef', '#3987e5', '#1c5cab', '#0d366b'] // sequential blue, step 100 to 700

function hexToRgb(h: string): [number, number, number] {
  const n = parseInt(h.slice(1), 16)
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
}

/** t in [0,1] to a colour on the one hue sequential ramp. */
export function ramp(t: number): string {
  const x = Math.max(0, Math.min(1, t)) * (RAMP.length - 1)
  const i = Math.min(RAMP.length - 2, Math.floor(x))
  const f = x - i
  const a = hexToRgb(RAMP[i])
  const b = hexToRgb(RAMP[i + 1])
  const c = a.map((v, k) => Math.round(v + (b[k] - v) * f))
  return `rgb(${c[0]},${c[1]},${c[2]})`
}

export function teamHex(colour?: string | null): string {
  if (!colour) return '#737373'
  const clean = colour.replace(/^#/, '')
  return /^[0-9a-fA-F]{6}$/.test(clean) ? `#${clean}` : '#737373'
}

export const pct = (v: number | null | undefined, d = 1) =>
  v == null || Number.isNaN(v) ? '—' : `${(v * 100).toFixed(d)}%`

