<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Upload, EditPen, Search, Document } from '@element-plus/icons-vue'
import { get, post, remove, request, basePath, documentPath } from '../api'
import {
  type KnowledgeBase,
  type DocumentRecord,
  type Page,
  type SearchResult,
  formatDate,
  statusLabel,
  isProcessing,
} from '../types'
import { report } from '../feedback'
import { usePolling } from '../polling'
import SafeMarkdown from '../components/SafeMarkdown.vue'
const route = useRoute(),
  router = useRouter(),
  kb = String(route.params.kb),
  path = basePath(kb)
const base = ref<KnowledgeBase>(),
  docs = ref<DocumentRecord[]>([]),
  total = ref(0),
  page = ref(1),
  loading = ref(true),
  failed = ref(false)
const tab = ref('documents'),
  filter = ref(''),
  status = ref(''),
  format = ref('')
const dialog = ref(false),
  mode = ref('file'),
  title = ref(''),
  content = ref(''),
  file = ref<File>(),
  busy = ref(false),
  formError = ref(''),
  preview = ref(false)
const query = ref(''),
  topK = ref(5),
  includeAbolished = ref(false),
  docType = ref(''),
  corpusTier = ref(''),
  results = ref<SearchResult[]>([]),
  articleContents = ref<Record<string, string>>({}),
  articleLimitReached = ref(false),
  searched = ref(false),
  searching = ref(false),
  searchError = ref('')
