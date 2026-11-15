<script setup lang="ts">
/** 在键值表单与 Raw 编辑器之间切换，保存时返回校验后的元数据对象。 */
import { nextTick, ref, useId } from 'vue'
import { Delete, Plus } from '@element-plus/icons-vue'

const props = defineProps<{ initialValue: Record<string, unknown>; disabled?: boolean }>()
const valueTypes = [
  { value: 'string', label: '文本' },
  { value: 'number', label: '数字' },
  { value: 'boolean', label: '布尔' },
  { value: 'null', label: '空值' },
  { value: 'structured', label: '对象 / 数组' },
] as const
type ValueType = (typeof valueTypes)[number]['value']
type Row = { id: number; key: string; originalKey?: string; type: ValueType; text: string }

const editorId = useId()
let nextRowId = 0
const mode = ref<'kv' | 'raw'>('kv')
const rows = ref(toRows(props.initialValue))
const raw = ref('')
const error = ref('')

function toRows(metadata: Record<string, unknown>): Row[] {
  return Object.entries(metadata).map(([key, value]) => {
    const kind = typeof value
    const type = value === null ? 'null' : kind === 'object' ? 'structured' : (kind as ValueType)
    const text = typeof value === 'string' ? value : JSON.stringify(value, null, 2)
    return { id: nextRowId++, key, originalKey: key, type, text }
  })
}

async function addRow() {
  const id = nextRowId++
  rows.value.push({ id, key: '', type: 'string', text: '' })
  await nextTick()
  document.getElementById(`${editorId}-key-${id}`)?.focus()
}

function removeRow(index: number) {
  rows.value.splice(index, 1)
  error.value = ''
}

function changeType(row: Row) {
  if (row.type === 'boolean' && !['true', 'false'].includes(row.text)) row.text = 'true'
  if (row.type === 'structured' && !row.text.trim()) row.text = '{}'
}

function parseJson(text: string): unknown {
  return JSON.parse(text, (_key, value: unknown) => {
    if (typeof value === 'number' && !Number.isFinite(value)) throw new Error('Invalid number')
    return value
  })
}

function readValue(row: Row): unknown {
  if (row.type === 'string') return row.text
  if (row.type === 'null') return null
  if (row.type === 'boolean') return row.text === 'true'
  const field = `字段 ${JSON.stringify(row.key)}`
  let value: unknown
  try {
    value = parseJson(row.text)
  } catch {
    // 格式无效时由下面的类型校验显示字段名和可用格式。
  }
  if (row.type === 'number') {
    if (typeof value !== 'number') throw new Error(`${field}需要填写有效数字。`)
  } else if (value === null || typeof value !== 'object') {
    throw new Error(`${field}需要填写有效的 JSON 对象或数组。`)
  }
  return value
}

/** 读取当前模式，校验失败时抛出可显示的错误。 */
function readMetadata(): Record<string, unknown> {
  if (mode.value === 'raw') {
    let value: unknown
    try {
      value = parseJson(raw.value)
    } catch {
      throw new Error('Raw 格式无效，请检查 JSON 对象。')
    }
    if (!value || typeof value !== 'object' || Array.isArray(value))
      throw new Error('Raw 元数据需要是 JSON 对象。')
    return value as Record<string, unknown>
  }

  const entries = new Map<string, unknown>()
  for (const [index, row] of rows.value.entries()) {
    if (!row.key.trim() && row.key !== row.originalKey)
      throw new Error(`请填写第 ${index + 1} 行的键。`)
    if (entries.has(row.key)) throw new Error(`键 ${JSON.stringify(row.key)} 已存在。`)
    entries.set(row.key, readValue(row))
  }
  return Object.fromEntries(entries)
}

function changeMode(next: string | number | boolean | undefined) {
  if ((next !== 'kv' && next !== 'raw') || next === mode.value) return
  error.value = ''
  try {
    const metadata = readMetadata()
    if (next === 'raw') raw.value = JSON.stringify(metadata, null, 2)
    else rows.value = toRows(metadata)
    mode.value = next
  } catch (cause) {
    if (cause instanceof Error) error.value = cause.message
  }
}

defineExpose({ readMetadata })
</script>

<template>
  <fieldset class="metadata-editor" :disabled="disabled" @input="error = ''">
    <legend>元数据</legend>
    <el-radio-group
      :model-value="mode"
      aria-label="元数据编辑模式"
      :disabled="disabled"
      @change="changeMode"
    >
      <el-radio-button value="kv">键值</el-radio-button>
      <el-radio-button value="raw">Raw</el-radio-button>
    </el-radio-group>
    <template v-if="mode === 'kv'">
      <div v-if="rows.length" class="metadata-rows">
        <div v-for="(row, index) in rows" :key="row.id" class="metadata-row">
          <el-input
            :id="`${editorId}-key-${row.id}`"
            v-model="row.key"
            :aria-label="`第 ${index + 1} 行的键`"
            placeholder="键"
          />
          <el-select
            v-model="row.type"
            :aria-label="`第 ${index + 1} 行的值类型`"
            @change="changeType(row)"
          >
            <el-option v-for="type in valueTypes" :key="type.value" v-bind="type" />
          </el-select>
          <el-select
            v-if="row.type === 'boolean'"
            v-model="row.text"
            :aria-label="`第 ${index + 1} 行的值`"
          >
            <el-option label="true" value="true" /><el-option label="false" value="false" />
          </el-select>
          <el-input
            v-else-if="row.type === 'null'"
            :aria-label="`第 ${index + 1} 行的值`"
            model-value="null"
            disabled
          />
          <el-input
            v-else
            v-model="row.text"
            :aria-label="`第 ${index + 1} 行的值`"
            :type="row.type === 'number' ? 'text' : 'textarea'"
            :inputmode="row.type === 'number' ? 'decimal' : undefined"
            :autosize="{ minRows: 1, maxRows: 4 }"
            resize="none"
            :class="{ 'code-input': row.type === 'structured' }"
            placeholder="值"
          />
          <el-button
            :icon="Delete"
            :aria-label="`删除第 ${index + 1} 行`"
            @click="removeRow(index)"
          />
        </div>
      </div>
      <el-button :icon="Plus" @click="addRow">添加字段</el-button>
    </template>
    <el-input
      v-else
      v-model="raw"
      aria-label="Raw 元数据"
      type="textarea"
      :rows="7"
      class="code-input"
    />
    <p v-if="error" role="alert" class="error-text">{{ error }}</p>
  </fieldset>
</template>
