<template>
  <div class="task-queue-page">
    <div class="page-header">
      <h2>任务队列监控</h2>
      <p class="description">实时监控文档处理任务的进度和状态</p>
    </div>

    <div class="filter-bar">
      <el-select v-model="filters.type" placeholder="任务类型" style="width: 150px;">
        <el-option label="全部" value="" />
        <el-option label="文档处理" value="document_process" />
        <el-option label="向量化" value="vector_embed" />
        <el-option label="知识图谱" value="knowledge_graph" />
      </el-select>
      <el-select v-model="filters.status" placeholder="任务状态" style="width: 150px;">
        <el-option label="全部" value="" />
        <el-option label="等待中" value="pending" />
        <el-option label="处理中" value="processing" />
        <el-option label="已完成" value="completed" />
        <el-option label="失败" value="failed" />
        <el-option label="已取消" value="cancelled" />
      </el-select>
      <el-button type="primary" @click="refreshTasks">
        <el-icon><Refresh /></el-icon>
        刷新
      </el-button>
    </div>

    <div class="stats-row">
      <div class="stat-card" v-for="stat in stats" :key="stat.label">
        <div class="stat-value" :class="stat.color">{{ stat.value }}</div>
        <div class="stat-label">{{ stat.label }}</div>
      </div>
    </div>

    <el-table
      :data="tasks"
      border
      style="width: 100%;"
      v-loading="loading"
    >
      <el-table-column prop="task_id" label="任务ID" min-width="200">
        <template #default="scope">
          <span class="task-id">{{ scope.row.task_id }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="task_type" label="任务类型">
        <template #default="scope">
          <el-tag :type="getTaskTypeTag(scope.row.task_type)">
            {{ getTaskTypeLabel(scope.row.task_type) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="status" label="状态">
        <template #default="scope">
          <el-tag :type="getStatusTag(scope.row.status)">
            {{ getStatusLabel(scope.row.status) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="progress" label="进度">
        <template #default="scope">
          <div class="progress-wrapper">
            <el-progress
              :percentage="scope.row.progress"
              :status="getProgressStatus(scope.row.status, scope.row.progress)"
              :stroke-width="12"
            />
            <span class="progress-text">{{ scope.row.progress }}%</span>
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="error" label="错误信息" min-width="200">
        <template #default="scope">
          <span v-if="scope.row.error" class="error-text">{{ scope.row.error }}</span>
          <span v-else class="no-error">-</span>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="创建时间" min-width="150" />
      <el-table-column prop="updated_at" label="更新时间" min-width="150" />
      <el-table-column label="操作">
        <template #default="scope">
          <el-button
            v-if="scope.row.status === 'pending' || scope.row.status === 'processing'"
            type="warning"
            size="small"
            @click="cancelTask(scope.row.task_id)"
          >
            <el-icon><Close /></el-icon>
            取消
          </el-button>
          <el-button
            v-if="scope.row.status !== 'processing'"
            type="danger"
            size="small"
            @click="deleteTask(scope.row.task_id)"
          >
            <el-icon><Delete /></el-icon>
            删除
          </el-button>
          <el-button
            v-if="scope.row.status === 'completed'"
            type="primary"
            size="small"
            @click="viewResult(scope.row)"
          >
            <el-icon><View /></el-icon>
            查看结果
          </el-button>
          <span v-if="scope.row.status === 'processing'" class="processing-text">处理中...</span>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog title="任务结果详情" v-model:visible="showResultDialog" width="600px">
      <div v-if="selectedTask" class="result-detail">
        <el-descriptions :column="1" border>
          <el-descriptions-item label="任务ID">{{ selectedTask.task_id }}</el-descriptions-item>
          <el-descriptions-item label="任务类型">{{ getTaskTypeLabel(selectedTask.task_type) }}</el-descriptions-item>
          <el-descriptions-item label="状态">{{ getStatusLabel(selectedTask.status) }}</el-descriptions-item>
          <el-descriptions-item label="进度">{{ selectedTask.progress }}%</el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ selectedTask.created_at }}</el-descriptions-item>
          <el-descriptions-item label="更新时间">{{ selectedTask.updated_at }}</el-descriptions-item>
          <el-descriptions-item label="处理结果" v-if="selectedTask.result">
            <pre class="result-json">{{ JSON.stringify(selectedTask.result, null, 2) }}</pre>
          </el-descriptions-item>
        </el-descriptions>
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

<script setup>import { ref, computed, onMounted, onUnmounted } from 'vue';
import { Refresh, Close, Delete, View } from '@element-plus/icons-vue';
import { listTasks, cancelTask as cancelTaskAPI, deleteTask as deleteTaskAPI } from '@/api/tasks';
const loading = ref(false);
const tasks = ref([]);
const total = ref(0);
const currentPage = ref(1);
const pageSize = ref(100);
const filters = ref({
 type: '',
 status: ''
});
const showResultDialog = ref(false);
const selectedTask = ref(null);
let refreshInterval = null;
const stats = computed(() => {
 const pending = tasks.value.filter(t => t.status === 'pending').length;
 const processing = tasks.value.filter(t => t.status === 'processing').length;
 const completed = tasks.value.filter(t => t.status === 'completed').length;
 const failed = tasks.value.filter(t => t.status === 'failed').length;
 return [
 { label: '等待中', value: pending, color: 'text-warning' },
 { label: '处理中', value: processing, color: 'text-primary' },
 { label: '已完成', value: completed, color: 'text-success' },
 { label: '失败', value: failed, color: 'text-danger' }
 ];
});
async function loadTasks() {
 loading.value = true;
 try {
 const response = await listTasks(filters.value.type, filters.value.status, pageSize.value);
 tasks.value = response.data.tasks || [];
 total.value = response.data.total || 0;
 }
 catch (error) {
 console.error('Failed to load tasks:', error);
 }
 finally {
 loading.value = false;
 }
}
function refreshTasks() {
 loadTasks();
}
async function cancelTask(taskId) {
 if (!confirm('确定要取消这个任务吗？'))
 return;
 try {
 await cancelTaskAPI(taskId);
 await loadTasks();
 }
 catch (error) {
 console.error('Failed to cancel task:', error);
 }
}
async function deleteTask(taskId) {
 if (!confirm('确定要删除这个任务吗？此操作不可撤销。'))
 return;
 try {
 await deleteTaskAPI(taskId);
 await loadTasks();
 }
 catch (error) {
 console.error('Failed to delete task:', error);
 }
}
function viewResult(task) {
 selectedTask.value = task;
 showResultDialog.value = true;
}
function getTaskTypeLabel(type) {
 const map = {
 'document_process': '文档处理',
 'vector_embed': '向量化',
 'knowledge_graph': '知识图谱'
 };
 return map[type] || type;
}
function getTaskTypeTag(type) {
 const map = {
 'document_process': 'primary',
 'vector_embed': 'success',
 'knowledge_graph': 'warning'
 };
 return map[type] || 'info';
}
function getStatusLabel(status) {
 const map = {
 'pending': '等待中',
 'processing': '处理中',
 'completed': '已完成',
 'failed': '失败',
 'cancelled': '已取消'
 };
 return map[status] || status;
}
function getStatusTag(status) {
 const map = {
 'pending': 'warning',
 'processing': 'primary',
 'completed': 'success',
 'failed': 'danger',
 'cancelled': 'info'
 };
 return map[status] || 'info';
}
function getProgressStatus(status, progress) {
 if (status === 'completed')
 return 'success';
 if (status === 'failed')
 return 'exception';
 return undefined;
}
function handlePageChange(page) {
 currentPage.value = page;
 loadTasks();
}
onMounted(() => {
 loadTasks();
 refreshInterval = setInterval(loadTasks, 5000);
});
onUnmounted(() => {
 if (refreshInterval) {
 clearInterval(refreshInterval);
 }
});
</script>

<style scoped>
.task-queue-page {
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

.stat-value.text-danger {
  color: #f56c6c;
}

.stat-label {
  font-size: 13px;
  color: #999;
}

.task-id {
  font-family: monospace;
  font-size: 12px;
  color: #666;
}

.progress-wrapper {
  display: flex;
  align-items: center;
  gap: 12px;
}

.progress-text {
  font-size: 14px;
  font-weight: 500;
  min-width: 50px;
}

.error-text {
  color: #f56c6c;
  font-size: 13px;
  word-break: break-all;
}

.no-error {
  color: #999;
  font-size: 13px;
}

.processing-text {
  color: #409eff;
  font-size: 13px;
}

.result-detail {
  max-height: 400px;
  overflow-y: auto;
}

.result-json {
  background: #f5f7fa;
  padding: 12px;
  border-radius: 4px;
  font-size: 12px;
  overflow-x: auto;
  max-height: 200px;
}

.el-descriptions__label {
  font-weight: 600;
}
</style>


