import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import 'element-plus/dist/index.css'
import { createRouter, createWebHashHistory } from 'vue-router'
import App from './App.vue'
import LoginView from './views/LoginView.vue'
import BasesView from './views/BasesView.vue'
import WorkspaceView from './views/WorkspaceView.vue'
import DocumentView from './views/DocumentView.vue'
import { authenticated } from './api'
import './style.css'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/login', component: LoginView },
    { path: '/', component: BasesView },
    { path: '/bases/:kb', component: WorkspaceView },
    { path: '/bases/:kb/documents/:doc', component: DocumentView },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})
router.beforeEach((to) => {
  if (to.path !== '/login' && !authenticated.value) return '/login'
  if (to.path === '/login' && authenticated.value) return '/'
})
createApp(App).use(router).use(ElementPlus, { locale: zhCn }).mount('#app')
