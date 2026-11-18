<script setup lang="ts">
/** 业务界面外壳，负责全局导航及页面刷新后的用户资料恢复。 */
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()
const showingReview = computed(() => route.name === 'review' || route.name === 'review-detail')
const showingWorkspace = computed(() => showingReview.value || route.name === 'qa')

onMounted(async () => {
  // 刷新页面后从令牌恢复登录态
  if (auth.isAuthenticated && !auth.user) {
    try {
      await auth.fetchMe()
    } catch {
      auth.clearLocal()
      router.push({ name: 'login' })
    }
  }
})

async function handleLogout() {
  await auth.doLogout()
  router.push({ name: 'login' })
}
</script>

<template>
  <el-container class="app-shell" :class="{ 'app-shell--workspace': showingWorkspace }">
    <el-header class="app-header">
      <div class="brand" @click="router.push('/')">
        <span class="brand-mark">智法宝</span>
        <span class="brand-sub">AI 法律助手平台</span>
      </div>

      <el-menu
        v-if="auth.isAuthenticated"
        mode="horizontal"
        :default-active="showingReview ? '/review' : route.path"
        :ellipsis="false"
        class="app-menu"
        router
      >
        <el-menu-item index="/review">合同审查</el-menu-item>
        <el-menu-item index="/qa">法律问答</el-menu-item>
        <el-menu-item index="/me">个人中心</el-menu-item>
      </el-menu>

      <div class="header-right">
        <template v-if="auth.isAuthenticated">
          <span class="who">{{ auth.displayName }}</span>
          <el-button link type="primary" @click="handleLogout">退出</el-button>
        </template>
        <template v-else>
          <el-button link type="primary" @click="router.push('/login')">登录</el-button>
          <el-button link @click="router.push('/register')">注册</el-button>
        </template>
      </div>
    </el-header>

    <el-main class="app-main">
      <router-view />
    </el-main>
  </el-container>
</template>

<style scoped>
.app-shell {
  min-height: 100vh;
}

.app-header {
  display: flex;
  align-items: center;
  gap: 24px;
  border-bottom: 1px solid var(--el-border-color-light);
  background: #fff;
}

.brand {
  display: flex;
  align-items: baseline;
  gap: 8px;
  cursor: pointer;
  white-space: nowrap;
}

.brand-mark {
  font-size: 18px;
  font-weight: 700;
  color: var(--el-color-primary);
}

.brand-sub {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.app-menu {
  flex: 1;
  border-bottom: none;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
  white-space: nowrap;
}

.who {
  font-size: 13px;
  color: var(--el-text-color-regular);
}

.app-main {
  background: var(--el-bg-color-page);
}

.app-shell--workspace {
  height: 100dvh;
  min-height: 0;
}
.app-shell--workspace .app-main {
  display: flex;
  min-height: 0;
  padding: 0;
  overflow: hidden;
}

@media (max-width: 700px) {
  .app-shell--workspace .app-header {
    gap: 8px;
    padding-inline: 12px;
  }
  .app-shell--workspace .brand-sub,
  .app-shell--workspace .who {
    display: none;
  }
  .app-shell--workspace .app-menu :deep(.el-menu-item) {
    padding-inline: clamp(6px, 2vw, 12px);
  }
}
</style>
