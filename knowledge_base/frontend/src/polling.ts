/** 根据页面可见性和组件生命周期刷新知识库任务状态。 */
import { onMounted, onUnmounted } from 'vue'
import { report } from './feedback'
/**
 * 在组件挂载后调度轮询，task 应把 signal 传给可取消的请求。
 * 页面隐藏或 needed 返回 false 时暂停，状态变化时可调用 resume 重新调度。
 */
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
  /** 取消当前请求和计时，页面可见时安排下次检查。 */
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
