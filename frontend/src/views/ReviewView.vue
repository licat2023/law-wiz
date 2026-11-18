<script setup lang="ts">
/** 管理审查文档列表、上传和当前任务的查看入口。 */
import { Document, FolderOpened, Upload } from '@element-plus/icons-vue'
import { ElMessage, ElNotification } from 'element-plus'
import { computed, onMounted, onUnmounted, ref, shallowRef, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import {
  createReview,
  listReviews,
  newIdempotencyKey,
  setReviewArchived,
  uploadFile,
} from '@/api/review'
import { ApiError } from '@/api/client'
import { ErrorCode, type ReviewListItem, type ReviewStatus, type ReviewTaskData } from '@/api/types'
import ArchiveRowActions from '@/components/ArchiveRowActions.vue'
import ReviewDetailView from './ReviewDetailView.vue'

const PAGE_SIZE = 20
const MAX_SIZE = 20 * 1024 * 1024
const STATUS_LABEL: Record<ReviewStatus, string> = {
  pending: '等待审查',
  processing: '审查中',
  succeeded: '已完成',
  failed: '审查失败',
}

interface Submission {
  file: File
  key: string
  fileId?: string
}

type ReviewDocument = Pick<ReviewListItem, 'task_id' | 'contract_title' | 'status' | 'created_at'>

const route = useRoute()
const router = useRouter()
const selectedTaskId = computed(() =>
  typeof route.params.taskId === 'string' ? route.params.taskId : null,
)
const workspace = ref<HTMLElement>()
const detailScroll = ref<HTMLElement>()
const fileInput = ref<HTMLInputElement>()
const documents = ref<ReviewDocument[]>([])
const documentTitle = computed(
  () => documents.value.find((item) => item.task_id === selectedTaskId.value)?.contract_title ?? '',
)
const listLoading = ref(false)
const listFailed = ref(false)
const hasMore = ref(false)
const observedStatuses = new Map<string, ReviewStatus>()
const archiveBusy = ref(false)
let nextPage = 1
let listRequest = 0

const submission = shallowRef<Submission>()
const uploading = ref(false)
const uploadProgress = ref(0)
const uploadError = ref('')
const dragging = ref(false)
let dragDepth = 0
let disposed = false

watch(selectedTaskId, () => detailScroll.value?.scrollTo(0, 0))

async function loadDocuments(reset = false) {
  if (listLoading.value && !reset) return
  const request = ++listRequest
  const resetIds = reset ? new Set(documents.value.map((item) => item.task_id)) : null
  listLoading.value = true
  listFailed.value = false
  try {
    const page = await listReviews({ page: reset ? 1 : nextPage, page_size: PAGE_SIZE })
    if (disposed || request !== listRequest) return
    if (resetIds) documents.value = documents.value.filter((item) => !resetIds.has(item.task_id))
    const loaded = new Set(documents.value.map((item) => item.task_id))
    for (const item of page.items) {
      if (!loaded.has(item.task_id)) {
        item.status = observedStatuses.get(item.task_id) ?? item.status
        documents.value.push(item)
      }
    }
    nextPage = page.page + 1
    hasMore.value = page.page * page.page_size < page.total
  } catch {
    if (request === listRequest) listFailed.value = true
  } finally {
    if (request === listRequest) listLoading.value = false
  }
}

async function archiveDocument(taskId: string) {
  if (archiveBusy.value) return
  archiveBusy.value = true
  try {
    await setReviewArchived(taskId, true)
    if (disposed) return
    documents.value = documents.value.filter((item) => item.task_id !== taskId)
    observedStatuses.delete(taskId)
    nextPage = 1
    void loadDocuments(true)
    if (selectedTaskId.value === taskId) await router.replace({ name: 'review' })
    ElNotification.success({
      title: '已归档',
      message: '如需恢复或彻底删除，请到个人中心查看。',
    })
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '归档失败，请重试')
  } finally {
    archiveBusy.value = false
  }
}

function updateTask(task: ReviewTaskData) {
  observedStatuses.set(task.task_id, task.status)
  const item = documents.value.find((doc) => doc.task_id === task.task_id)
  if (item) item.status = task.status
}

function chooseFile() {
  if (!uploading.value) fileInput.value?.click()
}

