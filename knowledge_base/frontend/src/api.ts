import { ref } from 'vue'

const tokenKey = 'kb-admin-token'
export const authenticated = ref(Boolean(sessionStorage.getItem(tokenKey)))
export function setToken(value: string) {
  if (value) sessionStorage.setItem(tokenKey, value)
  else sessionStorage.removeItem(tokenKey)
  authenticated.value = Boolean(value)
}
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
  if (body && !(body instanceof FormData)) result.set('Content-Type', 'application/json')
  if (idempotent) result.set('Idempotency-Key', crypto.randomUUID())
  return result
}
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
export const basePath = (id: string) => `/knowledge-bases/${encodeURIComponent(id)}`
export const documentPath = (kb: string, doc: string) =>
  `${basePath(kb)}/documents/${encodeURIComponent(doc)}`
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
  setTimeout(() => URL.revokeObjectURL(url), 60_000)
}
