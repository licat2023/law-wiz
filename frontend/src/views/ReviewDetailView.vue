<script setup lang="ts">
/**
 * 审查报告详情页（C-03 / C-04 / C-06）。
 *
 * 契约要点（05-接口设计 §5.4）：
 * 1. C-03 仅在任务 succeeded 时可用 → 进入页面先轮询 C-02 到终态再取结果；
 * 2. 风险点必须按 source_type 区分呈现，llm_inference 必须标注"仅供参考"；
 * 3. C-06（误报标记）是模型误报样本的唯一收集途径，界面必须给显式入口；
 * 4. char_start/char_end 基准是 plain_text，本期前端契约里没有该字段，
 *    故不做点击高亮，只展示 clause_text。
 */
import { Loading } from '@element-plus/icons-vue'
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, type TagProps } from 'element-plus'

import { http } from '@/api/client'
import { dismissRiskPoint, getReviewResult, getReviewTask } from '@/api/review'
import type {
  ReviewResultData,
  ReviewStage,
  RiskLevel,
  RiskPoint,
  RiskSourceType,
} from '@/api/types'

const POLL_INTERVALS = [1000, 2000, 3000, 5000]
const POLL_TIMEOUT = 90_000

const STAGE_TEXT: Record<Exclude<ReviewStage, null>, string> = {
  ocr: '正在识别合同文本…',
  extract_terms: '正在提取关键条款…',
  retrieve: '正在检索法律依据…',
  analyze: '正在分析风险点…',
  report: '正在生成审查报告…',
}

const LEVEL_META: Record<RiskLevel, { label: string; type: TagProps['type'] }> = {
  high: { label: '高风险', type: 'danger' },
  medium: { label: '中风险', type: 'warning' },
  low: { label: '低风险', type: 'info' },
}
const LEVEL_ORDER: RiskLevel[] = ['high', 'medium', 'low']

/**
 * 三类依据的呈现（契约 §5.4）：
 * retrieved_law → 法条，可展示引用；rule → 标注"依据审查规则"；
 * llm_inference → 必须标注"未找到直接法律依据，仅供参考"
 */
const SOURCE_META: Record<RiskSourceType, { label: string; type: TagProps['type'] }> = {
  retrieved_law: { label: '依据法条', type: 'success' },
  rule: { label: '依据审查规则', type: 'primary' },
  llm_inference: { label: '未找到直接法律依据，仅供参考', type: 'danger' },
}

const route = useRoute()
const router = useRouter()
const taskId = route.params.taskId as string

const taskStatus = ref<'pending' | 'processing' | 'succeeded' | 'failed' | 'timeout' | null>(null)
const stageText = ref('')
const failedMessage = ref('')
const result = ref<ReviewResultData | null>(null)
const dismissing = ref(false)

let disposed = false
onUnmounted(() => {
  disposed = true
})

function sleep(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

/** 轮询 C-02 到终态；超时返回 null */
async function pollUntilTerminal() {
  const deadline = Date.now() + POLL_TIMEOUT
  let idx = 0
  while (!disposed && Date.now() < deadline) {
    try {
      const task = await getReviewTask(taskId)
      if (task.status === 'succeeded' || task.status === 'failed') return task
      stageText.value = (task.stage && STAGE_TEXT[task.stage]) || ''
    } catch {
      // 网络抖动不中止轮询
    }
    await sleep(POLL_INTERVALS[idx])
    idx = Math.min(idx + 1, POLL_INTERVALS.length - 1)
  }
  return null
}

onMounted(async () => {
  try {
    const task = await pollUntilTerminal()
    if (disposed) return
    if (!task) {
      taskStatus.value = 'timeout'
      return
    }
    if (task.status === 'failed') {
      taskStatus.value = 'failed'
      failedMessage.value = task.error_message || '审查失败，请稍后重试'
      return
    }
    taskStatus.value = 'succeeded'
    result.value = await getReviewResult(taskId)
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '加载报告失败，请稍后重试')
    taskStatus.value = 'failed'
  }
})