function selectFiles(files: FileList | null) {
  if (!files?.length || uploading.value) return
  if (files.length !== 1) {
    ElMessage.warning('每次可以上传一份合同')
    return
  }

  const file = files[0]
  if (!/\.(pdf|docx|txt)$/i.test(file.name)) {
    ElMessage.error('请选择 PDF、DOCX 或 TXT 文件')
    return
  }
  if (file.size === 0 || file.size > MAX_SIZE) {
    ElMessage.error(file.size === 0 ? '文件为空，请选择有内容的合同' : '单个文件不能超过 20 MB')
    return
  }

  submission.value = { file, key: newIdempotencyKey() }
  uploadProgress.value = 0
  void router.push({ name: 'review' })
  void submitReview()
}

function handleFileInput(event: Event) {
  const input = event.target as HTMLInputElement
  selectFiles(input.files)
  input.value = ''
}

async function submitReview() {
  const pending = submission.value
  if (!pending || uploading.value) return
  uploading.value = true
  uploadError.value = ''
  try {
    if (!pending.fileId) {
      const uploaded = await uploadFile(pending.file, (percent) => {
        uploadProgress.value = percent
      })
      pending.fileId = uploaded.file_id
    }
    if (disposed) return

    uploadProgress.value = 100
    const title = pending.file.name.replace(/\.[^.]+$/, '') || pending.file.name
    const task = await createReview({ file_id: pending.fileId, contract_title: title }, pending.key)
    if (disposed) return

    if (!documents.value.some((item) => item.task_id === task.task_id)) {
      documents.value.unshift({
        task_id: task.task_id,
        contract_title: title,
        status: task.status,
        created_at: task.created_at ?? '',
      })
    }
    if (route.name === 'review') {
      await router.push({ name: 'review-detail', params: { taskId: task.task_id } })
    }
    submission.value = undefined
  } catch (error) {
    if (error instanceof ApiError && error.code === ErrorCode.FILE_NOT_FOUND) {
      pending.fileId = undefined
      uploadProgress.value = 0
    }
    uploadError.value = error instanceof Error ? error.message : '提交失败，请重试'
  } finally {
    uploading.value = false
  }
}

function isFileDrag(event: DragEvent) {
  return event.dataTransfer?.types.includes('Files') === true
}

function enterDrag(event: DragEvent) {
  if (!isFileDrag(event)) return
  dragDepth += 1
  dragging.value = true
}

function leaveDrag() {
  dragDepth = Math.max(0, dragDepth - 1)
  if (dragDepth === 0) dragging.value = false
}

function allowDrop(event: DragEvent) {
  if (!isFileDrag(event)) return
  event.preventDefault()
  if (event.dataTransfer) event.dataTransfer.dropEffect = uploading.value ? 'none' : 'copy'
}

function resetDrag() {
  dragDepth = 0
  dragging.value = false
}

function dropFiles(event: DragEvent) {
  if (!isFileDrag(event)) return
  event.preventDefault()
  resetDrag()
  selectFiles(event.dataTransfer?.files ?? null)
}

/** 防止文件落在导航栏或窗口的其他区域时被浏览器打开。 */
function blockOutsideDrop(event: DragEvent) {
  if (!isFileDrag(event) || workspace.value?.contains(event.target as Node)) return
  event.preventDefault()
  if (event.dataTransfer) event.dataTransfer.dropEffect = 'none'
  resetDrag()
}

onMounted(() => {
  void loadDocuments()
  window.addEventListener('dragover', blockOutsideDrop)
  window.addEventListener('drop', blockOutsideDrop)
  window.addEventListener('dragend', resetDrag)
  window.addEventListener('blur', resetDrag)
})
onUnmounted(() => {
  disposed = true
  window.removeEventListener('dragover', blockOutsideDrop)
  window.removeEventListener('drop', blockOutsideDrop)
  window.removeEventListener('dragend', resetDrag)
  window.removeEventListener('blur', resetDrag)
})
</script>

