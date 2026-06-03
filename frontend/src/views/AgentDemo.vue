<template>
  <div>
    <el-card style="max-width:1400px;margin:0 auto">
      <template #header>
        <div style="display:flex;justify-content:space-between;align-items:center">
          <div>
            <span style="font-size:18px;font-weight:600">Agent 智能助手</span>
            <span style="font-size:13px;color:#666;margin-left:16px">复杂任务拆分（依赖分析 + 上下文传递 + 并行执行）</span>
          </div>
          <div style="display:flex;align-items:center;gap:12px">
            <el-tag type="success">LangGraph</el-tag>
            <div v-if="isStreaming" class="flex items-center gap-2">
              <el-icon class="animate-spin text-blue-500"><Loading /></el-icon>
              <span style="font-size:13px;color:#409eff">实时执行中...</span>
            </div>
          </div>
        </div>
      </template>

      <!-- 进度条 -->
      <div v-if="isExecuting" style="margin-bottom:16px">
        <div style="display:flex;justify-content:space-between;margin-bottom:8px">
          <span style="font-size:13px;color:#666">执行进度</span>
          <span style="font-size:13px;color:#409eff">{{ currentPhase }} - {{ progressPercent }}%</span>
        </div>
        <el-progress :percentage="progressPercent" :color="progressColor" :show-text="false" />
      </div>

      <el-tabs v-model="activeTab">
        <el-tab-pane label="智能问答" name="qa">
          <div style="margin-bottom:16px">
            <p style="color:#666;font-size:13px">
              输入问题，Agent 将进行复杂任务拆分，支持依赖分析、并行执行和上下文传递
            </p>
          </div>

          <div style="margin-bottom:12px">
            <div style="font-weight:600;margin-bottom:8px">📂 选择文档（可选）</div>
            <el-select
              v-model="selectedDocumentIds"
              multiple
              filterable
              placeholder="选择要查询的文档（不选则查询所有文档）"
              style="width:100%"
            >
              <el-option
                v-for="doc in documents"
                :key="doc.id"
                :label="doc.title || doc.name || `文档 ${doc.id}`"
                :value="doc.id"
              />
            </el-select>
          </div>

          <el-input
            v-model="query"
            type="textarea"
            :rows="3"
            placeholder="例如：帮我分析这个会议，有哪些待办事项？有哪些争议点？"
            style="margin-bottom:12px"
          />

          <div style="display:flex;gap:8px;margin-bottom:16px">
            <el-button type="primary" :loading="loading" @click="handleQuery">
              <template #icon><Lightning /></template>
              执行 Agent
            </el-button>
            <el-button @click="query = ''">清空</el-button>
            <el-button @click="resetState">重置</el-button>
          </div>

          <!-- 实时思维链展示 -->
          <div v-if="isExecuting && streamingThoughts.length" style="margin-bottom:16px">
            <el-card title="💬 实时思维链" shadow="never" style="background:#f8fafc;border:1px solid #e2e8f0">
              <div style="max-height:300px;overflow-y:auto">
                <el-timeline mode="left">
                  <el-timeline-item
                    v-for="(thought, index) in streamingThoughts"
                    :key="index"
                    :color="getPhaseColor(thought.phase)"
                    :hollow="thought.phase === 'plan'"
                    style="animation: fadeIn 0.3s ease-in-out"
                  >
                    <div style="display:flex;gap:12px">
                      <div>
                        <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
                          <el-tag :type="getPhaseTagType(thought.phase)" size="small">
                            {{ getPhaseName(thought.phase) }}
                          </el-tag>
                          <span style="font-weight:600">{{ getAgentName(thought.agent_id) }}</span>
                          <span style="color:#999;font-size:12px">步骤 {{ thought.step }}</span>
                        </div>
                        <div style="font-size:14px">{{ thought.thought }}</div>
                        <div v-if="thought.action" style="margin-top:4px">
                          <el-tag type="success" size="small">📋 {{ thought.action }}</el-tag>
                        </div>
                        <div v-if="thought.observation" style="margin-top:4px;font-size:12px;color:#666">
                          👀 {{ thought.observation }}
                        </div>
                      </div>
                    </div>
                  </el-timeline-item>
                </el-timeline>
              </div>
            </el-card>
          </div>

          <!-- 中间结果预览 -->
          <div v-if="isExecuting && intermediateResults.length" style="margin-bottom:16px">
            <el-card title="📊 中间结果" shadow="never" style="background:#f0fdf4;border:1px solid #86efac">
              <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div
                  v-for="(item, index) in intermediateResults"
                  :key="index"
                  class="p-4 bg-white rounded-lg border border-gray-200"
                >
                  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
                    <span style="font-weight:600">{{ item.task_name }}</span>
                    <el-tag :type="item.status === 'success' ? 'success' : 'warning'" size="small">
                      {{ item.status === 'success' ? '完成' : '进行中' }}
                    </el-tag>
                  </div>
                  <div v-if="item.type === 'retrieve'" style="font-size:13px;color:#666">
                    <div style="margin-bottom:4px">📥 检索到 {{ item.data?.length || 0 }} 条相关内容</div>
                    <div v-if="item.data?.slice(0, 2).map(d => d.chunk_text || d.content).join('...').length > 0" 
                         style="max-height:80px;overflow:hidden;text-overflow:ellipsis">
                      {{ item.data?.slice(0, 2).map(d => d.chunk_text || d.content).join('...') }}
                    </div>
                  </div>
                  <div v-else-if="item.type === 'todo'" style="font-size:13px">
                    <div v-for="(todo, i) in item.data?.slice(0, 3)" :key="i" class="flex items-center gap-2">
                      <CircleCheck style="color:#67c23a" />
                      <span>{{ todo.content }}</span>
                    </div>
                  </div>
                  <div v-else-if="item.type === 'controversy'" style="font-size:13px">
                    <div v-for="(controversy, i) in item.data?.slice(0, 3)" :key="i" class="flex items-center gap-2">
                      <Warning style="color:#f56c6c" />
                      <span>{{ controversy.topic }}</span>
                    </div>
                  </div>
                  <div v-else style="font-size:13px;color:#666">
                    {{ item.data || '处理中...' }}
                  </div>
                </div>
              </div>
            </el-card>
          </div>

          <!-- 最终结果 -->
          <div v-if="result">
            <el-divider>📋 执行计划（PLAN 阶段）</el-divider>
            
            <div v-if="result.plan" style="margin-bottom:16px">
              <el-alert :title="result.plan.analysis" type="info" :closable="false" style="margin-bottom:12px" />
              
              <div style="margin-bottom:12px">
                <div style="font-weight:600;margin-bottom:8px">📊 并行分组</div>
                <el-tag v-for="(group, idx) in result.plan.parallel_groups" :key="idx" type="success" style="margin:4px">
                  Group-{{ idx + 1 }}: {{ group.join(' + ') }}
                </el-tag>
              </div>

              <el-table :data="result.plan.tasks" border size="small">
                <el-table-column prop="task_id" label="任务ID" width="100" />
                <el-table-column prop="task_type" label="类型" width="100">
                  <template #default="{ row }">
                    <el-tag size="small" :type="getTaskTypeTag(row.task_type)">{{ row.task_type }}</el-tag>
                  </template>
                </el-table-column>
                <el-table-column prop="description" label="描述" />
                <el-table-column prop="priority" label="优先级" width="80" />
                <el-table-column prop="dependencies" label="依赖" width="120">
                  <template #default="{ row }">
                    <span v-if="row.dependencies && row.dependencies.length">
                      {{ row.dependencies.join(', ') }}
                    </span>
                    <span v-else style="color:#999">无</span>
                  </template>
                </el-table-column>
                <el-table-column prop="can_parallel_with" label="可并行" width="120">
                  <template #default="{ row }">
                    <span v-if="row.can_parallel_with && row.can_parallel_with.length">
                      {{ row.can_parallel_with.join(', ') }}
                    </span>
                    <span v-else style="color:#999">无</span>
                  </template>
                </el-table-column>
                <el-table-column prop="status" label="状态" width="100">
                  <template #default="{ row }">
                    <el-tag size="small" :type="getStatusTag(row.status)">{{ row.status }}</el-tag>
                  </template>
                </el-table-column>
              </el-table>
            </div>

            <el-divider>⚡ 执行结果（EXECUTE 阶段）</el-divider>
            <div v-if="result.answer">
              <div style="font-weight:600;margin-bottom:8px;color:#409eff">💬 AI 回答</div>
              <el-card style="background:#e8f4ff;border:1px solid #409eff" shadow="never">
                <div style="font-size:14px;line-height:1.8">{{ result.answer }}</div>
              </el-card>
            </div>

            <div v-if="result.minutes">
              <div style="font-weight:600;margin-bottom:8px;margin-top:16px;color:#67c23a">📄 会议纪要</div>
              <el-card style="background:#f0f9eb;border:1px solid #67c23a" shadow="never">
                <div style="font-size:14px;line-height:1.8;white-space:pre-wrap">{{ result.minutes }}</div>
              </el-card>
            </div>

            <div v-if="result.todos && result.todos.length">
              <div style="font-weight:600;margin-bottom:8px;margin-top:16px;color:#e6a23c">✅ 待办事项 ({{ result.todos.length }})</div>
              <el-table :data="result.todos" border>
                <el-table-column prop="content" label="待办内容" />
                <el-table-column prop="assignee" label="负责人" width="120" />
                <el-table-column prop="deadline" label="截止时间" width="150" />
              </el-table>
            </div>

            <div v-if="result.controversies && result.controversies.length">
              <div style="font-weight:600;margin-bottom:8px;margin-top:16px;color:#f56c6c">⚠️ 争议点 ({{ result.controversies.length }})</div>
              <el-table :data="result.controversies" border>
                <el-table-column prop="topic" label="争议主题" width="180" />
                <el-table-column prop="description" label="描述" />
                <el-table-column prop="parties" label="涉及方" width="150">
                  <template #default="{ row }">
                    <span v-if="row.parties && row.parties.length">{{ row.parties.join(', ') }}</span>
                    <span v-else style="color:#999">-</span>
                  </template>
                </el-table-column>
              </el-table>
            </div>

            <el-divider>🔍 质量评估（REFLECT 阶段）</el-divider>
            <el-card v-if="result.reflection" shadow="never">
              <div style="display:flex;align-items:center;margin-bottom:16px">
                <span style="font-weight:600;margin-right:12px">质量评分：</span>
                <el-progress
                  :percentage="Math.round(result.reflection.quality_score * 100)"
                  :color="getScoreColor(result.reflection.quality_score)"
                  style="width:200px"
                />
                <span style="margin-left:12px;font-size:18px">{{ (result.reflection.quality_score * 100).toFixed(0) }}%</span>
              </div>

              <div v-if="result.reflection.issues && result.reflection.issues.length">
                <div style="font-weight:600;margin-bottom:8px">🔴 发现的问题</div>
                <el-tag v-for="(issue, idx) in result.reflection.issues" :key="idx" type="danger" style="margin:4px">
                  {{ issue }}
                </el-tag>
              </div>

              <div v-if="result.reflection.suggestions && result.reflection.suggestions.length" style="margin-top:12px">
                <div style="font-weight:600;margin-bottom:8px">💡 改进建议</div>
                <el-tag v-for="(sug, idx) in result.reflection.suggestions" :key="idx" type="success" style="margin:4px">
                  {{ sug }}
                </el-tag>
              </div>
            </el-card>
          </div>

          <el-empty v-else-if="executed && !result" description="Agent 未返回结果" />
        </el-tab-pane>

        <el-tab-pane label="执行过程" name="process">
          <div style="margin-bottom:16px">
            <p style="color:#666;font-size:13px">
              查看 Agent 的完整执行过程，包括规划、执行、反思三个阶段的思维链
            </p>
          </div>

          <div v-if="thoughts && thoughts.length" style="max-height:700px;overflow-y:auto">
            <el-timeline>
              <el-timeline-item
                v-for="(thought, index) in thoughts"
                :key="index"
                :color="getPhaseColor(thought.phase)"
                :hollow="thought.phase === 'plan'"
              >
                <el-card shadow="never">
                  <div style="display:flex;justify-content:space-between;align-items:center">
                    <div style="font-weight:600">
                      <el-tag :type="getPhaseTagType(thought.phase)" size="small" style="margin-right:8px">
                        {{ getPhaseName(thought.phase) }}
                      </el-tag>
                      {{ getAgentName(thought.agent_id) }}
                    </div>
                    <div style="color:#999;font-size:12px">步骤 {{ thought.step }}</div>
                  </div>
                  <div style="margin-top:8px;font-size:14px">{{ thought.thought }}</div>
                  <div v-if="thought.action" style="margin-top:4px">
                    <el-tag type="success" size="small">📋 {{ thought.action }}</el-tag>
                  </div>
                  <div v-if="thought.observation" style="margin-top:4px;font-size:12px;color:#666">
                    👀 {{ thought.observation }}
                  </div>
                </el-card>
              </el-timeline-item>
            </el-timeline>
          </div>
          <el-empty v-else description="无执行过程记录，请先执行问答" />
        </el-tab-pane>

        <el-tab-pane label="架构说明" name="architecture">
          <div style="margin-bottom:16px">
            <p style="color:#666;font-size:13px">
              复杂任务拆分架构说明
            </p>
          </div>

          <el-card shadow="never" style="background:#f5f7fa">
            <div style="text-align:center;font-size:16px;line-height:2.5">
              <div style="margin-bottom:24px">
                <el-tag type="info" size="large">👤 用户问题</el-tag>
                <el-icon style="margin:0 16px;font-size:20px"><ArrowDown /></el-icon>
              </div>

              <div style="margin-bottom:24px;padding:16px;background:#e8f4ff;border-radius:8px">
                <div style="font-weight:600;color:#409eff;margin-bottom:8px">📋 PLAN 阶段</div>
                <div style="font-size:14px;color:#666">
                  问题分析 → 任务拆解 → 依赖分析 → 并行分组 → 上下文传递规划
                </div>
              </div>
              <el-icon style="margin:8px;font-size:20px"><ArrowDown /></el-icon>

              <div style="margin-bottom:24px;padding:16px;background:#f0f9eb;border-radius:8px">
                <div style="font-weight:600;color:#67c23a;margin-bottom:8px">⚡ EXECUTE 阶段</div>
                <div style="font-size:14px;color:#666">
                  按并行组执行 → 任务协调 → 上下文传递 → 结果整合
                </div>
              </div>
              <el-icon style="margin:8px;font-size:20px"><ArrowDown /></el-icon>

              <div style="margin-bottom:24px;padding:16px;background:#fef0f0;border-radius:8px">
                <div style="font-weight:600;color:#f56c6c;margin-bottom:8px">🔍 REFLECT 阶段</div>
                <div style="font-size:14px;color:#666">
                  质量评估 → 缺陷检测 → 改进建议
                </div>
              </div>
              <el-icon style="margin:8px;font-size:20px"><ArrowDown /></el-icon>

              <div>
                <el-tag type="success" size="large">✅ 输出结果</el-tag>
              </div>
            </div>
          </el-card>

          <el-divider>核心能力</el-divider>

          <el-descriptions :column="2" border>
            <el-descriptions-item label="依赖分析">
              <el-tag type="info" size="small">dependencies</el-tag>
              <el-tag type="info" size="small">can_parallel_with</el-tag>
              <el-tag type="info" size="small">input_from</el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="上下文传递">
              <el-tag type="success" size="small">output_key</el-tag>
              <el-tag type="success" size="small">task_contexts</el-tag>
              <el-tag type="success" size="small">数据流</el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="并行执行">
              <el-tag type="warning" size="small">asyncio.gather</el-tag>
              <el-tag type="warning" size="small">parallel_groups</el-tag>
              <el-tag type="warning" size="small">并发</el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="任务类型">
              <el-tag type="primary" size="small">retrieve</el-tag>
              <el-tag type="primary" size="small">qa</el-tag>
              <el-tag type="primary" size="small">minutes/todo/controversy/combine</el-tag>
            </el-descriptions-item>
          </el-descriptions>

          <el-divider>示例：复杂问题拆分</el-divider>

          <el-card shadow="never">
            <div style="font-weight:600;margin-bottom:8px">问题："这个会议有哪些待办和争议点？"</div>
            <el-steps :active="3" finish-status="success">
              <el-step title="Plan" description="拆分任务" />
              <el-step title="并行执行" description="待办+争议点" />
              <el-step title="整合" description="统一输出" />
            </el-steps>
            <div style="margin-top:16px;font-size:13px;color:#666">
              <div>Group-1 (并行): [task_1: 抽取待办] + [task_2: 识别争议]</div>
              <div>Group-2 (顺序): [task_3: 整合结果]</div>
              <div style="margin-top:8px">上下文传递: task_1.output_key → task_3.input_from</div>
            </div>
          </el-card>
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { agentApi } from '@/api/agents'
import { documentApi } from '@/api/documents'
import { ElMessage } from 'element-plus'
import { ArrowDown, Loading, Lightning, CircleCheck, Warning } from '@element-plus/icons-vue'

