<template>
  <div class="config-page">
    <div class="page-header">
      <h1>配置管理中心</h1>
      <p class="subtitle">统一管理系统配置，支持动态加载和热更新</p>
    </div>

    <div class="config-controls">
      <select v-model="selectedCategory" class="category-select">
        <option value="">全部分类</option>
        <option v-for="cat in categories" :key="cat" :value="cat">{{ getCategoryLabel(cat) }}</option>
      </select>
      <button @click="loadConfigs" class="btn btn-secondary">
        刷新配置
      </button>
      <button @click="reloadConfigs" class="btn btn-outline">
        重新加载
      </button>
    </div>

    <div class="stats-row">
      <div class="stat-card">
        <div class="stat-value">{{ configs.length }}</div>
        <div class="stat-label">配置项总数</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ envCount }}</div>
        <div class="stat-label">环境变量覆盖</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ dbCount }}</div>
        <div class="stat-label">数据库配置</div>
      </div>
    </div>

    <div class="config-grid">
      <div 
        v-for="config in filteredConfigs" 
        :key="config.key" 
        class="config-card"
      >
        <div class="config-header">
          <div class="config-key">{{ config.key }}</div>
          <span :class="['source-badge', config.source]">{{ getSourceLabel(config.source) }}</span>
        </div>
        <div class="config-description">{{ config.description }}</div>
        <div class="config-value-section">
          <div class="value-label">当前值:</div>
          <div v-if="isSensitive(config.key)" class="config-value sensitive">
            {{ maskValue(config.value) }}
          </div>
          <div v-else class="config-value">
            {{ formatValue(config.value) }}
          </div>
        </div>
        <div class="config-meta">
          <span class="meta-item">{{ config.data_type }}</span>
          <span class="meta-item" v-if="config.required">必填</span>
          <span class="meta-item" v-if="config.min_value !== null">min: {{ config.min_value }}</span>
          <span class="meta-item" v-if="config.max_value !== null">max: {{ config.max_value }}</span>
        </div>
        <div class="config-actions">
          <button 
            @click="editConfig(config)" 
            class="btn btn-sm btn-primary"
            :disabled="isSensitive(config.key)"
          >
            编辑
          </button>
        </div>
      </div>
    </div>

    <div v-if="editingConfig" class="modal-overlay" @click.self="cancelEdit">
      <div class="modal-content">
        <div class="modal-header">
          <h3>编辑配置: {{ editingConfig.key }}</h3>
          <button @click="cancelEdit" class="close-btn">&times;</button>
        </div>
        <div class="modal-body">
          <div class="form-group">
            <label>当前值:</label>
            <div class="current-value">{{ editingConfig.value }}</div>
          </div>
          <div class="form-group">
            <label>新值:</label>
            <input 
              v-model="newValue" 
              type="text" 
              class="form-input"
              :placeholder="`输入新的${editingConfig.data_type}值`"
            />
          </div>
          <div class="form-group">
            <label>数据类型:</label>
            <span class="type-badge">{{ editingConfig.data_type }}</span>
          </div>
          <div v-if="editingConfig.enum_values" class="form-group">
            <label>可选值:</label>
            <div class="enum-options">
              <span 
                v-for="opt in editingConfig.enum_values" 
                :key="opt" 
                class="enum-option"
                @click="selectEnumValue(opt)"
              >
                {{ opt }}
              </span>
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button @click="cancelEdit" class="btn btn-secondary">取消</button>
          <button @click="saveConfig" class="btn btn-primary">保存</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import request from '../api/request'

const configs = ref([])
const categories = ref([])
const selectedCategory = ref('')
const editingConfig = ref(null)
const newValue = ref('')

const filteredConfigs = computed(() => {
  if (!selectedCategory.value) {
    return configs.value
  }
  return configs.value.filter(c => c.category === selectedCategory.value)
})

