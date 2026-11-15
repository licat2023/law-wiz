<script setup lang="ts">
/** 查看和维护文档修订、解析正文及分块，支持从检索结果定位来源。 */
import { computed, nextTick, onMounted, ref, useTemplateRef, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Download, EditPen, Refresh, Upload } from '@element-plus/icons-vue'
import { get, patch, post, remove, request, documentPath, basePath, download } from '../api'
import {
  defaults,
  isProcessing,
  statusLabel,
  formatDate,
  titlePath,
  type DocumentRecord,
  type KnowledgeBase,
  type Chunk,
  type Page,
  type IndexOptions,
} from '../types'
import { report } from '../feedback'
import { usePolling } from '../polling'
import { sourceParts } from '../markdown'
import SafeMarkdown from '../components/SafeMarkdown.vue'
import IndexSettings from '../components/IndexSettings.vue'
import MetadataEditor from '../components/MetadataEditor.vue'
const route = useRoute(),
  router = useRouter(),
  kb = String(route.params.kb),
  docId = String(route.params.doc),
  path = documentPath(kb, docId)
const doc = ref<DocumentRecord>(),
  base = ref<KnowledgeBase>(),
  loading = ref(true),
  failed = ref(false),
  busy = ref(false)
const tab = ref(String(route.query.tab || 'preview')),
  dialog = ref<'edit' | 'replace' | 'index'>('edit'),
  dialogOpen = ref(false),
  formError = ref(''),
  editTitle = ref(''),
  editContent = ref(''),
  openingContent = ref(''),
  editRevision = ref(0),
  editMetadata = ref<Record<string, unknown>>({}),
  file = ref<File>(),
  editPreview = ref(false),
  options = ref<IndexOptions>({ ...defaults })
const metadataEditor = useTemplateRef('metadataEditor')
const metadataEntries = computed(() => Object.entries(doc.value?.metadata ?? {}))
const chunks = ref<Chunk[]>([]),
  chunkTotal = ref(0),
  chunkPage = ref(1),
  chunkLoading = ref(false),
  index = ref(String(route.query.index || '')),
  selected = ref(String(route.query.chunk || ''))
