/** 业务页面路由及未登录访问的跳转规则。 */
import { createRouter, createWebHistory } from 'vue-router'

import { tokenStore } from '@/api/client'

const reviewWorkspace = () => import('@/views/ReviewView.vue')

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
      component: reviewWorkspace,
      meta: { title: '合同审查' },
    },
    {
      path: '/review/:taskId',
      name: 'review-detail',
      component: reviewWorkspace,
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

/** 访问受保护页面时保存原地址，供登录完成后返回。资源授权由后端接口校验。 */
router.beforeEach((to) => {
  document.title = to.meta.title ? `${to.meta.title} · 智法宝` : '智法宝'

  if (to.meta.public) return true
  if (tokenStore.access) return true

  return { name: 'login', query: { redirect: to.fullPath } }
})

export default router
