<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Collection, ArrowRight } from '@element-plus/icons-vue'
import { get, post, patch, remove, basePath } from '../api'
import { defaults, formatDate, type KnowledgeBase, type Page, type IndexOptions } from '../types'
import { report } from '../feedback'
import IndexSettings from '../components/IndexSettings.vue'
const bases = ref<KnowledgeBase[]>([]),
  total = ref(0),
  page = ref(1),
  loading = ref(true),
  failed = ref(false)
const dialog = ref(false),
  busy = ref(false),
  editing = ref<string | null>(null)
const name = ref(''),
  description = ref(''),
  options = ref<IndexOptions>({ ...defaults }),
  formError = ref('')
async function load() {
  loading.value = true
  failed.value = false
  try {
    const result = await get<Page<KnowledgeBase>>(
      `/knowledge-bases?page=${page.value}&page_size=12`,
    )
    bases.value = result.items
    total.value = result.total
  } catch (e) {
    failed.value = true
    report(e)
  } finally {
    loading.value = false
  }
}
function open(base?: KnowledgeBase) {
  editing.value = base?.id || null
  name.value = base?.name || ''
  description.value = base?.description || ''
  options.value = base
    ? {
        chunking_strategy: base.chunking_strategy,
        chunk_size: base.chunk_size,
        chunk_overlap: base.chunk_overlap,
        hierarchical_index: base.hierarchical_index,
      }
    : { ...defaults }
  formError.value = ''
  dialog.value = true
}
async function save() {
  if (!name.value.trim()) {
    formError.value = '请填写知识库名称。'
    return
  }
  if (options.value.chunk_overlap >= options.value.chunk_size) {
    formError.value = '重叠长度必须小于块长度。'
    return
  }
  busy.value = true
  formError.value = ''
  try {
    const data = { name: name.value.trim(), description: description.value, ...options.value }
    if (editing.value) await patch(basePath(editing.value), data)
    else await post('/knowledge-bases', data)
    dialog.value = false
    ElMessage.success('知识库已保存')
    await load()
  } catch (e) {
    formError.value = e instanceof Error ? e.message : '保存失败。'
  } finally {
    busy.value = false
  }
}
async function deleteBase(base: KnowledgeBase) {
  try {
    await ElMessageBox.confirm(
      `删除「${base.name}」及其中的 ${base.document_count} 份文档？此操作无法恢复。`,
      '删除知识库',
      { confirmButtonText: '删除知识库', cancelButtonText: '保留', type: 'warning' },
    )
    await remove(basePath(base.id))
    ElMessage.success('知识库已删除')
    await load()
  } catch (e) {
    report(e)
  }
}
onMounted(load)
</script>
<template>
  <header class="page-heading">
    <div>
      <p class="breadcrumb">管理工作区</p>
      <h1>知识库</h1>
      <p class="muted">按用途组织文档，为检索保留清晰的来源。</p>
    </div>
    <el-button type="primary" :icon="Plus" @click="open()">新建知识库</el-button>
  </header>
  <div class="section-meta">
    <span>共 {{ total }} 个知识库</span
    ><el-button text :loading="loading" @click="load">刷新列表</el-button>
  </div>
  <el-skeleton v-if="loading" :rows="6" animated />
  <div v-else-if="failed" class="empty-state">
    <h2>知识库暂时无法加载</h2>
    <p>检查服务连接后，再试一次。</p>
    <el-button @click="load">重新加载</el-button>
  </div>
  <div v-else-if="!bases.length" class="empty-state">
    <el-icon :size="42"><Collection /></el-icon>
    <h2>从第一个知识库开始</h2>
    <p>创建知识库后，即可上传文档或编写 Markdown。</p>
    <el-button type="primary" @click="open()">新建知识库</el-button>
  </div>
  <div v-else class="base-grid">
    <article v-for="base in bases" :key="base.id" class="base-card">
      <div class="base-card-top">
        <el-icon class="base-symbol" :size="24"><Collection /></el-icon
        ><span class="muted">{{ base.document_count }} 份文档</span>
      </div>
      <router-link :to="`/bases/${base.id}`" class="base-title"
        ><h2>{{ base.name }}</h2>
        <el-icon><ArrowRight /></el-icon
      ></router-link>
      <p class="base-description">{{ base.description || '暂无说明' }}</p>
      <div class="base-options">
        <span>{{
          base.hierarchical_index
            ? '层级索引'
            : base.chunking_strategy === 'semantic'
              ? '语义分块'
              : '固定分块'
        }}</span
        ><span>{{ base.chunk_size }} 字符</span>
      </div>
      <footer>
        <span class="tiny">更新于 {{ formatDate(base.updated_at) }}</span>
        <div>
          <el-button text @click="open(base)">编辑</el-button
          ><el-button text type="danger" @click="deleteBase(base)">删除</el-button>
        </div>
      </footer>
    </article>
  </div>
  <el-pagination
    v-if="total > 12"
    v-model:current-page="page"
    :total="total"
    :page-size="12"
    layout="prev, pager, next"
    @current-change="load"
  />
  <el-dialog
    v-model="dialog"
    :title="editing ? '编辑知识库' : '新建知识库'"
    width="560px"
    :close-on-click-modal="false"
    ><el-form label-position="top" @submit.prevent="save"
      ><el-form-item label="知识库名称" for="base-name" required
        ><el-input id="base-name" v-model="name" maxlength="120" show-word-limit /></el-form-item
      ><el-form-item label="说明" for="base-description"
        ><el-input
          id="base-description"
          v-model="description"
          type="textarea"
          :rows="3"
          maxlength="2000"
      /></el-form-item>
      <h3>默认索引设置</h3>
      <p class="hint">用于新上传的文档；已有文档可在详情中单独重建。</p>
      <IndexSettings v-model="options" />
      <p v-if="formError" role="alert" class="error-text">{{ formError }}</p></el-form
    ><template #footer
      ><el-button :disabled="busy" @click="dialog = false">取消</el-button
      ><el-button type="primary" :loading="busy" @click="save">保存知识库</el-button></template
    ></el-dialog
  >
</template>
