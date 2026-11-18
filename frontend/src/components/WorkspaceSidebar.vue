<script setup lang="ts">
/** 为交互页面提供统一的侧栏、顶部操作区和独立滚动列表。 */
withDefaults(defineProps<{ heading: string; busy?: boolean }>(), { busy: false })
</script>

<template>
  <aside class="workspace-sidebar" :aria-label="heading">
    <div class="workspace-sidebar-header">
      <slot name="toolbar" />
      <h2>{{ heading }}</h2>
    </div>
    <div class="workspace-sidebar-list" :aria-busy="busy">
      <slot />
    </div>
  </aside>
</template>

<style scoped>
.workspace-sidebar {
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--el-border-color-light);
  border-radius: 10px;
  background: var(--el-bg-color);
  overflow: hidden;
}
.workspace-sidebar-header {
  padding: 16px 14px 0;
}
.workspace-sidebar-header :deep(.el-button) {
  width: 100%;
}
.workspace-sidebar-header h2 {
  margin: 20px 4px 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-regular);
}
.workspace-sidebar-list {
  min-height: 0;
  flex: 1;
  padding: 0 8px 12px 12px;
  overflow: auto;
  scrollbar-gutter: stable;
}
@media (max-width: 700px) {
  .workspace-sidebar {
    max-height: min(235px, 40dvh);
  }
  .workspace-sidebar-header {
    padding-top: 12px;
  }
  .workspace-sidebar-header h2 {
    margin-top: 10px;
  }
}
</style>
