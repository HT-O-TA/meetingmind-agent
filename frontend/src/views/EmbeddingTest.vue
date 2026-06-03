<template>
  <div class="embedding-test">
    <h2 class="mb-4">向量化服务测试</h2>
    
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
          <div class="status-item" v-if="statusInfo.model">
            <span class="label">模型：</span>
            <span class="value">{{ statusInfo.model }}</span>
          </div>
          <div class="status-item" v-if="statusInfo.dimension">
            <span class="label">向量维度：</span>
            <span class="value">{{ statusInfo.dimension }}</span>
          </div>
        </div>
      </el-card>
    </div>

    <!-- 单文本向量化 -->
    <el-card class="mb-6">
      <template #header>
        <span>单文本向量化</span>
      </template>
      <div class="form-item">
        <el-input
          v-model="encodeText"
          type="textarea"
          :rows="3"
          placeholder="请输入要向量化的文本..."
          class="mb-3"
        />
        <el-button @click="encodeTextAction" type="primary">生成向量</el-button>
      </div>
      <div v-if="encodeResult" class="result-section">
        <h4 class="result-title">向量结果</h4>
        <div class="result-content">
          <div class="result-item">
            <span class="label">向量维度：</span>
            <span class="value">{{ encodeResult.dimension }}</span>
          </div>
          <div class="result-item">
            <span class="label">向量值（前10个）：</span>
            <span class="value code">{{ formatEmbedding(encodeResult.embedding) }}</span>
          </div>
        </div>
      </div>
    </el-card>

    <!-- 相似度计算 -->
    <el-card class="mb-6">
      <template #header>
        <span>文本相似度计算</span>
      </template>
      <div class="form-item">
        <el-input
          v-model="similarityText1"
          type="textarea"
          :rows="2"
          placeholder="文本1..."
          class="mb-3"
        />
        <el-input
          v-model="similarityText2"
          type="textarea"
          :rows="2"
          placeholder="文本2..."
          class="mb-3"
        />
        <el-button @click="calculateSimilarity" type="primary">计算相似度</el-button>
      </div>
      <div v-if="similarityResult" class="result-section">
        <h4 class="result-title">相似度结果</h4>
        <div class="result-content">
          <div class="similarity-score">
            <span :class="getSimilarityClass(similarityResult.similarity)">
              {{ (similarityResult.similarity * 100).toFixed(1) }}%
            </span>
          </div>
          <div class="similarity-bar">
            <div 
              class="similarity-fill" 
              :style="{ width: (similarityResult.similarity * 100) + '%' }"
              :class="getSimilarityClass(similarityResult.similarity)"
            ></div>
          </div>
        </div>
      </div>
    </el-card>

    <!-- 批量向量化 -->
    <el-card>
      <template #header>
        <span>批量向量化</span>
      </template>
      <div class="form-item">
        <el-input
          v-model="batchTexts"
          type="textarea"
          :rows="4"
          placeholder="每行输入一个文本..."
          class="mb-3"
        />
        <el-button @click="batchEncodeAction" type="primary">批量生成向量</el-button>
      </div>
      <div v-if="batchResult" class="result-section">
        <h4 class="result-title">批量结果</h4>
        <el-table :data="batchResult.results" border>
          <el-table-column prop="text" label="文本" width="300" />
          <el-table-column prop="dimension" label="向量维度" />
          <el-table-column label="向量预览">
            <template #default="scope">
              <span class="code">{{ formatEmbedding(scope.row.embedding) }}</span>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </el-card>
  </div>
</template>

<script setup>import { ref } from 'vue';
import { embeddingApi } from '@/api/embedding';
const statusInfo = ref(null);
const encodeText = ref('');
const encodeResult = ref(null);
const similarityText1 = ref('');
const similarityText2 = ref('');
const similarityResult = ref(null);
const batchTexts = ref('');
const batchResult = ref(null);
const checkStatus = async () => {
 try {
 const res = await embeddingApi.status();
 statusInfo.value = res.data;
 }
 catch (error) {
 statusInfo.value = { status: 'error', message: error.message };
 }
};
const encodeTextAction = async () => {
 if (!encodeText.value.trim()) {
 return;
 }
 try {
 const res = await embeddingApi.encode({ content: encodeText.value });
 encodeResult.value = res.data;
 }
 catch (error) {
 console.error('向量化失败:', error);
 }
};
const calculateSimilarity = async () => {
 if (!similarityText1.value.trim() || !similarityText2.value.trim()) {
 return;
 }
 try {
 const res = await embeddingApi.similarity({
 text1: similarityText1.value,
 text2: similarityText2.value
 });
 similarityResult.value = res.data;
 }
 catch (error) {
 console.error('计算相似度失败:', error);
 }
};
const batchEncodeAction = async () => {
 if (!batchTexts.value.trim()) {
 return;
 }
 const texts = batchTexts.value.split('\n').filter(t => t.trim());
 if (texts.length === 0)
 return;
 try {
 const res = await embeddingApi.batchEncode({ texts });
 batchResult.value = res.data;
 }
 catch (error) {
 console.error('批量向量化失败:', error);
 }
};
const formatEmbedding = (embedding) => {
 if (!embedding || embedding.length === 0)
 return '[]';
 const preview = embedding.slice(0, 10).map(v => v.toFixed(4));
 return `[${preview.join(', ')}, ...]`;
};
const getSimilarityClass = (score) => {
 if (score >= 0.8)
 return 'high';
 if (score >= 0.5)
 return 'medium';
 return 'low';
};
</script>

<style scoped>
.embedding-test {
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

.form-item {
  margin-bottom: 16px;
}

.result-section {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid #eee;
}

.result-title {
  font-size: 14px;
  font-weight: bold;
  margin-bottom: 12px;
}

.result-content {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.result-item {
  display: flex;
  align-items: flex-start;
}

.result-item .label {
  font-weight: bold;
  min-width: 100px;
}

.result-item .value {
  flex: 1;
}

.result-item .code {
  font-family: monospace;
  font-size: 12px;
  color: #666;
  word-break: break-all;
}

.similarity-score {
  font-size: 36px;
  font-weight: bold;
  text-align: center;
  margin-bottom: 12px;
}

.similarity-score.high {
  color: #2e7d32;
}

.similarity-score.medium {
  color: #f57c00;
}

.similarity-score.low {
  color: #c62828;
}

.similarity-bar {
  height: 20px;
  background: #f0f0f0;
  border-radius: 10px;
  overflow: hidden;
}

.similarity-fill {
  height: 100%;
  transition: width 0.3s ease;
}

.similarity-fill.high {
  background: #4caf50;
}

.similarity-fill.medium {
  background: #ff9800;
}

.similarity-fill.low {
  background: #f44336;
}
</style>