const envCount = computed(() => {
  return configs.value.filter(c => c.source === 'env').length
})

const dbCount = computed(() => {
  return configs.value.filter(c => c.source === 'database').length
})

const categoryLabels = {
  app: '应用配置',
  database: '数据库配置',
  cors: '跨域配置',
  upload: '上传配置',
  processing: '处理配置',
  log: '日志配置',
  cache: '缓存配置',
  embedding: '向量化配置',
  llm: 'LLM配置',
  rag: 'RAG配置',
  agent: 'Agent配置'
}

const sourceLabels = {
  env: '环境变量',
  database: '数据库',
  file: '配置文件',
  default: '默认值'
}

function getCategoryLabel(cat) {
  return categoryLabels[cat] || cat
}

function getSourceLabel(source) {
  return sourceLabels[source] || source
}

function isSensitive(key) {
  return key.toLowerCase().includes('key') || key.toLowerCase().includes('secret')
}

function maskValue(value) {
  if (typeof value === 'string' && value.length > 8) {
    return value.slice(0, 4) + '****' + value.slice(-4)
  }
  return '***'
}

function formatValue(value) {
  if (typeof value === 'boolean') {
    return value ? 'true' : 'false'
  }
  if (typeof value === 'object') {
    return JSON.stringify(value)
  }
  return String(value)
}

async function loadConfigs() {
  try {
    const response = await request.get('/api/v1/config/all')
    configs.value = response.data.configs
  } catch (error) {
    console.error('加载配置失败:', error)
  }
}

async function loadCategories() {
  try {
    const response = await request.get('/api/v1/config/categories')
    categories.value = response.data.categories
  } catch (error) {
    console.error('加载分类失败:', error)
  }
}

async function reloadConfigs() {
  try {
    await request.post('/api/v1/config/reload')
    await loadConfigs()
    alert('配置已重新加载')
  } catch (error) {
    console.error('重新加载配置失败:', error)
  }
}

function editConfig(config) {
  editingConfig.value = config
  newValue.value = String(config.value)
}

function cancelEdit() {
  editingConfig.value = null
  newValue.value = ''
}

function selectEnumValue(value) {
  newValue.value = String(value)
}

async function saveConfig() {
  if (!editingConfig.value) return
  
  try {
    const key = editingConfig.value.key
    const dataType = editingConfig.value.data_type
    
    let parsedValue = newValue.value
    if (dataType === 'int') {
      parsedValue = parseInt(newValue.value)
    } else if (dataType === 'float') {
      parsedValue = parseFloat(newValue.value)
    } else if (dataType === 'bool') {
      parsedValue = newValue.value.toLowerCase() === 'true' || newValue.value === '1'
    }
    
    await request.post(`/api/v1/config/${key}`, parsedValue)
    await loadConfigs()
    cancelEdit()
    alert('配置更新成功')
  } catch (error) {
    console.error('保存配置失败:', error)
    alert('保存失败: ' + (error.response?.data?.detail || error.message))
  }
}

onMounted(() => {
  loadConfigs()
  loadCategories()
})
</script>

<style scoped>
.config-page {
  max-width: 1200px;
  margin: 0 auto;
  padding: 24px;
}

.page-header {
  margin-bottom: 32px;
}

.page-header h1 {
  font-size: 28px;
  font-weight: 600;
  color: #1a1a2e;
  margin: 0 0 8px 0;
}

.subtitle {
  color: #666;
  margin: 0;
}

.config-controls {
  display: flex;
  gap: 12px;
  margin-bottom: 24px;
  align-items: center;
  flex-wrap: wrap;
}

.category-select {
  padding: 10px 16px;
  border-radius: 8px;
  border: 1px solid #ddd;
  font-size: 14px;
  min-width: 160px;
}

.btn {
  padding: 10px 20px;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  border: none;
  transition: all 0.2s;
}

