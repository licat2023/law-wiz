/**
 * 合同智能审查接口（M2 的 C 组）与文件上传（B 组）。
 *
 * 文件上传和审查任务分别由后端的 files 和 contract_review 领域提供，
 * 契约见 05-接口设计 §5.3/§5.4。
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

/** B-01 上传文件，浏览器提供传输总量时以整数百分比报告进度。 */
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
 * 同次提交遇到网络超时时应复用 `Idempotency-Key`，以便取回服务端已记录的任务。
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

/** C-04 生成报告端点地址，请求需携带当前用户的访问令牌。 */
export function reviewReportUrl(taskId: string, format: 'pdf' = 'pdf') {
  const base = import.meta.env.VITE_API_BASE ?? '/api'
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
