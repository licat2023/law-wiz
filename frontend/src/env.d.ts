/// <reference types="vite/client" />

/** 声明 Vue 单文件组件的默认导入类型。 */
declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<Record<string, unknown>, Record<string, unknown>, unknown>
  export default component
}
