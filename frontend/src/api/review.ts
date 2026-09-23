/**
 * 合同智能审查接口（M2 的 C 组）与文件上传（B 组）。
 *
 * ⚠️ **M2 的后端切片尚未实现**（见 `backend/app/slices/README.md`，由 B 负责）。
 * 本文件的函数签名已按 05-接口设计 §5.3/§5.4 冻结 ——
 * 后端实现后即可直接联调，**前端不需要改调用方式**。
 */

import { api, http } from './client'
import type {
  CreateReviewRequest,
  FileUploadData,
  Page,
  ReviewListItem,
  ReviewResultData,
  ReviewTaskData,
} from './types'

/** B-01 上传文件（multipart/form-data） */
export async function uploadFile(
  file: File,
  onProgress?: (percent: number) => void,
): Promise<FileUploadData> {
  const form = new FormData()
  form.append('file', file)

  const resp = await http.post('/files', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: (e) => {
      if (onProgress && e.total) {
        onProgress(Math.round((e.loaded / e.total) * 100))
      }
    },
  })
  return resp.data.data as FileUploadData
}

/**
 * C-01 发起合同审查（异步）。
 *
 * ⚠️ **必须携带 `Idempotency-Key`**（05-接口设计 §3.5）：审查会消耗 LLM 额度，
 * 网络超时重试时若不带同一个 key，会重复扣费并产生两个任务。
 *
 * **刻意不提供"不带幂等键"的版本** —— 契约要求必须带键，那么暴露一个不带的
 * 入口就等于给调用方留了一个必然踩的坑。
 */
export async function createReview(
  payload: CreateReviewRequest,
  idempotencyKey: string,
): Promise<ReviewTaskData> {
  const resp = await http.post('/reviews', payload, {
    headers: { 'Idempotency-Key': idempotencyKey },
  })
  return resp.data.data as ReviewTaskData
}

/** 生成幂等键。同一次用户操作（含其重试）必须复用同一个键 */
export function newIdempotencyKey(): string {
  return crypto.randomUUID()
}

/** C-02 查询审查任务状态（轮询用） */
export function getReviewTask(taskId: string) {
  return api.get<ReviewTaskData>(`/reviews/${taskId}`)
}

/** C-03 获取审查结果（仅任务 succeeded 时可调用） */
export function getReviewResult(taskId: string) {
  return api.get<ReviewResultData>(`/reviews/${taskId}/result`)
}

/** C-04 下载审查报告；返回可直接用于 <a download> 的地址 */
export function reviewReportUrl(taskId: string, format: 'pdf' = 'pdf') {
  const base = import.meta.env.VITE_API_BASE ?? '/api/v1'
  return `${base}/reviews/${taskId}/report?format=${format}`
}

/** C-05 审查历史列表 */
export function listReviews(params: { page?: number; page_size?: number; status?: string } = {}) {
  return api.get<Page<ReviewListItem>>('/reviews', params)
}

/** C-06 标记风险点为误报（收集模型误报样本的唯一途径） */
export function dismissRiskPoint(taskId: string, riskPointId: string, isDismissed = true) {
  return api.patch(`/reviews/${taskId}/risk-points/${riskPointId}`, {
    is_dismissed: isDismissed,
  })
}
