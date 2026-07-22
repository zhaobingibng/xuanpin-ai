import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'Dashboard',
    component: () => import('@/views/Dashboard.vue'),
  },
  {
    path: '/products/:id',
    name: 'ProductDetail',
    component: () => import('@/views/ProductDetail.vue'),
  },
  {
    path: '/workbench',
    name: 'Workbench',
    component: () => import('@/views/Workbench.vue'),
  },
  {
    path: '/reports/daily',
    name: 'DailyReport',
    component: () => import('@/views/DailyReport.vue'),
  },
  {
    path: '/shops',
    name: 'ShopRegistry',
    component: () => import('@/views/ShopRegistry.vue'),
  },
  {
    path: '/ai-analysis',
    name: 'AIAnalysis',
    component: () => import('@/views/AIAnalysis.vue'),
  },
  {
    path: '/tasks',
    name: 'TaskCenter',
    component: () => import('@/views/TaskCenter.vue'),
  },
  {
    path: '/tasks/:name',
    name: 'TaskHistory',
    component: () => import('@/views/TaskHistory.vue'),
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
