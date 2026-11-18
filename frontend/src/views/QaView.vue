<script setup lang="ts">
/**
 * 法律问答页（M3）。
 *
 * 对接口契约的实现约束（docs/05-接口设计.md §5.6 / §6.2）：
 * 1. E-04 预分配助手消息 ID，E-06 发布临时正文，E-03 提供保存后的回答和引文；
 * 2. 必须携带 Idempotency-Key；失败不自动重试（§6.2），用户重新发起
 *    即新的操作、用新的键；
 * 3. 正式助手消息的 `[编号]` 与引用快照对应，生成中只显示正文；
 * 4. 订阅中断时用 E-03 取回结果，等待回答期间同一页面只处理一条问答。
 */
import { ChatDotRound, Loading, Plus } from '@element-plus/icons-vue'
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { ElMessage, ElNotification } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'

import {
  archiveSession,
  createSession,
  getSession,
  listSessions,
  newIdempotencyKey,
  sendMessage,
  streamAnswer,
} from '@/api/qa'
import { listReviews } from '@/api/review'
import type { QaMessage, QaSession, ReviewListItem } from '@/api/types'
import SidebarEntry from '@/components/SidebarEntry.vue'
import WorkspaceSidebar from '@/components/WorkspaceSidebar.vue'

const POLL_INTERVALS = [1000, 2000, 3000, 5000]
const POLL_TIMEOUT = 90_000
const MESSAGE_PAGE_SIZE = 50
const REPORT_PAGE_SIZE = 100
const QA_INTRO = '可以帮你读合同条款、梳理纠纷、准备材料，或追问审查报告'
const REPORT_ANSWER_SEPARATOR = '\n\n本轮依据与建议\n'
const LEGACY_EVIDENCE_NOTICE = /^(知识库暂不可用，)?本轮未找到直接法律依据。[ \t]*(?:\r?\n)?/

interface DisplayMessage extends QaMessage {
  /** 等待最终校验和保存时收到的正文。 */
  partial?: string
}

interface AnswerPart {
  text: string
  citation?: number
}

const sessions = ref<QaSession[]>([])
const currentSession = ref<QaSession | null>(null)
const messages = ref<DisplayMessage[]>([])
const draft = ref('')
const selectedReportId = ref<string | null>(null)
const reports = ref<ReviewListItem[]>([])
const loadingReports = ref(false)
const reportLoadFailed = ref(false)
const waiting = ref(false)
const loadingSession = ref(false)
const firstMessagePage = ref(1)
const loadingHistory = ref(false)
const route = useRoute()
const router = useRouter()
const sessionReportId = computed(() => currentSession.value?.review_context?.review_task_id ?? null)
const reportChanged = computed(() => selectedReportId.value !== sessionReportId.value)
const reportOptions = computed(() => {
  const options = reports.value.map((report) => ({
    id: report.task_id,
    title: `${report.contract_title} · ${report.created_at.replace('T', ' ').slice(0, 16)}`,
  }))
  const context = currentSession.value?.review_context
  if (context?.available && !options.some((option) => option.id === context.review_task_id)) {
    options.unshift({ id: context.review_task_id, title: context.contract_title || '当前关联报告' })
  }
  return options
})

const msgListRef = ref<HTMLElement>()

let disposed = false
let answerStreamController: AbortController | undefined
onUnmounted(() => {
  disposed = true
  answerStreamController?.abort()
})

watch(
  () => [messages.value.length, messages.value.at(-1)?.partial, messages.value.at(-1)?.content],
  async () => {
    await nextTick()
    const el = msgListRef.value
    if (el && !loadingHistory.value) el.scrollTop = el.scrollHeight
  },
)

