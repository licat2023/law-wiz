/**
 * 法律 AI 问答接口（M3 的 E 组）。
 *
 * ⚠️ **M3 的后端切片尚未实现**（见 `backend/app/slices/README.md`，由 C 负责）。
 * 函数签名已按 05-接口设计 §5.6 冻结。
 */

import { api, http } from './client'
import type { Page, QaSession, QaSessionDetail } from './types'

/** E-01 创建问答会话 */
export function createSession(title?: string) {
  return api.post<QaSession>('/qa/sessions', title ? { title } : {})
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
 * 轮询到内容后按 ID 原地替换，避免消息顺序错乱。
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

/** E-05 归档会话（**归档而非删除**，历史问答保留可查） */
export function archiveSession(sessionId: string) {
  return api.delete<null>(`/qa/sessions/${sessionId}`)
}

export function newIdempotencyKey(): string {
  return crypto.randomUUID()
}
