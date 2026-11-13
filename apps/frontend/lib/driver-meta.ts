/**
 * Static driver details that the database does not hold yet. Hardcoded on purpose,
 * to be replaced by real data later. Height and weight are approximate and left out
 * where unsure, so the page shows a dash instead of a guess.
 */
export type DriverMeta = {
  name: string
  dob: string // ISO date
  nationality: string
  country: string // ISO 3166-1 alpha-2, used for the flag
  heightCm?: number
  weightKg?: number
}

export const DRIVER_META: Record<string, DriverMeta> = {
  VER: { name: 'Max Verstappen', dob: '1997-09-30', nationality: 'Dutch', country: 'NL', heightCm: 181, weightKg: 72 },
  HAM: { name: 'Lewis Hamilton', dob: '1985-01-07', nationality: 'British', country: 'GB', heightCm: 174, weightKg: 73 },
  NOR: { name: 'Lando Norris', dob: '1999-11-13', nationality: 'British', country: 'GB', heightCm: 170, weightKg: 68 },
  LEC: { name: 'Charles Leclerc', dob: '1997-10-16', nationality: 'Monégasque', country: 'MC', heightCm: 180, weightKg: 69 },
  SAI: { name: 'Carlos Sainz', dob: '1994-09-01', nationality: 'Spanish', country: 'ES', heightCm: 178, weightKg: 74 },
  RUS: { name: 'George Russell', dob: '1998-02-15', nationality: 'British', country: 'GB' },
  PIA: { name: 'Oscar Piastri', dob: '2001-04-06', nationality: 'Australian', country: 'AU', heightCm: 178, weightKg: 68 },
  ALO: { name: 'Fernando Alonso', dob: '1981-07-29', nationality: 'Spanish', country: 'ES', heightCm: 171, weightKg: 68 },
  STR: { name: 'Lance Stroll', dob: '1998-10-29', nationality: 'Canadian', country: 'CA' },
  GAS: { name: 'Pierre Gasly', dob: '1996-02-07', nationality: 'French', country: 'FR', heightCm: 177, weightKg: 70 },
  OCO: { name: 'Esteban Ocon', dob: '1996-09-17', nationality: 'French', country: 'FR' },
  ALB: { name: 'Alexander Albon', dob: '1996-03-23', nationality: 'Thai', country: 'TH', heightCm: 186, weightKg: 74 },
  TSU: { name: 'Yuki Tsunoda', dob: '2000-05-11', nationality: 'Japanese', country: 'JP', heightCm: 159, weightKg: 54 },
  HUL: { name: 'Nico Hülkenberg', dob: '1987-08-19', nationality: 'German', country: 'DE', heightCm: 184, weightKg: 76 },
  BOT: { name: 'Valtteri Bottas', dob: '1989-08-28', nationality: 'Finnish', country: 'FI', heightCm: 173, weightKg: 70 },
  PER: { name: 'Sergio Pérez', dob: '1990-01-26', nationality: 'Mexican', country: 'MX' },
  ANT: { name: 'Kimi Antonelli', dob: '2006-08-25', nationality: 'Italian', country: 'IT' },
  HAD: { name: 'Isack Hadjar', dob: '2004-09-28', nationality: 'French', country: 'FR' },
  BEA: { name: 'Oliver Bearman', dob: '2005-05-08', nationality: 'British', country: 'GB' },
  LAW: { name: 'Liam Lawson', dob: '2002-02-11', nationality: 'New Zealander', country: 'NZ' },
  COL: { name: 'Franco Colapinto', dob: '2003-05-27', nationality: 'Argentine', country: 'AR' },
  BOR: { name: 'Gabriel Bortoleto', dob: '2004-10-14', nationality: 'Brazilian', country: 'BR' },
  DOO: { name: 'Jack Doohan', dob: '2003-01-20', nationality: 'Australian', country: 'AU' },
}

export function getDriverMeta(code: string): DriverMeta | null {
  return DRIVER_META[code.trim().toUpperCase()] ?? null
}

export function ageFromDob(dob: string, now: Date = new Date()): number {
  const d = new Date(`${dob}T00:00:00Z`)
  let age = now.getUTCFullYear() - d.getUTCFullYear()
  const beforeBirthday =
    now.getUTCMonth() < d.getUTCMonth() ||
    (now.getUTCMonth() === d.getUTCMonth() && now.getUTCDate() < d.getUTCDate())
  if (beforeBirthday) age -= 1
  return age
}

/** ISO alpha-2 code to flag emoji via regional indicator symbols. */
export function flagEmoji(country: string): string {
  const c = country.trim().toUpperCase()
  if (!/^[A-Z]{2}$/.test(c)) return ''
  return String.fromCodePoint(...[...c].map(ch => 0x1f1e6 + ch.charCodeAt(0) - 65))
}

export const DRIVER_LIST = Object.entries(DRIVER_META)
  .map(([code, m]) => ({ code, ...m }))
  .sort((a, b) => a.name.split(' ').slice(-1)[0].localeCompare(b.name.split(' ').slice(-1)[0]))
