<script setup lang="ts">
/** 未匹配业务路由时展示，返回入口沿用首页重定向。 */
import { useRouter } from 'vue-router'

const router = useRouter()
</script>

<template>
  <div class="page">
    <el-result icon="warning" title="页面不存在" sub-title="请检查地址是否正确">
      <template #extra>
        <el-button type="primary" @click="router.push('/')">返回首页</el-button>
      </template>
    </el-result>
  </div>
</template>
