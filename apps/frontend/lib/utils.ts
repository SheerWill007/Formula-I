// ── Utility functions used across the app ────────────────────────────────────

/** Format milliseconds as M:SS.mmm  e.g. 85819 → "1:25.819" */
export function formatLapTime(ms: number | null | undefined): string {
  if (ms == null) return '—'
  const totalSeconds = ms / 1000
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = (totalSeconds % 60).toFixed(3).padStart(6, '0')
  return minutes > 0 ? `${minutes}:${seconds}` : `${seconds}s`
}

/** Format gap e.g. 171 → "+0.171s" */
export function formatGap(ms: number | null | undefined): string {
  if (ms == null || ms === 0) return '—'
  return `+${(ms / 1000).toFixed(3)}s`
}

/** Ensure hex colour has # prefix */
// eslint-disable-next-line @typescript-eslint/no-unused-vars
export function teamColour(colour: string | null | undefined, teamName?: string | null): string {
  if (!colour) return '#666666'
  return colour.startsWith('#') ? colour : `#${colour}`
}

/** Tyre compound colours */
export const COMPOUND_COLOURS: Record<string, string> = {
  SOFT: '#FF3333',
  MEDIUM: '#FFD700',
  HARD: '#FFFFFF',
  INTER: '#39B54A',
  INTERMEDIATE: '#39B54A',
  WET: '#0067FF',
}

export const COMPOUND_LABEL: Record<string, string> = {
  SOFT: 'S', MEDIUM: 'M', HARD: 'H', INTER: 'I', INTERMEDIATE: 'I', WET: 'W',
}

/**
 * Circuit hero images — real city/track photography via Unsplash.
 * Matched by GP name substring so partial matches work.
 */
const CIRCUIT_IMAGE_MAP: Array<[string, string]> = [
  ['Australian', 'https://images.unsplash.com/photo-1546412414-e1885259563a?w=1200&q=85'],
  ['Chinese', 'https://images.unsplash.com/photo-1537531383496-91af4b7ed77b?w=1200&q=85'],
  ['Japanese', 'https://images.unsplash.com/photo-1528360983277-13d401cdc186?w=1200&q=85'],
  ['Bahrain', 'https://images.unsplash.com/photo-1586374579358-9d19d632b6df?w=1200&q=85'],
  ['Saudi', 'https://images.unsplash.com/photo-1568605114967-8130f3a36994?w=1200&q=85'],
  ['Miami', 'https://images.unsplash.com/photo-1533106497176-45ae19e68ba2?w=1200&q=85'],
  ['Canadian', 'https://images.unsplash.com/photo-1519861531473-9200262188bf?w=1200&q=85'],
  ['Monaco', 'https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=1200&q=85'],
  ['Spanish', 'https://images.unsplash.com/photo-1504711434969-e33886168f5c?w=1200&q=85'],
  ['Barcelona', 'https://images.unsplash.com/photo-1504711434969-e33886168f5c?w=1200&q=85'],
  ['Austrian', 'https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=1200&q=85'],
  ['British', 'https://images.unsplash.com/photo-1504711434969-e33886168f5c?w=1200&q=85'],
  ['Silverstone', 'https://images.unsplash.com/photo-1504711434969-e33886168f5c?w=1200&q=85'],
  ['Belgian', 'https://images.unsplash.com/photo-1600585152220-90363fe7e115?w=1200&q=85'],
  ['Hungarian', 'https://images.unsplash.com/photo-1563213126-a4273aed2016?w=1200&q=85'],
  ['Dutch', 'https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=1200&q=85'],
  ['Italian', 'https://images.unsplash.com/photo-1504711434969-e33886168f5c?w=1200&q=85'],
  ['Monza', 'https://images.unsplash.com/photo-1504711434969-e33886168f5c?w=1200&q=85'],
  ['Azerbaijan', 'https://images.unsplash.com/photo-1586374579358-9d19d632b6df?w=1200&q=85'],
  ['Singapore', 'https://images.unsplash.com/photo-1525625293386-3f8f99389edd?w=1200&q=85'],
  ['United States', 'https://images.unsplash.com/photo-1533106497176-45ae19e68ba2?w=1200&q=85'],
  ['Austin', 'https://images.unsplash.com/photo-1533106497176-45ae19e68ba2?w=1200&q=85'],
  ['Mexico', 'https://images.unsplash.com/photo-1518105779142-d975f22f1b0a?w=1200&q=85'],
  ['São Paulo', 'https://images.unsplash.com/photo-1518105779142-d975f22f1b0a?w=1200&q=85'],
  ['Brazilian', 'https://images.unsplash.com/photo-1518105779142-d975f22f1b0a?w=1200&q=85'],
  ['Las Vegas', 'https://images.unsplash.com/photo-1605833556294-ea5c7a74f57d?w=1200&q=85'],
  ['Qatar', 'https://images.unsplash.com/photo-1586374579358-9d19d632b6df?w=1200&q=85'],
  ['Abu Dhabi', 'https://images.unsplash.com/photo-1509804428544-c2f9298e62a4?w=1200&q=85'],
]