const applied = ref({ query: '', status: '', format: '' })
const busyDocument = ref('')
let loadSequence = 0
async function loadDocs(signal?: AbortSignal) {
  const sequence = ++loadSequence
  const params = new URLSearchParams({ page: String(page.value), page_size: '20' })
  for (const [key, value] of Object.entries(applied.value)) if (value) params.set(key, value)
  const data = await get<Page<DocumentRecord>>(`${path}/documents?${params}`, signal)
  if (sequence !== loadSequence) return
  docs.value = data.items
  total.value = data.total
}
async function applyFilters() {
  page.value = 1
  applied.value = { query: filter.value.trim(), status: status.value, format: format.value }
  await load()
  polling.resume()
}
async function resetFilters() {
  filter.value = ''
  status.value = ''
  format.value = ''
  await applyFilters()
}
async function retryDocument(doc: DocumentRecord) {
  busyDocument.value = doc.id
  try {
    await post(`${documentPath(kb, doc.id)}/indexes`, { revision: doc.revision }, true)
    await loadDocs()
    polling.resume()
    ElMessage.success('已重新安排索引任务')
  } catch (error) {
    report(error)
  } finally {
    busyDocument.value = ''
  }
}
async function deleteDocument(doc: DocumentRecord) {
  try {
    await ElMessageBox.confirm(
      `删除「${doc.title}」及其原文件和索引？此操作无法恢复。`,
      '删除文档',
      { confirmButtonText: '删除文档', cancelButtonText: '保留', type: 'warning' },
    )
    busyDocument.value = doc.id
    await remove(documentPath(kb, doc.id))
    await loadDocs()
    ElMessage.success('文档已删除')
  } catch (error) {
    report(error)
  } finally {
    busyDocument.value = ''
  }
}
async function load() {
  loading.value = true
  failed.value = false
  try {
    const values = await Promise.all([get<KnowledgeBase>(path), loadDocs()])
    base.value = values[0]
  } catch (e) {
    failed.value = true
    report(e)
  } finally {
    loading.value = false
  }
}
const polling = usePolling(
  loadDocs,
  () => tab.value === 'documents' && docs.value.some((d) => isProcessing(d.status)),
)
function open(next: string) {
  mode.value = next
  title.value = ''
  content.value = ''
  file.value = undefined
  formError.value = ''
  dialog.value = true
  preview.value = false
}
function choose(event: Event) {
  file.value = (event.target as HTMLInputElement).files?.[0]
}
async function createDocument() {
  if (mode.value === 'file' && !file.value) {
    formError.value = '请选择要上传的文件。'
    return
  }
  if (mode.value === 'markdown' && (!title.value.trim() || !content.value.trim())) {
    formError.value = '请填写标题和 Markdown 正文。'
    return
  }
  busy.value = true
  formError.value = ''
  try {
    let doc: DocumentRecord
    if (mode.value === 'file') {
      const data = new FormData()
      data.append('file', file.value!)
      if (title.value.trim()) data.append('title', title.value.trim())
      doc = await request<DocumentRecord>(`${path}/documents`, { method: 'POST', body: data }, true)
    } else
      doc = await post<DocumentRecord>(
        `${path}/documents`,
        { title: title.value.trim(), content: content.value },
        true,
      )
    dialog.value = false
    ElMessage.success('文档已创建，正在建立索引')
    await router.push(`/bases/${kb}/documents/${doc.id}`)
  } catch (e) {
    formError.value = e instanceof Error ? e.message : '创建失败。'
  } finally {
    busy.value = false
  }
}
async function search() {
  if (!query.value.trim()) {
    searchError.value = '请输入检索问题。'
    return
  }
  searching.value = true
  searchError.value = ''
  searched.value = false
  results.value = []
  articleContents.value = {}
  articleLimitReached.value = false
  try {
    const data = await post<{
      items: SearchResult[]
      article_contents?: Record<string, string>
      article_limit_reached?: boolean
    }>(`${path}/search`, {
      query: query.value.trim(),
      top_k: topK.value,
      include_abolished: includeAbolished.value,
      ...(docType.value ? { doc_type: docType.value } : {}),
      ...(corpusTier.value ? { corpus_tier: corpusTier.value } : {}),
    })
    results.value = data.items
    articleContents.value = data.article_contents ?? {}
    articleLimitReached.value = data.article_limit_reached ?? false
    searched.value = true
  } catch (e) {
    searchError.value = e instanceof Error ? e.message : '检索失败。'
  } finally {
    searching.value = false
  }
}
function locate(item: SearchResult) {
  void router.push({
    path: `/bases/${kb}/documents/${item.document_id}`,
    query: {
      index: item.index_revision_id,
      chunk: item.chunk_id,
      start: String(item.char_start),
      end: String(item.char_end),
      revision: String(item.revision),
      tab: 'source',
    },
  })
}
onMounted(load)
</script>
<template>
  <header class="page-heading">
    <div>
      <p class="breadcrumb">
        <router-link to="/">知识库</router-link><span>/</span>{{ base?.name || '文档工作区' }}
      </p>
      <h1>{{ base?.name || '文档工作区' }}</h1>
      <p class="muted">{{ base?.description || '集中管理文档，检查索引并验证检索结果。' }}</p>
    </div>
    <div class="actions">
      <el-button :icon="EditPen" @click="open('markdown')">新建 Markdown</el-button
      ><el-button type="primary" :icon="Upload" @click="open('file')">上传文档</el-button>
    </div>
  </header>
  <el-tabs v-model="tab" @tab-change="polling.resume"
    ><el-tab-pane label="文档" name="documents" /><el-tab-pane label="检索测试" name="search"
  /></el-tabs>
  <template v-if="tab === 'documents'">
    <div class="toolbar">
      <el-input
        v-model="filter"
        :prefix-icon="Search"
        placeholder="搜索文档标题"
        aria-label="搜索文档标题"
        clearable
        @keyup.enter="applyFilters"
        @clear="applyFilters"
      /><el-select
        v-model="status"
        placeholder="所有状态"
        clearable
        aria-label="文档状态"
        @change="applyFilters"
        ><el-option label="已就绪" value="ready" /><el-option
          label="处理中"
          value="indexing" /><el-option label="处理失败" value="failed" /></el-select
      ><el-select
        v-model="format"
        placeholder="所有格式"
        clearable
        aria-label="文件格式"
        @change="applyFilters"
        ><el-option
          v-for="f in ['pdf', 'docx', 'markdown', 'txt']"
          :key="f"
          :label="f.toUpperCase()"
          :value="f" /></el-select
      ><el-button :loading="loading" :icon="Search" @click="applyFilters">搜索</el-button
      ><el-button v-if="filter || status || format" text @click="resetFilters">重置</el-button>
    </div>
    <el-skeleton v-if="loading" :rows="5" animated />
    <div v-else-if="failed" class="empty-state">
      <h2>文档暂时无法加载</h2>
      <el-button @click="load">重新加载</el-button>
    </div>
    <div v-else-if="!docs.length" class="empty-state">
      <el-icon :size="40"><Document /></el-icon>
      <template v-if="applied.query || applied.status || applied.format"
        ><h2>没有符合条件的文档</h2>
        <p>调整关键词或筛选条件后重试。</p>
        <el-button @click="resetFilters">清除筛选</el-button></template
      >
      <template v-else
        ><h2>把第一份资料放进来</h2>
        <p>支持 Word、文本型 PDF、Markdown 和 TXT。扫描件暂不支持。</p>
        <el-button type="primary" @click="open('file')">上传文档</el-button></template
      >
    </div>
    <template v-else
      ><div class="table-wrap">
        <el-table :data="docs" class="document-table"
          ><el-table-column label="文档" min-width="240"
            ><template #default="{ row }"
              ><router-link :to="`/bases/${kb}/documents/${row.id}`" class="doc-link">{{
                row.title
              }}</router-link>
              <div class="tiny">{{ row.filename }}</div></template
            ></el-table-column
          ><el-table-column label="格式" width="112"
            ><template #default="{ row }"
              ><span class="format-badge">{{ row.format.toUpperCase() }}</span></template
            ></el-table-column
          ><el-table-column label="索引状态" width="135"
            ><template #default="{ row }"
              ><el-tag
                :type="
                  row.status === 'failed' ? 'danger' : row.status === 'ready' ? 'success' : 'info'
                "
                effect="plain"
                >{{ statusLabel(row.status) }}</el-tag
              >
              <div v-if="row.active_index_id && row.status !== 'ready'" class="tiny">
                旧索引仍可检索
              </div></template
            ></el-table-column
          ><el-table-column prop="chunk_count" label="分块" width="80" /><el-table-column
            label="更新于"
            min-width="170"
            ><template #default="{ row }"
              ><span class="muted">{{ formatDate(row.updated_at) }}</span></template
            ></el-table-column
          ><el-table-column label="操作" width="150"
            ><template #default="{ row }"
              ><el-button
                v-if="row.status === 'failed'"
                text
                type="primary"
                :loading="busyDocument === row.id"
                @click="retryDocument(row)"
                >重试</el-button
              ><el-button
                text
                type="danger"
                :disabled="busyDocument === row.id"
                @click="deleteDocument(row)"
                >删除</el-button
              ></template
            ></el-table-column
          ></el-table
        >
      </div>
      <ul class="mobile-document-list" aria-label="文档列表">
        <li v-for="row in docs" :key="row.id" class="mobile-document">
          <header>
            <div class="mobile-document-title">
              <router-link :to="`/bases/${kb}/documents/${row.id}`" class="doc-link">{{
                row.title
              }}</router-link>
              <div class="tiny">{{ row.filename }}</div>
            </div>
            <el-tag
              :type="
                row.status === 'failed' ? 'danger' : row.status === 'ready' ? 'success' : 'info'
              "
              effect="plain"
              >{{ statusLabel(row.status) }}</el-tag
            >
          </header>
          <div class="mobile-document-meta">
            <span class="format-badge">{{ row.format.toUpperCase() }}</span>
            <span>{{ row.chunk_count }} 个分块</span>
            <span v-if="row.active_index_id && row.status !== 'ready'">旧索引仍可检索</span>
          </div>
          <footer>
            <span class="tiny">{{ formatDate(row.updated_at) }}</span>
            <div>
              <el-button
                v-if="row.status === 'failed'"
                text
                type="primary"
                :loading="busyDocument === row.id"
                @click="retryDocument(row)"
                >重试</el-button
              >
              <el-button
                text
                type="danger"
                :disabled="busyDocument === row.id"
                :aria-label="`删除 ${row.title}`"
                @click="deleteDocument(row)"
                >删除</el-button
              >
            </div>
          </footer>
        </li>
      </ul>
      <div class="pagination-bar">
        <span class="muted">共 {{ total }} 份匹配文档</span
        ><el-pagination
          v-if="total > 20"
          v-model:current-page="page"
          :total="total"
          :page-size="20"
          layout="prev, pager, next"
          @current-change="load"
        /></div
    ></template>
  </template>
  <section v-else class="search-workspace">
    <div class="search-form">
      <h2>验证你的知识库</h2>
      <p class="muted">输入问题，查看实际命中的片段与完整上下文。</p>
      <el-form label-position="top" @submit.prevent="search"
        ><el-form-item label="检索问题" for="search-query"
          ><el-input
            id="search-query"
            v-model="query"
            type="textarea"
            :rows="3"
            placeholder="例如：合同解除需要满足哪些条件？"
        /></el-form-item>
        <div class="form-pair">
          <el-form-item label="返回数量"
            ><el-input-number v-model="topK" :min="1" :max="20" /></el-form-item
          ><el-form-item label="文档类型"
            ><el-input v-model="docType" placeholder="可选" /></el-form-item
          ><el-form-item label="语料层级"
            ><el-input v-model="corpusTier" placeholder="可选"
          /></el-form-item>
        </div>
        <el-checkbox v-model="includeAbolished">包含已废止资料</el-checkbox>
        <p v-if="searchError" role="alert" class="error-text">{{ searchError }}</p>
        <el-button type="primary" native-type="submit" :icon="Search" :loading="searching"
          >开始检索</el-button
        ></el-form
      >
    </div>
    <div class="search-results" aria-live="polite">
      <div v-if="!searched && !searching" class="search-intro">
        <el-icon :size="34"><Search /></el-icon>
        <p>检索结果将显示在这里</p>
      </div>
      <el-skeleton v-if="searching" :rows="5" animated />
      <el-alert
        v-if="articleLimitReached"
        title="部分法条超过完整引用长度上限，未列入结果。"
        type="warning"
        :closable="false"
      />
      <div v-if="searched && !results.length && !articleLimitReached" class="empty-state">
        <h3>未找到匹配依据</h3>
        <p>尝试换一种表述，或检查文档是否已完成索引。</p>
      </div>
      <template v-if="searched && results.length"
        ><div class="section-meta">找到 {{ results.length }} 条依据</div>
        <article v-for="(item, i) in results" :key="item.chunk_id" class="result-item">
          <header>
            <h3>{{ i + 1 }}. {{ item.title }}</h3>
            <span class="score">相关度 {{ Number(item.score).toFixed(3) }}</span>
          </header>
          <SafeMarkdown :content="item.content" />
          <details v-if="item.article_chunk_id && articleContents[item.article_chunk_id]">
            <summary>展开完整条文</summary>
            <SafeMarkdown :content="articleContents[item.article_chunk_id]" />
          </details>
          <details v-else-if="item.parent_content && item.parent_content !== item.content">
            <summary>展开父级上下文</summary>
            <SafeMarkdown :content="item.parent_content" />
          </details>
          <div class="result-footer">
            <span class="tiny"
              >修订 {{ item.revision
              }}<template v-if="item.page_number"> · 第 {{ item.page_number }} 页</template
              ><template v-if="item.metadata.article_no">
                · {{ item.metadata.article_no }}</template
              ></span
            ><el-button text type="primary" @click="locate(item)">定位来源</el-button>
          </div>
        </article></template
      >
    </div>
  </section>
  <el-dialog
    v-model="dialog"
    destroy-on-close
    :title="mode === 'file' ? '上传文档' : '新建 Markdown'"
    :width="mode === 'file' ? '560px' : '900px'"
    :close-on-click-modal="false"
    ><el-form label-position="top"
      ><el-form-item
        :label="mode === 'file' ? '标题（可选，默认使用文件名）' : '文档标题'"
        for="new-title"
        ><el-input id="new-title" v-model="title" maxlength="200" /></el-form-item
      ><template v-if="mode === 'file'"
        ><label for="upload-file" class="file-picker"
          ><el-icon :size="30"><Upload /></el-icon><strong>选择文档</strong
          ><input
            id="upload-file"
            type="file"
            accept=".pdf,.docx,.md,.markdown,.txt"
            @change="choose"
          /><span>{{ file?.name || '支持 .docx / .pdf / .md / .markdown / .txt' }}</span></label
        >
        <p class="hint">
          上传后自动解析并索引。PDF 需包含可选中的文本；不支持扫描件和旧版 .doc。
        </p></template
      ><template v-else
        ><div class="editor-switch">
          <el-switch v-model="preview" active-text="预览 Markdown" />
        </div>
        <SafeMarkdown v-if="preview" :content="content" /><el-form-item
          v-else
          label="Markdown 正文"
          for="new-content"
          ><el-input
            id="new-content"
            v-model="content"
            type="textarea"
            :rows="15"
            placeholder="# 文档标题&#10;&#10;在这里编写内容…" /></el-form-item
      ></template>
      <p v-if="formError" role="alert" class="error-text">{{ formError }}</p></el-form
    ><template #footer
      ><el-button :disabled="busy" @click="dialog = false">取消</el-button
      ><el-button type="primary" :loading="busy" @click="createDocument">{{
        mode === 'file' ? '上传并建立索引' : '创建并建立索引'
      }}</el-button></template
    ></el-dialog
  >
</template>
