<script setup lang="ts">
/** 展示可选择的侧栏条目，并在归档操作区旁预览超长标题。 */
import { onBeforeUnmount, ref } from 'vue'
import { RouterLink, type RouteLocationRaw } from 'vue-router'

import ArchiveRowActions from './ArchiveRowActions.vue'

const props = withDefaults(
  defineProps<{
    title: string
    to?: RouteLocationRaw
    selected?: boolean
    archivable?: boolean
    busy?: boolean
  }>(),
  { selected: false, archivable: true, busy: false, to: undefined },
)
const emit = defineEmits<{ select: []; archive: [] }>()
const entry = ref<HTMLElement>()
const titleViewport = ref<HTMLElement>()
const TITLE_PREVIEW_DELAY = 500
let pointerInside = false
let titleTimer: number | undefined

function scheduleTitlePreview() {
  if (!props.archivable || titleTimer !== undefined) return
  titleTimer = window.setTimeout(() => {
    titleTimer = undefined
    const title = titleViewport.value
    if (!title || title.scrollWidth <= title.clientWidth) return
    title.scrollTo({
      left: title.scrollWidth,
      behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches
        ? 'instant'
        : 'smooth',
    })
  }, TITLE_PREVIEW_DELAY)
}

function resetTitle() {
  window.clearTimeout(titleTimer)
  titleTimer = undefined
  titleViewport.value?.scrollTo({ left: 0, behavior: 'instant' })
}

function enterRow(event: PointerEvent) {
  if (event.pointerType === 'touch') return
  pointerInside = true
  scheduleTitlePreview()
}

function leaveRow(event: PointerEvent) {
  if (event.pointerType === 'touch') return
  pointerInside = false
  if (!entry.value?.matches(':has(:focus-visible)')) resetTitle()
}

function enterFocus(event: FocusEvent) {
  if (event.target instanceof HTMLElement && event.target.matches(':focus-visible')) {
    scheduleTitlePreview()
  }
}

function leaveFocus(event: FocusEvent) {
  if (!pointerInside && !entry.value?.contains(event.relatedTarget as Node | null)) resetTitle()
}

onBeforeUnmount(resetTitle)
</script>

<template>
  <div
    ref="entry"
    class="sidebar-entry archive-action-row"
    :class="{ 'is-selected': selected, 'has-archive': archivable }"
    @pointerenter="enterRow"
    @pointerleave="leaveRow"
    @focusin="enterFocus"
    @focusout="leaveFocus"
  >
    <component
      :is="to ? RouterLink : 'button'"
      v-bind="to ? { to } : { type: 'button', 'aria-current': selected ? 'true' : undefined }"
      class="sidebar-entry-target"
      @click="emit('select')"
    >
      <el-icon class="sidebar-entry-icon" aria-hidden="true"><slot name="icon" /></el-icon>
      <span class="sidebar-entry-info">
        <span ref="titleViewport" class="sidebar-entry-title" :title="title">{{ title }}</span>
        <span class="sidebar-entry-meta"><slot /></span>
      </span>
    </component>
    <ArchiveRowActions v-if="archivable" mode="archive" :busy="busy" @archive="emit('archive')" />
  </div>
</template>

<style scoped>
.sidebar-entry {
  --entry-padding-inline: 8px;
  --archive-title-inset: calc(var(--archive-box-width) - var(--entry-padding-inline));
  margin-bottom: 4px;
  border-radius: 6px;
}
.sidebar-entry:hover,
.sidebar-entry.is-selected {
  background: var(--el-fill-color-light);
}
.sidebar-entry-target {
  display: flex;
  align-items: flex-start;
  gap: 9px;
  width: 100%;
  padding: 10px var(--entry-padding-inline);
  border: 0;
  border-radius: inherit;
  background: transparent;
  color: var(--el-text-color-primary);
  font: inherit;
  text-align: left;
  text-decoration: none;
  cursor: pointer;
}
.sidebar-entry-target:focus-visible {
  outline: 2px solid var(--el-color-primary);
  outline-offset: -2px;
}
.sidebar-entry-icon {
  flex: none;
  margin-top: 2px;
  color: var(--el-color-primary);
}
.sidebar-entry-info {
  display: grid;
  gap: 4px;
  min-width: 0;
  flex: 1;
}
.sidebar-entry-title {
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  font-size: 14px;
  font-weight: 500;
}
.sidebar-entry.has-archive:hover .sidebar-entry-title,
.sidebar-entry.has-archive:has(:focus-visible) .sidebar-entry-title {
  margin-inline-end: var(--archive-title-inset);
}
.sidebar-entry-meta {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 8px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
@media (hover: none) {
  .sidebar-entry.has-archive .sidebar-entry-title {
    margin-inline-end: var(--archive-title-inset);
  }
}
</style>