const CIRCUIT_NAME_MAP: Array<[string, string]> = [
  ['Australian', 'Albert Park Circuit'],
  ['Chinese', 'Shanghai International Circuit'],
  ['Japanese', 'Suzuka Circuit'],
  ['Bahrain', 'Bahrain International Circuit'],
  ['Saudi', 'Jeddah Corniche Circuit'],
  ['Miami', 'Miami International Autodrome'],
  ['Emilia Romagna', 'Autodromo Enzo e Dino Ferrari'],
  ['Monaco', 'Circuit de Monaco'],
  ['Spanish', 'Circuit de Barcelona-Catalunya'],
  ['Canadian', 'Circuit Gilles Villeneuve'],
  ['Austrian', 'Red Bull Ring'],
  ['British', 'Silverstone Circuit'],
  ['Belgian', 'Circuit de Spa-Francorchamps'],
  ['Hungarian', 'Hungaroring'],
  ['Dutch', 'Circuit Zandvoort'],
  ['Italian', 'Autodromo Nazionale Monza'],
  ['Azerbaijan', 'Baku City Circuit'],
  ['Singapore', 'Marina Bay Street Circuit'],
  ['United States', 'Circuit of the Americas'],
  ['Mexico', 'Autodromo Hermanos Rodriguez'],
  ['São Paulo', 'Interlagos'],
  ['Las Vegas', 'Las Vegas Strip Circuit'],
  ['Qatar', 'Lusail International Circuit'],
  ['Abu Dhabi', 'Yas Marina Circuit'],
]

export function getCircuitImage(gpName: string): string {
  if (!gpName) return 'https://images.unsplash.com/photo-1504711434969-e33886168f5c?w=1200&q=85'
  const match = CIRCUIT_IMAGE_MAP.find(([key]) =>
    gpName.toLowerCase().includes(key.toLowerCase())
  )
  return match
    ? match[1]
    : 'https://images.unsplash.com/photo-1504711434969-e33886168f5c?w=1200&q=85'
}

export function getCircuitName(gpName: string): string | null {
  if (!gpName) return null
  const match = CIRCUIT_NAME_MAP.find(([key]) =>
    gpName.toLowerCase().includes(key.toLowerCase())
  )
  return match?.[1] ?? null
}

/** Abbreviation for session type */
export function sessionTypeLabel(type: string): string {
  const map: Record<string, string> = {
    R: 'Race',
    Q: 'Qualifying',
    FP1: 'Practice 1',
    FP2: 'Practice 2',
    FP3: 'Practice 3',
    S: 'Sprint',
    SQ: 'Sprint Qualifying',
    SS: 'Sprint Shootout',
  }
  return map[type] ?? type
}
