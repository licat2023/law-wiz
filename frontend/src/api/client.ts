/**
 * Axios 实例与拦截器。
 *
 * 职责（且仅这些）：
 * 1. 注入访问令牌（`Authorization: Bearer`）；
 * 2. **按统一响应体的 `code` 判成败**，而不是 HTTP 状态码 ——
 *    后端两者都给，但业务结果以 `code` 为准（05-接口设计 §3.2）；
 * 3. 访问令牌过期时自动刷新并**重放原请求**；
 * 4. 把字段级错误原样抛给调用方，供表单高亮。
 *
 * **不在这里弹全局提示**：提示时机属于界面决策（有的错误适合行内提示，
 * 有的适合弹窗）。这里只负责"把错误变成有结构的异常"。
 */

import axios, {
  AxiosError,
  type AxiosInstance,
  type AxiosRequestConfig,
  type InternalAxiosRequestConfig,
} from 'axios'
import { ref } from 'vue'

import { ErrorCode, type ApiResponse, type ErrorDetails, type LoginData } from './types'

const BASE_URL = import.meta.env.VITE_API_BASE ?? '/api/v1'

/** 带业务错误码的异常。界面可据 `code` 决定展示方式 */
export class ApiError extends Error {
  readonly code: number
  readonly httpStatus: number
  readonly requestId: string
  /** 字段级错误，供表单高亮 */
  readonly fieldErrors: { field: string; reason: string }[]

  constructor(opts: {
    code: number
    message: string
    httpStatus: number
    requestId: string
    fieldErrors?: { field: string; reason: string }[]
  }) {
    super(opts.message)
    this.name = 'ApiError'
    this.code = opts.code
    this.httpStatus = opts.httpStatus
    this.requestId = opts.requestId
    this.fieldErrors = opts.fieldErrors ?? []
  }

  /** 取某个字段的错误原因，供表单使用 */
  fieldError(field: string): string | undefined {
    return this.fieldErrors.find((e) => e.field === field)?.reason
  }
}

// ============================================================
// 令牌存储
// ============================================================

/**
 * 令牌存放位置。
 *
 * ⚠️ 这里**刻意放在内存 + sessionStorage**，不放 localStorage：
 * - 内存：刷新页面即失效，但配合下面的 sessionStorage 恢复；
 * - sessionStorage：关闭标签页即清除，比 localStorage 的长期驻留更保守。
 *
 * 后端不使用 `HttpOnly` Cookie（那样小程序与原生 App 无法接入，见 ADR-0010），
 * 因此 XSS 风险由前端承担 —— XSS 的根治手段是严格转义与 CSP，
 * 而不是把令牌挪到 Cookie。此处选择"存活期更短"作为风险缓解。
 */
const ACCESS_TOKEN_KEY = 'lawwiz.access_token'
const REFRESH_TOKEN_KEY = 'lawwiz.refresh_token'

// ⚠️ 令牌必须放在 `ref` 里，**不能只读 sessionStorage**：登录态判定
// （`auth.isAuthenticated`）是 computed，依赖的必须是**响应式**数据，
// 否则登录写入令牌后它不会重新求值，导航栏要刷新页面才更新。
const accessToken = ref<string | null>(sessionStorage.getItem(ACCESS_TOKEN_KEY))
const refreshToken = ref<string | null>(sessionStorage.getItem(REFRESH_TOKEN_KEY))

export const tokenStore = {
  get access(): string | null {
    return accessToken.value
  },
  get refresh(): string | null {
    return refreshToken.value
  },
  save(data: Pick<LoginData, 'access_token' | 'refresh_token'>) {
    accessToken.value = data.access_token
    refreshToken.value = data.refresh_token
    sessionStorage.setItem(ACCESS_TOKEN_KEY, data.access_token)
    sessionStorage.setItem(REFRESH_TOKEN_KEY, data.refresh_token)
  },
  clear() {
    accessToken.value = null
    refreshToken.value = null
    sessionStorage.removeItem(ACCESS_TOKEN_KEY)
    sessionStorage.removeItem(REFRESH_TOKEN_KEY)
  },
}

/** 登出时由 auth store 注入，避免此处 import store 造成循环依赖 */
let onUnauthorized: (() => void) | null = null
export function setUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn
}

