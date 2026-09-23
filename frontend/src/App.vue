<script setup lang="ts">
/**
 * 根组件：顶部导航 + 内容区。
 *
 * 导航项**只列一期已实现的板块** —— 把 P2–P4 的入口画上去但点不开，
 * 会让演示时显得残缺；宁可到实现时再加。
 */
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()

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
  <el-container class="app-shell">
    <el-header class="app-header">
      <div class="brand" @click="router.push('/')">
        <span class="brand-mark">智法宝</span>
        <span class="brand-sub">AI 法律助手平台</span>
      </div>

      <el-menu
        v-if="auth.isAuthenticated"
        mode="horizontal"
        :default-active="$route.path"
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
</style>