const activeTab = ref('qa')
const query = ref('')
const loading = ref(false)
const executed = ref(false)
const result = ref(null)
const thoughts = ref([])
const documents = ref([])
const selectedDocumentIds = ref([])

// 实时执行状态
const isExecuting = ref(false)
const isStreaming = ref(false)
const streamingThoughts = ref([])
const intermediateResults = ref([])
const currentPhase = ref('初始化')
const progressPercent = ref(0)

const phaseNames = { plan: '规划', execute: '执行', reflect: '反思' }
const agentNames = {
  plan_agent: '规划 Agent',
  execute_agent: '执行 Agent',
  reflect_agent: '反思 Agent',
  qa_sub_agent: '问答子 Agent',
  minutes_sub_agent: '纪要子 Agent',
  todo_sub_agent: '待办子 Agent',
  controversy_sub_agent: '争议点子 Agent',
}

const progressColor = computed(() => {
  if (currentPhase.value === '规划') return '#409eff'
  if (currentPhase.value === '执行') return '#67c23a'
  if (currentPhase.value === '反思') return '#f56c6c'
  return '#909399'
})

function getPhaseName(phase) { return phaseNames[phase] || phase }
function getAgentName(agentId) { return agentNames[agentId] || agentId }
function getPhaseColor(phase) {
  return { plan: '#409eff', execute: '#67c23a', reflect: '#f56c6c' }[phase] || '#909399'
}
function getPhaseTagType(phase) {
  return { plan: 'info', execute: 'success', reflect: 'danger' }[phase] || 'info'
}
function getScoreColor(score) {
  if (score >= 0.8) return '#67c23a'
  if (score >= 0.6) return '#e6a23c'
  return '#f56c6c'
}
function getTaskTypeTag(type) {
  return {
    qa: 'primary', minutes: 'success', todo: 'warning',
    controversy: 'danger', retrieve: 'info', combine: ''
  }[type] || 'info'
}
function getStatusTag(status) {
  return {
    pending: 'info', in_progress: 'warning',
    completed: 'success', failed: 'danger', skipped: 'info'
  }[status] || 'info'
}

