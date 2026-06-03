<template>
  <div>
    <!-- 统计卡片 -->
    <el-row :gutter="12" style="margin-bottom:16px">
      <el-col :span="6" v-for="item in statCards" :key="item.label">
        <el-card shadow="never" style="text-align:center;padding:8px 0">
          <div style="font-size:24px;font-weight:700" :style="{color: item.color}">{{ item.value }}</div>
          <div style="font-size:12px;color:#999;margin-top:4px">{{ item.label }}</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 筛选栏 -->
    <el-card shadow="never" style="margin-bottom:16px">
      <el-row :gutter="12" align="middle">
        <el-col :span="5">
          <el-select v-model="filters.status" placeholder="状态筛选" clearable style="width:100%" @change="load">
            <el-option label="待处理" value="pending" />
            <el-option label="进行中" value="in_progress" />
            <el-option label="已完成" value="done" />
            <el-option label="已取消" value="cancelled" />
          </el-select>
        </el-col>
        <el-col :span="5">
          <el-select v-model="filters.priority" placeholder="优先级" clearable style="width:100%" @change="load">
            <el-option label="高" value="high" />
            <el-option label="中" value="medium" />
            <el-option label="低" value="low" />
          </el-select>
        </el-col>
        <el-col :span="6">
          <el-input v-model="filters.assignee_name" placeholder="负责人搜索" clearable @keyup.enter="load" />
        </el-col>
        <el-col :span="4">
          <el-button type="primary" @click="load">查询</el-button>
          <el-button @click="resetFilters">重置</el-button>
        </el-col>
        <el-col :span="4" style="text-align:right">
          <el-button type="primary" @click="showDialog = true">新增待办</el-button>
        </el-col>
      </el-row>
    </el-card>

    <!-- 待办列表 -->
    <el-table :data="store.todos" v-loading="store.loading" stripe border>
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="title" label="标题" min-width="200" />
      <el-table-column prop="assignee_name" label="负责人" width="100">
        <template #default="{ row }">{{ row.assignee_name || '-' }}</template>
      </el-table-column>
      <el-table-column prop="priority" label="优先级" width="80">
        <template #default="{ row }">
          <el-tag :type="priorityType(row.priority)" size="small">{{ priorityLabel(row.priority) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="status" label="状态" width="90">
        <template #default="{ row }">
          <el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="due_date" label="截止时间" width="140">
        <template #default="{ row }">{{ row.due_date ? formatDate(row.due_date) : '-' }}</template>
      </el-table-column>
      <el-table-column label="操作" width="180">
        <template #default="{ row }">
          <el-button size="small" type="success" :disabled="row.status === 'done'" @click="markDone(row)">完成</el-button>
          <el-button size="small" @click="openEdit(row)">编辑</el-button>
          <el-button size="small" type="danger" @click="remove(row.id)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      style="margin-top:16px;justify-content:flex-end;display:flex"
      :total="store.total" :page-size="pageSize" :current-page="page"
      layout="total, prev, pager, next"
      @current-change="(p) => { page = p; load() }"
    />

    <!-- 新增/编辑弹窗 -->
    <el-dialog v-model="showDialog" :title="editingId ? '编辑待办' : '新增待办'" width="480px" @close="resetForm">
      <el-form :model="form" label-width="80px">
        <el-form-item label="标题"><el-input v-model="form.title" /></el-form-item>
        <el-form-item label="描述"><el-input v-model="form.description" type="textarea" :rows="2" /></el-form-item>
        <el-form-item label="负责人"><el-input v-model="form.assignee_name" /></el-form-item>
        <el-form-item label="优先级">
          <el-select v-model="form.priority" style="width:100%">
            <el-option label="高" value="high" /><el-option label="中" value="medium" /><el-option label="低" value="low" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态" v-if="editingId">
          <el-select v-model="form.status" style="width:100%">
            <el-option label="待处理" value="pending" /><el-option label="进行中" value="in_progress" />
            <el-option label="已完成" value="done" /><el-option label="已取消" value="cancelled" />
          </el-select>
        </el-form-item>
        <el-form-item label="截止时间">
          <el-date-picker v-model="form.due_date" type="datetime" style="width:100%" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showDialog = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submit">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useTodoStore } from '@/stores/todo'
import { ElMessageBox } from 'element-plus'

const store = useTodoStore()
const page = ref(1)
const pageSize = 20
const showDialog = ref(false)
const editingId = ref(null)
const submitting = ref(false)
const filters = reactive({ status: '', priority: '', assignee_name: '' })
const form = reactive({ title: '', description: '', assignee_name: '', priority: 'medium', status: 'pending', due_date: null })

const statCards = computed(() => [
  { label: '全部', value: store.stats.total, color: '#409eff' },
  { label: '待处理', value: store.stats.pending, color: '#e6a23c' },
  { label: '进行中', value: store.stats.in_progress, color: '#409eff' },
  { label: '已完成', value: store.stats.done, color: '#67c23a' },
])

const priorityType = (p) => ({ high: 'danger', medium: 'warning', low: 'info' }[p] || '')
const priorityLabel = (p) => ({ high: '高', medium: '中', low: '低' }[p] || p)
const statusType = (s) => ({ pending: 'info', in_progress: 'warning', done: 'success', cancelled: '' }[s] || '')
const statusLabel = (s) => ({ pending: '待处理', in_progress: '进行中', done: '已完成', cancelled: '已取消' }[s] || s)
const formatDate = (d) => new Date(d).toLocaleString('zh-CN')

function load() {
  const params = { page: page.value, page_size: pageSize }
  if (filters.status) params.status = filters.status
  if (filters.priority) params.priority = filters.priority
  if (filters.assignee_name) params.assignee_name = filters.assignee_name
  store.fetchTodos(params)
  store.fetchStats()
}

function resetFilters() {
  filters.status = ''; filters.priority = ''; filters.assignee_name = ''
  load()
}

function openEdit(row) {
  editingId.value = row.id
  Object.assign(form, { title: row.title, description: row.description || '', assignee_name: row.assignee_name || '', priority: row.priority, status: row.status, due_date: row.due_date })
  showDialog.value = true
}

function resetForm() {
  editingId.value = null
  Object.assign(form, { title: '', description: '', assignee_name: '', priority: 'medium', status: 'pending', due_date: null })
}

async function submit() {
  if (!form.title) return
  submitting.value = true
  try {
    if (editingId.value) {
      await store.updateTodo(editingId.value, form)
    } else {
      // 全局待办需要 meeting_id，这里设为 null 时后端需支持（已在 schema 设为可选）
      await store.createTodo({ ...form, meeting_id: null })
    }
    showDialog.value = false
    load()
  } finally {
    submitting.value = false
  }
}

async function markDone(row) {
  await store.updateTodo(row.id, { status: 'done' })
}

async function remove(id) {
  await ElMessageBox.confirm('确认删除该待办？', '提示', { type: 'warning' })
  await store.removeTodo(id)
}

onMounted(load)
</script>
