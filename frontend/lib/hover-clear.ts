type TimerHandle = ReturnType<typeof setTimeout>

export function createHoverClearController(clearFn: () => void, delayMs = 90) {
  let timer: TimerHandle | null = null

  return {
    schedule() {
      if (timer !== null) {
        clearTimeout(timer)
      }
      timer = setTimeout(() => {
        timer = null
        clearFn()
      }, delayMs)
    },
    cancel() {
      if (timer !== null) {
        clearTimeout(timer)
        timer = null
      }
    },
    dispose() {
      if (timer !== null) {
        clearTimeout(timer)
        timer = null
      }
    },
  }
}
