/** 统一展示知识库操作错误，支持以服务端请求 ID 排查失败。 */
import { ElMessage } from 'element-plus'
import { ApiError } from './api'
/** 忽略关闭确认框和主动取消请求，其余异常显示为错误提示。 */
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