function sleep(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

/** 旧提示只在展示时去掉，报告背景内的编号保留为正文。 */
function answerParts(message: QaMessage): AnswerPart[] {
  const separator = message.content.startsWith('报告原有分析\n')
    ? message.content.indexOf(REPORT_ANSWER_SEPARATOR)
    : -1
  const bodyStart = separator < 0 ? 0 : separator + REPORT_ANSWER_SEPARATOR.length
  const body = message.content
    .slice(bodyStart)
    .replace(LEGACY_EVIDENCE_NOTICE, (_notice, outage) => (outage ? '知识库暂不可用。' : ''))
  const parts: AnswerPart[] = bodyStart ? [{ text: message.content.slice(0, bodyStart) }] : []
  const count = message.citations?.length ?? 0
  for (const text of body.split(/(\[[1-9]\d*\])/)) {
    if (!text) continue
    const match = /^\[([1-9]\d*)\]$/.exec(text)
    const number = match ? Number(match[1]) : 0
    parts.push(number > 0 && number <= count ? { text, citation: number } : { text })
  }
  return parts
}

function footnoteId(messageId: string, number: number) {
  return `qa-note-${messageId}-${number}`
}

/** 展开并聚焦当前消息内的对应法条。 */
function showFootnote(messageId: string, number: number) {
  const note = document.getElementById(footnoteId(messageId, number))
  const details = note?.closest('details')
  if (!note || !details) return
  details.open = true
  note.focus({ preventScroll: true })
  note.scrollIntoView({ block: 'nearest' })
}

/** 读取已保存的结果。订阅结束或断开后首次立即读取，未完成时递增等待。 */
async function waitForAnswer(
  sessionId: string,
  assistantId: string,
  page: number,
  deadline: number,
): Promise<QaMessage | null> {
  let idx = 0
  while (!disposed) {
    try {
      const detail = await getSession(sessionId, { page, page_size: MESSAGE_PAGE_SIZE })
      const msg = detail.messages.items.find((m) => m.message_id === assistantId)
      if (msg && msg.content) return msg
      if (!msg) page = Math.max(1, Math.ceil(detail.messages.total / MESSAGE_PAGE_SIZE))
    } catch {
      // 网络抖动继续轮询
    }
    const remaining = deadline - Date.now()
    if (remaining <= 0) break
    await sleep(Math.min(POLL_INTERVALS[idx], remaining))
    idx = Math.min(idx + 1, POLL_INTERVALS.length - 1)
  }
  return null
}

async function settleAnswer(sessionId: string, placeholder: DisplayMessage, page: number) {
  const controller = new AbortController()
  answerStreamController = controller
  const deadline = Date.now() + POLL_TIMEOUT
  const timer = window.setTimeout(() => controller.abort(), POLL_TIMEOUT)
  try {
    await streamAnswer(sessionId, placeholder.message_id, controller.signal, (text) => {
      const message = messages.value.find((item) => item.message_id === placeholder.message_id)
      if (!disposed && message) message.partial = (message.partial ?? '') + text
    })
  } catch {
    // 断线或旧后端仍可从会话详情取得同一回答。
  } finally {
    window.clearTimeout(timer)
    answerStreamController = undefined
  }
  const answer = await waitForAnswer(sessionId, placeholder.message_id, page, deadline)
  if (disposed) return
  const idx = messages.value.findIndex((m) => m.message_id === placeholder.message_id)
  if (idx < 0) return
  messages.value[idx] = answer ?? {
    ...placeholder,
    partial: undefined,
    content: '（回答耗时较长，请稍后重新打开会话查看）',
  }
}

async function loadSessionList() {
  try {
    const page = await listSessions({ page: 1, page_size: 50, status: 'active' })
    sessions.value = page.items
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '加载会话列表失败')
  }
}

/** 下拉展开时刷新当前账号已完成的审查，支持跨页选择。 */
async function loadReports(visible: boolean) {
  if (!visible || loadingReports.value) return
  loadingReports.value = true
  reportLoadFailed.value = false
  try {
    const params = { page_size: REPORT_PAGE_SIZE, status: 'succeeded' }
    const first = await listReviews({ ...params, page: 1 })
    const options = new Map(first.items.map((report) => [report.task_id, report]))
    const lastPage = Math.ceil(first.total / REPORT_PAGE_SIZE)
    for (let page = 2; page <= lastPage && !disposed; page += 1) {
      const next = await listReviews({ ...params, page })
      for (const report of next.items) options.set(report.task_id, report)
    }
    if (!disposed) reports.value = [...options.values()]
  } catch {
    reportLoadFailed.value = true
    ElMessage.error('加载审查报告失败，可重新展开列表重试')
  } finally {
    loadingReports.value = false
  }
}

