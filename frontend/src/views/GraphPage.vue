<template>
  <div class="graph-page">
    <div class="page-header">
      <h2>知识图谱</h2>
      <p class="description">可视化展示会议文档中的实体关系网络</p>
    </div>

    <div class="stats-row">
      <div class="stat-card" v-for="stat in statistics" :key="stat.label">
        <div class="stat-value" :class="stat.color">{{ stat.value }}</div>
        <div class="stat-label">{{ stat.label }}</div>
      </div>
    </div>

    <div class="toolbar">
      <el-input
        v-model="searchQuery"
        placeholder="搜索实体..."
        style="width: 200px;"
        @keyup.enter="searchEntity"
      >
        <template #append>
          <el-button @click="searchEntity">
            <el-icon><Search /></el-icon>
          </el-button>
        </template>
      </el-input>
      
      <el-select v-model="depth" placeholder="展开深度" style="width: 120px;">
        <el-option label="1层" :value="1" />
        <el-option label="2层" :value="2" />
        <el-option label="3层" :value="3" />
      </el-select>

      <div class="action-buttons">
        <el-button type="primary" @click="buildGraph">
          <el-icon><Refresh /></el-icon>
          构建图谱
        </el-button>
        <el-button @click="viewAll">
          <el-icon><Share /></el-icon>
          全览图谱
        </el-button>
        <el-button @click="saveGraph">
          <el-icon><Document /></el-icon>
          保存到Neo4j
        </el-button>
        <el-button @click="loadGraph">
          <el-icon><Download /></el-icon>
          从Neo4j加载
        </el-button>
        <el-button type="danger" @click="clearGraph">
          <el-icon><Delete /></el-icon>
          清空图谱
        </el-button>
      </div>
    </div>

    <div class="graph-wrapper">
      <GraphVisualization
        :graph-data="graphData"
        :loading="loading"
        @node-click="handleNodeClick"
      />
    </div>

    <div v-if="selectedEntity" class="entity-panel">
      <div class="panel-header">
        <h3>{{ selectedEntity.name }}</h3>
        <el-button @click="selectedEntity = null">
          <el-icon><Close /></el-icon>
        </el-button>
      </div>
      <div class="panel-content">
        <el-descriptions :column="1" border>
          <el-descriptions-item label="实体ID">{{ selectedEntity.id }}</el-descriptions-item>
          <el-descriptions-item label="类型">{{ getNodeTypeName(selectedEntity.type) }}</el-descriptions-item>
          <el-descriptions-item label="描述" v-if="selectedEntity.description">
            {{ selectedEntity.description }}
          </el-descriptions-item>
        </el-descriptions>
        <div class="related-entities">
          <h4>相关实体</h4>
          <div class="entity-tags">
            <el-tag
              v-for="(related, relation) in selectedEntity.related"
              :key="relation"
              type="info"
              @click="searchEntityByName(related)"
            >
              {{ related }} ({{ relation }})
            </el-tag>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { Search, Refresh, Document, Download, Delete, Close, Share } from '@element-plus/icons-vue'
import GraphVisualization from '@/components/GraphVisualization.vue'
import {
  getGraphStatistics,
  getEntitySubgraph,
  buildGraph as buildGraphAPI,
  saveGraph as saveGraphAPI,
  loadGraph as loadGraphAPI,
  clearGraph as clearGraphAPI
} from '@/api/graph'

const loading = ref(false)
const searchQuery = ref('')
const depth = ref(2)
const selectedEntity = ref(null)
const statistics = reactive({
  memory: { entities: 0, relations: 0 },
  neo4j: { nodes: 0, relationships: 0 }
})

const graphData = ref({
  nodes: {},
  edges: []
})

const nodeTypeNames = {
  person: '人物',
  organization: '组织',
  location: '地点',
  meeting: '会议',
  document: '文档',
  topic: '主题',
  action: '动作',
  default: '其他'
}

function getNodeTypeName(type) {
  return nodeTypeNames[type] || '其他'
}

