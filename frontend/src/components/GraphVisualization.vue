<template>
  <div class="graph-container" ref="containerRef">
    <svg ref="svgRef" class="graph-svg" @click="handleSvgClick">
      <defs>
        <marker id="arrowhead" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
          <polygon points="0 0, 10 3.5, 0 7" fill="#909399" />
        </marker>
      </defs>
      
      <g class="edges">
        <g v-for="(edge, index) in edges" :key="'edge-' + index">
          <path
            :d="edge.path"
            fill="none"
            stroke="#909399"
            stroke-width="2"
            marker-end="url(#arrowhead)"
            class="edge-line"
          />
          <text
            :x="edge.labelX"
            :y="edge.labelY"
            class="edge-label"
            text-anchor="middle"
          >
            {{ edge.label }}
          </text>
        </g>
      </g>
      
      <g class="nodes">
        <g
          v-for="(node, id) in nodes"
          :key="'node-' + id"
          :transform="`translate(${node.x}, ${node.y})`"
          @click.stop="handleNodeClick(node)"
          class="node-group"
          :class="{ selected: selectedNode === id }"
        >
          <circle
            :r="node.radius"
            :fill="getNodeColor(node.type)"
            class="node-circle"
          />
          <text
            y="4"
            class="node-label"
            text-anchor="middle"
          >
            {{ node.label }}
          </text>
        </g>
      </g>
    </svg>
    
    <div v-if="selectedNode" class="node-detail-panel">
      <div class="panel-header">
        <span class="panel-title">{{ nodes[selectedNode]?.label }}</span>
        <el-button @click="selectedNode = null" class="close-btn">
          <el-icon><Close /></el-icon>
        </el-button>
      </div>
      <div class="panel-content">
        <div class="info-row">
          <span class="label">类型:</span>
          <span class="value">{{ getNodeTypeName(nodes[selectedNode]?.type) }}</span>
        </div>
        <div class="info-row">
          <span class="label">入度:</span>
          <span class="value">{{ nodes[selectedNode]?.inDegree || 0 }}</span>
        </div>
        <div class="info-row">
          <span class="label">出度:</span>
          <span class="value">{{ nodes[selectedNode]?.outDegree || 0 }}</span>
        </div>
        <div v-if="nodes[selectedNode]?.description" class="info-row">
          <span class="label">描述:</span>
          <span class="value">{{ nodes[selectedNode]?.description }}</span>
        </div>
      </div>
    </div>
    
    <div v-if="loading" class="loading-overlay">
      <el-loading text="加载图谱中..." />
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, nextTick } from 'vue'
import { Close } from '@element-plus/icons-vue'

