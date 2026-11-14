import { ElMessage } from 'element-plus'
import { ApiError } from './api'
export function report(error: unknown) {
  if (error === 'cancel' || error === 'close') return
  if (error instanceof DOMException && error.name === 'AbortError') return
  const message = error instanceof Error ? error.message : '操作失败，请重试。'
  ElMessage({
    type: 'error',
    message:
      error instanceof ApiError && error.requestId
        ? `${message}（请求 ${error.requestId}）`
        : message,
    duration: 6000,
  })
}
