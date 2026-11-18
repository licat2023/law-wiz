<script setup lang="ts">
/** 个人中心展示账号信息、审查记录与归档管理。 */
import { onMounted, ref } from 'vue'
import { Document } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox, type TagProps } from 'element-plus'

import { useRouter } from 'vue-router'
import { deleteArchivedReview, listReviews, setReviewArchived } from '@/api/review'
import type { ReviewListItem, ReviewStatus } from '@/api/types'
import ReviewRowActions from '@/components/ReviewRowActions.vue'

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
const ARCHIVE_PAGE_SIZE = 10
const archived = ref<ReviewListItem[]>([])
const archivePage = ref(1)
const archiveTotal = ref(0)
const archiveLoading = ref(false)
const archiveError = ref(false)
const archiveBusy = ref(false)

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

async function loadArchive(page = archivePage.value) {
  if (archiveLoading.value) return
  archiveLoading.value = true
  archiveError.value = false
  try {
    const result = await listReviews({ page, page_size: ARCHIVE_PAGE_SIZE, archived: true })
    archived.value = result.items
    archivePage.value = result.page
    archiveTotal.value = result.total
  } catch {
    archiveError.value = true
  } finally {
    archiveLoading.value = false
  }
}

async function manageArchived(item: ReviewListItem, action: 'restore' | 'delete') {
  if (archiveBusy.value || archiveLoading.value) return
  archiveBusy.value = true
  try {
    if (action === 'delete') {
      const confirmed = await ElMessageBox.confirm(
        `确定删除「${item.contract_title || '未命名合同'}」？此条目的审查报告和风险记录将一并删除，且无法恢复。`,
        '彻底删除文档',
        {
          type: 'warning',
          confirmButtonText: '彻底删除',
          cancelButtonText: '取消',
          confirmButtonType: 'danger',
        },
      ).then(
        () => true,
        () => false,
      )
      if (!confirmed) return
      await deleteArchivedReview(item.task_id)
    } else {
      await setReviewArchived(item.task_id, false)
      void loadHistory()
    }
    ElMessage.success(action === 'delete' ? '已彻底删除' : '已还原')
    archived.value = archived.value.filter((row) => row.task_id !== item.task_id)
    archiveTotal.value -= 1
    const lastPage = Math.max(1, Math.ceil(archiveTotal.value / ARCHIVE_PAGE_SIZE))
    await loadArchive(Math.min(archivePage.value, lastPage))
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '操作失败，请重试')
  } finally {
    archiveBusy.value = false
  }
}

onMounted(async () => {
  if (!auth.user) await auth.fetchMe().catch(() => undefined)
  void loadHistory()
  void loadArchive()
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
    <el-card class="archive-card" shadow="never">
      <template #header>
        <div class="archive-heading">
          <span>归档管理</span>
          <el-button
            link
            type="primary"
            :disabled="archiveBusy || archiveLoading"
            @click="loadArchive()"
          >
            刷新
          </el-button>
        </div>
      </template>
      <div v-loading="archiveLoading" class="archive-list">
        <div v-for="item in archived" :key="item.task_id" class="review-action-row archive-row">
          <el-icon class="archive-icon" aria-hidden="true"><Document /></el-icon>
          <div class="archive-info">
            <div class="archive-name" :title="item.contract_title">
              {{ item.contract_title || '未命名合同' }}
            </div>
            <div class="archive-date">归档于 {{ item.archived_at?.slice(0, 10) }}</div>
          </div>
          <ReviewRowActions
            mode="manage"
            :busy="archiveBusy || archiveLoading"
            @restore="manageArchived(item, 'restore')"
            @delete="manageArchived(item, 'delete')"
          />
        </div>
        <p v-if="archiveError" class="archive-empty" role="status">加载失败，请刷新重试。</p>
        <p v-else-if="!archiveLoading && !archived.length" class="archive-empty">暂无归档文档</p>
      </div>
      <el-pagination
        v-if="archiveTotal > ARCHIVE_PAGE_SIZE"
        :current-page="archivePage"
        :page-size="ARCHIVE_PAGE_SIZE"
        :total="archiveTotal"
        :disabled="archiveBusy || archiveLoading"
        size="small"
        layout="prev, pager, next"
        class="archive-pagination"
        @current-change="loadArchive"
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
.archive-card {
  margin-top: 20px;
}
.archive-heading,
.archive-row {
  display: flex;
  align-items: center;
}
.archive-heading {
  justify-content: space-between;
}
.archive-list {
  min-height: 44px;
}
.archive-row {
  padding: 9px 10px;
  gap: 10px;
  border-radius: 6px;
}
.archive-row:hover,
.archive-row:focus-within {
  background: var(--el-fill-color-light);
}
.archive-icon {
  flex: none;
  color: var(--el-color-primary);
}
.archive-info {
  min-width: 0;
}
.archive-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.archive-date {
  margin-top: 3px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.archive-empty {
  margin: 12px 0;
  text-align: center;
  font-size: 14px;
  color: var(--el-text-color-secondary);
}
.archive-pagination {
  margin-top: 12px;
  justify-content: flex-end;
}
</style>