const props = defineProps({
  graphData: {
    type: Object,
    default: () => ({ nodes: {}, edges: [] })
  },
  loading: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['nodeClick'])

const containerRef = ref(null)
const svgRef = ref(null)
const selectedNode = ref(null)

const nodes = ref({})
const edges = ref([])

const nodeColors = {
  person: '#409eff',
  organization: '#67c23a',
  location: '#e6a23c',
  meeting: '#f56c6c',
  document: '#909399',
  topic: '#b37feb',
  action: '#54d8a3',
  default: '#909399'
}

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

function getNodeColor(type) {
  return nodeColors[type] || nodeColors.default
}

function getNodeTypeName(type) {
  return nodeTypeNames[type] || '其他'
}

function calculateLayout() {
  const graph = props.graphData
  const container = containerRef.value
  
  if (!container || !graph.nodes) {
    nodes.value = {}
    edges.value = []
    return
  }
  
  const width = container.clientWidth - 40
  const height = container.clientHeight - 40
  const centerX = width / 2
  const centerY = height / 2
  
  const nodeList = Object.values(graph.nodes || {})
  const nodeCount = nodeList.length
  
  if (nodeCount === 0) {
    nodes.value = {}
    edges.value = []
    return
  }
  
  const radius = Math.min(width, height) * 0.35
  const newNodes = {}
  
  nodeList.forEach((node, index) => {
    const angle = (2 * Math.PI * index) / nodeCount - Math.PI / 2
    const x = centerX + radius * Math.cos(angle)
    const y = centerY + radius * Math.sin(angle)
    
    newNodes[node.id] = {
      ...node,
      x,
      y,
      radius: Math.max(30, Math.min(50, 150 / Math.sqrt(nodeCount))),
      label: node.name || node.label || node.id
    }
  })
  
  nodes.value = newNodes
  
  const newEdges = []
  (graph.edges || []).forEach((edge, index) => {
    const source = newNodes[edge.source]
    const target = newNodes[edge.target]
    
    if (!source || !target) return
    
    const dx = target.x - source.x
    const dy = target.y - source.y
    const dist = Math.sqrt(dx * dx + dy * dy)
    
    const sourceAngle = Math.atan2(dy, dx)
    const targetAngle = Math.atan2(source.y - target.y, source.x - target.x)
    
    const sourceX = source.x + source.radius * Math.cos(sourceAngle)
    const sourceY = source.y + source.radius * Math.sin(sourceAngle)
    const targetX = target.x + target.radius * Math.cos(targetAngle)
    const targetY = target.y + target.radius * Math.sin(targetAngle)
    
    const midX = (sourceX + targetX) / 2
    const midY = (sourceY + targetY) / 2
    
    const perpX = -(targetY - sourceY) * 0.1
    const perpY = (targetX - sourceX) * 0.1
    const ctrlX = midX + perpX
    const ctrlY = midY + perpY
    
    const path = `M ${sourceX} ${sourceY} Q ${ctrlX} ${ctrlY} ${targetX} ${targetY}`
    
    newEdges.push({
      ...edge,
      path,
      labelX: midX,
      labelY: midY - 10,
      label: edge.relation || ''
    })
  })
  
  edges.value = newEdges
}

function handleNodeClick(node) {
  selectedNode.value = node.id
  emit('nodeClick', node)
}

function handleSvgClick() {
  selectedNode.value = null
}

watch(() => props.graphData, () => {
  nextTick(() => {
    calculateLayout()
  })
}, { deep: true })

onMounted(() => {
  calculateLayout()
  window.addEventListener('resize', calculateLayout)
})
</script>

<style scoped>
.graph-container {
  position: relative;
  width: 100%;
  height: 100%;
  background: #fff;
  border-radius: 8px;
  overflow: hidden;
}

.graph-svg {
  width: 100%;
  height: 100%;
}

.edge-line {
  transition: stroke 0.2s;
}

.edge-line:hover {
  stroke: #409eff;
}

.edge-label {
  font-size: 12px;
  fill: #909399;
  background: rgba(255, 255, 255, 0.9);
  padding: 2px 6px;
  border-radius: 4px;
}

.node-group {
  cursor: pointer;
  transition: transform 0.2s;
}

.node-group:hover {
  transform: scale(1.1);
}

.node-group.selected .node-circle {
  stroke: #409eff;
  stroke-width: 3;
}

.node-circle {
  transition: fill 0.2s, stroke 0.2s;
}

.node-label {
  font-size: 12px;
  fill: #fff;
  font-weight: 500;
  pointer-events: none;
}

.node-detail-panel {
  position: absolute;
  top: 20px;
  right: 20px;
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1);
  padding: 16px;
  width: 280px;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid #eee;
}

.panel-title {
  font-size: 16px;
  font-weight: 600;
  color: #333;
}

.close-btn {
  padding: 0;
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.info-row {
  margin-bottom: 12px;
}

.info-row:last-child {
  margin-bottom: 0;
}

.info-row .label {
  font-size: 13px;
  color: #999;
  display: block;
  margin-bottom: 4px;
}

.info-row .value {
  font-size: 14px;
  color: #333;
  font-weight: 500;
}

.loading-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(255, 255, 255, 0.8);
  display: flex;
  align-items: center;
  justify-content: center;
}
</style>