async function loadDocuments() {
  try {
    const res = await documentApi.list({ limit: 100 })
    documents.value = res?.data?.items || res?.data || []
  } catch (err) {
    console.error('加载文档失败', err)
  }
}

onMounted(() => {
  loadDocuments()
})

function resetState() {
  query.value = ''
  result.value = null
  thoughts.value = []
  streamingThoughts.value = []
  intermediateResults.value = []
  executed.value = false
  isExecuting.value = false
  isStreaming.value = false
  currentPhase.value = '初始化'
  progressPercent.value = 0
}

async function handleQuery() {
  if (!query.value.trim()) {
    ElMessage.warning('请输入问题')
    return
  }

  resetState()
  loading.value = true
  isExecuting.value = true

  try {
    const payload = {
      question: query.value,
    }
    if (selectedDocumentIds.value.length > 0) {
      payload.document_ids = selectedDocumentIds.value
    }

    // 尝试使用流式API
    try {
      const stream = await agentApi.queryStream(payload)
      await handleStreamResponse(stream)
    } catch (streamErr) {
      console.log('流式API不可用，使用普通API')
      const res = await agentApi.query(payload)
      await handleNonStreamResponse(res)
    }

    executed.value = true
    ElMessage.success('Agent 执行成功')
  } catch (e) {
    ElMessage.error('Agent 执行失败: ' + (e.message || '未知错误'))
  } finally {
    loading.value = false
    isExecuting.value = false
    isStreaming.value = false
  }
}