<template>
  <div
    ref="workspace"
    class="review-workspace"
    @dragenter="enterDrag"
    @dragover="allowDrop"
    @dragleave="leaveDrag"
    @drop="dropFiles"
  >
    <aside class="review-documents" aria-labelledby="review-documents-title">
      <div class="documents-header">
        <el-button type="primary" :icon="Upload" :disabled="uploading" @click="chooseFile">
          上传文档
        </el-button>
        <input
          ref="fileInput"
          type="file"
          accept=".pdf,.docx,.txt"
          hidden
          @change="handleFileInput"
        />
        <h2 id="review-documents-title">审查文档</h2>
      </div>
      <div class="documents-list" :aria-busy="listLoading">
        <RouterLink v-if="submission" class="document-row" :to="{ name: 'review' }">
          <el-icon class="document-icon" aria-hidden="true"><Document /></el-icon>
          <span class="document-info">
            <span class="document-name" :title="submission.file.name">{{
              submission.file.name
            }}</span>
            <span class="document-status" :data-status="uploadError ? 'failed' : 'processing'">
              {{ uploadError ? '提交失败' : '正在提交' }}
            </span>
          </span>
        </RouterLink>
        <div v-for="item in documents" :key="item.task_id" class="archive-action-row">
          <RouterLink
            class="document-row"
            :to="{ name: 'review-detail', params: { taskId: item.task_id } }"
          >
            <el-icon class="document-icon" aria-hidden="true"><Document /></el-icon>
            <span class="document-info">
              <span class="document-name" :title="item.contract_title">{{
                item.contract_title
              }}</span>
              <span class="document-meta">
                <span class="document-status" :data-status="item.status">
                  {{ STATUS_LABEL[item.status] }}
                </span>
                <span v-if="item.created_at">{{ item.created_at.slice(0, 10) }}</span>
              </span>
            </span>
          </RouterLink>
          <ArchiveRowActions
            mode="archive"
            :busy="archiveBusy"
            @archive="archiveDocument(item.task_id)"
          />
        </div>

        <p v-if="listLoading && !documents.length" class="list-hint">正在加载文档…</p>
        <p v-else-if="!listFailed && !documents.length && !submission" class="list-hint">
          暂无审查文档
        </p>
        <div v-if="listFailed" class="list-hint" role="status">
          文档列表加载失败
          <el-button link type="primary" @click="loadDocuments()">重试</el-button>
        </div>
        <el-button
          v-else-if="hasMore"
          class="load-more"
          link
          type="primary"
          :loading="listLoading"
          @click="loadDocuments()"
        >
          加载更多
        </el-button>
      </div>
    </aside>

    <section class="review-content" aria-labelledby="review-page-title">
      <header class="content-header">
        <h1 id="review-page-title">合同智能审查</h1>
      </header>
      <div ref="detailScroll" class="content-body">
        <ReviewDetailView
          v-if="selectedTaskId"
          :key="selectedTaskId"
          :task-id="selectedTaskId"
          :document-title="documentTitle"
          @task-update="updateTask"
          @choose-file="chooseFile"
        />
        <div v-else-if="submission" class="review-guide">
          <div class="guide-icon">
            <el-icon><Document /></el-icon>
          </div>
          <h2>{{ submission.file.name }}</h2>
          <template v-if="uploadError">
            <p role="alert">{{ uploadError }}</p>
            <div class="submission-actions">
              <el-button type="primary" @click="submitReview">重试提交</el-button>
              <el-button @click="submission = undefined">关闭</el-button>
            </div>
          </template>
          <template v-else>
            <p role="status">{{ uploadProgress === 100 ? '正在提交审查…' : '正在上传文档…' }}</p>
            <el-progress class="upload-progress" :percentage="uploadProgress" />
          </template>
        </div>
        <div v-else class="review-guide">
          <div class="guide-icon">
            <el-icon><FolderOpened /></el-icon>
          </div>
          <h2>上传合同开始审查</h2>
          <p>选择文件，或将文件拖入审查界面。</p>
          <p v-if="documents.length" class="history-hint">也可以在左侧查看已有任务。</p>
          <el-button class="guide-upload" type="primary" :icon="Upload" @click="chooseFile">
            上传文档
          </el-button>
          <p class="file-tip">支持 PDF、DOCX、TXT，单个文件不超过 20 MB</p>
        </div>
      </div>
    </section>

    <div v-if="dragging" class="file-drop-overlay" role="status">
      <div class="file-drop-message">
        <el-icon :size="32"><Upload /></el-icon>
        <strong>{{ uploading ? '正在提交，请稍候' : '松开鼠标上传合同' }}</strong>
      </div>
    </div>
  </div>
