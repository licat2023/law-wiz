<script setup lang="ts">
import { watch } from 'vue'
import { useRouter } from 'vue-router'
import { Collection, Document, Search, SwitchButton } from '@element-plus/icons-vue'
import { authenticated, setToken } from './api'
const router = useRouter()
watch(authenticated, (value) => {
  if (!value) void router.replace('/login')
})
function logout() {
  setToken('')
}
function focusMain() {
  document.getElementById('main')?.focus()
}
</script>
<template>
  <a class="skip-link" href="#main" @click.prevent="focusMain">跳转到主内容</a>
  <div v-if="authenticated" class="app-shell">
    <aside class="sidebar">
      <router-link to="/" class="brand"
        ><el-icon :size="27"><Collection /></el-icon
        ><span>知识库<span class="brand-subtitle">文档与检索工作台</span></span></router-link
      >
      <div class="side-caption">管理工作区</div>
      <router-link to="/" class="side-nav"
        ><el-icon><Document /></el-icon>知识库与文档</router-link
      >
      <div class="side-context">
        <el-icon><Search /></el-icon>
        <p>从文档到可靠依据<span>管理来源、检查索引，验证每一次召回。</span></p>
      </div>
      <div class="side-footer">
        <span class="admin-dot" />管理员<el-button
          text
          class="logout"
          aria-label="退出登录"
          @click="logout"
          ><el-icon><SwitchButton /></el-icon
        ></el-button>
      </div>
    </aside>
    <main id="main" class="main-panel" tabindex="-1"><router-view :key="$route.path" /></main>
  </div>
  <main v-else id="main" tabindex="-1"><router-view /></main>
</template>
