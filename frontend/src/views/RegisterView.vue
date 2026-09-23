<script setup lang="ts">
/**
 * 注册页（A-01）。
 *
 * ⚠️ **验证码说明**：一期没有接入短信/邮件通道（无法自建，见 02-技术栈 §3.6）。
 * 开发环境后端接受固定验证码 `000000`，并在日志打印本应发送的内容。
 * 页面上直接写明这一点 —— 否则队友会以为验证码发丢了。
 */
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'

import { ApiError } from '@/api/client'
import { ErrorCode } from '@/api/types'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()

const formRef = ref<FormInstance>()
const submitting = ref(false)
const fieldErrors = reactive<Record<string, string>>({})

/** 注册方式：手机号或邮箱（后端要求至少提供一个） */
const mode = ref<'phone' | 'email'>('phone')

const form = reactive({
  phone: '',
  email: '',
  password: '',
  confirmPassword: '',
  verify_code: '',
})

const rules = computed<FormRules>(() => ({
  phone:
    mode.value === 'phone'
      ? [
          { required: true, message: '请输入手机号', trigger: 'blur' },
          { pattern: /^1[3-9]\d{9}$/, message: '手机号格式不正确', trigger: 'blur' },
        ]
      : [],
  email:
    mode.value === 'email'
      ? [
          { required: true, message: '请输入邮箱', trigger: 'blur' },
          { type: 'email', message: '邮箱格式不正确', trigger: 'blur' },
        ]
      : [],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 8, max: 64, message: '密码长度 8–64 位', trigger: 'blur' },
    {
      validator: (_r, v: string, cb) =>
        /[A-Za-z]/.test(v) && /\d/.test(v) ? cb() : cb(new Error('密码需同时包含字母与数字')),
      trigger: 'blur',
    },
  ],
  confirmPassword: [
    { required: true, message: '请再次输入密码', trigger: 'blur' },
    {
      validator: (_r, v: string, cb) =>
        v === form.password ? cb() : cb(new Error('两次输入的密码不一致')),
      trigger: 'blur',
    },
  ],
  verify_code: [{ required: true, message: '请输入验证码', trigger: 'blur' }],
}))

function clearFieldErrors() {
  Object.keys(fieldErrors).forEach((k) => delete fieldErrors[k])
}

async function handleSubmit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  submitting.value = true
  clearFieldErrors()
  try {
    await auth.doRegister({
      phone: mode.value === 'phone' ? form.phone : undefined,
      email: mode.value === 'email' ? form.email : undefined,
      password: form.password,
      verify_code: form.verify_code,
    })
    ElMessage.success('注册成功，请登录')
    router.replace({
      name: 'login',
      query: { account: mode.value === 'phone' ? form.phone : form.email },
    })
  } catch (e) {
    if (e instanceof ApiError) {
      e.fieldErrors.forEach(({ field, reason }) => {
        fieldErrors[field] = reason
      })
      if (e.code === ErrorCode.PHONE_TAKEN || e.code === ErrorCode.EMAIL_TAKEN) {
        ElMessage.error(e.message)
      } else if (e.fieldErrors.length === 0) {
        ElMessage.error(e.message)
      }
    } else {
      ElMessage.error('注册失败，请稍后重试')
    }
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="page">
    <el-card class="form-card" shadow="never">
      <h1 class="page-title">注册智法宝</h1>
      <p class="page-desc">手机号与邮箱二选一即可</p>

      <el-radio-group v-model="mode" style="margin-bottom: 16px">
        <el-radio-button value="phone">手机号</el-radio-button>
        <el-radio-button value="email">邮箱</el-radio-button>
      </el-radio-group>

      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-position="top"
        @submit.prevent="handleSubmit"
      >
        <el-form-item
          v-if="mode === 'phone'"
          label="手机号"
          prop="phone"
          :error="fieldErrors.phone"
        >
          <el-input v-model="form.phone" placeholder="13800000000" maxlength="11" />
        </el-form-item>

        <el-form-item v-else label="邮箱" prop="email" :error="fieldErrors.email">
          <el-input v-model="form.email" placeholder="you@example.com" />
        </el-form-item>

        <el-form-item label="密码" prop="password" :error="fieldErrors.password">
          <el-input
            v-model="form.password"
            type="password"
            show-password
            placeholder="至少 8 位，含字母与数字"
          />
        </el-form-item>

        <el-form-item label="确认密码" prop="confirmPassword">
          <el-input
            v-model="form.confirmPassword"
            type="password"
            show-password
            placeholder="再次输入密码"
          />
        </el-form-item>

        <el-form-item label="验证码" prop="verify_code" :error="fieldErrors.verify_code">
          <el-input v-model="form.verify_code" placeholder="开发环境固定为 000000" maxlength="8" />
        </el-form-item>

        <el-alert type="info" :closable="false" show-icon style="margin-bottom: 16px">
          <template #title>开发环境说明</template>
          一期未接入短信/邮件通道，验证码固定为 <b>000000</b>。
        </el-alert>

        <el-button type="primary" :loading="submitting" native-type="submit" style="width: 100%">
          注册
        </el-button>
      </el-form>

      <div class="form-footer">
        已有账号？
        <el-button link type="primary" @click="router.push('/login')">去登录</el-button>
      </div>
    </el-card>
  </div>
</template>