</template>

<style scoped>
.review-workspace {
  position: relative;
  display: grid;
  grid-template-columns: minmax(230px, 280px) minmax(0, 1fr);
  gap: 16px;
  flex: 1;
  min-width: 0;
  min-height: 0;
  padding: clamp(12px, 1.5vw, 24px);
}
.review-documents,
.review-content {
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--el-border-color-light);
  border-radius: 10px;
  background: var(--el-bg-color);
  overflow: hidden;
}
.documents-header {
  padding: 16px 14px 0;
}
.documents-header .el-button {
  width: 100%;
}
.documents-header h2 {
  margin: 20px 4px 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-regular);
}
.documents-list,
.content-body {
  min-height: 0;
  flex: 1;
  overflow: auto;
  scrollbar-gutter: stable;
}
.documents-list {
  padding: 0 8px 12px 12px;
}
.document-row {
  display: flex;
  align-items: flex-start;
  gap: 9px;
  padding: 10px 8px;
  border-radius: 6px;
  color: var(--el-text-color-primary);
  text-decoration: none;
}
.document-row:hover,
.document-row.router-link-exact-active {
  background: var(--el-color-primary-light-9);
}
.document-row.router-link-exact-active {
  color: var(--el-color-primary);
}
.document-row:focus-visible {
  outline: 2px solid var(--el-color-primary);
  outline-offset: -2px;
}
.document-icon {
  margin-top: 2px;
  flex: none;
  color: var(--el-color-primary);
}
.document-info {
  display: grid;
  gap: 4px;
  min-width: 0;
  flex: 1;
}
.document-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 14px;
  font-weight: 500;
}
.document-meta {
  display: flex;
  gap: 8px;
  align-items: baseline;
  flex-wrap: wrap;
}
.document-meta,
.document-status,
.list-hint {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.document-status[data-status='processing'] {
  color: var(--el-color-primary);
}
.document-status[data-status='failed'] {
  color: var(--el-color-danger-dark-2);
}
.list-hint,
.load-more {
  margin: 10px 8px;
}
.content-header {
  padding: 16px 22px;
  border-bottom: 1px solid var(--el-border-color-extra-light);
}
.content-header h1 {
  margin: 0;
  font-size: 17px;
  font-weight: 650;
}
.review-guide {
  display: flex;
  min-height: 100%;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  padding: 36px 20px;
  text-align: center;
}
.guide-icon {
  display: grid;
  width: 56px;
  height: 56px;
  place-items: center;
  margin-bottom: 16px;
  border-radius: 14px;
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  font-size: 27px;
}
.review-guide h2 {
  margin: 0 0 8px;
  font-size: 23px;
  overflow-wrap: anywhere;
}
.review-guide p {
  margin: 0;
  color: var(--el-text-color-regular);
  font-size: 14px;
  line-height: 1.7;
}
.review-guide .history-hint {
  margin-top: 2px;
}
.guide-upload,
.upload-progress,
.submission-actions {
  margin-top: 20px;
}
.upload-progress {
  width: min(100%, 340px);
}
.review-guide .file-tip {
  margin-top: 12px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.file-drop-overlay {
  position: absolute;
  inset: 0;
  z-index: 2;
  display: grid;
  place-items: center;
  padding: 24px;
  border: 2px dashed var(--el-color-primary);
  background: rgb(235 244 255 / 92%);
  pointer-events: none;
}
.file-drop-message {
  display: grid;
  justify-items: center;
  gap: 12px;
  color: var(--el-color-primary-dark-2);
  font-size: 20px;
}

@media (max-width: 700px) {
  .review-workspace {
    grid-template-columns: minmax(0, 1fr);
    grid-template-rows: minmax(0, auto) minmax(0, 1fr);
    gap: 10px;
  }
  .review-documents {
    max-height: min(235px, 40dvh);
  }
  .documents-header {
    padding-top: 12px;
  }
  .documents-header h2 {
    margin-top: 10px;
  }
  .content-header {
    padding: 13px 16px;
  }
  .review-guide {
    padding: 24px 14px;
  }
}
</style>
