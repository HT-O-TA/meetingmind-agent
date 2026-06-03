<template>
  <div>
    <el-card style="max-width:900px;margin:0 auto">
      <template #header>
        <span style="font-size:16px;font-weight:600">智能查询</span>
        <span style="font-size:13px;color:#666;margin-left:16px">基于 RAG 的 AI 问答</span>
      </template>
      <p style="color:#666;margin-bottom:16px">输入问题，AI 将从会议记录和文档库中检索相关内容并生成回答</p>

      <el-input
        v-model="query"
        type="textarea"
        :rows="3"
        placeholder="例如：上次项目会议的结论是什么？"
        style="margin-bottom:12px"
      />
      <el-button type="primary" :loading="searchLoading" @click="search">查询</el-button>
      <el-button type="info" style="margin-left:8px" @click="checkStatus">检查服务</el-button>

      <div v-if="statusInfo" style="margin-top:16px">
        <el-tag :type="statusInfo.mode === 'pgvector' ? 'success' : 'warning'">
          {{ statusInfo.mode === 'pgvector' ? 'pgvector 模式' : '轻量模式' }}
        </el-tag>
      </div>

      <!-- AI 回答区域 -->
      <div v-if="aiAnswer" style="margin-top:24px">
        <div style="font-weight:600;margin-bottom:12px">AI 回答</div>
        <el-card style="background:#e8f4ff;border:1px solid #409eff" shadow="never">
          <div style="font-size:14px;line-height:1.8">{{ aiAnswer }}</div>
        </el-card>
      </div>

      <!-- 检索结果区域 -->
      <div v-if="searchResults.length" style="margin-top:24px">
        <div style="font-weight:600;margin-bottom:12px">参考信息 ({{ searchResults.length }})</div>
        <el-card
          v-for="(r, i) in searchResults"
          :key="r.chunk_id"
          style="margin-bottom:12px;background:#f9f9f9"
          shadow="never"
        >
          <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px">
            <div>
              <el-tag size="small" :type="getSimilarityType(r.similarity)">
                相似度: {{ (r.similarity * 100).toFixed(1) }}%
              </el-tag>
              <el-tag v-if="r.document_id" size="small" style="margin-left:8px" type="info">
                文档ID: {{ r.document_id }}
              </el-tag>
              <el-tag v-if="r.meeting_id" size="small" style="margin-left:8px" type="success">
                会议ID: {{ r.meeting_id }}
              </el-tag>
              <el-tag v-if="r.department" size="small" style="margin-left:8px">
                {{ r.department }}
              </el-tag>
            </div>
            <span style="font-size:12px;color:#999">#{{ i + 1 }}</span>
          </div>
          <div style="font-size:13px;line-height:1.7">{{ r.chunk_text }}</div>
        </el-card>
      </div>

      <el-empty v-else-if="searched && !aiAnswer" description="未找到相关内容" style="margin-top:24px" />
    </el-card>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ragApi } from '@/api/rag'
import { vectorSearchApi } from '@/api/vectorSearch'
import { ElMessage } from 'element-plus'

const query = ref('')
const aiAnswer = ref('')
const searchResults = ref([])
const searchLoading = ref(false)
const searched = ref(false)
const statusInfo = ref(null)

async function checkStatus() {
  try {
    const res = await vectorSearchApi.getStatus()
    statusInfo.value = res.data
    ElMessage.success('服务状态检查完成')
  } catch (e) {
    ElMessage.error('服务状态检查失败')
  }
}

async function search() {
  if (!query.value.trim()) return ElMessage.warning('请输入查询内容')
  searchLoading.value = true
  searched.value = false
  aiAnswer.value = ''
  searchResults.value = []
  try {
    const res = await ragApi.ask({
      question: query.value,
      top_k: 10,
      use_llm: true,
    })
    const data = res.data
    aiAnswer.value = data?.answer || ''
    searchResults.value = data?.chunks || []
    searched.value = true
  } catch (e) {
    ElMessage.error('搜索失败: ' + (e.message || '未知错误'))
  } finally {
    searchLoading.value = false
  }
}

function getSimilarityType(similarity) {
  if (similarity >= 0.8) return 'success'
  if (similarity >= 0.6) return 'warning'
  return 'info'
}
</script>

<style scoped>
</style>