async function selectSession(sessionId: string) {
  if (loadingSession.value || waiting.value) {
    ElMessage.warning('请等待当前回答完成')
    return
  }
  loadingSession.value = true
  try {
    let detail = await getSession(sessionId, { page: 1, page_size: MESSAGE_PAGE_SIZE })
    const lastPage = Math.max(1, Math.ceil(detail.messages.total / MESSAGE_PAGE_SIZE))
    if (lastPage > 1) {
      detail = await getSession(sessionId, { page: lastPage, page_size: MESSAGE_PAGE_SIZE })
    }
    if (disposed) return
    firstMessagePage.value = lastPage
    currentSession.value = detail
    selectedReportId.value = sessionReportId.value
    messages.value = detail.messages.items
    draft.value = ''
    await router.replace({ name: 'qa', query: { session: sessionId } })

    const pending = [...messages.value].reverse().find((m) => m.role === 'assistant' && !m.content)
    if (pending && detail.status === 'active') {
      waiting.value = true
      void settleAnswer(sessionId, pending, lastPage).finally(() => {
        waiting.value = false
      })
    }
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '加载会话失败')
  } finally {
    loadingSession.value = false
  }
}

async function loadEarlierMessages() {
  const session = currentSession.value
  if (!session || loadingHistory.value || firstMessagePage.value === 1) return
  loadingHistory.value = true
  const page = firstMessagePage.value - 1
  try {
    const detail = await getSession(session.session_id, { page, page_size: MESSAGE_PAGE_SIZE })
    if (disposed || currentSession.value?.session_id !== session.session_id) return
    const list = msgListRef.value
    const previousHeight = list?.scrollHeight ?? 0
    messages.value.unshift(...detail.messages.items)
    firstMessagePage.value = page
    await nextTick()
    if (list) list.scrollTop += list.scrollHeight - previousHeight
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '加载更早消息失败')
  } finally {
    loadingHistory.value = false
  }
}

async function newChat() {
  if (waiting.value || loadingSession.value) {
    ElMessage.warning('请等待当前回答完成')
    return
  }
  currentSession.value = null
  selectedReportId.value = null
  messages.value = []
  draft.value = ''
  firstMessagePage.value = 1
  await router.replace({ name: 'qa' })
}

/** E-05：将会话移到个人中心的归档管理。 */
async function archive(s: QaSession) {
  if (waiting.value || loadingSession.value) return
  loadingSession.value = true
  try {
    await archiveSession(s.session_id)
    if (disposed) return
    sessions.value = sessions.value.filter((x) => x.session_id !== s.session_id)
    if (currentSession.value?.session_id === s.session_id) {
      currentSession.value = null
      selectedReportId.value = null
      messages.value = []
      draft.value = ''
      firstMessagePage.value = 1
      await router.replace({ name: 'qa' })
    }
    ElNotification.success({
      title: '已归档',
      message: '如需恢复或彻底删除，请到个人中心查看。',
    })
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '归档失败')
  } finally {
    loadingSession.value = false
  }
}

async function handleSend() {
  const content = draft.value.trim()
  if (!content || waiting.value || loadingSession.value) return

  let session = currentSession.value
  if (session && (session.status !== 'active' || session.review_context?.available === false))
    return

  waiting.value = true
  try {
    // 报告上下文随会话保存。选择变化时保留旧会话，首条消息发往新会话。
    if (!session || reportChanged.value) {
      session = await createSession(
        selectedReportId.value === null ? {} : { review_task_id: selectedReportId.value },
      )
      if (disposed) return
      currentSession.value = session
      sessions.value.unshift(session)
      messages.value = []
      firstMessagePage.value = 1
      await router.replace({ name: 'qa', query: { session: session.session_id } })
    }
    const firstQuestion = session.message_count === 0
    // 每次主动发起都是一次新操作，用新的幂等键（§6.2 失败不自动重试）
    const resp = await sendMessage(session.session_id, content, newIdempotencyKey())
    draft.value = ''

    messages.value.push({
      message_id: resp.user_message_id,
      role: 'user',
      content,
      has_citation: false,
      created_at: new Date().toISOString(),
    })
    const placeholder: DisplayMessage = {
      message_id: resp.assistant_message_id,
      role: 'assistant',
      content: '',
      has_citation: false,
      created_at: '',
    }
    messages.value.push(placeholder)

    session.message_count += 2
    await settleAnswer(
      session.session_id,
      placeholder,
      Math.ceil(session.message_count / MESSAGE_PAGE_SIZE),
    )
    if (disposed) return
    if (firstQuestion) loadSessionList() // 首条提问会生成会话标题，刷新列表
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '发送失败，请稍后重试')
  } finally {
    waiting.value = false
  }
}

