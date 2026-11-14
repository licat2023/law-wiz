import { onMounted, onUnmounted } from 'vue'
import { report } from './feedback'
export function usePolling(task: (signal: AbortSignal) => Promise<void>, needed: () => boolean) {
  let timer: ReturnType<typeof setTimeout> | undefined
  let controller: AbortController | undefined
  let disposed = false
  async function tick() {
    if (disposed || document.hidden || !needed()) return
    controller = new AbortController()
    try {
      await task(controller.signal)
    } catch (error) {
      if (!disposed) report(error)
    } finally {
      controller = undefined
      if (!disposed) timer = setTimeout(tick, 2500)
    }
  }
  function resume() {
    clearTimeout(timer)
    controller?.abort()
    if (!document.hidden) timer = setTimeout(tick, 2500)
  }
  onMounted(() => {
    document.addEventListener('visibilitychange', resume)
    timer = setTimeout(tick, 2500)
  })
  onUnmounted(() => {
    disposed = true
    clearTimeout(timer)
    controller?.abort()
    document.removeEventListener('visibilitychange', resume)
  })
  return { resume }
}
