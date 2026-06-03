<template>
  <div class="vector-search-test">
    <h2 class="mb-4">向量检索测试</h2>
    
    <!-- 服务状态 -->
    <div class="mb-6">
      <el-button @click="checkStatus" type="primary" class="mb-3">检查服务状态</el-button>
      <el-card v-if="statusInfo" class="mb-4">
        <div class="status-info">
          <div class="status-item">
            <span class="label">服务状态：</span>
            <span :class="['value', statusInfo.status === 'online' ? 'success' : 'error']">
              {{ statusInfo.status === 'online' ? '✓ 在线' : '✗ 离线' }}
            </span>
          </div>
          <div class="status-item">
            <span class="label">检索模式：</span>
            <span :class="['value', statusInfo.mode === 'pgvector' ? 'success' : 'warning']">
              {{ statusInfo.mode === 'pgvector' ? 'pgvector' : '轻量模式' }}
            </span>
          </div>
          <div class="status-item">
            <span class="label">pgvector可用：</span>
            <span :class="['value', statusInfo.pgvector_available ? 'success' : 'warning']">
              {{ statusInfo.pgvector_available ? '✓ 支持' : '✗ 不支持' }}
            </span>
          </div>
        </div>
      </el-card>
    </div>

    <!-- 向量检索 -->
    <el-card class="mb-6">
      <template #header>
        <span>向量检索</span>
      </template>
      <div class="form-item">
        <el-input
          v-model="searchQuery"
          type="textarea"
          :rows="3"
          placeholder="请输入查询文本..."
          class="mb-3"
        />
        <div class="form-row mb-3">
          <el-input-number v-model="topK" :min="1" :max="20" label="返回数量" />
          <el-input-number v-model="similarityThreshold" :min="0" :max="1" :step="0.1" label="相似度阈值" />
          <el-button @click="searchAction" type="primary">检索</el-button>
        </div>
      </div>
      
      <div v-if="searchResults.length > 0" class="results-section">
        <h4 class="result-title">检索结果 ({{ searchResults.length }})</h4>
        <div class="result-list">
          <div v-for="(result, index) in searchResults" :key="result.chunk_id" class="result-item">
            <div class="result-header">
              <span class="result-index">#{{ index + 1 }}</span>
              <span class="similarity" :class="getSimilarityClass(result.similarity)">
                相似度: {{ (result.similarity * 100).toFixed(1) }}%
              </span>
              <span v-if="result.document_id" class="doc-id">文档ID: {{ result.document_id }}</span>
            </div>
            <div class="result-content">{{ result.chunk_text }}</div>
          </div>
        </div>
      </div>
      
      <div v-else-if="searched && searchResults.length === 0" class="no-results">
        <el-empty description="未找到相关结果" />
      </div>
    </el-card>

    <!-- 查看文档向量块 -->
    <el-card>
      <template #header>
        <span>查看文档向量块</span>
      </template>
      <div class="form-item">
        <el-input
          v-model="documentId"
          type="number"
          placeholder="请输入文档ID..."
          class="mb-3"
          style="width: 200px"
        />
        <el-button @click="getChunksAction" type="primary">查询</el-button>
      </div>
      
      <div v-if="documentChunks.length > 0">
        <h4 class="result-title">文档 {{ documentId }} 的向量块 ({{ documentChunks.length }})</h4>
        <el-table :data="documentChunks" border stripe>
          <el-table-column prop="chunk_index" label="块序号" width="80" />
          <el-table-column prop="chunk_text" label="文本内容" />
          <el-table-column prop="department" label="部门" width="100" />
        </el-table>
      </div>
      
      <div v-else-if="chunksSearched && documentChunks.length === 0" class="no-results">
        <el-empty description="未找到文档或该文档没有向量块" />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue';
import { vectorSearchApi } from '@/api/vectorSearch';
import { config } from '@/config';

const statusInfo = ref(null);
const searchQuery = ref('');
const topK = ref(config.search.defaultTopK);
const similarityThreshold = ref(config.search.similarityThreshold);
const searchResults = ref([]);
const searched = ref(false);
const documentId = ref('');
const documentChunks = ref([]);
const chunksSearched = ref(false);

const checkStatus = async () => {
  try {
    const res = await vectorSearchApi.getStatus();
    statusInfo.value = res.data;
  } catch (error) {
    statusInfo.value = { status: 'error', message: error.message };
  }
};

const searchAction = async () => {
  if (!searchQuery.value.trim()) {
    return;
  }
  
  searched.value = false;
  searchResults.value = [];
  
  try {
    const res = await vectorSearchApi.search({
      content: searchQuery.value,
      top_k: topK.value,
      similarity_threshold: similarityThreshold.value,
    });
    searchResults.value = res.data.results || [];
    searched.value = true;
  } catch (error) {
    console.error('检索失败:', error);
  }
};

const getChunksAction = async () => {
  if (!documentId.value) {
    return;
  }
  
  chunksSearched.value = false;
  documentChunks.value = [];
  
  try {
    const res = await vectorSearchApi.getChunks(documentId.value);
    documentChunks.value = res.data.chunks || [];
    chunksSearched.value = true;
  } catch (error) {
    console.error('获取向量块失败:', error);
  }
};

const getSimilarityClass = (score) => {
  if (score >= 0.8) return 'high';
  if (score >= 0.5) return 'medium';
  return 'low';
};
</script>

<style scoped>
.vector-search-test {
  padding: 20px;
}

.status-info {
  display: flex;
  flex-wrap: wrap;
  gap: 20px;
}

.status-item {
  display: flex;
  align-items: center;
}

.status-item .label {
  font-weight: bold;
  margin-right: 8px;
}

.status-item .value {
  padding: 4px 12px;
  border-radius: 4px;
  background: #f5f5f5;
}

.status-item .value.success {
  background: #e8f5e9;
  color: #2e7d32;
}

.status-item .value.error {
  background: #ffebee;
  color: #c62828;
}

.status-item .value.warning {
  background: #fff3e0;
  color: #e65100;
}

.form-item {
  margin-bottom: 16px;
}

.form-row {
  display: flex;
  gap: 16px;
  align-items: center;
}

.results-section {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid #eee;
}

.result-title {
  font-size: 14px;
  font-weight: bold;
  margin-bottom: 12px;
}

.result-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.result-item {
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  padding: 12px;
  background: #fafafa;
}

.result-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}

.result-index {
  font-weight: bold;
  color: #1976d2;
}

.similarity {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
}

.similarity.high {
  background: #e8f5e9;
  color: #2e7d32;
}

.similarity.medium {
  background: #fff3e0;
  color: #e65100;
}

.similarity.low {
  background: #ffebee;
  color: #c62828;
}

.doc-id {
  font-size: 12px;
  color: #666;
}

.result-content {
  color: #333;
  line-height: 1.6;
}

.no-results {
  margin-top: 16px;
}
</style>