onMounted(async () => {
  void loadSessionList()
  const sessionId = route.query.session
  if (typeof sessionId === 'string' && !disposed) await selectSession(sessionId)
})
</script>

<template>
  <div class="workspace-with-sidebar">
    <WorkspaceSidebar heading="历史会话">
      <template #toolbar>
        <el-button
          type="primary"
          :icon="Plus"
          :disabled="loadingSession || waiting"
          @click="newChat"
        >
          新建对话
        </el-button>
      </template>
      <SidebarEntry
        v-for="s in sessions"
        :key="s.session_id"
        :title="s.title || '新对话'"
        :selected="s.session_id === currentSession?.session_id"
        :busy="loadingSession || waiting"
        @select="selectSession(s.session_id)"
        @archive="archive(s)"
      >
        <template #icon><ChatDotRound /></template>
        <span>{{ s.message_count }} 条消息</span>
      </SidebarEntry>
      <el-empty v-if="sessions.length === 0" description="暂无历史会话" :image-size="60" />
    </WorkspaceSidebar>

    <section class="chat" aria-label="问答内容">
      <template v-if="currentSession">
        <div v-if="currentSession.review_context" class="review-context">
          <router-link
            v-if="currentSession.review_context.available"
            :to="{
              name: 'review-detail',
              params: { taskId: currentSession.review_context.review_task_id },
            }"
          >
            {{ currentSession.review_context.contract_title || '查看关联审查报告' }}
          </router-link>
          <span v-else>关联报告或风险项已不可用，仍可查看历史问答</span>
          <span v-if="currentSession.review_context.risk_label">
            {{ currentSession.review_context.risk_label }}
          </span>
        </div>
        <div ref="msgListRef" class="msg-list">
          <el-button
            v-if="firstMessagePage > 1"
            text
            :loading="loadingHistory"
            @click="loadEarlierMessages"
          >
            加载更早消息
          </el-button>
          <div v-for="m in messages" :key="m.message_id" class="msg-row" :class="m.role">
            <div class="bubble" :aria-busy="m.role === 'assistant' && !m.content">
              <template v-if="m.role === 'assistant' && !m.content">
                <span v-if="m.partial" class="answer-preview">{{ m.partial }}</span>
                <span v-else class="thinking">正在生成回答</span>
                <el-icon class="is-loading" aria-hidden="true"><Loading /></el-icon>
              </template>
              <template v-else-if="m.role === 'assistant'">
                <template v-for="(part, i) in answerParts(m)" :key="i">
                  <sup v-if="part.citation" class="cite-ref">
                    <a
                      :href="`#${footnoteId(m.message_id, part.citation)}`"
                      :aria-label="`查看法律依据 ${part.citation}`"
                      @click.prevent="showFootnote(m.message_id, part.citation)"
                      >{{ part.text }}</a
                    >
                  </sup>
                  <template v-else>{{ part.text }}</template>
                </template>
              </template>
              <template v-else>{{ m.content }}</template>

              <details v-if="m.citations?.length" class="citations">
                <summary>法律依据（{{ m.citations.length }}）</summary>
                <ol class="citation-list">
                  <li
                    v-for="(c, i) in m.citations"
                    :id="footnoteId(m.message_id, i + 1)"
                    :key="i"
                    class="citation"
                    tabindex="-1"
                  >
                    <p class="cite-head">{{ c.law_name || '未知法规' }} {{ c.article_no }}</p>
                    <p v-if="c.quoted_text" class="cite-text">{{ c.quoted_text }}</p>
                  </li>
                </ol>
              </details>

              <div v-if="m.role === 'assistant' && m.model_name" class="msg-meta">
                {{ m.model_name }} · {{ m.latency_ms != null ? `${m.latency_ms}ms` : '' }}
              </div>
            </div>
          </div>

          <el-empty
            v-if="messages.length === 0"
            :description="
              currentSession.review_context ? '可以询问如何处置风险，或怎样修改相关条款' : QA_INTRO
            "
            :image-size="80"
          />
        </div>
      </template>
      <el-empty v-else class="chat-start" :description="QA_INTRO" :image-size="80" />

      <div
        v-if="
          !currentSession ||
          (currentSession.status === 'active' && currentSession.review_context?.available !== false)
        "
        class="input-area"
      >
        <div class="report-controls">
          <el-select
            v-model="selectedReportId"
            aria-label="关联审查报告"
            class="report-select"
            placeholder="选择审查报告（可选）"
            clearable
            filterable
            :value-on-clear="null"
            :loading="loadingReports"
            :disabled="waiting || loadingSession"
            :no-data-text="reportLoadFailed ? '加载失败，请重新展开' : '暂无已完成的审查报告'"
            @visible-change="loadReports"
          >
            <el-option
              v-for="report in reportOptions"
              :key="report.id"
              :label="report.title"
              :value="report.id"
            />
          </el-select>
          <span v-if="currentSession && reportChanged" class="report-change">
            发送后将开启新对话
          </span>
        </div>
        <div class="draft-row">
          <el-input
            v-model="draft"
            type="textarea"
            :rows="3"
            resize="none"
            :placeholder="
              selectedReportId
                ? '输入报告相关问题，Enter 发送，Shift+Enter 换行'
                : '输入法律问题，Enter 发送，Shift+Enter 换行'
            "
            :disabled="waiting || loadingSession"
            @keydown.enter.exact.prevent="handleSend"
          />
          <el-button
            type="primary"
            :loading="waiting"
            :disabled="!draft.trim() || loadingSession"
            @click="handleSend"
          >
            发送
          </el-button>
        </div>
      </div>
      <p v-else-if="currentSession?.status === 'archived'" class="archive-note">
        此会话已归档，可到个人中心还原。
      </p>
    </section>
  </div>
