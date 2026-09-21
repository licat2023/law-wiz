/**
 * 认证状态（Pinia）。
 *
 * 这里是**端到端参考实现**：其余页面（合同审查、法律问答）按同一模式组织 ——
 * store 只做状态与动作，网络细节在 `api/`，界面在 `views/`。
 */

import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import * as authApi from '@/api/auth'
import { setUnauthorizedHandler, tokenStore } from '@/api/client'
import type { LoginRequest, RegisterRequest, UpdateProfileRequest, UserData } from '@/api/types'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<UserData | null>(null)
  const loading = ref(false)

  /** 是否已登录。以"有访问令牌"为准，用户信息可能尚未拉取 */
  const isAuthenticated = computed(() => Boolean(tokenStore.access))

  const displayName = computed(
    () => user.value?.profile?.real_name || user.value?.phone || user.value?.email || '未登录',
  )

  async function doLogin(payload: LoginRequest) {
    loading.value = true
    try {
      const data = await authApi.login(payload)
      tokenStore.save(data)
      await fetchMe()
    } finally {
      loading.value = false
    }
  }

  async function doRegister(payload: RegisterRequest) {
    loading.value = true
    try {
      return await authApi.register(payload)
    } finally {
      loading.value = false
    }
  }

  async function fetchMe() {
    if (!tokenStore.access) {
      user.value = null
      return
    }
    user.value = await authApi.getMe()
  }

  async function updateProfile(payload: UpdateProfileRequest) {
    user.value = await authApi.updateMe(payload)
  }

  async function doLogout() {
    const refreshToken = tokenStore.refresh
    try {
      if (refreshToken) await authApi.logout(refreshToken)
    } catch {
      // 登出失败不应阻塞用户：本地令牌清掉即可，
      // 服务端令牌会在 TTL 到期后自然失效
    } finally {
      clearLocal()
    }
  }

  function clearLocal() {
    tokenStore.clear()
    user.value = null
  }

  // 令牌刷新失败时由 client 通知此处清理状态
  setUnauthorizedHandler(clearLocal)

  return {
    user,
    loading,
    isAuthenticated,
    displayName,
    doLogin,
    doRegister,
    fetchMe,
    updateProfile,
    doLogout,
    clearLocal,
  }
})
