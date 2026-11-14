<script setup lang="ts">
/** 通过 v-model 编辑知识库默认或单次重建所用的索引参数。 */
import { computed } from 'vue'
import type { IndexOptions } from '../types'
const model = defineModel<IndexOptions>({ required: true })
// 层级索引与叶子块切分由两个字段表示。切换到层级预设时先使用固定切分。
const preset = computed({
  get: () => (model.value.hierarchical_index ? 'hierarchy' : model.value.chunking_strategy),
  set: (value: string) => {
    model.value = {
      ...model.value,
      hierarchical_index: value === 'hierarchy',
      chunking_strategy: value === 'semantic' ? 'semantic' : 'fixed',
    }
  },
})
</script>
<template>
  <div class="index-settings">
    <el-form-item label="索引方式">
      <el-radio-group v-model="preset" class="preset-group">
        <el-radio-button value="fixed">固定分块</el-radio-button
        ><el-radio-button value="semantic">语义分块</el-radio-button
        ><el-radio-button value="hierarchy">层级索引</el-radio-button>
      </el-radio-group>
    </el-form-item>
    <p class="hint">
      {{
        preset === 'fixed'
          ? '按字符长度切分，适合均匀文本。'
          : preset === 'semantic'
            ? '根据相邻语义距离形成边界，需要可用的嵌入服务。'
            : '保留章节父块，检索叶子块时可扩展完整上下文。'
      }}
    </p>
    <el-form-item v-if="preset === 'hierarchy'" label="叶子块切分"
      ><el-select v-model="model.chunking_strategy"
        ><el-option label="固定分块" value="fixed" /><el-option
          label="语义分块"
          value="semantic" /></el-select
    ></el-form-item>
    <div class="form-pair">
      <el-form-item label="块长度（字符）"
        ><el-input-number
          v-model="model.chunk_size"
          :min="50"
          :max="8000"
          :step="100"
          controls-position="right"
      /></el-form-item>
      <el-form-item label="重叠长度（字符）"
        ><el-input-number
          v-model="model.chunk_overlap"
          :min="0"
          :max="Math.min(4000, Math.max(0, model.chunk_size - 1))"
          controls-position="right"
      /></el-form-item>
    </div>
  </div>
</template>
