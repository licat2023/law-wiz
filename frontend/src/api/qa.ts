/**
 * 法律 AI 问答接口（M3 的 E 组）。
 *
 * 异步提交、助手消息流和会话历史的契约见 docs/05-接口设计.md §5.6。
 */

import { api, http } from './client'
import type { Page, QaSession, QaSessionDetail } from './types'

/** E-01 创建问答会话，可关联已完成报告及任务内风险点。 */
export function createSession(
  payload: { title?: string; review_task_id?: string; risk_point_id?: string } = {},
) {
  return api.post<QaSession>('/qa/sessions', payload)
}

/** E-02 会话列表 */
export function listSessions(params: { page?: number; page_size?: number; status?: string } = {}) {
  return api.get<Page<QaSession>>('/qa/sessions', params)
}

/** E-03 会话详情（含消息分页） */
export function getSession(sessionId: string, params: { page?: number; page_size?: number } = {}) {
  return api.get<QaSessionDetail>(`/qa/sessions/${sessionId}`, params)
}

/**
 * E-04 提问（异步）。
 *
 * ⚠️ **必须携带 `Idempotency-Key`**（05-接口设计 §3.5）：重复提交会产生两条
 * 内容不同的回答，用户无法判断哪条有效。
 *
 * 返回 `assistant_message_id` 是**预分配**的，前端可用它先在界面占位，
 * 订阅该消息的增量，收到正式结果后按 ID 原地替换。
 */
export async function sendMessage(
  sessionId: string,
  content: string,
  idempotencyKey: string,
): Promise<{ user_message_id: string; assistant_message_id: string; status: string }> {
  const resp = await http.post(
    `/qa/sessions/${sessionId}/messages`,
    { content },
    { headers: { 'Idempotency-Key': idempotencyKey } },
  )
  return resp.data.data as {
    user_message_id: string
    assistant_message_id: string
    status: string
  }
}

/** 订阅已有助手消息。流结束后调用方通过会话详情读取正式结果。 */
export async function streamAnswer(
  sessionId: string,
  assistantId: string,
  signal: AbortSignal,
  onDelta: (text: string) => void,
) {
  const response = await http.get<ReadableStream<Uint8Array>>(
    `/qa/sessions/${sessionId}/messages/${assistantId}/stream`,
    {
      adapter: 'fetch',
      responseType: 'stream',
      headers: { Accept: 'text/event-stream, application/json' },
      signal,
      timeout: 0,
    },
  )
  const body = response.data
  const contentType = response.headers['content-type']
  if (typeof contentType !== 'string' || !contentType.startsWith('text/event-stream')) {
    await body.cancel()
    throw new Error('问答流响应格式不合法')
  }

  const reader = body.pipeThrough(new TextDecoderStream()).getReader()
  const separator = /\r?\n\r?\n/
  let buffer = ''
  try {
    while (!signal.aborted) {
      const next = await reader.read()
      if (next.done) return
      buffer += next.value
      let boundary = separator.exec(buffer)
      while (boundary) {
        const lines = buffer.slice(0, boundary.index).split(/\r?\n/)
        buffer = buffer.slice(boundary.index + boundary[0].length)
        const event = lines
          .find((line) => line.startsWith('event:'))
          ?.slice(6)
          .trim()
        if (event === 'done') return
        if (event === 'delta') {
          const data = lines.find((line) => line.startsWith('data:'))?.slice(5)
          const text = data ? JSON.parse(data).text : undefined
          if (typeof text === 'string' && text) onDelta(text)
        }
        boundary = separator.exec(buffer)
      }
    }
  } finally {
    await reader.cancel().catch(() => undefined)
    reader.releaseLock()
  }
}

/** E-05 归档会话（**归档而非删除**，历史问答保留可查） */
export function archiveSession(sessionId: string) {
  return api.delete<null>(`/qa/sessions/${sessionId}`)
}

/** 为一次新提问生成幂等键。同一个请求重放时沿用原键。 */
export function newIdempotencyKey(): string {
  return crypto.randomUUID()
}
