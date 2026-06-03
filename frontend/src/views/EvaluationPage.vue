<template>
  <div>
    <!-- 评估按钮 -->
    <el-card shadow="never" style="margin-bottom:16px">
      <el-button type="primary" :loading="evaluating" @click="evaluateAll">评估全部数据集</el-button>
      <el-button style="margin-left:8px" @click="loadDataset">加载数据集</el-button>
    </el-card>

    <!-- 评估指标卡片 -->
    <el-row :gutter="12" v-if="metrics" style="margin-bottom:16px">
      <!-- 检索指标 -->
      <el-col :span="24" style="margin-bottom:12px">
        <div style="font-size:14px;font-weight:600;color:#333;margin-bottom:8px">🔍 检索指标</div>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never" style="text-align:center;padding:8px 0">
          <div style="font-size:24px;font-weight:700;color:#409eff">{{ metrics.retrieval.mean_average_similarity.toFixed(4) }}</div>
          <div style="font-size:12px;color:#999;margin-top:4px">平均相似度</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never" style="text-align:center;padding:8px 0">
          <div style="font-size:24px;font-weight:700;color:#67c23a">{{ (metrics.retrieval.mean_recall_at_k * 100).toFixed(1) }}%</div>
          <div style="font-size:12px;color:#999;margin-top:4px">召回率@k</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never" style="text-align:center;padding:8px 0">
          <div style="font-size:24px;font-weight:700;color:#e6a23c">{{ (metrics.retrieval.mean_hit_at_k * 100).toFixed(1) }}%</div>
          <div style="font-size:12px;color:#999;margin-top:4px">命中率@k</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never" style="text-align:center;padding:8px 0">
          <div style="font-size:24px;font-weight:700;color:#f56c6c">{{ metrics.retrieval.mean_mrr.toFixed(4) }}</div>
          <div style="font-size:12px;color:#999;margin-top:4px">MRR</div>
        </el-card>
      </el-col>
      
      <!-- 生成指标 -->
      <el-col :span="24" style="margin-bottom:12px;margin-top:16px">
        <div style="font-size:14px;font-weight:600;color:#333;margin-bottom:8px">✨ 生成指标</div>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never" style="text-align:center;padding:8px 0">
          <div style="font-size:24px;font-weight:700;color:#909399">{{ (metrics.generation?.mean_answer_similarity || 0).toFixed(4) }}</div>
          <div style="font-size:12px;color:#999;margin-top:4px">答案相似度</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never" style="text-align:center;padding:8px 0">
          <div style="font-size:24px;font-weight:700;color:#909399">{{ (metrics.generation?.mean_context_relevance || 0).toFixed(4) }}</div>
          <div style="font-size:12px;color:#999;margin-top:4px">上下文相关性</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 数据集列表 -->
    <el-card v-if="dataset.length" shadow="never">
      <template #header>
        <span>评估数据集</span>
        <span style="font-size:13px;color:#666;margin-left:16px">{{ dataset.length }} 个测试用例</span>
      </template>
      <el-table :data="dataset" stripe border>
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="question" label="问题" min-width="300" />
        <el-table-column prop="category" label="类别" width="120" />
        <el-table-column prop="difficulty" label="难度" width="80">
          <template #default="{ row }">
            <el-tag :type="difficultyType(row.difficulty)" size="small">{{ difficultyLabel(row.difficulty) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100">
          <template #default="{ row }">
            <el-button size="small" @click="evaluateSingle(row)">评估</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 单个评估结果 -->
    <el-card v-if="singleResult" shadow="never" style="margin-top:16px">
      <template #header>
        <span>评估结果详情</span>
      </template>
      <div style="margin-bottom:16px">
        <div style="font-weight:600;margin-bottom:4px">问题：</div>
        <div style="color:#666">{{ singleResult.question }}</div>
      </div>
      <div style="margin-bottom:16px">
        <div style="font-weight:600;margin-bottom:4px">期望回答：</div>
        <div style="color:#666">{{ singleResult.expected_answer }}</div>
      </div>
      <div v-if="singleResult.actual_answer" style="margin-bottom:16px">
        <div style="font-weight:600;margin-bottom:4px">实际回答：</div>
        <div style="color:#409eff">{{ singleResult.actual_answer }}</div>
      </div>
      <div style="margin-bottom:16px">
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
        <div style="font-weight:600;margin-bottom:8px">检索结果：</div>
        <el-card
          v-for="(r, i) in singleResult.retrieval_results"
          :key="i"
          style="margin-bottom:8px;background:#f9f9f9"
          shadow="never"
        >
          <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:4px">
            <span>相似度: {{ (r.similarity * 100).toFixed(1) }}%</span>
            <span style="font-size:12px;color:#999">#{{ i + 1 }}</span>
          </div>
          <div style="font-size:13px;color:#666">{{ r.chunk_text?.slice(0, 200) }}{{ r.chunk_text?.length > 200 ? '...' : '' }}</div>
        </el-card>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'

const dataset = ref([])
const metrics = ref(null)
const singleResult = ref(null)
const evaluating = ref(false)

const difficultyType = (d) => ({ easy: 'success', medium: 'warning', hard: 'danger' }[d] || '')
const difficultyLabel = (d) => ({ easy: '简单', medium: '中等', hard: '困难' }[d] || d)

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

const formatMetric = (key, value) => {
  if (key.includes('similarity') || key === 'mrr' || key.includes('recall') || key.includes('precision')) {
    return value.toFixed(4)
  }
  return value
}

async function loadDataset() {
  try {
    const res = await fetch('/api/v1/evaluation/dataset')
    const data = await res.json()
    if (data.code === 200) {
      dataset.value = data.data
    }
  } catch (e) {
    ElMessage.error('加载数据集失败')
  }
}

async function evaluateAll() {
  evaluating.value = true
  try {
    const res = await fetch('/api/v1/evaluation/evaluate-all', { method: 'POST' })
    const data = await res.json()
    if (data.code === 200) {
      metrics.value = data.data.overall_metrics
      ElMessage.success('评估完成')
    }
  } catch (e) {
    ElMessage.error('评估失败')
  } finally {
    evaluating.value = false
  }
}

async function evaluateSingle(item) {
  try {
    const res = await fetch(`/api/v1/evaluation/evaluate/${item.id}`, { method: 'POST' })
    const data = await res.json()
    if (data.code === 200) {
      singleResult.value = data.data
    }
  } catch (e) {
    ElMessage.error('评估失败')
  }
}

loadDataset()
</script>
