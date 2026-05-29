import { afterEach, describe, expect, it, vi } from 'vitest'

import { createHoverClearController } from '@/lib/hover-clear'

describe('hover clear controller', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it('delays the clear callback until the grace period expires', () => {
    vi.useFakeTimers()
    const clearFn = vi.fn()
    const controller = createHoverClearController(clearFn, 90)

    controller.schedule()
    vi.advanceTimersByTime(89)

    expect(clearFn).not.toHaveBeenCalled()

    vi.advanceTimersByTime(1)

    expect(clearFn).toHaveBeenCalledTimes(1)
  })

  it('cancels a pending clear when hover resumes quickly', () => {
    vi.useFakeTimers()
    const clearFn = vi.fn()
    const controller = createHoverClearController(clearFn, 90)

    controller.schedule()
    vi.advanceTimersByTime(40)
    controller.cancel()
    vi.advanceTimersByTime(100)

    expect(clearFn).not.toHaveBeenCalled()
  })

  it('resets the timer when schedule is called again', () => {
    vi.useFakeTimers()
    const clearFn = vi.fn()
    const controller = createHoverClearController(clearFn, 90)

    controller.schedule()
    vi.advanceTimersByTime(60)
    controller.schedule()
    vi.advanceTimersByTime(60)

    expect(clearFn).not.toHaveBeenCalled()

    vi.advanceTimersByTime(30)

    expect(clearFn).toHaveBeenCalledTimes(1)
  })
})