async function loadStatistics() {
  try {
    const response = await getGraphStatistics()
    statistics.memory = response.data.memory || { entities: 0, relations: 0 }
    statistics.neo4j = response.data.neo4j || { nodes: 0, relationships: 0 }
  } catch (error) {
    console.error('Failed to load statistics:', error)
  }
}

async function searchEntity() {
  if (!searchQuery.value.trim()) return
  await searchEntityByName(searchQuery.value)
}

async function viewAll() {
  loading.value = true
  try {
    const response = await getEntitySubgraph('', depth.value)
    if (response.data) {
      graphData.value = response.data
      selectedEntity.value = null
    }
  } catch (error) {
    console.error('Failed to view all:', error)
  } finally {
    loading.value = false
  }
}

async function searchEntityByName(entityName) {
  loading.value = true
  try {
    const response = await getEntitySubgraph(entityName, depth.value)
    if (response.data) {
      graphData.value = response.data
      if (response.data.nodes[entityName]) {
        selectedEntity.value = response.data.nodes[entityName]
      }
    }
  } catch (error) {
    console.error('Failed to search entity:', error)
    if (error.response?.status === 404) {
      alert(`未找到实体: ${entityName}`)
    }
  } finally {
    loading.value = false
  }
}

async function buildGraph() {
  loading.value = true
  try {
    await buildGraphAPI()
    await loadStatistics()
    await searchEntityByName(Object.keys(graphData.value.nodes)[0] || '')
    alert('图谱构建成功')
  } catch (error) {
    console.error('Failed to build graph:', error)
    alert('图谱构建失败')
  } finally {
    loading.value = false
  }
}

async function saveGraph() {
  loading.value = true
  try {
    await saveGraphAPI()
    await loadStatistics()
    alert('图谱保存成功')
  } catch (error) {
    console.error('Failed to save graph:', error)
    alert('图谱保存失败')
  } finally {
    loading.value = false
  }
}

async function loadGraph() {
  loading.value = true
  try {
    await loadGraphAPI()
    await loadStatistics()
    alert('图谱加载成功')
  } catch (error) {
    console.error('Failed to load graph:', error)
    alert('图谱加载失败')
  } finally {
    loading.value = false
  }
}

async function clearGraph() {
  if (!confirm('确定要清空图谱吗？此操作不可撤销。')) return
  
  loading.value = true
  try {
    await clearGraphAPI()
    await loadStatistics()
    graphData.value = { nodes: {}, edges: [] }
    selectedEntity.value = null
    alert('图谱已清空')
  } catch (error) {
    console.error('Failed to clear graph:', error)
    alert('清空失败')
  } finally {
    loading.value = false
  }
}

function handleNodeClick(node) {
  selectedEntity.value = node
}
</script>

<style scoped>
.graph-page {
  padding: 20px;
  height: calc(100vh - 120px);
  display: flex;
  flex-direction: column;
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

.stat-value.text-primary {
  color: #409eff;
}

.stat-value.text-success {
  color: #67c23a;
}

.stat-label {
  font-size: 13px;
  color: #999;
}

.toolbar {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 20px;
  padding: 16px;
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.action-buttons {
  display: flex;
  gap: 8px;
  margin-left: auto;
}

.graph-wrapper {
  flex: 1;
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  overflow: hidden;
}

.entity-panel {
  position: fixed;
  bottom: 20px;
  left: 20px;
  width: 320px;
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
  overflow: hidden;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  border-bottom: 1px solid #eee;
  background: #fafafa;
}

.panel-header h3 {
  margin: 0;
  font-size: 16px;
}

.panel-content {
  padding: 16px;
  max-height: 300px;
  overflow-y: auto;
}

.related-entities {
  margin-top: 16px;
}

.related-entities h4 {
  margin: 0 0 12px;
  font-size: 14px;
  color: #666;
}

.entity-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.entity-tags .el-tag {
  cursor: pointer;
}
</style>

