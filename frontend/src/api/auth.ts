/**
 * M1 认证与用户接口。
 *
 * 与 `backend/app/slices/auth/schemas.py` 一一对应；
 * 接口编号沿用 05-接口设计 §5.1 的 A 组。
 */

import { api } from './client'
import type {
  LoginData,
  LoginRequest,
  RegisterData,
  RegisterRequest,
  UpdateProfileRequest,
  UserData,
} from './types'

/** A-01 用户注册 */
export function register(payload: RegisterRequest) {
  return api.post<RegisterData>('/auth/register', payload)
}

/** A-02 用户登录 */
export function login(payload: LoginRequest) {
  return api.post<LoginData>('/auth/login', payload)
}

/** A-03 刷新令牌（正常由 client.ts 的拦截器自动调用，此处仅供显式使用） */
export function refresh(refreshToken: string) {
  return api.post<LoginData>('/auth/refresh', { refresh_token: refreshToken })
}

/** A-04 登出 */
export function logout(refreshToken: string) {
  return api.post<null>('/auth/logout', { refresh_token: refreshToken })
}

/** A-05 获取当前用户信息（手机号与邮箱为**脱敏**值） */
export function getMe() {
  return api.get<UserData>('/users/me')
}

/** A-06 更新当前用户信息 */
export function updateMe(payload: UpdateProfileRequest) {
  return api.put<UserData>('/users/me', payload)
}