/** C-06：标记/取消误报，成功后就地更新本地状态 */
async function toggleDismiss(rp: RiskPoint) {
  dismissing.value = true
  try {
    const updated = (await dismissRiskPoint(taskId, rp.id, !rp.is_dismissed)) as RiskPoint
    rp.is_dismissed = updated.is_dismissed
    ElMessage.success(rp.is_dismissed ? '已标记为误报' : '已取消误报标记')
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '操作失败，请稍后重试')
  } finally {
    dismissing.value = false
  }
}

/** C-04：带认证头取二进制流后触发下载 */
async function downloadReport() {
  try {
    const resp = await http.get(`/reviews/${taskId}/report?format=pdf`, {
      responseType: 'blob',
      timeout: 60_000,
    })
    const url = URL.createObjectURL(resp.data as Blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${result.value?.contract_title ?? '审查报告'}.pdf`
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '报告下载失败，请稍后重试')
  }
}

const grouped = computed<Record<RiskLevel, RiskPoint[]>>(() => {
  const groups: Record<RiskLevel, RiskPoint[]> = { high: [], medium: [], low: [] }
  result.value?.risk_points.forEach((rp) => groups[rp.risk_level].push(rp))
  return groups
})
</script>

<template>
  <div class="page">
    <el-page-header :content="`审查报告 #${taskId}`" @back="router.back()" />

    <!-- 审查进行中 -->
    <el-card
      v-if="taskStatus === 'pending' || taskStatus === 'processing'"
      shadow="never"
      style="margin-top: 16px"
    >
      <div class="loading-wrap">
        <el-icon class="is-loading" :size="28"><Loading /></el-icon>
        <p>{{ stageText || '正在分析合同…' }}</p>
      </div>
    </el-card>

    <!-- 失败 -->
    <el-card v-else-if="taskStatus === 'failed'" shadow="never" style="margin-top: 16px">
      <el-result icon="error" title="审查失败" :sub-title="failedMessage">
        <template #extra>
          <el-button type="primary" @click="router.push('/review')">重新上传</el-button>
        </template>
      </el-result>
    </el-card>

    <!-- 超时 -->
    <el-card v-else-if="taskStatus === 'timeout'" shadow="never" style="margin-top: 16px">
      <el-result
        icon="info"
        title="审查耗时较长"
        sub-title="已超过 90 秒，请稍后从审查记录中查看结果"
      >
        <template #extra>
          <el-button type="primary" @click="router.push('/review')">返回审查页</el-button>
        </template>
      </el-result>
    </el-card>

    <!-- 报告 -->
    <template v-else-if="result">
      <el-card shadow="never" style="margin-top: 16px">
        <div class="report-header">
          <div>
            <h2 class="report-title">{{ result.contract_title }}</h2>
            <p class="report-summary">{{ result.summary || '—' }}</p>
          </div>
          <el-button type="primary" plain @click="downloadReport">下载 PDF 报告</el-button>
        </div>
        <div class="counts">
          <el-tag v-for="lv in LEVEL_ORDER" :key="lv" :type="LEVEL_META[lv].type" effect="dark">
            {{ LEVEL_META[lv].label }} {{ result.counts[lv] }}
          </el-tag>
        </div>
      </el-card>

      <!-- 关键条款提取 -->
      <el-card v-if="result.extracted_terms" shadow="never" style="margin-top: 16px">
        <template #header>关键条款提取</template>
        <el-descriptions :column="2" border>
          <el-descriptions-item
            v-if="result.extracted_terms.parties?.length"
            label="合同主体"
            :span="2"
          >
            {{ result.extracted_terms.parties.join('；') }}
          </el-descriptions-item>
          <el-descriptions-item v-if="result.extracted_terms.amount" label="标的金额">
            {{ result.extracted_terms.amount }}
          </el-descriptions-item>
          <el-descriptions-item v-if="result.extracted_terms.term" label="合同期限">
            {{ result.extracted_terms.term }}
          </el-descriptions-item>
          <el-descriptions-item v-if="result.extracted_terms.payment_terms" label="付款条款">
            {{ result.extracted_terms.payment_terms }}
          </el-descriptions-item>
          <el-descriptions-item v-if="result.extracted_terms.jurisdiction" label="管辖法院">
            {{ result.extracted_terms.jurisdiction }}
          </el-descriptions-item>
          <el-descriptions-item v-if="result.extracted_terms.liability" label="违约责任" :span="2">
            {{ result.extracted_terms.liability }}
          </el-descriptions-item>
        </el-descriptions>
      </el-card>

      <!-- 风险点（按等级分组） -->
      <el-card v-for="lv in LEVEL_ORDER" :key="lv" shadow="never" style="margin-top: 16px">
        <template #header> {{ LEVEL_META[lv].label }}（{{ grouped[lv].length }}） </template>
        <el-empty v-if="grouped[lv].length === 0" description="未发现该等级风险" :image-size="60" />
        <div
          v-for="rp in grouped[lv]"
          :key="rp.id"
          class="risk-item"
          :class="{ dismissed: rp.is_dismissed }"
        >
          <div class="risk-top">
            <el-tag :type="LEVEL_META[rp.risk_level].type" size="small">
              {{ LEVEL_META[rp.risk_level].label }}
            </el-tag>
            <el-tag v-if="rp.risk_category" size="small" type="info">{{ rp.risk_category }}</el-tag>
            <span v-if="rp.clause_title" class="clause-title">{{ rp.clause_title }}</span>
            <el-tag size="small" :type="SOURCE_META[rp.source_type].type">
              {{ SOURCE_META[rp.source_type].label }}
            </el-tag>
          </div>

          <blockquote v-if="rp.clause_text" class="clause-text">{{ rp.clause_text }}</blockquote>

          <p class="risk-desc">{{ rp.description }}</p>
          <p v-if="rp.suggestion" class="risk-suggestion">修改建议：{{ rp.suggestion }}</p>
          <p v-if="rp.legal_basis" class="legal-basis">法律依据：{{ rp.legal_basis }}</p>

          <div class="risk-actions">
            <el-button
              link
              :type="rp.is_dismissed ? 'info' : 'danger'"
              :disabled="dismissing"
              @click="toggleDismiss(rp)"
            >
              {{ rp.is_dismissed ? '已标记误报（点击恢复）' : '这是误报' }}
            </el-button>
          </div>
        </div>
      </el-card>
    </template>
  </div>
</template>

<style scoped>
.loading-wrap {
  text-align: center;
  padding: 32px 0;
  color: var(--el-text-color-secondary);
}
.report-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
}
.report-title {
  margin: 0 0 8px;
  font-size: 20px;
}
.report-summary {
  margin: 0;
  color: #666;
  line-height: 1.6;
}
.counts {
  margin-top: 12px;
  display: flex;
  gap: 8px;
}
.risk-item {
  padding: 16px 0;
  border-bottom: 1px solid #f0f0f0;
}
.risk-item:last-child {
  border-bottom: none;
}
.risk-item.dismissed {
  opacity: 0.5;
}
.risk-top {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.clause-title {
  font-weight: 600;
  color: #333;
}
.clause-text {
  margin: 8px 0;
  padding: 8px 12px;
  border-left: 3px solid #dcdfe6;
  background: #f7f8fa;
  color: #666;
  font-size: 13px;
}
.risk-desc {
  margin: 8px 0 4px;
  line-height: 1.6;
}
.risk-suggestion {
  margin: 4px 0;
  color: #67c23a;
  font-size: 13px;
}
.legal-basis {
  margin: 4px 0;
  color: #409eff;
  font-size: 13px;
}
.risk-actions {
  margin-top: 8px;
}
</style>
