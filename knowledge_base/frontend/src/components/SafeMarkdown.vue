<script setup lang="ts">
import { computed } from 'vue'
import { renderMarkdown } from '../markdown'
const props = defineProps<{ content: string }>()
const html = computed(() => renderMarkdown(props.content))
</script>
<template>
  <!-- The renderer disables HTML and images and restricts link protocols. -->
  <!-- eslint-disable-next-line vue/no-v-html -->
  <article class="markdown-body" v-html="html" />
</template>
