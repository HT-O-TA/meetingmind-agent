import { defineStore } from 'pinia'
import { ref } from 'vue'
import { todoApi } from '@/api/todos'
import { ElMessage } from 'element-plus'

export const useTodoStore = defineStore('todo', () => {
  const todos = ref([])
  const total = ref(0)
  const loading = ref(false)
  const stats = ref({ total: 0, done: 0, pending: 0, in_progress: 0, completion_rate: 0 })

  async function fetchTodos(params = {}) {
    loading.value = true
    try {
      const res = await todoApi.list(params)
      todos.value = res.data || []
      total.value = res.total || 0
    } finally {
      loading.value = false
    }
  }

  async function fetchStats(meetingId = null) {
    try {
      const res = await todoApi.stats(meetingId ? { meeting_id: meetingId } : {})
      stats.value = res.data
    } catch {
      // 统计接口失败不影响列表展示
    }
  }

  async function createTodo(data) {
    const res = await todoApi.create(data)
    todos.value.unshift(res.data)
    total.value++
    ElMessage.success('创建成功')
    return res.data
  }

  async function updateTodo(id, data) {
    const res = await todoApi.update(id, data)
    const idx = todos.value.findIndex(t => t.id === id)
    if (idx !== -1) todos.value[idx] = res.data
    return res.data
  }

  async function removeTodo(id) {
    await todoApi.remove(id)
    todos.value = todos.value.filter(t => t.id !== id)
    total.value--
    ElMessage.success('删除成功')
  }

  return { todos, total, loading, stats, fetchTodos, fetchStats, createTodo, updateTodo, removeTodo }
})
