/**
 * 与后端接口契约对应的类型定义。
 *
 * ⚠️ **这些类型必须与后端各切片的 `schemas.py` 保持一致** ——
 * 后端 Pydantic 模型是契约的唯一真源（见 03-概要设计 §5.5），
 * 本文件是它在 TypeScript 侧的镜像。改后端字段名时**必须同步改这里**。
 *
 * 两条全局约定（见 05-接口设计 §3）：
 * 1. **ID 一律是 string**，不是 number —— 后端主键是 BIGINT UNSIGNED，
 *    超出 JS 安全整数范围（2^53-1）后会静默丢精度。前端不得对 ID 做算术。
 * 2. **时间一律是 ISO 8601 带时区偏移的字符串**。
 */

// ============================================================
// 通用响应体（05-接口设计 §3.2）
// ============================================================

export interface ApiResponse<T = unknown> {
  code: number
  message: string
  data: T | null
  request_id: string
}

export interface FieldError {
  field: string
  reason: string
}

/** 参数校验失败时 data 的形状 */
export interface ErrorDetails {
  details: FieldError[]
}

/** 分页响应的 data 形状，所有列表接口统一 */
export interface Page<T> {
  items: T[]
  page: number
  page_size: number
  total: number
}

// ============================================================
// 业务错误码（05-接口设计 §3.3）
// ============================================================

export const ErrorCode = {
  OK: 0,

  PARAM_INVALID: 40001,
  BODY_MALFORMED: 40002,
  PAGE_OUT_OF_RANGE: 40003,

  ACCESS_TOKEN_INVALID: 40101,
  REFRESH_TOKEN_INVALID: 40102,

  FORBIDDEN: 40301,

  REVIEW_NOT_FOUND: 40401,
  QA_SESSION_NOT_FOUND: 40402,
  KB_DOC_NOT_FOUND: 40403,
  FILE_NOT_FOUND: 40404,

  PHONE_TAKEN: 40901,
  EMAIL_TAKEN: 40902,
  BAD_CREDENTIALS: 40903,
  ACCOUNT_DISABLED: 40904,
  REVIEW_IN_PROGRESS: 40905,
  REVIEW_NOT_FINISHED: 40906,
  REVIEW_FAILED: 40907,
  KB_DOC_EXISTS: 40908,
  SESSION_ARCHIVED: 40909,

  FILE_TOO_LARGE: 41301,
  UNSUPPORTED_FILE_TYPE: 41501,

  RATE_LIMITED: 42901,

  INTERNAL_ERROR: 50000,
  LLM_BAD_RESPONSE: 50201,
  OCR_BAD_RESPONSE: 50202,
  LLM_UNAVAILABLE: 50301,
  OCR_UNAVAILABLE: 50302,
  VECTOR_UNAVAILABLE: 50303,
} as const

// ============================================================
// 认证与用户（M1）
// ============================================================

export interface RegisterRequest {
  phone?: string
  email?: string
  password: string
  verify_code: string
}

export interface RegisterData {
  user_id: string
}

export interface LoginRequest {
  /** 手机号或邮箱 */
  account: string
  password: string
}

export interface LoginData {
  access_token: string
  refresh_token: string
  token_type: 'Bearer'
  /** 访问令牌有效期（秒） */
  expires_in: number
}

export interface ProfileData {
  real_name: string | null
  org_name: string | null
  org_role: string | null
}

export interface UserData {
  id: string
  /** **已脱敏**，形如 138****0000 */
  phone: string | null
  /** **已脱敏** */
  email: string | null
  account_type: string
  status: string
  last_login_at: string | null
  created_at: string
  profile: ProfileData | null
}

export interface UpdateProfileRequest {
  real_name?: string
  org_name?: string
  org_role?: string
}

// ============================================================
// 合同智能审查（M2）
// ============================================================

export interface FileUploadData {
  file_id: string
  original_name: string | null
  byte_size: number
  mime_type: string | null
  sha256: string
  /** 内容寻址命中去重时为 true */
  is_duplicate: boolean
}

export interface CreateReviewRequest {
  file_id: string
  contract_title?: string
  /** 为 true 时允许对同一文件并发多个审查任务 */
  force?: boolean
}

/** 审查任务状态（05-接口设计 §6.3）。终态是 succeeded / failed */
export type ReviewStatus = 'pending' | 'processing' | 'succeeded' | 'failed'

/** 处理阶段，用于展示进度文案 */
export type ReviewStage = 'ocr' | 'extract_terms' | 'retrieve' | 'analyze' | 'report' | null

export interface ReviewTaskData {
  task_id: string
  status: ReviewStatus
  stage: ReviewStage
  progress: number
  error_code?: string | null
  error_message?: string | null
  started_at?: string | null
  finished_at?: string | null
  created_at?: string
}

export type RiskLevel = 'high' | 'medium' | 'low'

/**
 * 风险点的依据类型。
 *
 * ⚠️ **前端必须据此区分呈现**（03-概要设计 §5.3、05-接口设计 §5.4）：
 * - `retrieved_law`  依据检索到的法条 → 展示法条引用，可点击查看原文
 * - `rule`           依据人工风险规则 → 标注"依据审查规则"，不冒充法条
 * - `llm_inference`  模型推断、**无直接法律依据** → 必须标注"仅供参考"
 *
 * 三者混为一谈是本项目最容易被质疑的设计缺陷。
 */
export type RiskSourceType = 'retrieved_law' | 'rule' | 'llm_inference'

export interface RiskPoint {
  id: string
  risk_level: RiskLevel
  risk_category: string | null
  clause_title: string | null
  clause_text: string | null
  /** ⚠️ 偏移基准是 contract_version.plain_text（原文），不是 OCR 结果、不是 PDF 坐标 */
  char_start: number | null
  char_end: number | null
  description: string
  suggestion: string | null
  legal_basis: string | null
  source_type: RiskSourceType
  confidence: number | null
  is_dismissed: boolean
}

export interface ExtractedTerms {
  parties?: string[]
  amount?: string
  payment_terms?: string
  liability?: string
  jurisdiction?: string
  term?: string
  [key: string]: unknown
}

export interface ReviewResultData {
  task_id: string
  contract_title: string
  summary: string | null
  counts: { high: number; medium: number; low: number }
  extracted_terms: ExtractedTerms | null
  risk_points: RiskPoint[]
}

export interface ReviewListItem {
  task_id: string
  contract_title: string
  status: ReviewStatus
  counts: { high: number; medium: number; low: number }
  created_at: string
  finished_at: string | null
}

// ============================================================
// 法律问答（M3）
// ============================================================

export interface QaCitation {
  document_id: string | null
  kb_chunk_id: string | null
  law_name: string | null
  article_no: string | null
  quoted_text: string | null
  relevance_score: number | null
}

export interface QaMessage {
  message_id: string
  role: 'user' | 'assistant'
  content: string
  /**
   * ⚠️ 为 false 时前端**必须**提示"未找到直接法律依据" ——
   * 这是"回答溯源"的反面：溯源不了的时候要说出来（05-接口设计 §5.6）
   */
  has_citation: boolean
  citations?: QaCitation[]
  model_name?: string | null
  latency_ms?: number | null
  created_at: string
}

export interface QaSession {
  session_id: string
  title: string | null
  status: 'active' | 'archived'
  message_count: number
  last_message_at?: string | null
  created_at: string
}

export interface QaSessionDetail extends QaSession {
  messages: Page<QaMessage>
}
