<script setup lang="ts">
/**
 * 法律问答页（M3）。
 *
 * 对接口契约的实现约束（docs/05-接口设计.md §5.6 / §6.2）：
 * 1. 提问是异步的：E-04 返回**预分配**的 assistant_message_id，先用它在界面
 *    占位（"正在思考…"），轮询 E-03 拿到内容后**按 ID 原地替换**；
 * 2. 必须携带 Idempotency-Key；失败不自动重试（§6.2），用户重新发起
 *    即新的操作、用新的键；
 * 3. has_citation === false 时必须显式提示"未找到直接法律依据，仅供参考"；
 * 4. 轮询间隔递增 1s→2s→3s→5s，上限 90 秒，同一页面最多 1 个轮询循环
 *    （等待回答期间禁止再次提问与切换会话）。
 */
import { Loading } from '@element-plus/icons-vue'
import { nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

import {
  archiveSession,
  createSession,
  getSession,
  listSessions,
  newIdempotencyKey,
  sendMessage,
} from '@/api/qa'
import type { QaMessage, QaSession } from '@/api/types'

const POLL_INTERVALS = [1000, 2000, 3000, 5000]
const POLL_TIMEOUT = 90_000

interface DisplayMessage extends QaMessage {
  /** 轮询超时占位，不算"未找到依据" */
  timedOut?: boolean
}

const sessions = ref<QaSession[]>([])
const currentSession = ref<QaSession | null>(null)
const messages = ref<DisplayMessage[]>([])
const draft = ref('')
const waiting = ref(false)

const msgListRef = ref<HTMLElement>()

let disposed = false
onUnmounted(() => {
  disposed = true
})

watch(
  () => messages.value.length,
  async () => {
    await nextTick()
    const el = msgListRef.value
    if (el) el.scrollTop = el.scrollHeight
  },
)

function sleep(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

/** 轮询 E-03，直到该 assistant 消息有内容或 90 秒超时 */
async function waitForAnswer(sessionId: string, assistantId: string): Promise<QaMessage | null> {
  const deadline = Date.now() + POLL_TIMEOUT
  let idx = 0
  while (!disposed && Date.now() < deadline) {
    await sleep(POLL_INTERVALS[idx])
    idx = Math.min(idx + 1, POLL_INTERVALS.length - 1)
    try {
      const detail = await getSession(sessionId, { page: 1, page_size: 100 })
      const msg = detail.messages.items.find((m) => m.message_id === assistantId)
      if (msg && msg.content) return msg
    } catch {
      // 网络抖动继续轮询
    }
  }
  return null
}

async function loadSessionList() {
  try {
    const page = await listSessions({ page: 1, page_size: 50 })
    sessions.value = page.items
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '加载会话列表失败')
  }
}

async function selectSession(s: QaSession) {
  if (waiting.value) {
    ElMessage.warning('请等待当前回答完成')
    return
  }
  currentSession.value = s
  messages.value = []
  try {
    const detail = await getSession(s.session_id, { page: 1, page_size: 100 })
    messages.value = detail.messages.items
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '加载会话失败')
  }
}

async function newChat() {
  if (waiting.value) {
    ElMessage.warning('请等待当前回答完成')
    return
  }
  try {
    const s = await createSession()
    sessions.value.unshift(s)
    currentSession.value = s
    messages.value = []
    draft.value = ''
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '创建会话失败')
  }
}

/** E-05：归档（而非删除） */
async function archive(s: QaSession) {
  try {
    await archiveSession(s.session_id)
    sessions.value = sessions.value.filter((x) => x.session_id !== s.session_id)
    if (currentSession.value?.session_id === s.session_id) {
      currentSession.value = null
      messages.value = []
    }
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '归档失败')
  }
}

async function handleSend() {
  const content = draft.value.trim()
  if (!content || !currentSession.value || waiting.value) return

  const session = currentSession.value
  const firstQuestion = session.message_count === 0

  waiting.value = true
  try {
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

    const answer = await waitForAnswer(session.session_id, resp.assistant_message_id)
    if (disposed) return
    if (answer) {
      const idx = messages.value.findIndex((m) => m.message_id === answer.message_id)
      if (idx >= 0) messages.value[idx] = answer
      else messages.value.push(answer)
    } else {
      placeholder.content = '（回答耗时较长，请稍后重新打开会话查看）'
      placeholder.timedOut = true
    }
    session.message_count += 2
    if (firstQuestion) loadSessionList() // 首条提问会生成会话标题，刷新列表
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '发送失败，请稍后重试')
  } finally {
    waiting.value = false
  }
}

