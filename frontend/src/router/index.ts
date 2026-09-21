import { createRouter, createWebHistory } from 'vue-router'

import { tokenStore } from '@/api/client'

/**
 * 路由表。
 *
 * ```mermaid
 * graph LR
 *   Login --> Review --> Detail
 *   Login --> Qa
 *   Login --> Me
 * ```
 *
 * 一期只有三个业务板块：合同审查（M2）、法律问答（M3）、个人中心。
 * 其余模块（M4 存证、M6 签署、M7 印章）属 P2–P4，路由到时再加。
 */
const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/review' },
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/LoginView.vue'),
      meta: { public: true, title: '登录' },
    },
    {
      path: '/register',
      name: 'register',
      component: () => import('@/views/RegisterView.vue'),
      meta: { public: true, title: '注册' },
    },
    {
      path: '/review',
      name: 'review',
      component: () => import('@/views/ReviewView.vue'),
      meta: { title: '合同审查' },
    },
    {
      path: '/review/:taskId',
      name: 'review-detail',
      component: () => import('@/views/ReviewDetailView.vue'),
      meta: { title: '审查报告' },
    },
    {
      path: '/qa',
      name: 'qa',
      component: () => import('@/views/QaView.vue'),
      meta: { title: '法律问答' },
    },
    {
      path: '/me',
      name: 'me',
      component: () => import('@/views/MeView.vue'),
      meta: { title: '个人中心' },
    },
    {
      path: '/:pathMatch(.*)*',
      name: 'not-found',
      component: () => import('@/views/NotFoundView.vue'),
      meta: { public: true, title: '页面不存在' },
    },
  ],
})

/**
 * 鉴权守卫。
 *
 * ⚠️ 这**只是体验优化**，不是安全边界 —— 真正的权限校验必须在后端
 * （每个带 {id} 的接口都要校验资源归属，否则返回 40301）。
 * 前端守卫的作用是"未登录时不要展示一个注定 401 的页面"。
 */
router.beforeEach((to) => {
  document.title = to.meta.title ? `${to.meta.title} · 智法宝` : '智法宝'

  if (to.meta.public) return true
  if (tokenStore.access) return true

  return { name: 'login', query: { redirect: to.fullPath } }
})

export default router
