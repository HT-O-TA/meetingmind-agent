<template>
  <div class="trace-page">
    <el-card>
      <template #header>
        <div class="header">
          <div>
            <h2>Agent 节点 Trace</h2>
            <p>仅展示本进程实际执行的节点、耗时与错误；服务重启后清空。</p>
          </div>
          <el-button type="primary" :loading="loading" @click="loadTrace">刷新</el-button>
        </div>
      </template>

      <el-row :gutter="16" class="summary">
        <el-col :span="6"><el-statistic title="保留 Span" :value="summary.retained_spans || 0" /></el-col>
        <el-col :span="6"><el-statistic title="执行中" :value="summary.active_spans || 0" /></el-col>
        <el-col :span="6">
          <el-statistic title="成功率" :value="successRate" suffix="%" />
        </el-col>
        <el-col :span="6">
          <el-statistic title="平均耗时" :value="summary.average_latency_ms || 0" suffix=" ms" />
        </el-col>
      </el-row>

      <el-table :data="spans" stripe empty-text="尚无真实 Agent Trace，请先执行一次 Agent 查询">
        <el-table-column prop="started_at" label="时间" width="190">
          <template #default="scope">{{ formatTime(scope.row.started_at) }}</template>
        </el-table-column>
        <el-table-column prop="operation_name" label="节点" min-width="170" />
        <el-table-column prop="component_type" label="类型" width="120" />
        <el-table-column prop="duration_ms" label="耗时(ms)" width="110" />
        <el-table-column prop="retry_count" label="重试" width="80" />
        <el-table-column prop="status" label="状态" width="100">
          <template #default="scope">
            <el-tag :type="scope.row.status === 'completed' ? 'success' : 'danger'">
              {{ scope.row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="证据" min-width="260">
          <template #default="scope">
            <span v-if="scope.row.error" class="error">{{ scope.row.error }}</span>
            <span v-else>{{ scope.row.output || '—' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { traceApi } from '@/api/trace'

const loading = ref(false)
const spans = ref([])
const summary = ref({})
const successRate = computed(() => {
  const rate = summary.value.success_rate
  return rate == null ? 0 : Number((rate * 100).toFixed(1))
})

function formatTime(timestamp) {
  return timestamp ? new Date(timestamp * 1000).toLocaleString() : '—'
}

async function loadTrace() {
  loading.value = true
  try {
    const [spanData, summaryData] = await Promise.all([
      traceApi.getSpans(100),
      traceApi.getSummary(),
    ])
    spans.value = spanData || []
    summary.value = summaryData || {}
  } catch (error) {
    ElMessage.error('Trace 加载失败')
  } finally {
    loading.value = false
  }
}

onMounted(loadTrace)
</script>

<style scoped>
.trace-page { max-width: 1200px; margin: 0 auto; }
.header { display: flex; align-items: center; justify-content: space-between; }
.header h2 { margin: 0 0 6px; }
.header p { margin: 0; color: #6b7280; font-size: 13px; }
.summary { margin-bottom: 24px; }
.error { color: #f56c6c; }
</style>
