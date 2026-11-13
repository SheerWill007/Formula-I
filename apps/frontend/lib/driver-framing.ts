/**
 * Per-driver framing for the private cutouts in public/drivers/. The images
 * differ in crop and resolution, so each gets its own size and position.
 *
 * kind "crop": cut off at the thighs or torso. Fills the hero height, bleeds off
 *              the bottom and fades into the floor.
 * kind "full": shoes visible. Smaller, stands on the floor with a shadow.
 * height:      figure height as a percentage of the hero stage.
 * x:           horizontal nudge in percent of the figure width.
 *
 * Run scripts/trim-driver-images.py after adding images so the silhouettes are
 * trimmed before tuning these numbers.
 */
export type Framing = { kind: 'full' | 'crop'; height: number; x: number }

export const DEFAULT_FRAMING: Framing = { kind: 'crop', height: 100, x: 0 }

const FRAMING: Record<string, Partial<Framing>> = {
  sai: { kind: 'crop', height: 102 },
  nor: { kind: 'crop', height: 100 },
  pia: { kind: 'crop', height: 90 }, // wide pose, arms raised
  ham: { kind: 'crop', height: 100 },
  alb: { kind: 'crop', height: 100 },
  alo: { kind: 'full', height: 90 },
  lec: { kind: 'full', height: 84 }, // smallest source (377px tall); about 1.8x upscale at most
  str: { kind: 'full', height: 88 },
}

export function framingFor(code: string): Framing {
  return { ...DEFAULT_FRAMING, ...(FRAMING[code.trim().toLowerCase()] ?? {}) }
}
