import { createRouter, createWebHistory } from 'vue-router'
import { useUserStore } from '@/stores/user'

const routes = [
  { path: '/login', component: () => import('@/views/LoginPage.vue') },
  {
    path: '/',
    component: () => import('@/components/layout/AppLayout.vue'),
    children: [
      { path: '', redirect: '/meetings' },
      { path: 'meetings', component: () => import('@/views/MeetingList.vue') },
      { path: 'meetings/upload', component: () => import('@/views/MeetingUpload.vue') },
      { path: 'meetings/:id', component: () => import('@/views/MeetingDetail.vue') },
      { path: 'meetings/:id/edit', component: () => import('@/views/MeetingEdit.vue') },
      { path: 'todos', component: () => import('@/views/TodoList.vue') },
      { path: 'documents', component: () => import('@/views/DocumentList.vue') },
      { path: 'tasks', component: () => import('@/views/TaskQueuePage.vue') },
      { path: 'feedback', component: () => import('@/views/BadCasePage.vue') },
      { path: 'graph', component: () => import('@/views/GraphPage.vue') },
      { path: 'query', component: () => import('@/views/QueryPage.vue') },
      { path: 'agent', component: () => import('@/views/AgentDemo.vue') },
      { path: 'trace', component: () => import('@/views/TracePage.vue') },
      { path: 'users', component: () => import('@/views/UserList.vue') },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

let isTokenValidating = false

router.beforeEach(async (to, from, next) => {
  if (to.path === '/login') {
    next()
    return
  }
  
  const token = localStorage.getItem('token')
  
  if (!token) {
    next({ path: '/login', query: { redirect: to.fullPath } })
    return
  }
  
  next()
})

export default router
