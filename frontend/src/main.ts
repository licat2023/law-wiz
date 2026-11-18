/** 创建业务界面并安装认证状态、页面路由和全局样式。 */
import { createPinia } from 'pinia'
import { createApp } from 'vue'

import App from './App.vue'
import router from './router'
// 页面直接调用 ElMessage，按需解析器不会为这些调用加载样式。
import 'element-plus/es/components/message/style/css'
import './styles/main.css'

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.mount('#app')
