<script setup lang="ts">
/** 文档与会话共用的归档图标。父元素使用 archive-action-row 包住条目与图标。 */
import { Delete, RefreshLeft, TakeawayBox } from '@element-plus/icons-vue'

withDefaults(defineProps<{ mode: 'archive' | 'manage'; busy?: boolean }>(), { busy: false })

const emit = defineEmits<{ archive: []; restore: []; delete: [] }>()
</script>

<template>
  <div class="archive-row-actions" role="group" aria-label="归档操作">
    <button
      v-if="mode === 'archive'"
      class="archive-row-action"
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
        class="archive-row-action archive-row-action--restore"
        type="button"
        title="还原"
        aria-label="还原"
        :disabled="busy"
        @click="emit('restore')"
      >
        <el-icon aria-hidden="true"><RefreshLeft /></el-icon>
      </button>
      <button
        class="archive-row-action"
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
.archive-action-row {
  position: relative;
}
.archive-action-row .archive-row-actions {
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
.archive-action-row:hover .archive-row-actions,
.archive-action-row:has(:focus-visible) .archive-row-actions {
  opacity: 1;
}
.archive-action-row .archive-row-action {
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
.archive-action-row .archive-row-action--restore {
  --archive-action-color: var(--el-color-success-dark-2);
  --archive-action-background: var(--el-color-success-light-9);
  color: var(--archive-action-color);
}
.archive-action-row:hover .archive-row-action,
.archive-action-row:has(:focus-visible) .archive-row-action {
  pointer-events: auto;
}
.archive-action-row .archive-row-action:disabled {
  cursor: wait;
  opacity: 0.45;
}
.archive-action-row .archive-row-action:hover:not(:disabled),
.archive-action-row .archive-row-action:focus-visible {
  color: var(--archive-action-color, var(--el-color-danger-dark-2));
  background: var(--archive-action-background, var(--el-color-danger-light-9));
}
.archive-action-row .archive-row-action:focus-visible {
  outline: 2px solid currentColor;
  outline-offset: -2px;
}
@media (hover: none) {
  .archive-action-row .archive-row-actions {
    opacity: 1;
  }
  .archive-action-row .archive-row-action {
    pointer-events: auto;
  }
}
</style>