// ============================================================
// 实例与拦截器
// ============================================================

export const http: AxiosInstance = axios.create({
  baseURL: BASE_URL,
  timeout: 30_000,
  headers: { 'Content-Type': 'application/json' },
})

http.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = tokenStore.access
  if (token && config.headers) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// --- 令牌刷新：并发请求需共用同一次刷新，否则会发出多个刷新请求，
//     而刷新令牌是**一次性消费**的（轮换），后到的会失败并误判为登录失效 ---
let refreshing: Promise<boolean> | null = null

async function refreshAccessToken(): Promise<boolean> {
  const refreshToken = tokenStore.refresh
  if (!refreshToken) return false

  try {
    // 用裸 axios，避免走本实例的拦截器造成递归
    const resp = await axios.post<ApiResponse<LoginData>>(
      `${BASE_URL}/auth/refresh`,
      { refresh_token: refreshToken },
      { timeout: 15_000 },
    )
    if (resp.data.code !== ErrorCode.OK || !resp.data.data) return false
    tokenStore.save(resp.data.data)
    return true
  } catch {
    return false
  }
}

function toApiError(error: AxiosError<ApiResponse<unknown>>): ApiError {
  const resp = error.response
  if (resp?.data && typeof resp.data === 'object' && 'code' in resp.data) {
    const body = resp.data
    const details = (body.data as ErrorDetails | null)?.details
    return new ApiError({
      code: body.code,
      message: body.message || '请求失败',
      httpStatus: resp.status,
      requestId: body.request_id ?? '',
      fieldErrors: details,
    })
  }

  // 网络层失败（超时、连接被拒、被网关拦截）
  const isTimeout = error.code === 'ECONNABORTED'
  return new ApiError({
    code: ErrorCode.INTERNAL_ERROR,
    message: isTimeout ? '请求超时，请稍后重试' : '网络异常，请检查网络连接',
    httpStatus: resp?.status ?? 0,
    requestId: '',
  })
}

http.interceptors.response.use(
  (resp) => resp,
  async (error: AxiosError<ApiResponse<unknown>>) => {
    const apiError = toApiError(error)
    const original = error.config as (AxiosRequestConfig & { _retried?: boolean }) | undefined

    // 访问令牌失效 → 刷新一次并重放；已重放过则不再重试
    if (
      apiError.code === ErrorCode.ACCESS_TOKEN_INVALID &&
      original &&
      !original._retried &&
      tokenStore.refresh
    ) {
      original._retried = true

      refreshing ??= refreshAccessToken().finally(() => {
        refreshing = null
      })
      const ok = await refreshing

      if (ok) {
        // 重放时重新注入新令牌
        const token = tokenStore.access
        original.headers = { ...(original.headers ?? {}), Authorization: `Bearer ${token}` }
        return http.request(original)
      }

      // 刷新也失败：登录态确实失效
      tokenStore.clear()
      onUnauthorized?.()
    }

    throw apiError
  },
)

/**
 * 统一拆包：成功返回 `data`，失败抛 `ApiError`。
 *
 * 业务码非 0 时后端通常也返回非 2xx，但**不能只依赖状态码** ——
 * 因此这里显式判 `code`，两者都覆盖。
 */
export async function request<T>(config: AxiosRequestConfig): Promise<T> {
  const resp = await http.request<ApiResponse<T>>(config)
  const body = resp.data
  if (body.code !== ErrorCode.OK) {
    const details = (body.data as ErrorDetails | null)?.details
    throw new ApiError({
      code: body.code,
      message: body.message,
      httpStatus: resp.status,
      requestId: body.request_id,
      fieldErrors: details,
    })
  }
  return body.data as T
}

export const api = {
  get: <T>(url: string, params?: Record<string, unknown>) =>
    request<T>({ method: 'GET', url, params }),
  post: <T>(url: string, data?: unknown) => request<T>({ method: 'POST', url, data }),
  put: <T>(url: string, data?: unknown) => request<T>({ method: 'PUT', url, data }),
  patch: <T>(url: string, data?: unknown) => request<T>({ method: 'PATCH', url, data }),
  delete: <T>(url: string) => request<T>({ method: 'DELETE', url }),
}
