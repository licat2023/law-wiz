<script setup lang="ts">
/**
 * 个人中心（A-05 / A-06）。
 *
 * ⚠️ 页面展示的手机号与邮箱是**后端脱敏后的值**（如 `138****0000`）——
 * 完整值不通过任何接口返回（05-接口设计 §5.2）。这不是"没做完"，
 * 而是有意的设计：完整值一旦出现在响应里，就可能被日志、截图、浏览器缓存带出。
 */
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { useRouter } from 'vue-router'
import { listReviews } from '@/api/review'
import type { ReviewListItem, ReviewStatus } from '@/api/types'
import type { TagProps } from 'element-plus'

import { ApiError } from '@/api/client'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const saving = ref(false)
const fieldErrors = reactive<Record<string, string>>({})

const form = reactive({
  real_name: '',
  org_name: '',
  org_role: '',
})

const REVIEW_STATUS_META: Record<ReviewStatus, { label: string; type: TagProps['type'] }> = {
  pending: { label: '待处理', type: 'info' },
  processing: { label: '审查中', type: 'warning' },
  succeeded: { label: '已完成', type: 'success' },
  failed: { label: '失败', type: 'danger' },
}

const router = useRouter()
const history = ref<ReviewListItem[]>([])
const historyLoading = ref(false)

async function loadHistory() {
  historyLoading.value = true
  try {
    const page = await listReviews({ page: 1, page_size: 10 })
    history.value = page.items
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '加载审查记录失败')
  } finally {
    historyLoading.value = false
  }
}

function statusMeta(status: ReviewStatus) {
  return REVIEW_STATUS_META[status]
}

onMounted(async () => {
  if (!auth.user) await auth.fetchMe().catch(() => undefined)
  form.real_name = auth.user?.profile?.real_name ?? ''
  form.org_name = auth.user?.profile?.org_name ?? ''
  form.org_role = auth.user?.profile?.org_role ?? ''
  loadHistory()
})

async function handleSave() {
  saving.value = true
  Object.keys(fieldErrors).forEach((k) => delete fieldErrors[k])
  try {
    await auth.updateProfile({
      real_name: form.real_name || undefined,
      org_name: form.org_name || undefined,
      org_role: form.org_role || undefined,
    })
    ElMessage.success('已保存')
  } catch (e) {
    if (e instanceof ApiError) {
      e.fieldErrors.forEach(({ field, reason }) => {
        fieldErrors[field] = reason
      })
      ElMessage.error(e.message)
    }
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="page">
    <h1 class="page-title">个人中心</h1>
    <p class="page-desc">查看账号信息与机构资料</p>

    <el-row :gutter="20">
      <el-col :xs="24" :md="10">
        <el-card shadow="never">
          <template #header>账号信息</template>
          <el-descriptions :column="1" border>
            <el-descriptions-item label="用户 ID">
              {{ auth.user?.id ?? '—' }}
            </el-descriptions-item>
            <el-descriptions-item label="手机号">
              {{ auth.user?.phone ?? '未绑定' }}
            </el-descriptions-item>
            <el-descriptions-item label="邮箱">
              {{ auth.user?.email ?? '未绑定' }}
            </el-descriptions-item>
            <el-descriptions-item label="账号类型">
              {{ auth.user?.account_type === 'enterprise' ? '企业' : '个人' }}
            </el-descriptions-item>
            <el-descriptions-item label="注册时间">
              {{ auth.user?.created_at?.replace('T', ' ').slice(0, 19) ?? '—' }}
            </el-descriptions-item>
          </el-descriptions>

          <el-alert type="info" :closable="false" show-icon style="margin-top: 12px">
            手机号与邮箱为脱敏展示，完整值不通过接口返回。
          </el-alert>
        </el-card>
      </el-col>

      <el-col :xs="24" :md="14">
        <el-card shadow="never">
          <template #header>机构资料</template>
          <el-form label-position="top" @submit.prevent="handleSave">
            <el-form-item label="姓名" :error="fieldErrors.real_name">
              <el-input v-model="form.real_name" maxlength="64" placeholder="用于报告署名" />
            </el-form-item>
            <el-form-item label="公司 / 机构" :error="fieldErrors.org_name">
              <el-input v-model="form.org_name" maxlength="200" placeholder="选填" />
            </el-form-item>
            <el-form-item label="职务" :error="fieldErrors.org_role">
              <el-input v-model="form.org_role" maxlength="64" placeholder="选填" />
            </el-form-item>
            <el-button type="primary" :loading="saving" native-type="submit">保存</el-button>
          </el-form>
        </el-card>
      </el-col>
    </el-row>
    <el-card shadow="never" style="margin-top: 20px">
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center">
          <span>合同审查记录</span>
          <el-button link type="primary" @click="loadHistory">刷新</el-button>
        </div>
      </template>
      <el-table v-loading="historyLoading" :data="history">
        <el-table-column prop="contract_title" label="合同名称" min-width="160" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusMeta(row.status).type" size="small">
              {{ statusMeta(row.status).label }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="高/中/低风险" width="140">
          <template #default="{ row }">
            <span class="cnt-high">{{ row.counts.high }}</span> /
            <span class="cnt-mid">{{ row.counts.medium }}</span> /
            <span class="cnt-low">{{ row.counts.low }}</span>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="180">
          <template #default="{ row }">
            {{ row.created_at.replace('T', ' ').slice(0, 19) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100">
          <template #default="{ row }">
            <el-button link type="primary" @click="router.push(`/review/${row.task_id}`)">
              查看
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty
        v-if="!historyLoading && history.length === 0"
        description="暂无审查记录"
        :image-size="60"
      />
    </el-card>
  </div>
</template>

<style scoped>
.cnt-high {
  color: var(--el-color-danger);
  font-weight: 600;
}
.cnt-mid {
  color: var(--el-color-warning);
  font-weight: 600;
}
.cnt-low {
  color: var(--el-text-color-secondary);
}
</style>
