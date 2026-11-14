<script setup lang="ts">
/** 使用独立的知识库管理账号登录，成功后保存当前标签页的访问令牌。 */
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Collection } from '@element-plus/icons-vue'
import { post, setToken } from '../api'
const router = useRouter()
const form = reactive({ username: '', password: '' })
const busy = ref(false),
  error = ref('')
async function login() {
  error.value = ''
  if (!form.username.trim() || !form.password) {
    error.value = '请填写管理员账号和密码。'
    return
  }
  busy.value = true
  try {
    const result = await post<{ access_token: string }>('/auth/login', form)
    setToken(result.access_token)
    form.password = ''
    await router.replace('/')
  } catch (e) {
    error.value = e instanceof Error ? e.message : '登录失败，请重试。'
  } finally {
    busy.value = false
  }
}
</script>
<template>
  <div class="login-page">
    <section class="login-story">
      <el-icon :size="44"><Collection /></el-icon>
      <h1>让知识有据可循。</h1>
      <p>归集文档，整理上下文。<br />在每一次检索中，回到准确的来源。</p>
      <div class="login-rule" />
      <span>知识库管理工作台</span>
    </section>
    <section class="login-form">
      <h2>管理员登录</h2>
      <p class="muted">使用知识库的独立管理账号继续。</p>
      <el-form label-position="top" @submit.prevent="login">
        <el-form-item label="管理员账号" for="username"
          ><el-input
            id="username"
            v-model="form.username"
            autocomplete="username"
            autofocus
            :disabled="busy"
        /></el-form-item>
        <el-form-item label="密码" for="password"
          ><el-input
            id="password"
            v-model="form.password"
            type="password"
            show-password
            autocomplete="current-password"
            :disabled="busy"
        /></el-form-item>
        <p v-if="error" role="alert" class="error-text">{{ error }}</p>
        <el-button type="primary" native-type="submit" :loading="busy" class="full-width"
          >登录工作台</el-button
        >
      </el-form>
    </section>
  </div>
</template>
