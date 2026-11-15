/** 封装知识库管理 API 的鉴权、JSON 响应与文件下载。 */
import { ref } from 'vue'
import type { SearchResponse, SearchStrategy } from './types'

const tokenKey = 'kb-admin-token'
/** 当前标签页是否持有管理令牌。服务端拒绝令牌时由请求层清理。 */
export const authenticated = ref(Boolean(sessionStorage.getItem(tokenKey)))
/** 写入当前标签页的管理令牌。传空字符串时清除登录状态。 */
export function setToken(value: string) {
  if (value) sessionStorage.setItem(tokenKey, value)
  else sessionStorage.removeItem(tokenKey)
  authenticated.value = Boolean(value)
}
/** 保留业务错误码及请求 ID，供调用方展示或定位失败。 */
export class ApiError extends Error {
  code: number
  requestId?: string
  constructor(message: string, code: number, requestId?: string) {
    super(message)
    this.code = code
    this.requestId = requestId
  }
}
function headers(body?: BodyInit | null, idempotent = false) {
  const result = new Headers()
  const token = sessionStorage.getItem(tokenKey)
  if (token) result.set('Authorization', `Bearer ${token}`)
  // 表单上传的 Content-Type 由浏览器生成，其中包含 multipart 分隔符。
  if (body && !(body instanceof FormData)) result.set('Content-Type', 'application/json')
  if (idempotent) result.set('Idempotency-Key', crypto.randomUUID())
  return result
}
/**
 * 调用 /api 下的 JSON 端点，按业务码返回 data 或抛出 ApiError。
 * fetch 阶段取消时保留 AbortError。idempotent 为 true 时每次调用生成一个新键。
 */
export async function request<T>(
  path: string,
  options: RequestInit = {},
  idempotent = false,
): Promise<T> {
  let response: Response
  try {
    response = await fetch(`/api${path}`, {
      ...options,
      headers: headers(options.body, idempotent),
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new Error('无法连接知识库服务，请检查连接后重试。', { cause: error })
  }
  let payload: { code: number; data: T; message?: string; request_id?: string }
  try {
    payload = await response.json()
  } catch {
    throw new Error('服务返回了无法识别的响应。')
  }
  if (response.status === 401 || payload.code === 40100 || payload.code === 40101) setToken('')
  if (payload.code !== 0)
    throw new ApiError(payload.message || '操作失败，请重试。', payload.code, payload.request_id)
  return payload.data
}
export const get = <T>(path: string, signal?: AbortSignal) => request<T>(path, { signal })
export const post = <T>(path: string, data: unknown, idempotent = false) =>
  request<T>(path, { method: 'POST', body: JSON.stringify(data) }, idempotent)
export const patch = <T>(path: string, data: unknown) =>
  request<T>(path, { method: 'PATCH', body: JSON.stringify(data) })
export const remove = (path: string) => request<{ id: string }>(path, { method: 'DELETE' })
/** 生成知识库端点路径，id 按单个 URL 路径段编码。 */
export const basePath = (id: string) => `/knowledge-bases/${encodeURIComponent(id)}`
/** 生成指定知识库下的文档端点路径。 */
export const documentPath = (kb: string, doc: string) =>
  `${basePath(kb)}/documents/${encodeURIComponent(doc)}`
/** 为管理端检索测试返回各阶段的候选排名。 */
export const searchKnowledgeBase = (
  kb: string,
  options: {
    query: string
    top_k: number
    include_abolished: boolean
    doc_type?: string
    corpus_tier?: number
    strategy?: SearchStrategy
  },
) => post<SearchResponse>(`${basePath(kb)}/search`, { ...options, diagnostics: true })
/** 通过带认证头的请求读取文档原件，并以指定文件名触发浏览器下载。 */
export async function download(path: string, filename: string) {
  const response = await fetch(`/api${path}/file`, { headers: headers() })
  if (!response.ok || response.headers.get('content-type')?.includes('application/json')) {
    const data = await response.json()
    if (response.status === 401) setToken('')
    throw new Error(data.message || '下载失败。')
  }
  const url = URL.createObjectURL(await response.blob())
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.append(anchor)
  anchor.click()
  anchor.remove()
  // 给浏览器留出读取对象 URL 的时间。
  setTimeout(() => URL.revokeObjectURL(url), 60_000)
}
