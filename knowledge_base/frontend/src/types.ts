export interface IndexOptions {
  chunking_strategy: 'fixed' | 'semantic'
  chunk_size: number
  chunk_overlap: number
  hierarchical_index: boolean
}
export interface KnowledgeBase extends IndexOptions {
  id: string
  application_id: string
  name: string
  description: string
  document_count: number
  created_at: string
  updated_at: string
}
export interface Job {
  id: string
  document_id: string
  revision: number
  index_id: string
  status: string
  stage: string
  error_message: string | null
  attempts: number
  created_at: string
  updated_at: string
}
export interface DocumentRecord {
  id: string
  knowledge_base_id: string
  title: string
  filename: string
  format: string
  revision: number
  status: string
  active_index_id: string | null
  chunk_count: number
  error_message: string | null
  metadata: Record<string, unknown>
  created_at: string
  updated_at: string
  content?: string
  jobs?: Job[]
  indexes?: { id: string; revision: number; status: string; options: IndexOptions }[]
}
export interface Chunk {
  id: string
  parent_id: string | null
  level: number
  chunk_no: number
  content: string
  char_start: number
  char_end: number
  title_path: string | string[]
  page_number: number | null
  article_no: string | null
  index_id: string
}
export interface SearchResult {
  knowledge_base_id: string
  document_id: string
  revision: number
  index_revision_id: string
  chunk_id: string
  title: string
  content: string
  score: number
  parent_content: string | null
  article_chunk_id?: string | null
  char_start: number
  char_end: number
  page_number: number | null
  metadata: Record<string, unknown>
}
export interface Page<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}
export const defaults: IndexOptions = {
  chunking_strategy: 'fixed',
  chunk_size: 800,
  chunk_overlap: 100,
  hierarchical_index: false,
}
export const titlePath = (value: string | string[] | undefined) =>
  Array.isArray(value) ? value.join(' / ') : value || ''
export const isProcessing = (status: string) =>
  ['pending', 'parsing', 'chunking', 'embedding', 'running', 'processing'].includes(status)
export const statusLabel = (status: string) =>
  ({
    pending: '等待处理',
    parsing: '解析中',
    chunking: '分块中',
    embedding: '生成向量',
    ready: '已就绪',
    failed: '处理失败',
    cancelled: '已取消',
    running: '处理中',
    processing: '处理中',
    completed: '已完成',
    succeeded: '已完成',
    cleanup: '清理中',
    deleted: '已删除',
  })[status] || status
export function formatDate(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false })
}