// 检索链接和手动选择会锁定索引，避免轮询刷新时跳到新发布的版本。
const manualIndex = ref(Boolean(route.query.index))
const editable = computed(() => ['md', 'markdown'].includes(doc.value?.format || ''))
const selectedChunk = computed(() => chunks.value.find((chunk) => chunk.id === selected.value))
const related = ref<Chunk[]>([])
const findingChildren = ref(false)
const children = computed(() => [
  ...new Map(
    [...chunks.value, ...related.value]
      .filter((chunk) => chunk.parent_id === selected.value)
      .map((chunk) => [chunk.id, chunk]),
  ).values(),
])
const sourceRevision = computed(() => Number(route.query.revision || doc.value?.revision))
const sourceCurrent = computed(
  () => !route.query.revision || sourceRevision.value === doc.value?.revision,
)
const parsedContent = computed(() => doc.value?.content || '')
const sourceChars = computed(() => Array.from(parsedContent.value))
const sourcePageSize = 10_000
const sourceStart = computed(() => Math.max(0, Number(route.query.start) || 0))
const sourcePage = ref(Math.floor(sourceStart.value / sourcePageSize) + 1)
const sourcePageCount = computed(() =>
  Math.max(1, Math.ceil(sourceChars.value.length / sourcePageSize)),
)
const previewAll = ref(false)
const previewLimit = 20_000
const previewContent = computed(() =>
  previewAll.value ? parsedContent.value : sourceChars.value.slice(0, previewLimit).join(''),
)
// 只给匹配修订的正文加高亮，并把全篇偏移换算为当前页内偏移。
const highlight = computed(() => {
  const offset = (sourcePage.value - 1) * sourcePageSize
  const text = sourceChars.value.slice(offset, offset + sourcePageSize).join('')
  const start = Math.max(0, sourceStart.value - offset)
  const end = Math.min(sourcePageSize, Number(route.query.end || 0) - offset)
  return sourceCurrent.value && start < end ? sourceParts(text, start, end) : [text, '', '']
})
watch(sourcePageCount, (count) => {
  if (sourcePage.value > count) sourcePage.value = 1
})
const jobs = computed(() => doc.value?.jobs || [])
const indexes = computed(() => [
  ...new Set(
    [
      doc.value?.active_index_id,
      ...(doc.value?.indexes || []).map((value) => value.id),
      ...jobs.value.map((job) => job.index_id),
      index.value,
    ].filter((id): id is string => Boolean(id)),
  ),
])
async function loadDoc(signal?: AbortSignal) {
  const previous = doc.value?.active_index_id
  doc.value = await get<DocumentRecord>(path, signal)
  if (!index.value || (!manualIndex.value && index.value === previous)) {
    const changed = index.value !== doc.value.active_index_id
    index.value = doc.value.active_index_id || ''
    if (changed && tab.value === 'chunks') {
      chunkPage.value = 1
      selected.value = ''
      await loadChunks()
    }
  }
}
const polling = usePolling(loadDoc, () =>
  Boolean(
    doc.value &&
    (isProcessing(doc.value.status) || jobs.value.some((job) => isProcessing(job.status))),
  ),
)
async function load() {
  loading.value = true
  failed.value = false
  try {
    await Promise.all([
      loadDoc(),
      get<KnowledgeBase>(basePath(kb)).then((value) => {
        base.value = value
      }),
    ])
    if (tab.value === 'chunks') await loadLocatedChunks()
  } catch (e) {
    failed.value = true
    report(e)
  } finally {
    loading.value = false
  }
  await nextTick()
  document.querySelector('mark')?.scrollIntoView({ block: 'center' })
}
async function loadChunks() {
  if (!index.value) {
    chunks.value = []
    return
  }
  chunkLoading.value = true
  try {
    const data = await get<Page<Chunk>>(
      `${path}/chunks?index_id=${encodeURIComponent(index.value)}&page=${chunkPage.value}&page_size=100`,
    )
    chunks.value = data.items
    chunkTotal.value = data.total
    if (!selected.value || !chunks.value.some((c) => c.id === selected.value))
      selected.value = chunks.value[0]?.id || ''
  } catch (e) {
    report(e)
  } finally {
    chunkLoading.value = false
  }
}
watch(selected, () => {
  related.value = []
})
watch(tab, (value) => {
  if (value === 'chunks') void loadLocatedChunks()
  polling.resume()
})
/** 打开分块面板时先载入一页，再跨页定位检索结果指定的分块。 */
async function loadLocatedChunks() {
  await loadChunks()
  if (route.query.chunk) await selectChunk(String(route.query.chunk)).catch(report)
}
async function findChildren() {
  const parent = selected.value
  findingChildren.value = true
  try {
    const matches: Chunk[] = []
    for (let page = 1; page <= Math.ceil(chunkTotal.value / 100); page++) {
      const data = await get<Page<Chunk>>(
        `${path}/chunks?index_id=${encodeURIComponent(index.value)}&page=${page}&page_size=100`,
      )
      matches.push(...data.items.filter((chunk) => chunk.parent_id === parent))
    }
    // 查询跨多页时，用户可能已经选中另一个父块。
    if (selected.value === parent) related.value = matches
    if (!matches.length) ElMessage.info('该分块没有子块。')
  } catch (error) {
    report(error)
  } finally {
    findingChildren.value = false
  }
}
async function selectChunk(id: string) {
  selected.value = id
  if (chunks.value.some((c) => c.id === id)) return
  const pages = Math.ceil(chunkTotal.value / 100)
  for (let page = 1; page <= pages; page++) {
    const data = await get<Page<Chunk>>(
      `${path}/chunks?index_id=${encodeURIComponent(index.value)}&page=${page}&page_size=100`,
    )
    if (data.items.some((c) => c.id === id)) {
      chunkPage.value = page
      chunks.value = data.items
      return
    }
  }
  ElMessage.info('未找到关联分块，请检查索引版本。')
}
function open(mode: 'edit' | 'replace' | 'index') {
  dialog.value = mode
  dialogOpen.value = true
  formError.value = ''
  editTitle.value = doc.value?.title || ''
  editContent.value = doc.value?.content || ''
  openingContent.value = editContent.value
  // 保存使用打开表单时的修订，以便后端拒绝覆盖期间发生的并发更新。
  editRevision.value = doc.value?.revision || 0
  editMetadata.value = doc.value?.metadata ?? {}
  file.value = undefined
  editPreview.value = false
  if (base.value)
    options.value = {
      chunking_strategy: base.value.chunking_strategy,
      chunk_size: base.value.chunk_size,
      chunk_overlap: base.value.chunk_overlap,
      hierarchical_index: base.value.hierarchical_index,
    }
  const active = doc.value?.indexes?.find((value) => value.id === doc.value?.active_index_id)
  if (active) options.value = { ...active.options }
}
function choose(event: Event) {
  file.value = (event.target as HTMLInputElement).files?.[0]
}
async function save() {
  if (!doc.value) return
  busy.value = true
  formError.value = ''
  try {
    if (dialog.value === 'edit') {
      if (!metadataEditor.value) return
      if (!editTitle.value.trim()) throw new Error('请填写文档标题。')
      const contentChanged = editable.value && editContent.value !== openingContent.value
      if (contentChanged && !editContent.value.trim()) throw new Error('Markdown 正文不能为空。')
      await patch(path, {
        revision: editRevision.value,
        title: editTitle.value.trim(),
        metadata: metadataEditor.value.readMetadata(),
        ...(contentChanged ? { content: editContent.value } : {}),
      })
    } else if (dialog.value === 'replace') {
      if (!file.value) throw new Error('请选择替换文件。')
      const data = new FormData()
      data.append('file', file.value)
      data.append('revision', String(editRevision.value))
      await request(`${path}/file`, { method: 'PUT', body: data }, true)
    } else {
      if (options.value.chunk_overlap >= options.value.chunk_size)
        throw new Error('重叠长度必须小于块长度。')
      await post(`${path}/indexes`, { revision: editRevision.value, ...options.value }, true)
    }
    dialogOpen.value = false
    ElMessage.success('更改已保存')
    await loadDoc()
    polling.resume()
  } catch (e) {
    formError.value = e instanceof Error ? e.message : '保存失败。'
  } finally {
    busy.value = false
  }
}
async function deleteDoc() {
  if (!doc.value) return
  try {
    await ElMessageBox.confirm(
      `删除「${doc.value.title}」及其所有分块与原文件？此操作无法恢复。`,
      '删除文档',
      { confirmButtonText: '删除文档', cancelButtonText: '保留', type: 'warning' },
    )
    await remove(path)
    ElMessage.success('文档已删除')
    await router.push(`/bases/${kb}`)
  } catch (e) {
    report(e)
  }
}
async function downloadFile() {
  if (!doc.value) return
  try {
    await download(path, doc.value.filename)
  } catch (e) {
    report(e)
  }
}
function showChunks() {
  if (route.query.index) index.value = String(route.query.index)
  tab.value = 'chunks'
}
function changeIndex() {
  manualIndex.value = true
  chunkPage.value = 1
  selected.value = ''
  void loadChunks()
}
function chunkKind(chunk: Chunk) {
  if (chunk.level === 2) return '子块'
  if (chunk.level === 1) return '父块'
  return chunks.value.some((child) => child.parent_id === chunk.id) ? '根块' : '分块'
}
onMounted(load)
</script>
<template>
  <el-skeleton v-if="loading" :rows="8" animated />
  <div v-else-if="failed" class="empty-state">
    <h1>文档暂时无法加载</h1>
    <p>文档可能已删除，或服务暂时无法连接。</p>
    <el-button @click="load">重新加载</el-button
    ><router-link :to="`/bases/${kb}`">返回知识库</router-link>
  </div>
  <template v-else-if="doc">
    <header class="page-heading document-heading">
      <div>
        <p class="breadcrumb">
          <router-link to="/">知识库</router-link><span>/</span
          ><router-link :to="`/bases/${kb}`">{{ base?.name || '文档' }}</router-link
          ><span>/</span>文档详情
        </p>
        <h1>{{ doc.title }}</h1>
        <p class="muted">
          {{ doc.filename }}<span class="metadata-separator">/</span>修订 {{ doc.revision
          }}<span class="metadata-separator">/</span>{{ doc.format.toUpperCase() }}
        </p>
      </div>
      <div class="actions">
        <el-button :icon="Download" @click="downloadFile">下载原文件</el-button
        ><el-button :icon="EditPen" @click="open('edit')">编辑文档</el-button>
      </div>
    </header>
    <div class="document-status">
      <div>
        <el-tag
          :type="doc.status === 'failed' ? 'danger' : doc.status === 'ready' ? 'success' : 'info'"
          effect="plain"
          >{{ statusLabel(doc.status) }}</el-tag
        ><span>{{ doc.chunk_count }} 个生效分块</span
        ><span v-if="doc.active_index_id" class="tiny">生效索引 {{ doc.active_index_id }}</span>
      </div>
      <el-button text :icon="Refresh" @click="loadDoc().catch(report)">刷新状态</el-button>
    </div>
    <el-alert
      v-if="doc.error_message"
      :title="doc.error_message"
      type="error"
      :closable="false"
      show-icon
    />
    <p v-if="doc.active_index_id && doc.status !== 'ready'" class="hint">
      新版本尚未就绪，现有生效索引继续提供检索。失败时可检查原因并重新建立索引。
    </p>
    <el-tabs v-model="tab"
      ><el-tab-pane label="文档预览" name="preview" /><el-tab-pane
        label="原文与定位"
        name="source" /><el-tab-pane label="分块浏览" name="chunks" /><el-tab-pane
        label="处理任务"
        name="jobs" /><el-tab-pane label="文档信息" name="info"
    /></el-tabs>
    <div v-if="tab === 'preview'" class="document-paper">
      <SafeMarkdown v-if="editable && previewContent" :content="previewContent" />
      <div v-else class="source-text">{{ previewContent || '文档解析完成后将在此显示正文。' }}</div>
      <div v-if="!previewAll && sourceChars.length > previewLimit" class="source-context">
        <p>当前预览前 {{ previewLimit }} 个字符。</p>
        <el-button @click="previewAll = true">加载完整预览</el-button>
      </div>
    </div>
    <section v-if="tab === 'source'" class="document-paper">
      <div v-if="route.query.chunk" class="source-context">
        <el-alert
          v-if="!sourceCurrent"
          title="检索来自旧修订；当前正文已更新，请使用同一索引的分块核对依据。"
          type="warning"
          :closable="false"
        />
        <p>
          来源修订 {{ sourceRevision
          }}<template v-if="route.query.index"> · 索引 {{ route.query.index }}</template>
        </p>
        <el-button @click="showChunks">查看命中分块</el-button>
      </div>
      <pre
        class="source-text">{{highlight[0] || (!parsedContent ? '暂无解析正文。' : '')}}<mark v-if="highlight[1]">{{highlight[1]}}</mark>{{highlight[2]}}</pre>
      <el-pagination
        v-if="sourcePageCount > 1"
        v-model:current-page="sourcePage"
        :page-count="sourcePageCount"
        :pager-count="5"
        layout="prev, pager, next"
      />
    </section>
    <section v-if="tab === 'chunks'">
      <div class="chunk-toolbar">
        <el-select
          v-model="index"
          aria-label="索引版本"
          placeholder="选择索引版本"
          @change="changeIndex"
          ><el-option
            v-for="id in indexes"
            :key="id"
            :label="`${id === doc.active_index_id ? '生效' : '历史 / 处理中'} · ${id}`"
            :value="id" /></el-select
        ><span class="muted">共 {{ chunkTotal }} 个分块</span>
      </div>
      <el-skeleton v-if="chunkLoading" :rows="5" animated />
      <div v-else-if="!chunks.length" class="empty-state">
        <h2>这个索引还没有可查看的分块</h2>
        <p>索引完成后可查看分块正文和父子关系。</p>
      </div>
      <div v-else class="chunk-browser">
        <nav class="chunk-list" aria-label="分块列表">
          <button
            v-for="chunk in chunks"
            :key="chunk.id"
            :class="{ selected: selected === chunk.id }"
            :aria-current="selected === chunk.id ? 'true' : undefined"
            @click="selected = chunk.id"
          >
            <strong>{{ chunkKind(chunk) }} {{ chunk.chunk_no + 1 }}</strong
            ><span>{{
              titlePath(chunk.title_path) || chunk.article_no || chunk.content.slice(0, 45)
            }}</span
            ><small
              >{{ chunk.char_start }}–{{ chunk.char_end }} 字符<template v-if="chunk.page_number">
                · 第 {{ chunk.page_number }} 页</template
              ></small
            >
          </button>
        </nav>
        <article v-if="selectedChunk" class="chunk-content">
          <div class="section-meta">
            <span>层级 {{ selectedChunk.level }} · 分块 {{ selectedChunk.chunk_no + 1 }}</span
            ><el-button
              v-if="selectedChunk.parent_id"
              text
              type="primary"
              @click="selectChunk(selectedChunk.parent_id).catch(report)"
              >查看父块</el-button
            >
          </div>
          <h2 v-if="selectedChunk.title_path?.length" class="chunk-heading">
            {{ titlePath(selectedChunk.title_path) }}
          </h2>
          <p v-if="selectedChunk.article_no" class="hint">{{ selectedChunk.article_no }}</p>
          <SafeMarkdown :content="selectedChunk.content" />
          <el-button v-if="chunkTotal > 100" text :loading="findingChildren" @click="findChildren"
            >查找所有页中的子块</el-button
          >
          <div v-if="children.length" class="child-navigation">
            <h2 class="chunk-heading">子块</h2>
            <el-button v-for="child in children" :key="child.id" @click="selected = child.id"
              >分块 {{ child.chunk_no + 1 }}</el-button
            >
          </div>
          <div class="tiny break-word">
            分块 ID：{{ selectedChunk.id }}<br />索引 ID：{{ selectedChunk.index_id }}
          </div>
        </article>
      </div>
      <el-pagination
        v-if="chunkTotal > 100"
        v-model:current-page="chunkPage"
        :total="chunkTotal"
        :page-size="100"
        layout="prev, pager, next"
        @current-change="loadChunks"
      />
    </section>
    <section v-if="tab === 'jobs'" class="job-panel">
      <div class="section-meta">
        <span>{{ jobs.length }} 个处理任务</span
        ><el-button type="primary" :icon="Refresh" @click="open('index')">建立新索引</el-button>
      </div>
      <div v-if="!jobs.length" class="empty-state"><p>暂无处理任务。</p></div>
      <article v-for="job in jobs" :key="job.id" class="job-item">
        <header>
          <h2>
            {{ statusLabel(job.stage)
            }}<el-tag
              :type="
                job.status === 'failed'
                  ? 'danger'
                  : ['ready', 'completed', 'succeeded'].includes(job.status)
                    ? 'success'
                    : 'info'
              "
              >{{ statusLabel(job.status) }}</el-tag
            >
          </h2>
          <span class="tiny">{{ formatDate(job.updated_at) }}</span>
        </header>
        <p class="muted">文档修订 {{ job.revision }} · 尝试 {{ job.attempts }} 次</p>
        <div class="job-stages">
          <span
            v-for="stage in ['pending', 'parsing', 'chunking', 'embedding', 'ready']"
            :key="stage"
            :class="{ current: stage === job.stage }"
            >{{ statusLabel(stage) }}</span
          >
        </div>
        <p v-if="job.error_message" class="error-text" role="status">{{ job.error_message }}</p>
        <p class="tiny break-word">任务 {{ job.id }}<br />索引 {{ job.index_id }}</p>
      </article>
    </section>
    <section v-if="tab === 'info'" class="info-panel">
      <h2>文档信息</h2>
      <dl class="document-facts">
        <dt>文档 ID</dt>
        <dd>{{ doc.id }}</dd>
        <dt>当前修订</dt>
        <dd>{{ doc.revision }}</dd>
        <dt>创建时间</dt>
        <dd>{{ formatDate(doc.created_at) }}</dd>
        <dt>更新时间</dt>
        <dd>{{ formatDate(doc.updated_at) }}</dd>
      </dl>
      <h3>元数据</h3>
      <dl v-if="metadataEntries.length" class="metadata-list">
        <div v-for="[key, value] in metadataEntries" :key="key">
          <dt>{{ key || '""' }}</dt>
          <dd>{{ typeof value === 'string' && value ? value : JSON.stringify(value, null, 2) }}</dd>
        </div>
      </dl>
      <p v-else class="muted">暂无元数据。</p>
      <div class="info-actions">
        <el-button :icon="EditPen" @click="open('edit')">编辑元数据</el-button
        ><el-button :icon="Upload" @click="open('replace')">替换文件</el-button
        ><el-button :icon="Refresh" @click="open('index')">建立新索引</el-button>
      </div>
      <div class="danger-zone">
        <div>
          <h3>删除文档</h3>
          <p class="muted">移除原文件、索引和所有分块，无法恢复。</p>
        </div>
        <el-button type="danger" plain @click="deleteDoc">删除文档</el-button>
      </div>
    </section>
    <el-dialog
      v-model="dialogOpen"
      destroy-on-close
      :title="dialog === 'edit' ? '编辑文档' : dialog === 'replace' ? '替换原文件' : '建立新索引'"
      :width="dialog === 'edit' ? '860px' : '560px'"
      :close-on-click-modal="false"
      ><el-form label-position="top"
        ><template v-if="dialog === 'edit'"
          ><el-form-item label="文档标题" for="edit-title"
            ><el-input id="edit-title" v-model="editTitle" maxlength="200" /></el-form-item
          ><template v-if="editable"
            ><div class="editor-switch">
              <el-switch v-model="editPreview" active-text="预览 Markdown" />
            </div>
            <SafeMarkdown v-if="editPreview" :content="editContent" /><el-form-item
              v-else
              label="Markdown 正文"
              for="edit-content"
              ><el-input
                id="edit-content"
                v-model="editContent"
                type="textarea"
                :rows="12" /></el-form-item></template
          ><MetadataEditor
            v-if="dialogOpen"
            ref="metadataEditor"
            :initial-value="editMetadata"
            :disabled="busy" /></template
        ><template v-else-if="dialog === 'replace'"
          ><p class="hint">替换后生成新修订并自动索引。新索引就绪前，现有索引继续可用。</p>
          <label for="replace-file" class="file-picker"
            ><el-icon :size="30"><Upload /></el-icon><strong>选择替换文件</strong
            ><input
              id="replace-file"
              type="file"
              accept=".pdf,.docx,.md,.markdown,.txt"
              @change="choose"
            /><span>{{ file?.name || '支持 Word、PDF、Markdown、TXT' }}</span></label
          ></template
        ><template v-else
          ><p class="hint">为修订 {{ editRevision }} 建立独立索引。完成后自动切换生效版本。</p>
          <IndexSettings v-model="options"
        /></template>
        <p v-if="formError" role="alert" class="error-text">{{ formError }}</p></el-form
      ><template #footer
        ><el-button :disabled="busy" @click="dialogOpen = false">取消</el-button
        ><el-button type="primary" :loading="busy" @click="save">{{
          dialog === 'index' ? '开始建立索引' : dialog === 'replace' ? '替换并建立索引' : '保存更改'
        }}</el-button></template
      ></el-dialog
    >
  </template>
</template>
