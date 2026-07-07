<template>
  <div class="bad-case-page">
    <div class="page-header">
      <h2>Bad Case 管理</h2>
      <p class="description">收集和管理用户反馈中的问题案例，持续优化系统性能</p>
    </div>

    <div class="stats-row">
      <div class="stat-card" v-for="stat in stats" :key="stat.label">
        <div class="stat-value" :class="stat.color">{{ stat.value }}</div>
        <div class="stat-label">{{ stat.label }}</div>
      </div>
    </div>

    <div class="filter-bar">
      <el-select v-model="filters.category" placeholder="问题类型" style="width: 150px;">
        <el-option label="全部" value="" />
        <el-option label="事实错误" value="factual_error" />
        <el-option label="回答不完整" value="incomplete" />
        <el-option label="答非所问" value="irrelevant" />
        <el-option label="逻辑错误" value="logical_error" />
        <el-option label="格式错误" value="format_error" />
        <el-option label="其他" value="other" />
      </el-select>
      <el-select v-model="filters.status" placeholder="处理状态" style="width: 150px;">
        <el-option label="全部" value="" />
        <el-option label="待分析" value="pending" />
        <el-option label="分析中" value="analyzing" />
        <el-option label="已改进" value="improved" />
        <el-option label="已验证" value="verified" />
        <el-option label="已关闭" value="closed" />
      </el-select>
      <el-select v-model="filters.priority" placeholder="优先级" style="width: 120px;">
        <el-option label="全部" value="" />
        <el-option label="高" value="high" />
        <el-option label="中" value="medium" />
        <el-option label="低" value="low" />
      </el-select>
      <el-button type="primary" @click="refreshBadCases">
        <el-icon><Refresh /></el-icon>
        刷新
      </el-button>
    </div>

    <el-table
      :data="badCases"
      border
      style="width: 100%;"
      v-loading="loading"
    >
      <el-table-column prop="bad_case_id" label="ID" min-width="150">
        <template #default="scope">
          <span class="case-id">{{ scope.row.bad_case_id }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="category" label="问题类型">
        <template #default="scope">
          <el-tag :type="getCategoryTag(scope.row.category)">
            {{ getCategoryLabel(scope.row.category) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="priority" label="优先级">
        <template #default="scope">
          <el-tag :type="getPriorityTag(scope.row.priority)">
            {{ getPriorityLabel(scope.row.priority) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="input_text" label="用户输入" min-width="200">
        <template #default="scope">
          <span class="text-content">{{ scope.row.input_text }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="actual_output" label="实际回答" min-width="200">
        <template #default="scope">
          <span class="text-content">{{ scope.row.actual_output }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="resolution_status" label="状态">
        <template #default="scope">
          <el-tag :type="getStatusTag(scope.row.resolution_status)">
            {{ getStatusLabel(scope.row.resolution_status) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="timestamp" label="创建时间" min-width="150" />
      <el-table-column label="操作">
        <template #default="scope">
          <el-button
            v-if="scope.row.resolution_status === 'pending'"
            type="primary"
            size="small"
            @click="analyzeCase(scope.row.bad_case_id)"
          >
            <el-icon><Search /></el-icon>
            分析
          </el-button>
          <el-button
            type="primary"
            size="small"
            @click="viewDetail(scope.row)"
          >
            <el-icon><View /></el-icon>
            详情
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog title="Bad Case 详情" v-model:visible="showDetailDialog" width="800px">
      <div v-if="selectedCase" class="detail-content">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="Case ID" :span="2">
            <code>{{ selectedCase.bad_case_id }}</code>
          </el-descriptions-item>
          <el-descriptions-item label="问题类型">
            <el-tag :type="getCategoryTag(selectedCase.category)">
              {{ getCategoryLabel(selectedCase.category) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="优先级">
            <el-tag :type="getPriorityTag(selectedCase.priority)">
              {{ getPriorityLabel(selectedCase.priority) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="getStatusTag(selectedCase.resolution_status)">
              {{ getStatusLabel(selectedCase.resolution_status) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ selectedCase.timestamp }}</el-descriptions-item>
          <el-descriptions-item label="用户输入" :span="2">
            <div class="text-block">{{ selectedCase.input_text }}</div>
          </el-descriptions-item>
          <el-descriptions-item label="实际回答" :span="2">
            <div class="text-block">{{ selectedCase.actual_output }}</div>
          </el-descriptions-item>
          <el-descriptions-item label="期望回答" :span="2">
            <div class="text-block">{{ selectedCase.expected_output || '-' }}</div>
          </el-descriptions-item>
          <el-descriptions-item label="根因分析" :span="2">
            <div class="text-block">{{ selectedCase.analysis || '-' }}</div>
          </el-descriptions-item>
          <el-descriptions-item label="改进方案" :span="2">
            <div class="text-block">{{ selectedCase.improvement_plan || '-' }}</div>
          </el-descriptions-item>
        </el-descriptions>

        <div v-if="selectedCase.resolution_status === 'pending'" class="detail-actions">
          <el-button type="primary" @click="analyzeCase(selectedCase.bad_case_id)">
            <el-icon><Search /></el-icon>
            分析根因
          </el-button>
          <el-button @click="updateStatus(selectedCase.bad_case_id, 'closed')">
            <el-icon><CircleCheck /></el-icon>
            关闭
          </el-button>
        </div>
      </div>
    </el-dialog>

    <el-pagination
      v-if="total > 0"
      :total="total"
      :page-size="pageSize"
      :current-page="currentPage"
      @current-change="handlePageChange"
      layout="prev, pager, next"
      style="margin-top: 20px; text-align: right;"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { Refresh, Search, View } from '@element-plus/icons-vue'
import { getBadCases, analyzeBadCase, updateBadCase } from '@/api/feedback'

const loading = ref(false)
const badCases = ref([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(20)
const filters = ref({
  category: '',
  status: '',
  priority: ''
})
const showDetailDialog = ref(false)
const selectedCase = ref(null)

const stats = computed(() => {
  const pending = badCases.value.filter(bc => bc.resolution_status === 'pending').length
  const analyzing = badCases.value.filter(bc => bc.resolution_status === 'analyzing').length
  const improved = badCases.value.filter(bc => bc.resolution_status === 'improved').length
  const verified = badCases.value.filter(bc => bc.resolution_status === 'verified').length
  return [
    { label: '待分析', value: pending, color: 'text-warning' },
    { label: '分析中', value: analyzing, color: 'text-primary' },
    { label: '已改进', value: improved, color: 'text-success' },
    { label: '已验证', value: verified, color: 'text-info' }
  ]
})

async function loadBadCases() {
  loading.value = true
  try {
    const response = await getBadCases(
      filters.value.category,
      filters.value.status,
      filters.value.priority,
      pageSize.value,
      (currentPage.value - 1) * pageSize.value
    )
    badCases.value = response.data || []
    total.value = response.data?.length || 0
  } catch (error) {
    console.error('Failed to load bad cases:', error)
  } finally {
    loading.value = false
  }
}

function refreshBadCases() {
  currentPage.value = 1
  loadBadCases()
}

function viewDetail(caseItem) {
  selectedCase.value = caseItem
  showDetailDialog.value = true
}

async function analyzeCase(badCaseId) {
  if (!confirm('确定要分析这个 Bad Case 吗？这将生成根因分析和改进建议。')) return
  
  try {
    await analyzeBadCase(badCaseId)
    await loadBadCases()
    showDetailDialog.value = false
  } catch (error) {
    console.error('Failed to analyze bad case:', error)
  }
}

async function updateStatus(badCaseId, status) {
  if (!confirm(`确定要将状态改为"${getStatusLabel(status)}"吗？`)) return
  
  try {
    await updateBadCase(badCaseId, { resolutionStatus: status })
    await loadBadCases()
    showDetailDialog.value = false
  } catch (error) {
    console.error('Failed to update status:', error)
  }
}

function getCategoryLabel(category) {
  const map = {
    'factual_error': '事实错误',
    'incomplete': '回答不完整',
    'irrelevant': '答非所问',
    'logical_error': '逻辑错误',
    'format_error': '格式错误',
    'other': '其他'
  }
  return map[category] || category
}

function getCategoryTag(category) {
  const map = {
    'factual_error': 'danger',
    'incomplete': 'warning',
    'irrelevant': 'info',
    'logical_error': 'danger',
    'format_error': 'info',
    'other': 'default'
  }
  return map[category] || 'default'
}

function getPriorityLabel(priority) {
  const map = {
    'high': '高',
    'medium': '中',
    'low': '低'
  }
  return map[priority] || priority
}

function getPriorityTag(priority) {
  const map = {
    'high': 'danger',
    'medium': 'warning',
    'low': 'info'
  }
  return map[priority] || 'default'
}

function getStatusLabel(status) {
  const map = {
    'pending': '待分析',
    'analyzing': '分析中',
    'improved': '已改进',
    'verified': '已验证',
    'closed': '已关闭'
  }
  return map[status] || status
}

function getStatusTag(status) {
  const map = {
    'pending': 'warning',
    'analyzing': 'primary',
    'improved': 'success',
    'verified': 'success',
    'closed': 'info'
  }
  return map[status] || 'default'
}

function handlePageChange(page) {
  currentPage.value = page
  loadBadCases()
}

onMounted(() => {
  loadBadCases()
})
</script>

<style scoped>
.bad-case-page {
  padding: 20px;
}

.page-header {
  margin-bottom: 20px;
}

.page-header h2 {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
}

.page-header .description {
  margin: 8px 0 0;
  color: #666;
  font-size: 14px;
}

.filter-bar {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
  align-items: center;
}

.stats-row {
  display: flex;
  gap: 20px;
  margin-bottom: 20px;
}

.stat-card {
  flex: 1;
  background: #fff;
  border-radius: 8px;
  padding: 16px;
  text-align: center;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.stat-value {
  font-size: 24px;
  font-weight: 600;
  margin-bottom: 4px;
}

.stat-value.text-warning {
  color: #e6a23c;
}

.stat-value.text-primary {
  color: #409eff;
}

.stat-value.text-success {
  color: #67c23a;
}

.stat-value.text-info {
  color: #909399;
}

.stat-label {
  font-size: 13px;
  color: #999;
}

.case-id {
  font-family: monospace;
  font-size: 12px;
  color: #666;
}

.text-content {
  font-size: 13px;
  color: #666;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.detail-content {
  max-height: 600px;
  overflow-y: auto;
}

.text-block {
  background: #f5f7fa;
  padding: 12px;
  border-radius: 4px;
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  max-height: 150px;
  overflow-y: auto;
}

.detail-actions {
  display: flex;
  gap: 12px;
  margin-top: 20px;
  justify-content: flex-end;
}
</style>


