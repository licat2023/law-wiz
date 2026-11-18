<script setup lang="ts">
/** 审查文档列表共用的行内图标动作。父元素使用 review-action-row 包住条目与图标。 */
import { Delete, RefreshLeft, TakeawayBox } from '@element-plus/icons-vue'

withDefaults(defineProps<{ mode: 'archive' | 'manage'; busy?: boolean }>(), { busy: false })

const emit = defineEmits<{ archive: []; restore: []; delete: [] }>()
</script>

<template>
  <div class="review-row-actions" role="group" aria-label="文档操作">
    <button
      v-if="mode === 'archive'"
      class="review-row-action"
      type="button"
      title="归档"
      aria-label="归档"
      :disabled="busy"
      @click="emit('archive')"
    >
      <el-icon aria-hidden="true"><TakeawayBox /></el-icon>
    </button>
    <template v-else>
      <button
        class="review-row-action review-row-action--restore"
        type="button"
        title="还原"
        aria-label="还原"
        :disabled="busy"
        @click="emit('restore')"
      >
        <el-icon aria-hidden="true"><RefreshLeft /></el-icon>
      </button>
      <button
        class="review-row-action"
        type="button"
        title="彻底删除"
        aria-label="彻底删除"
        :disabled="busy"
        @click="emit('delete')"
      >
        <el-icon aria-hidden="true"><Delete /></el-icon>
      </button>
    </template>
  </div>
</template>

<style>
.review-action-row {
  position: relative;
}
.review-action-row .review-row-actions {
  position: absolute;
  inset: 0 0 0 auto;
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 0 8px 0 28px;
  border-radius: 0 6px 6px 0;
  background: linear-gradient(90deg, transparent, var(--el-bg-color) 42%);
  pointer-events: none;
  opacity: 0;
}
.review-action-row:hover .review-row-actions,
.review-action-row:has(:focus-visible) .review-row-actions {
  opacity: 1;
}
.review-action-row .review-row-action {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  padding: 0;
  border: 0;
  border-radius: 5px;
  background: transparent;
  color: var(--el-text-color-secondary);
  cursor: pointer;
  font-size: 17px;
}
.review-action-row .review-row-action--restore {
  --review-action-color: var(--el-color-success-dark-2);
  --review-action-background: var(--el-color-success-light-9);
  color: var(--review-action-color);
}
.review-action-row:hover .review-row-action,
.review-action-row:has(:focus-visible) .review-row-action {
  pointer-events: auto;
}
.review-action-row .review-row-action:disabled {
  cursor: wait;
  opacity: 0.45;
}
.review-action-row .review-row-action:hover:not(:disabled),
.review-action-row .review-row-action:focus-visible {
  color: var(--review-action-color, var(--el-color-danger-dark-2));
  background: var(--review-action-background, var(--el-color-danger-light-9));
}
.review-action-row .review-row-action:focus-visible {
  outline: 2px solid currentColor;
  outline-offset: -2px;
}
@media (hover: none) {
  .review-action-row .review-row-actions {
    opacity: 1;
  }
  .review-action-row .review-row-action {
    pointer-events: auto;
  }
}
</style>
