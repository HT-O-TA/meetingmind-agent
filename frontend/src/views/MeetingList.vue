<template>
  <div>
    <!-- 搜索和筛选区域 -->
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;flex-wrap:wrap;gap:12px">
      <div style="display:flex;gap:12px;flex-wrap:wrap">
        <el-input v-model="keyword" placeholder="搜索会议标题..." style="width:280px" clearable @keyup.enter="load" />
        
        <el-select v-model="status" placeholder="状态筛选" clearable style="width:120px">
          <el-option label="草稿" value="draft" />
          <el-option label="处理中" value="processing" />
          <el-option label="已完成" value="completed" />
          <el-option label="已归档" value="archived" />
        </el-select>
        
        <el-select v-model="department" placeholder="部门筛选" clearable style="width:120px">
          <el-option label="技术部" value="技术部" />
          <el-option label="产品部" value="产品部" />
          <el-option label="市场部" value="市场部" />
          <el-option label="财务部" value="财务部" />
        </el-select>
        
        <el-select v-model="meetingType" placeholder="会议类型" clearable style="width:120px">
          <el-option label="通用会议" value="general" />
          <el-option label="项目会议" value="project" />
          <el-option label="周会" value="weekly" />
        </el-select>
        
        <el-button type="primary" @click="load">查询</el-button>
        <el-button @click="reset">重置</el-button>
      </div>
      
      <el-button type="primary" @click="$router.push('/meetings/upload')">新建会议</el-button>
    </div>

    <el-table :data="store.meetings" v-loading="store.loading" stripe border>
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="title" label="会议标题" min-width="180">
        <template #default="{ row }">
          <el-link type="primary" @click="$router.push(`/meetings/${row.id}`)">{{ row.title }}</el-link>
        </template>
      </el-table-column>
      <el-table-column prop="organizer_name" label="组织者" width="100" />
      <el-table-column prop="department" label="部门" width="100" />
      <el-table-column prop="meeting_type" label="会议类型" width="100">
        <template #default="{ row }">{{ meetingTypeLabel(row.meeting_type) }}</template>
      </el-table-column>
      <el-table-column prop="status" label="状态" width="90">
        <template #default="{ row }">
          <el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="创建时间" width="160">
        <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="120">
        <template #default="{ row }">
          <el-button size="small" @click="$router.push(`/meetings/${row.id}`)">查看</el-button>
          <el-button size="small" type="danger" @click="remove(row.id)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      style="margin-top:16px;justify-content:flex-end;display:flex"
      :total="store.total"
      :page-size="pageSize"
      :current-page="page"
      :page-sizes="[10, 20, 50, 100]"
      layout="total, sizes, prev, pager, next, jumper"
      @size-change="(size) => { pageSize = size; page = 1; load() }"
      @current-change="(p) => { page = p; load() }"
    />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useMeetingStore } from '@/stores/meeting'
import { meetingApi } from '@/api/meetings'
import { ElMessage, ElMessageBox } from 'element-plus'

const store = useMeetingStore()
const keyword = ref('')
const status = ref('')
const department = ref('')
const meetingType = ref('')
const page = ref(1)
const pageSize = ref(20)

function load() {
  store.fetchMeetings({ 
    page: page.value, 
    page_size: pageSize.value, 
    keyword: keyword.value || undefined,
    status: status.value || undefined,
    department: department.value || undefined,
    meeting_type: meetingType.value || undefined
  })
}

function reset() {
  keyword.value = ''
  status.value = ''
  department.value = ''
  meetingType.value = ''
  page.value = 1
  load()
}

function statusType(s) {
  return { draft: 'info', processing: 'warning', completed: 'success', archived: '' }[s] || 'info'
}
function statusLabel(s) {
  return { draft: '草稿', processing: '处理中', completed: '已完成', archived: '已归档' }[s] || s
}
function meetingTypeLabel(t) {
  return { general: '通用会议', project: '项目会议', weekly: '周会' }[t] || t
}
function formatDate(d) {
  return d ? new Date(d).toLocaleString('zh-CN') : '-'
}

async function remove(id) {
  await ElMessageBox.confirm('确认删除该会议？', '提示', { type: 'warning' })
  await meetingApi.remove(id)
  ElMessage.success('删除成功')
  load()
}

onMounted(load)
</script>
