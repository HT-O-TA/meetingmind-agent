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
      { path: 'embedding', component: () => import('@/views/EmbeddingTest.vue') },
      { path: 'vector-search', component: () => import('@/views/VectorSearchTest.vue') },
      { path: 'query', component: () => import('@/views/QueryPage.vue') },
      { path: 'agent', component: () => import('@/views/AgentDemo.vue') },
      { path: 'users', component: () => import('@/views/UserList.vue') },
      { path: 'evaluation', component: () => import('@/views/EvaluationPage.vue') },
      { path: 'confirmation', component: () => import('@/views/ConfirmationPage.vue') },
      { path: 'profile', component: () => import('@/views/ProfilePage.vue') },
      { path: 'tests', component: () => import('@/views/TestPage.vue') },
      { path: 'config', component: () => import('@/views/ConfigPage.vue') },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

let isTokenValidating = false

router.beforeEach(async (to, from, next) => {
  const userStore = useUserStore()
  
  if (to.path === '/login') {
    next()
    return
  }
  
  if (!userStore.token) {
    next()
    return
  }
  
  if (!userStore.isTokenValidated && !isTokenValidating) {
    isTokenValidating = true
    try {
      await userStore.validateToken()
    } finally {
      isTokenValidating = false
    }
  }
  
  next()
})

export default router