.btn-sm {
  padding: 6px 12px;
  font-size: 12px;
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-primary {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
}

.btn-primary:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
}

.btn-secondary {
  background: #f0f0f0;
  color: #333;
}

.btn-secondary:hover:not(:disabled) {
  background: #e0e0e0;
}

.btn-outline {
  background: transparent;
  border: 1px solid #ddd;
  color: #666;
}

.btn-outline:hover {
  background: #f8f8f8;
}

.stats-row {
  display: flex;
  gap: 16px;
  margin-bottom: 24px;
}

.stat-card {
  flex: 1;
  background: #fff;
  padding: 20px;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  text-align: center;
}

.stat-value {
  font-size: 28px;
  font-weight: 700;
  color: #667eea;
  margin-bottom: 4px;
}

.stat-label {
  font-size: 14px;
  color: #666;
}

.config-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
  gap: 20px;
}

.config-card {
  background: #fff;
  border-radius: 12px;
  padding: 20px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}

.config-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.config-key {
  font-size: 15px;
  font-weight: 600;
  color: #1a1a2e;
}

.source-badge {
  padding: 3px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
}

.source-badge.env {
  background: #dbeafe;
  color: #1d4ed8;
}

.source-badge.database {
  background: #dcfce7;
  color: #166534;
}

.source-badge.file {
  background: #fef3c7;
  color: #b45309;
}

.source-badge.default {
  background: #f3f4f6;
  color: #6b7280;
}

.config-description {
  font-size: 13px;
  color: #666;
  margin-bottom: 12px;
}

.config-value-section {
  margin-bottom: 12px;
}

.value-label {
  font-size: 12px;
  color: #999;
  margin-bottom: 4px;
}

.config-value {
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 14px;
  color: #333;
  word-break: break-all;
  padding: 8px 12px;
  background: #f8f9fa;
  border-radius: 6px;
}

.config-value.sensitive {
  color: #ef4444;
}

.config-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}

.meta-item {
  padding: 2px 8px;
  background: #f0f0f0;
  border-radius: 4px;
  font-size: 12px;
  color: #666;
}

.config-actions {
  display: flex;
  gap: 8px;
}

.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-content {
  background: #fff;
  border-radius: 12px;
  width: 90%;
  max-width: 500px;
  overflow: hidden;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px;
  border-bottom: 1px solid #f0f0f0;
}

.modal-header h3 {
  margin: 0;
  font-size: 18px;
  color: #1a1a2e;
}

.close-btn {
  background: none;
  border: none;
  font-size: 24px;
  cursor: pointer;
  color: #999;
  padding: 0;
  line-height: 1;
}

.modal-body {
  padding: 20px;
}

.form-group {
  margin-bottom: 16px;
}

.form-group label {
  display: block;
  font-size: 14px;
  font-weight: 500;
  color: #333;
  margin-bottom: 8px;
}

.form-input {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid #ddd;
  border-radius: 8px;
  font-size: 14px;
  box-sizing: border-box;
}

.current-value {
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 14px;
  color: #666;
  padding: 8px 12px;
  background: #f8f9fa;
  border-radius: 6px;
}

.type-badge {
  padding: 4px 10px;
  background: #667eea;
  color: white;
  border-radius: 4px;
  font-size: 12px;
}

.enum-options {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.enum-option {
  padding: 4px 12px;
  background: #f0f0f0;
  border-radius: 4px;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}

.enum-option:hover {
  background: #e0e0e0;
}

.modal-footer {
  display: flex;
  gap: 12px;
  padding: 20px;
  border-top: 1px solid #f0f0f0;
  justify-content: flex-end;
}

@media (max-width: 768px) {
  .config-controls {
    flex-direction: column;
    align-items: stretch;
  }
  
  .category-select {
    width: 100%;
  }
  
  .stats-row {
    flex-direction: column;
  }
  
  .config-grid {
    grid-template-columns: 1fr;
  }
}
</style>
