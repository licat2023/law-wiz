<template>
  <div class="review-container">
    <div class="header">
      <h1>合同智能审查</h1>
      <p class="desc">上传合同，自动识别条款并生成含法律依据的风险审查报告</p>
    </div>

    <div class="upload-card">
      <el-upload
        ref="uploadRef"
        v-model:file-list="fileList"
        class="upload-area"
        drag
        :auto-upload="false"
        :limit="1"
        accept=".pdf,.docx,.jpg,.jpeg,.png"
        :on-change="handleFileChange"
        :on-exceed="handleExceed"
      >
        <el-icon size="48"><UploadFilled /></el-icon>
        <div class="text">
          <p>将文件拖到此处，或点击上传</p>
          <p class="tip">支持 PDF / Word（docx）/ JPG / PNG，单个文件不超过 20MB</p>
        </div>
      </el-upload>

      <div class="btn-wrap">
        <el-button type="primary" :disabled="fileList.length === 0 || loading" @click="startReview">
          {{ loading ? '审查中...' : '开始智能审查' }}
        </el-button>
      </div>

      <div v-if="loading" class="progress-wrap">
        <p>{{ progressText }}</p>
        <el-progress :percentage="progress" :indeterminate="true" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  ElMessage,
  type UploadFile,
  type UploadInstance,
  type UploadRawFile,
  type UploadUserFile,
} from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'

import { createReview, getReviewTask, newIdempotencyKey, uploadFile } from '@/api/review'
import type { ReviewStage } from '@/api/types'

const MAX_SIZE = 20 * 1024 * 1024
const ALLOWED_EXT = ['.pdf', '.docx', '.jpg', '.jpeg', '.png']
/** 递增轮询间隔（契约：1s → 2s → 3s → 5s），避免长任务下产生大量无用请求 */
const POLL_INTERVALS = [1000, 2000, 3000, 5000]
/** 轮询上限 90 秒，超时不再无限转圈 */
const POLL_TIMEOUT = 90_000

const STAGE_TEXT: Record<Exclude<ReviewStage, null>, string> = {
  ocr: '正在识别合同文本…',
  extract_terms: '正在提取关键条款…',
  retrieve: '正在检索法律依据…',
  analyze: '正在分析风险点…',
  report: '正在生成审查报告…',
}

const router = useRouter()
const uploadRef = ref<UploadInstance>()
const fileList = ref<UploadUserFile[]>([])
const loading = ref(false)
/** 0：上传阶段；1：审查阶段 */
const phase = ref(0)
const uploadPercent = ref(0)
const taskProgress = ref(0)
const stageText = ref('')

/**
 * 幂等键：同一次用户操作（含重试）必须复用同一个键（契约第 2 条）。
 * 创建失败时保留，重试不发新键；成功后清空。
 */
const idemKey = ref<string | null>(null)

const progress = computed(() => (phase.value === 0 ? uploadPercent.value : taskProgress.value))
const progressText = computed(() =>
  phase.value === 0 ? '正在上传合同文件…' : stageText.value || '正在AI分析合同条款，请稍候',
)

/** 校验扩展名与大小；不合法返回原因，合法返回 null */
function validateFile(file: File): string | null {
  const ext = '.' + (file.name.split('.').pop() ?? '').toLowerCase()
  if (!ALLOWED_EXT.includes(ext)) {
    return `不支持 ${ext || '该'} 格式，仅支持 PDF / Word（docx）/ JPG / PNG`
  }
  if (file.size > MAX_SIZE) {
    return '文件超过 20MB 限制'
  }
  return null
}

function handleFileChange(file: UploadFile) {
  // 换了文件即视为一次新的用户操作，幂等键作废
  idemKey.value = null
  const raw = file.raw
  if (!raw) return
  const reason = validateFile(raw)
  if (reason) {
    ElMessage.error(reason)
    uploadRef.value?.handleRemove(file)
  }
}

/** 单选模式：再次选择文件时替换旧文件 */
function handleExceed(files: File[]) {
  uploadRef.value?.clearFiles()
  const f = files[0]
  if (f) uploadRef.value?.handleStart(f as UploadRawFile)
}

function sleep(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

/**
 * 按递增间隔轮询任务状态，直到终态（succeeded / failed）或 90 秒超时。
 * 网络抖动不中止轮询；超时返回 null。
 */
async function pollTask(taskId: string) {
  const deadline = Date.now() + POLL_TIMEOUT
  let intervalIdx = 0
  for (;;) {
    let task
    try {
      task = await getReviewTask(taskId)
    } catch {
      task = null
    }
    if (task && (task.status === 'succeeded' || task.status === 'failed')) return task
    if (task) {
      taskProgress.value = task.progress
      stageText.value = (task.stage && STAGE_TEXT[task.stage]) || ''
    }
    if (Date.now() >= deadline) return null
    await sleep(POLL_INTERVALS[intervalIdx])
    intervalIdx = Math.min(intervalIdx + 1, POLL_INTERVALS.length - 1)
  }
}

async function startReview() {
  const raw = fileList.value[0]?.raw
  if (!raw) {
    ElMessage.error('请先选择合同文件')
    return
  }
  const reason = validateFile(raw)
  if (reason) {
    ElMessage.error(reason)
    return
  }

  // 同一次用户操作复用同一个幂等键：创建失败重试时不重复扣费、不产生两个任务
  idemKey.value ??= newIdempotencyKey()

  loading.value = true
  try {
    phase.value = 0
    uploadPercent.value = 0
    const uploaded = await uploadFile(raw, (p) => {
      uploadPercent.value = p
    })

    phase.value = 1
    taskProgress.value = 0
    stageText.value = ''
    const task = await createReview(
      { file_id: uploaded.file_id, contract_title: raw.name.replace(/\.[^.]+$/, '') },
      idemKey.value,
    )

    const result = await pollTask(task.task_id)
    if (!result) {
      ElMessage.warning('审查耗时较长（超过 90 秒），请稍后到审查记录中查看结果')
      return
    }
    if (result.status === 'failed') {
      ElMessage.error(result.error_message || '审查失败，请稍后重试')
      return
    }

    ElMessage.success('合同审查完成！')
    uploadRef.value?.clearFiles()
    fileList.value = []
    idemKey.value = null
    router.push(`/review/${task.task_id}`)
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '操作失败，请稍后重试')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.review-container {
  padding: 40px;
  max-width: 1000px;
  margin: 0 auto;
}
.header h1 {
  font-size: 28px;
  margin: 0 0 8px;
  color: #333;
}
.desc {
  color: #666;
  margin-bottom: 32px;
  font-size: 16px;
}
.upload-card {
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  padding: 32px;
  background: #fff;
}
.upload-area {
  padding: 40px 0;
}
.upload-area :deep(.el-upload-dragger) {
  border: 1px dashed #dcdfe6;
  border-radius: 8px;
}
.text {
  margin-top: 16px;
}
.tip {
  color: #999;
  font-size: 14px;
}
.btn-wrap {
  margin-top: 24px;
  text-align: center;
}
.progress-wrap {
  margin-top: 24px;
}
</style>
