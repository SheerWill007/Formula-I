import { describe, expect, it } from 'vitest'
import { NAV_ITEMS, isActive } from './nav'

describe('isActive', () => {
  it('matches home only on the root path', () => {
    expect(isActive('/', '/')).toBe(true)
    expect(isActive('/sessions', '/')).toBe(false)
  })

  it('matches a section and its child pages', () => {
    expect(isActive('/sessions', '/sessions')).toBe(true)
    expect(isActive('/sessions/9158/telemetry', '/sessions')).toBe(true)
    expect(isActive('/drivers/VER', '/drivers')).toBe(true)
  })

  it('does not match a different section sharing a prefix', () => {
    expect(isActive('/sessions-archive', '/sessions')).toBe(false)
  })
})

describe('NAV_ITEMS', () => {
  it('includes predictions and telemetry so every section is reachable', () => {
    const hrefs = NAV_ITEMS.map(i => i.href)
    expect(hrefs).toContain('/predictions')
    expect(hrefs).toContain('/telemetry')
  })

  it('keeps the mobile bottom bar to five items', () => {
    expect(NAV_ITEMS.filter(i => i.bottom)).toHaveLength(5)
  })
})