</template>

<style scoped>
.archive-note {
  margin: 0;
  border-top: 1px solid var(--el-border-color-light);
  padding: 12px 16px;
  color: var(--el-text-color-regular);
  font-size: 14px;
}
.chat {
  min-width: 0;
  min-height: 0;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  display: flex;
  flex-direction: column;
}
.review-context {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 16px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  font-size: 14px;
  color: var(--el-text-color-secondary);
}
.review-context a {
  color: var(--el-color-primary);
}
.msg-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 24px;
}
.chat-start {
  flex: 1;
}
.msg-row {
  display: flex;
  margin-bottom: 16px;
}
.msg-row.user {
  justify-content: flex-end;
}
.msg-row.assistant {
  justify-content: flex-start;
}
.bubble {
  max-width: 72%;
  padding: 10px 14px;
  border-radius: 10px;
  font-size: 14px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}
.user .bubble {
  background: var(--el-color-primary);
  color: #fff;
}
.assistant .bubble {
  background: #f5f7fa;
  color: #333;
}
.thinking {
  margin-right: 6px;
}
.cite-ref {
  margin-inline: 1px;
  line-height: 0;
  font-size: 0.75em;
}
.cite-ref a {
  color: var(--el-color-primary);
  text-decoration: none;
}
.cite-ref a:hover,
.cite-ref a:focus-visible {
  text-decoration: underline;
}
.citations {
  margin-top: 8px;
  white-space: normal;
}
.citations summary {
  color: var(--el-color-primary);
  cursor: pointer;
  font-size: 13px;
}
.citation-list {
  margin: 0;
  padding-inline-start: 24px;
}
.citation {
  margin-top: 8px;
  border-radius: 3px;
}
.citation:focus {
  outline: 2px solid var(--el-color-primary-light-5);
  outline-offset: 3px;
}
.cite-head {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: #409eff;
}
.cite-text {
  margin: 4px 0 0;
  font-size: 12px;
  color: #666;
  white-space: pre-wrap;
}
.msg-meta {
  margin-top: 6px;
  font-size: 12px;
  color: #999;
}
.input-area {
  border-top: 1px solid #e5e7eb;
  padding: 12px 16px;
  display: grid;
  gap: 8px;
}
.report-controls {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 12px;
}
.report-select {
  width: 300px;
  max-width: 100%;
}
.report-change {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.draft-row {
  display: flex;
  gap: 12px;
  align-items: flex-end;
}
.draft-row .el-button {
  height: 40px;
}
</style>
