<template>
  <div>
    <!-- 页面标题和状态 -->
    <el-card shadow="never" style="margin-bottom:16px">
      <div style="display: flex; justify-content: space-between; align-items: center;">
        <div>
          <h2 style="margin: 0 0 8px 0;">RAG 评估中心</h2>
          <div style="font-size: 13px; color: #999;">评估 RAG 系统性能，监控指标变化</div>
        </div>
        <div style="display: flex; align-items: center; gap: 8px;">
          <el-badge :value="statusText" :type="statusType" />
          <el-button size="small" @click="refreshStatistics">刷新统计</el-button>
          <el-button size="small" @click="clearResults">清除结果</el-button>
        </div>
      </div>
    </el-card>

    <!-- 操作按钮 -->
    <el-card shadow="never" style="margin-bottom:16px">
      <el-space :size="8">
        <el-button type="primary" :loading="evaluating" @click="evaluateAll">
          <template #icon><el-icon><RefreshCw /></el-icon></template>
          评估全部数据集
        </el-button>
        <el-button :loading="loadingDataset" @click="loadDataset">
          <template #icon><el-icon><FolderOpen /></el-icon></template>
          加载数据集
        </el-button>
        <el-button :loading="runningRegression" @click="runRegression">
          <template #icon><el-icon><TrendingUp /></el-icon></template>
          运行回归测试
        </el-button>
        <el-button :loading="establishingBaseline" @click="establishBaseline">
          <template #icon><el-icon><Target /></el-icon></template>
          建立基准
        </el-button>
        <el-button :loading="loadingStatistics" @click="loadStatistics">
          <template #icon><el-icon><BarChart3 /></el-icon></template>
          获取统计
        </el-button>
      </el-space>
    </el-card>

    <!-- 统计概览 -->
    <el-row :gutter="12" v-if="statistics" style="margin-bottom:16px">
      <el-col :span="24">
        <el-card shadow="never">
          <template #header>
            <span>📊 系统统计</span>
          </template>
          <el-row :gutter="12">
            <el-col :span="4">
              <div style="font-size:12px;color:#999">总评估次数</div>
              <div style="font-size:24px;font-weight:700;color:#409eff">{{ statistics.total_evaluations }}</div>
            </el-col>
            <el-col :span="4">
              <div style="font-size:12px;color:#999">平均忠实度</div>
              <div style="font-size:24px;font-weight:700;color:#67c23a">{{ (statistics.average_scores?.faithfulness || 0).toFixed(2) }}</div>
            </el-col>
            <el-col :span="4">
              <div style="font-size:12px;color:#999">平均相关性</div>
              <div style="font-size:24px;font-weight:700;color:#67c23a">{{ (statistics.average_scores?.answer_relevancy || 0).toFixed(2) }}</div>
            </el-col>
            <el-col :span="4">
              <div style="font-size:12px;color:#999">平均精度</div>
              <div style="font-size:24px;font-weight:700;color:#e6a23c">{{ (statistics.average_scores?.context_precision || 0).toFixed(2) }}</div>
            </el-col>
            <el-col :span="4">
              <div style="font-size:12px;color:#999">平均召回</div>
              <div style="font-size:24px;font-weight:700;color:#e6a23c">{{ (statistics.average_scores?.context_recall || 0).toFixed(2) }}</div>
            </el-col>
            <el-col :span="4">
              <div style="font-size:12px;color:#999">平均得分</div>
              <div style="font-size:24px;font-weight:700;color:#f56c6c">{{ (statistics.average_scores?.average || 0).toFixed(2) }}</div>
            </el-col>
          </el-row>
        </el-card>
      </el-col>
    </el-row>

    <!-- RAGAS 指标卡片 -->
    <el-row :gutter="12" v-if="ragasMetrics" style="margin-bottom:16px">
      <el-col :span="24" style="margin-bottom:12px">
        <div style="font-size:14px;font-weight:600;color:#333;margin-bottom:8px">🎯 RAGAS 评估指标</div>
      </el-col>
      <el-col :span="4" v-for="(value, key) in ragasMetrics" :key="key">
        <el-card shadow="never" style="text-align:center;padding:8px 0;transition: all 0.3s;" :class="{ 'is-warning': value < 0.6, 'is-danger': value < 0.4 }">
          <div :style="{fontSize:'24px',fontWeight:'700',color: getScoreColor(value)}">{{ (value * 100).toFixed(1) }}%</div>
          <div style="font-size:12px;color:#999;margin-top:4px">{{ ragasMetricLabel(key) }}</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 检索指标卡片 -->
    <el-row :gutter="12" v-if="metrics" style="margin-bottom:16px">
      <el-col :span="24">
        <el-card shadow="never">
          <template #header>
            <span>🔍 检索指标</span>
            <span style="font-size:13px;color:#666;margin-left:16px">基于 {{ metrics.dataset_size || 0 }} 个测试用例</span>
          </template>
          <el-row :gutter="12">
            <el-col :span="6">
              <div style="text-align:center;padding:8px 0">
                <div style="font-size:24px;font-weight:700;color:#409eff">{{ metrics.retrieval.mean_average_similarity.toFixed(4) }}</div>
                <div style="font-size:12px;color:#999;margin-top:4px">平均相似度</div>
              </div>
            </el-col>
            <el-col :span="6">
              <div style="text-align:center;padding:8px 0">
                <div style="font-size:24px;font-weight:700;color:#67c23a">{{ (metrics.retrieval.mean_recall_at_k * 100).toFixed(1) }}%</div>
                <div style="font-size:12px;color:#999;margin-top:4px">召回率@k</div>
              </div>
            </el-col>
            <el-col :span="6">
              <div style="text-align:center;padding:8px 0">
                <div style="font-size:24px;font-weight:700;color:#e6a23c">{{ (metrics.retrieval.mean_hit_at_k * 100).toFixed(1) }}%</div>
                <div style="font-size:12px;color:#999;margin-top:4px">命中率@k</div>
              </div>
            </el-col>
            <el-col :span="6">
              <div style="text-align:center;padding:8px 0">
                <div style="font-size:24px;font-weight:700;color:#f56c6c">{{ metrics.retrieval.mean_mrr.toFixed(4) }}</div>
                <div style="font-size:12px;color:#999;margin-top:4px">MRR</div>
              </div>
            </el-col>
          </el-row>
          
          <!-- 生成指标 -->
          <div style="margin-top:16px;padding-top:16px;border-top:1px solid #eee">
            <div style="font-size:14px;font-weight:600;color:#333;margin-bottom:8px">✨ 生成指标</div>
            <el-row :gutter="12">
              <el-col :span="6" v-for="(value, key) in generationMetrics" :key="key">
                <div style="text-align:center;padding:8px 0">
                  <div style="font-size:20px;font-weight:600;color:#909399">{{ value.toFixed(4) }}</div>
                  <div style="font-size:12px;color:#999;margin-top:4px">{{ generationMetricLabel(key) }}</div>
                </div>
              </el-col>
            </el-row>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 回归测试结果 -->
    <el-card v-if="regressionResult" shadow="never" style="margin-bottom:16px">
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <span>📈 回归测试报告</span>
          <span :style="{fontSize:'13px',color: regressionPassRate >= 80 ? '#67c23a' : regressionPassRate >= 60 ? '#e6a23c' : '#f56c6c', marginLeft: '16px'}">
            通过率: {{ regressionPassRate.toFixed(1) }}%
          </span>
        </div>
      </template>
      <el-row :gutter="12">
        <el-col :span="6">
          <div style="font-size:12px;color:#999">测试用例数</div>
          <div style="font-size:24px;font-weight:600">{{ regressionResult.total_cases }}</div>
        </el-col>
        <el-col :span="6">
          <div style="font-size:12px;color:#999">通过数</div>
          <div style="font-size:24px;font-weight:600;color:#67c23a">{{ regressionResult.passed_cases }}</div>
        </el-col>
        <el-col :span="6">
          <div style="font-size:12px;color:#999">失败数</div>
          <div style="font-size:24px;font-weight:600;color:#f56c6c">{{ regressionResult.failed_cases }}</div>
        </el-col>
        <el-col :span="6">
          <div style="font-size:12px;color:#999">耗时</div>
          <div style="font-size:24px;font-weight:600">{{ regressionResult.duration_ms }}ms</div>
        </el-col>
      </el-row>
      
      <div v-if="regressionResult.regressions?.length || regressionResult.improvements?.length" style="margin-top:16px">
        <div v-if="regressionResult.regressions?.length" style="margin-bottom:12px">
          <div style="font-size:13px;font-weight:600;color:#f56c6c;margin-bottom:8px">⚠️ 性能退化</div>
          <el-tag v-for="(r, i) in regressionResult.regressions" :key="i" type="danger" style="margin-right:8px">{{ r }}</el-tag>
        </div>
        <div v-if="regressionResult.improvements?.length">
          <div style="font-size:13px;font-weight:600;color:#67c23a;margin-bottom:8px">✅ 性能提升</div>
          <el-tag v-for="(i, idx) in regressionResult.improvements" :key="idx" type="success" style="margin-right:8px">{{ i }}</el-tag>
        </div>
      </div>
    </el-card>

    <!-- 数据集列表 -->
    <el-card v-if="dataset.length" shadow="never" style="margin-bottom:16px">
      <template #header>
        <span>📋 评估数据集</span>
        <span style="font-size:13px;color:#666;margin-left:16px">{{ dataset.length }} 个测试用例</span>
      </template>
      <el-table :data="dataset" stripe border :loading="loadingDataset">
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="question" label="问题" min-width="300" />
        <el-table-column prop="category" label="类别" width="120" />
        <el-table-column prop="difficulty" label="难度" width="100">
          <template #default="{ row }">
            <el-tag :type="difficultyType(row.difficulty)" size="small">{{ difficultyLabel(row.difficulty) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="expected_answer" label="期望回答" min-width="200" />
        <el-table-column label="操作" width="120">
          <template #default="{ row }">
            <el-button size="small" :loading="evaluatingSingle === row.id" @click="evaluateSingle(row)">评估</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 单个评估结果 -->
    <el-card v-if="singleResult" shadow="never" style="margin-top:16px">
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <span>📝 评估结果详情</span>
          <el-button size="small" @click="singleResult = null">关闭</el-button>
        </div>
      </template>
      
      <div v-if="singleResult.error" style="margin-bottom:16px;padding:12px;background:#fef0f0;border-radius:4px">
        <div style="color:#f56c6c;font-weight:600">❌ 评估失败</div>
        <div style="color:#999;margin-top:4px">{{ singleResult.error }}</div>
      </div>

      <template v-else>
        <div style="margin-bottom:16px">
          <div style="font-weight:600;margin-bottom:4px">问题：</div>
          <div style="color:#666;padding:8px;background:#f9f9f9;border-radius:4px">{{ singleResult.question }}</div>
        </div>
        <div style="margin-bottom:16px">
          <div style="font-weight:600;margin-bottom:4px">期望回答：</div>
          <div style="color:#666;padding:8px;background:#f9f9f9;border-radius:4px">{{ singleResult.expected_answer }}</div>
        </div>
        <div v-if="singleResult.actual_answer" style="margin-bottom:16px">
          <div style="font-weight:600;margin-bottom:4px">实际回答：</div>
          <div style="color:#409eff;padding:8px;background:#f0f5ff;border-radius:4px">{{ singleResult.actual_answer }}</div>
        </div>
        
        <div v-if="singleResult.retrieval_metrics" style="margin-bottom:16px">
          <div style="font-weight:600;margin-bottom:8px">🔍 检索指标：</div>
          <el-row :gutter="12">
            <el-col :span="6" v-for="(value, key) in singleResult.retrieval_metrics" :key="key">
              <div style="font-size:12px;color:#999">{{ metricLabel(key) }}</div>
              <div style="font-size:16px;font-weight:600">{{ formatMetric(key, value) }}</div>
            </el-col>
          </el-row>
        </div>
        
        <div v-if="Object.keys(singleResult.generation_metrics || {}).length" style="margin-bottom:16px">
          <div style="font-weight:600;margin-bottom:8px">✨ 生成指标：</div>
          <el-row :gutter="12">
            <el-col :span="6" v-for="(value, key) in singleResult.generation_metrics" :key="key">
              <div style="font-size:12px;color:#999">{{ generationMetricLabel(key) }}</div>
              <div style="font-size:16px;font-weight:600">{{ formatMetric(key, value) }}</div>
            </el-col>
          </el-row>
        </div>
        
        <div v-if="singleResult.retrieval_results?.length" style="margin-bottom:16px">
          <div style="font-weight:600;margin-bottom:8px">📄 检索结果：</div>
          <el-collapse v-model="expandedChunks">
            <el-collapse-item v-for="(r, i) in singleResult.retrieval_results" :key="i" :title="`#${i + 1} - 相似度: ${(r.similarity * 100).toFixed(1)}%`">
              <div style="font-size:13px;color:#666">{{ r.chunk_text }}</div>
            </el-collapse-item>
          </el-collapse>
        </div>
      </template>
    </el-card>

    <!-- 空状态 -->
    <el-empty v-if="!dataset.length && !metrics && !ragasMetrics && !regressionResult && !singleResult && !evaluating" description="暂无数据，请先加载数据集或运行评估" />

    <!-- 加载遮罩 -->
    <el-loading v-if="evaluating || runningRegression || establishingBaseline" text="正在处理..." />
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { RefreshCw, FolderOpen, TrendingUp, Target, BarChart3 } from '@element-plus/icons-vue'

const dataset = ref([])
const metrics = ref(null)
const ragasMetrics = ref(null)
const singleResult = ref(null)
const regressionResult = ref(null)
const statistics = ref(null)
const evaluating = ref(false)
const runningRegression = ref(false)
const establishingBaseline = ref(false)
const loadingDataset = ref(false)
const loadingStatistics = ref(false)
const evaluatingSingle = ref(null)
const expandedChunks = ref([])

const difficultyType = (d) => ({ easy: 'success', medium: 'warning', hard: 'danger' }[d] || '')
const difficultyLabel = (d) => ({ easy: '简单', medium: '中等', hard: '困难' }[d] || d)

const regressionPassRate = computed(() => {
  if (!regressionResult.value) return 0
  const { passed_cases, total_cases } = regressionResult.value
  return total_cases > 0 ? (passed_cases / total_cases) * 100 : 0
})

const generationMetrics = computed(() => {
  if (!metrics.value?.generation) return {}
  return {
    answer_similarity: metrics.value.generation.mean_answer_similarity || 0,
    context_relevance: metrics.value.generation.mean_context_relevance || 0,
  }
})

const statusText = computed(() => {
  if (evaluating.value) return '评估中'
  if (runningRegression.value) return '回归测试中'
  if (establishingBaseline.value) return '建立基准中'
  return '就绪'
})

const statusType = computed(() => {
  if (evaluating.value || runningRegression.value || establishingBaseline.value) return 'warning'
  return 'success'
})

const getScoreColor = (score) => {
  if (!score) return '#909399'
  if (score >= 0.8) return '#67c23a'
  if (score >= 0.6) return '#e6a23c'
  return '#f56c6c'
}

const metricLabel = (key) => ({
  mean_average_similarity: '平均相似度',
  max_similarity: '最大相似度',
  min_similarity: '最小相似度',
  recall_at_k: 'Recall@k',
  precision_at_k: 'Precision@k',
  mrr: 'MRR',
  hits: '命中数',
  result_count: '结果数',
}[key] || key)

const generationMetricLabel = (key) => ({
  answer_similarity: '答案相似度',
  context_relevance: '上下文相关性',
  max_context_similarity: '最大上下文相似度',
  avg_context_similarity: '平均上下文相似度',
  answer_length: '回答长度',
}[key] || key)

const ragasMetricLabel = (key) => ({
  faithfulness: '忠实度',
  answer_relevancy: '答案相关性',
  context_precision: '上下文精度',
  context_recall: '上下文召回',
  answer_similarity: '答案相似度',
  answer_correctness: '答案正确性',
}[key] || key)

const formatMetric = (key, value) => {
  if (key.includes('similarity') || key === 'mrr' || key.includes('recall') || key.includes('precision')) {
    return value.toFixed(4)
  }
  return value
}

async function loadDataset() {
  loadingDataset.value = true
  try {
    const res = await fetch('/api/v1/evaluation/dataset')
    const data = await res.json()
    if (data.code === 200) {
      dataset.value = data.data
      ElMessage.success(`成功加载 ${data.data.length} 个测试用例`)
    } else {
      ElMessage.warning(data.message || '加载数据集失败')
    }
  } catch (e) {
    ElMessage.error('加载数据集失败：网络错误')
    console.error('Load dataset error:', e)
  } finally {
    loadingDataset.value = false
  }
}

async function evaluateAll() {
  evaluating.value = true
  try {
    const res = await fetch('/api/v1/evaluation/evaluate-all', { method: 'POST' })
    const data = await res.json()
    if (data.code === 200) {
      metrics.value = data.data.overall_metrics
      if (data.data.ragas_metrics) {
        ragasMetrics.value = data.data.ragas_metrics
      }
      ElMessage.success('评估完成')
    } else {
      ElMessage.warning(data.message || '评估失败')
    }
  } catch (e) {
    ElMessage.error('评估失败：网络错误')
    console.error('Evaluate all error:', e)
  } finally {
    evaluating.value = false
  }
}

async function evaluateSingle(item) {
  evaluatingSingle.value = item.id
  try {
    const res = await fetch(`/api/v1/evaluation/evaluate/${item.id}`, { method: 'POST' })
    const data = await res.json()
    if (data.code === 200) {
      singleResult.value = data.data
    } else {
      singleResult.value = { error: data.message || '评估失败' }
    }
  } catch (e) {
    singleResult.value = { error: '评估失败：网络错误' }
    console.error('Evaluate single error:', e)
  } finally {
    evaluatingSingle.value = null
  }
}

async function runRegression() {
  runningRegression.value = true
  try {
    const res = await fetch('/api/v1/evaluation/regression', { method: 'POST' })
    const data = await res.json()
    if (data.code === 200) {
      regressionResult.value = data.data
      ElMessage.success('回归测试完成')
    } else {
      ElMessage.warning(data.message || '回归测试失败')
    }
  } catch (e) {
    ElMessage.error('回归测试失败：网络错误')
    console.error('Run regression error:', e)
  } finally {
    runningRegression.value = false
  }
}

async function establishBaseline() {
  establishingBaseline.value = true
  try {
    const res = await fetch('/api/v1/evaluation/baseline', { method: 'POST' })
    const data = await res.json()
    if (data.code === 200) {
      regressionResult.value = data.data.report
      ElMessage.success('基准已建立')
    } else {
      ElMessage.warning(data.message || '建立基准失败')
    }
  } catch (e) {
    ElMessage.error('建立基准失败：网络错误')
    console.error('Establish baseline error:', e)
  } finally {
    establishingBaseline.value = false
  }
}

async function loadStatistics() {
  loadingStatistics.value = true
  try {
    const res = await fetch('/api/v1/evaluation/statistics')
    const data = await res.json()
    if (data.code === 200) {
      statistics.value = data.data
    } else {
      ElMessage.warning(data.message || '获取统计失败')
    }
  } catch (e) {
    ElMessage.error('获取统计失败：网络错误')
    console.error('Load statistics error:', e)
  } finally {
    loadingStatistics.value = false
  }
}

async function refreshStatistics() {
  await loadStatistics()
  ElMessage.success('统计已刷新')
}

async function clearResults() {
  try {
    await ElMessageBox.confirm('确定要清除所有评估结果吗？', '确认清除', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })
    metrics.value = null
    ragasMetrics.value = null
    singleResult.value = null
    regressionResult.value = null
    statistics.value = null
    ElMessage.success('已清除所有结果')
  } catch {
    // 用户取消
  }
}

// 页面加载时自动加载数据集和统计
loadDataset()
loadStatistics()
</script>

<style scoped>
.el-card.is-warning {
  border-left: 4px solid #e6a23c;
}
.el-card.is-danger {
  border-left: 4px solid #f56c6c;
}
</style>
