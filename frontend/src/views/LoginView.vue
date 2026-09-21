<script setup lang="ts">
/**
 * 登录页（A-02）—— **端到端参考实现**。
 *
 * 三个值得注意的处理：
 * 1. **字段级错误行内展示**：后端返回 `data.details` 里的 `field`/`reason`，
 *    直接映射到表单项，而不是笼统弹一个"登录失败"。
 * 2. **登录失败文案不透露账号是否存在**：后端统一返回 40903，
 *    前端也统一展示，不额外区分。
 * 3. **幂等性不需要**：登录是只读操作，重复提交无害。
 */
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'

import { ApiError } from '@/api/client'
import { ErrorCode } from '@/api/types'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()

const formRef = ref<FormInstance>()
const submitting = ref(false)
/** 字段级错误：由后端 data.details 填充，提交时清空 */
const fieldErrors = reactive<Record<string, string>>({})

const form = reactive({
  account: '',
  password: '',
})

const rules: FormRules = {
  account: [{ required: true, message: '请输入手机号或邮箱', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

function clearFieldErrors() {
  Object.keys(fieldErrors).forEach((k) => delete fieldErrors[k])
}

/** 把后端字段级错误映射到表单 */
function applyFieldErrors(err: ApiError) {
  clearFieldErrors()
  err.fieldErrors.forEach(({ field, reason }) => {
    fieldErrors[field] = reason
  })
}

async function handleSubmit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  submitting.value = true
  clearFieldErrors()
  try {
    await auth.doLogin({ account: form.account.trim(), password: form.password })
    ElMessage.success('登录成功')
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/review'
    router.replace(redirect)
  } catch (e) {
    if (e instanceof ApiError) {
      applyFieldErrors(e)
      // 40903 是"账号或密码错误"，后端刻意不区分两者（防账号枚举），
      // 前端也不应擅自补充猜测性提示
      if (e.code === ErrorCode.BAD_CREDENTIALS || e.code === ErrorCode.ACCOUNT_DISABLED) {
        ElMessage.error(e.message)
      } else if (e.fieldErrors.length === 0) {
        ElMessage.error(e.message)
      }
    } else {
      ElMessage.error('登录失败，请稍后重试')
    }
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="page">
    <el-card class="form-card" shadow="never">
      <h1 class="page-title">登录智法宝</h1>
      <p class="page-desc">用手机号或邮箱登录，继续处理合同与法律咨询</p>

      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-position="top"
        @submit.prevent="handleSubmit"
      >
        <el-form-item label="手机号 / 邮箱" prop="account" :error="fieldErrors.account">
          <el-input
            v-model="form.account"
            placeholder="13800000000 或 you@example.com"
            autocomplete="username"
          />
        </el-form-item>

        <el-form-item label="密码" prop="password" :error="fieldErrors.password">
          <el-input
            v-model="form.password"
            type="password"
            show-password
            placeholder="请输入密码"
            autocomplete="current-password"
            @keyup.enter="handleSubmit"
          />
        </el-form-item>

        <el-button
          type="primary"
          class="submit-btn"
          :loading="submitting"
          native-type="submit"
          style="width: 100%"
        >
          登录
        </el-button>
      </el-form>

      <div class="form-footer">
        还没有账号？
        <el-button link type="primary" @click="router.push('/register')">立即注册</el-button>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.submit-btn {
  margin-top: 4px;
}
</style>