async function handleStreamResponse(stream) {
  const reader = stream.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  isStreaming.value = true

  while (true) {
    const { done, value } = await reader.read()
    if (done) {
      buffer += decoder.decode()
      break
    }

    try {
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''
      
      for (const line of lines) {
        const trimmed = line.trim()
        if (!trimmed.startsWith('data: ')) continue

        const dataStr = trimmed.slice(6)
        if (dataStr === '[DONE]') {
          progressPercent.value = 100
          return
        }
        
        const data = JSON.parse(dataStr)
        handleStreamEvent(data)
      }
    } catch (e) {
      console.error('解析流式数据失败', e)
    }
  }
}

function handleStreamEvent(data) {
  if (data.type === 'thought') {
    streamingThoughts.value.push(data.data)
    updateProgress(data.data.phase)
  } else if (data.type === 'task_result') {
    intermediateResults.value.push(data.data)
  } else if (data.type === 'plan') {
    result.value = { plan: data.data }
    currentPhase.value = '规划'
    progressPercent.value = 30
  } else if (data.type === 'final') {
    result.value = data.data
    thoughts.value = data.data.thoughts || streamingThoughts.value
    progressPercent.value = 100
  }
}

function updateProgress(phase) {
  if (phase === 'plan') {
    currentPhase.value = '规划'
    progressPercent.value = Math.min(progressPercent.value + 5, 33)
  } else if (phase === 'execute') {
    currentPhase.value = '执行'
    progressPercent.value = Math.min(progressPercent.value + 10, 66)
  } else if (phase === 'reflect') {
    currentPhase.value = '反思'
    progressPercent.value = Math.min(progressPercent.value + 15, 95)
  }
}

async function handleNonStreamResponse(res) {
  const data = res?.data || res
  result.value = data
  thoughts.value = data?.thoughts || []
  streamingThoughts.value = data?.thoughts || []
  
  // 模拟进度更新
  if (data?.plan) {
    currentPhase.value = '规划'
    progressPercent.value = 33
  }
  if (data?.answer || data?.todos || data?.minutes) {
    currentPhase.value = '执行'
    progressPercent.value = 66
  }
  if (data?.reflection) {
    currentPhase.value = '反思'
    progressPercent.value = 100
  }
}
</script>

<style scoped>
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(-10px); }
  to { opacity: 1; transform: translateY(0); }
}

.grid {
  display: grid;
}

@media (min-width: 768px) {
  .md\:grid-cols-2 {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

.gap-4 {
  gap: 1rem;
}
</style>
