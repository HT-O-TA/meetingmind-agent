<template>
  <div>
    <!-- 页面标题 -->
    <el-card shadow="never" style="margin-bottom:16px">
      <div style="display: flex; justify-content: space-between; align-items: center;">
        <div>
          <h2 style="margin: 0 0 8px 0;">🤝 人机协作中心</h2>
          <div style="font-size: 13px; color: #999;">处理待确认的 Agent 请求，实现人机协作</div>
        </div>
        <div style="display: flex; align-items: center; gap: 8px;">
          <el-badge :value="pendingCount" type="danger" />
          <el-button size="small" @click="refreshList">刷新列表</el-button>
        </div>
      </div>
    </el-card>

    <!-- 待处理请求列表 -->
    <el-card v-if="pendingRequests.length" shadow="never" style="margin-bottom:16px">
      <template #header>
        <span>📋 待处理请求</span>
        <span style="font-size:13px;color:#666;margin-left:16px">{{ pendingRequests.length }} 个待处理</span>
      </template>
      
      <el-timeline>
        <el-timeline-item
          v-for="request in pendingRequests"
          :key="request.request_id"
          color="warning"
        >
          <el-card shadow="never" style="width: 100%">
            <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px;">
              <div>
                <div style="display: flex; align-items: center; gap: 8px;">
                  <span style="font-weight:600">{{ request.title }}</span>
                  <el-tag type="warning" size="small">{{ request.type }}</el-tag>
                </div>
                <div style="font-size:12px;color:#999;margin-top:4px">
                  创建时间: {{ formatTime(request.created_at) }}
                </div>
              </div>
              <span style="font-size:12px;color:#666">{{ request.session_id?.slice(0, 8) }}...</span>
            </div>
            
            <div style="margin-bottom:12px;padding:12px;background:#f9f9f9;border-radius:4px">
              <div style="font-size:12px;color:#999;margin-bottom:4px">请求内容:</div>
              <div style="font-size:14px">{{ request.content }}</div>
            </div>
            
            <div v-if="request.options && request.options.length" style="margin-bottom:12px">
              <div style="font-size:12px;color:#999;margin-bottom:8px">可选回复:</div>
              <el-space :size="8">
                <el-button
                  v-for="(option, index) in request.options"
                  :key="index"
                  size="small"
                  type="primary"
                  @click="respond(request.request_id, option)"
                >
                  {{ option }}
                </el-button>
              </el-space>
            </div>
            
            <div style="display: flex; gap: 8px;">
              <el-input
                v-model="customResponses[request.request_id]"
                placeholder="输入自定义回复..."
                style="flex: 1;"
              />
              <el-button type="primary" @click="respond(request.request_id, customResponses[request.request_id])">
                发送回复
              </el-button>
              <el-button @click="reject(request.request_id)">拒绝</el-button>
            </div>
          </el-card>
        </el-timeline-item>
      </el-timeline>
    </el-card>

    <!-- 空状态 -->
    <el-empty v-if="!pendingRequests.length && !loading" description="暂无待处理的确认请求" />

    <!-- 历史记录 -->
    <el-card v-if="history.length" shadow="never">
      <template #header>
        <span>📝 处理历史</span>
        <span style="font-size:13px;color:#666;margin-left:16px">{{ history.length }} 条记录</span>
      </template>
      
      <el-table :data="history" border>
        <el-table-column prop="request_id" label="请求ID" width="120" />
        <el-table-column prop="title" label="标题" />
        <el-table-column prop="type" label="类型" width="100">
          <template #default="{ row }">
            <el-tag :type="getTypeTagType(row.type)" size="small">{{ row.type }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="response" label="用户回复" width="200" />
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="getStatusTagType(row.status)" size="small">{{ getStatusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="160" />
        <el-table-column prop="responded_at" label="处理时间" width="160" />
      </el-table>
    </el-card>

    <!-- 加载遮罩 -->
    <el-loading v-if="loading" text="加载中..." />
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

const pendingRequests = ref([])
const history = ref([])
const loading = ref(false)
const customResponses = ref({})

const pendingCount = computed(() => pendingRequests.value.length)

const formatTime = (timestamp) => {
  if (!timestamp) return '-'
  return new Date(timestamp * 1000).toLocaleString('zh-CN')
}

const getTypeTagType = (type) => {
  const types = {
    'tool_call': 'primary',
    'confirmation': 'warning',
    'approval': 'danger',
    'info': 'info',
  }
  return types[type] || 'default'
}

const getStatusTagType = (status) => {
  const types = {
    'pending': 'warning',
    'responded': 'success',
    'cancelled': 'info',
    'timeout': 'danger',
  }
  return types[status] || 'default'
}

const getStatusLabel = (status) => {
  const labels = {
    'pending': '待处理',
    'responded': '已处理',
    'cancelled': '已取消',
    'timeout': '已超时',
  }
  return labels[status] || status
}

async function loadPendingRequests() {
  loading.value = true
  try {
    const res = await fetch('/api/v1/agents/confirmations/pending')
    const data = await res.json()
    if (data.code === 200) {
      pendingRequests.value = data.pending_requests
      // 初始化自定义回复输入
      data.pending_requests.forEach(r => {
        if (!(r.request_id in customResponses.value)) {
          customResponses.value[r.request_id] = ''
        }
      })
    }
  } catch (e) {
    ElMessage.error('加载待处理请求失败')
    console.error('Load pending requests error:', e)
  } finally {
    loading.value = false
  }
}

async function loadHistory() {
  try {
    const res = await fetch('/api/v1/agents/confirmations/history?limit=50')
    const data = await res.json()
    if (data.code === 200) {
      history.value = data.history
    }
  } catch (e) {
    console.error('Load history error:', e)
  }
}

async function respond(requestId, response) {
  if (!response.trim()) {
    ElMessage.warning('请输入回复内容')
    return
  }
  
  try {
    const res = await fetch('/api/v1/agents/confirmations/respond', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ request_id: requestId, response })
    })
    const data = await res.json()
    if (data.code === 200) {
      ElMessage.success('回复成功')
      customResponses.value[requestId] = ''
      await loadPendingRequests()
      await loadHistory()
    } else {
      ElMessage.warning(data.message || '回复失败')
    }
  } catch (e) {
    ElMessage.error('回复失败')
    console.error('Respond error:', e)
  }
}

async function reject(requestId) {
  try {
    await ElMessageBox.confirm('确定要拒绝此请求吗？', '确认拒绝', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })
    
    await respond(requestId, '拒绝')
  } catch {
    // 用户取消
  }
}

async function refreshList() {
  await loadPendingRequests()
  await loadHistory()
  ElMessage.success('已刷新')
}

// 页面加载时自动加载数据
loadPendingRequests()
loadHistory()

// 定时刷新
setInterval(loadPendingRequests, 30000)
</script>
