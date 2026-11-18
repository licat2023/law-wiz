<script setup lang="ts">
/** 个人中心展示账号信息和合同审查记录；联系方式由后端脱敏。 */
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { useRouter } from 'vue-router'
import { listReviews } from '@/api/review'
import type { ReviewListItem, ReviewStatus } from '@/api/types'
import type { TagProps } from 'element-plus'

import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()

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
  loadHistory()
})
</script>

<template>
  <div class="page">
    <h1 class="page-title">个人中心</h1>

    <el-card shadow="never" style="margin-top: 16px">
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
    </el-card>
    <el-card shadow="never" style="margin-top: 20px">
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center">
          <span>合同审查记录</span>
          <el-button link type="primary" @click="loadHistory">刷新</el-button>
        </div>
      </template>
      <el-table v-loading="historyLoading" :data="history">
        <template #empty>暂无审查记录</template>
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