onMounted(async () => {
  await loadSessionList()
  if (sessions.value.length > 0 && !disposed) {
    await selectSession(sessions.value[0])
  }
})
</script>

<template>
  <div class="qa-container">
    <aside class="side">
      <el-button type="primary" style="width: 100%" @click="newChat">新建对话</el-button>

      <div class="session-list">
        <div
          v-for="s in sessions"
          :key="s.session_id"
          class="session-item"
          :class="{ active: s.session_id === currentSession?.session_id }"
          @click="selectSession(s)"
        >
          <div class="session-title">{{ s.title || '新对话' }}</div>
          <div class="session-meta">
            <span>{{ s.message_count }} 条消息</span>
            <el-button link size="small" type="danger" @click.stop="archive(s)">归档</el-button>
          </div>
        </div>
        <el-empty v-if="sessions.length === 0" description="暂无历史会话" :image-size="60" />
      </div>
    </aside>

    <main class="chat">
      <template v-if="currentSession">
        <div ref="msgListRef" class="msg-list">
          <div v-for="m in messages" :key="m.message_id" class="msg-row" :class="m.role">
            <div class="bubble">
              <template v-if="m.role === 'assistant' && !m.content">
                <span class="thinking">正在思考</span>
                <el-icon class="is-loading"><Loading /></el-icon>
              </template>
              <template v-else>{{ m.content }}</template>

              <div
                v-if="m.role === 'assistant' && m.content && !m.timedOut && !m.has_citation"
                class="no-cite"
              >
                提示：本条回答未找到直接法律依据，仅供参考
              </div>

              <div v-if="m.citations && m.citations.length" class="citations">
                <div v-for="(c, i) in m.citations" :key="i" class="citation">
                  <p class="cite-head">
                    {{ c.law_name || '未知法规' }} · {{ c.article_no || '—' }}
                  </p>
                  <p v-if="c.quoted_text" class="cite-text">{{ c.quoted_text }}</p>
                </div>
              </div>

              <div v-if="m.role === 'assistant' && m.model_name" class="msg-meta">
                {{ m.model_name }} · {{ m.latency_ms != null ? `${m.latency_ms}ms` : '' }}
              </div>
            </div>
          </div>

          <el-empty
            v-if="messages.length === 0"
            description="向 AI 咨询法律问题，回答会标注所依据的法条"
            :image-size="80"
          />
        </div>

        <div class="input-area">
          <el-input
            v-model="draft"
            type="textarea"
            :rows="3"
            resize="none"
            placeholder="输入法律问题，Enter 发送，Shift+Enter 换行"
            :disabled="waiting"
            @keydown.enter.exact.prevent="handleSend"
          />
          <el-button
            type="primary"
            :loading="waiting"
            :disabled="!draft.trim()"
            @click="handleSend"
          >
            发送
          </el-button>
        </div>
      </template>

      <el-empty v-else description="点击左侧「新建对话」开始法律咨询" />
    </main>
  </div>
</template>

<style scoped>
.qa-container {
  display: flex;
  gap: 16px;
  height: calc(100vh - 60px - 40px);
}
.side {
  width: 260px;
  flex-shrink: 0;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 16px;
  overflow-y: auto;
}
.session-list {
  margin-top: 12px;
}
.session-item {
  padding: 10px 12px;
  border-radius: 6px;
  cursor: pointer;
  margin-bottom: 4px;
}
.session-item:hover {
  background: #f5f7fa;
}
.session-item.active {
  background: var(--el-color-primary-light-9);
}
.session-title {
  font-size: 14px;
  color: #333;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.session-meta {
  margin-top: 4px;
  font-size: 12px;
  color: #999;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.chat {
  flex: 1;
  min-width: 0;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  display: flex;
  flex-direction: column;
}
.msg-list {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
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
.no-cite {
  margin-top: 8px;
  font-size: 12px;
  color: #e6a23c;
}
.citations {
  margin-top: 10px;
  border-top: 1px dashed #dcdfe6;
  padding-top: 8px;
}
.citation {
  margin-bottom: 8px;
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
}
.msg-meta {
  margin-top: 6px;
  font-size: 12px;
  color: #999;
}
.input-area {
  border-top: 1px solid #e5e7eb;
  padding: 12px 16px;
  display: flex;
  gap: 12px;
  align-items: flex-end;
}
.input-area .el-button {
  height: 40px;
}
</style>
