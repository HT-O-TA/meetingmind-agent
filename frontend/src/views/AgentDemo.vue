<template>
  <div class="agent-page">
    <section class="page-header">
      <div>
        <h2>会议 Agent</h2>
        <p>真实执行路径：路由 → 检索或业务节点 → 工具策略 / HITL → 校验与有限修复。</p>
      </div>
      <el-tag type="info">有界会话上下文</el-tag>
    </section>

    <el-card shadow="never" class="query-card">
      <el-input
        v-model="question"
        type="textarea"
        :rows="4"
        maxlength="2000"
        show-word-limit
        placeholder="例如：总结这次会议的决定，或把已确认的待办创建为 Jira Issue"
        @keydown.ctrl.enter.prevent="runQuery"
      />

      <div class="query-options">
        <el-select
          v-model="documentIds"
          multiple
          collapse-tags
          clearable
          placeholder="限定文档（可选）"
          class="document-select"
        >
          <el-option
            v-for="document in documents"
            :key="document.id"
            :label="document.title || document.filename || `文档 ${document.id}`"
            :value="document.id"
          />
        </el-select>
        <el-switch
          v-model="enableHitl"
          active-text="启用高风险操作确认"
        />
        <div class="actions">
          <el-button v-if="running" @click="stopQuery">停止</el-button>
          <el-button @click="clearResult">清空</el-button>
          <el-button type="primary" :loading="running" @click="runQuery">
            执行
          </el-button>
        </div>
      </div>
    </el-card>

    <el-alert
      v-if="errorMessage"
      :title="errorMessage"
      type="error"
      show-icon
      :closable="false"
      class="block"
    />

    <el-card v-if="pendingAction" shadow="never" class="block confirmation-card">
      <template #header>
        <div class="card-title">
          <span>高风险操作等待确认</span>
          <el-tag type="warning">{{ result?.risk_level || 'high' }}</el-tag>
        </div>
      </template>
      <pre>{{ pretty(pendingAction) }}</pre>
      <div class="confirmation-actions">
        <el-button :loading="confirmationLoading" @click="respondConfirmation('rejected')">
          拒绝
        </el-button>
        <el-button type="danger" :loading="confirmationLoading" @click="respondConfirmation('approved')">
          确认执行
        </el-button>
      </div>
    </el-card>

    <el-card v-if="result" shadow="never" class="block">
      <template #header>
        <div class="card-title">
          <span>执行结果</span>
          <div class="tags">
            <el-tag>{{ result.task_type || 'qa' }}</el-tag>
            <el-tag v-if="result.workflow_type" type="success">{{ result.workflow_type }}</el-tag>
            <el-tag v-if="result.confirmation_status" type="info">
              {{ result.confirmation_status }}
            </el-tag>
          </div>
        </div>
      </template>

      <el-tabs v-model="activeTab">
        <el-tab-pane label="回答与证据" name="answer">
          <div v-if="result.answer" class="answer">{{ result.answer }}</div>

          <template v-if="hasStructuredOutput">
            <h3>结构化结果</h3>
            <pre>{{ pretty(structuredOutput) }}</pre>
          </template>

          <template v-if="result.citations?.length">
            <h3>引用</h3>
            <el-table :data="result.citations" size="small" border>
              <el-table-column prop="citation_id" label="引用" width="100" />
              <el-table-column prop="document_id" label="文档" width="90" />
              <el-table-column prop="speaker" label="说话人" width="110" />
              <el-table-column prop="text_excerpt" label="证据片段" min-width="320" />
              <el-table-column prop="score" label="分数" width="90" />
            </el-table>
          </template>

          <el-empty v-if="!result.answer && !hasStructuredOutput" description="没有可展示的业务输出" />
        </el-tab-pane>

        <el-tab-pane label="策略与校验" name="policy">
          <el-descriptions :column="1" border>
            <el-descriptions-item label="路由原因">{{ result.route_reason || '-' }}</el-descriptions-item>
            <el-descriptions-item label="检索置信度">{{ formatScore(result.retrieval_confidence) }}</el-descriptions-item>
            <el-descriptions-item label="风险等级">{{ result.risk_level || '-' }}</el-descriptions-item>
            <el-descriptions-item label="需要确认">{{ result.requires_confirmation ? '是' : '否' }}</el-descriptions-item>
            <el-descriptions-item label="执行耗时">{{ formatLatency(result.latency_ms) }}</el-descriptions-item>
          </el-descriptions>
          <h3>策略结果</h3>
          <pre>{{ pretty(result.policy_results || []) }}</pre>
          <h3>校验错误</h3>
          <pre>{{ pretty(result.validation_errors || []) }}</pre>
        </el-tab-pane>

        <el-tab-pane label="真实事件" name="events">
          <el-alert
            title="这里只展示后端实际发送的业务事件，不展示或伪造模型私有思维链。"
            type="info"
            show-icon
            :closable="false"
          />
          <el-timeline class="event-list">
            <el-timeline-item
              v-for="(event, index) in events"
              :key="`${event.type}-${index}`"
              :timestamp="event.time"
            >
              <strong>{{ event.type }}</strong>
              <span class="event-message">{{ event.message }}</span>
            </el-timeline-item>
          </el-timeline>
          <el-empty v-if="events.length === 0" description="尚无事件" />
        </el-tab-pane>

        <el-tab-pane label="能力边界" name="boundary">
          <ul class="boundary-list">
            <li>正式图是确定性业务图，不宣称通用 Multi-Agent 或无限 ReAct。</li>
            <li>会话上下文保存在当前进程的有界窗口，服务重启后清空。</li>
            <li>Jira 写工具已完成合同和审计验证；未配置真实凭据时不会产生外部 Issue。</li>
            <li>Trace 只记录实际节点与耗时，不生成模拟 token、成本或质量分。</li>
          </ul>
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { agentApi } from '@/api/agents'
import { documentApi } from '@/api/documents'

const question = ref('')
const documentIds = ref([])
const documents = ref([])
const enableHitl = ref(true)
const running = ref(false)
const confirmationLoading = ref(false)
const errorMessage = ref('')
const result = ref(null)
const events = ref([])
const activeTab = ref('answer')
const controller = ref(null)
const sessionId = sessionStorage.getItem('meetingmind_agent_session') || crypto.randomUUID()
sessionStorage.setItem('meetingmind_agent_session', sessionId)

const pendingAction = computed(() => {
  if (result.value?.confirmation_status !== 'required') return null
  return result.value.pending_action || null
})

const structuredOutput = computed(() => ({
  minutes: result.value?.minutes || null,
  todos: result.value?.todos || null,
  controversies: result.value?.controversies || null,
}))

const hasStructuredOutput = computed(() => Object.values(structuredOutput.value).some(Boolean))

function pretty(value) {
  return JSON.stringify(value, null, 2)
}

function formatScore(value) {
  return typeof value === 'number' ? value.toFixed(3) : '-'
}

function formatLatency(value) {
  return typeof value === 'number' ? `${value.toFixed(1)} ms` : '-'
}

function summarizeEvent(type, data) {
  if (typeof data === 'string') return data
  return data?.message || data?.phase || data?.status || data?.question || type
}

function recordEvent(type, data) {
  events.value.push({
    type,
    message: summarizeEvent(type, data),
    time: new Date().toLocaleTimeString(),
  })
}

function handleEvent(event) {
  if (!event?.type) return
  if (event.type === 'final') {
    result.value = event.data || null
    return
  }
  if (event.type === 'error') {
    errorMessage.value = event.data?.message || 'Agent 执行失败'
  }
  recordEvent(event.type, event.data)
}

async function runQuery() {
  const normalizedQuestion = question.value.trim()
  if (!normalizedQuestion) {
    ElMessage.warning('请输入问题')
    return
  }

  stopQuery()
  running.value = true
  errorMessage.value = ''
  result.value = null
  events.value = []
  controller.value = new AbortController()
  const payload = {
    question: normalizedQuestion,
    session_id: sessionId,
    enable_human_in_the_loop: enableHitl.value,
  }
  if (documentIds.value.length) payload.document_ids = documentIds.value

  try {
    await agentApi.queryStream(payload, handleEvent, controller.value.signal)
    if (!result.value && !errorMessage.value) {
      result.value = await agentApi.query(payload)
      recordEvent('fallback', 'SSE 未返回最终结果，已使用普通查询接口')
    }
  } catch (error) {
    if (error.name !== 'AbortError') {
      errorMessage.value = error.message || 'Agent 执行失败'
    }
  } finally {
    running.value = false
    controller.value = null
  }
}

function stopQuery() {
  controller.value?.abort()
  controller.value = null
  running.value = false
}

function clearResult() {
  stopQuery()
  result.value = null
  events.value = []
  errorMessage.value = ''
}

async function respondConfirmation(response) {
  const requestId = pendingAction.value?.request_id
  if (!requestId) {
    ElMessage.error('确认请求缺少 request_id')
    return
  }
  confirmationLoading.value = true
  try {
    const responseData = await agentApi.resumeConfirmation(requestId, response)
    if (responseData?.result) result.value = responseData.result
    else result.value = { ...result.value, confirmation_status: response }
    recordEvent('confirmation', response)
    ElMessage.success(response === 'approved' ? '已确认执行' : '已拒绝执行')
  } catch (error) {
    ElMessage.error(error.message || '确认处理失败')
  } finally {
    confirmationLoading.value = false
  }
}

async function loadDocuments() {
  try {
    const response = await documentApi.list({ limit: 100 })
    documents.value = response?.items || response?.data?.items || response?.data || []
  } catch {
    documents.value = []
  }
}

onMounted(loadDocuments)
</script>

<style scoped>
.agent-page {
  max-width: 1200px;
  margin: 0 auto;
  padding: 24px;
}

.page-header,
.card-title,
.query-options,
.confirmation-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.page-header h2 {
  margin: 0 0 6px;
}

.page-header p {
  margin: 0 0 20px;
  color: #606266;
}

.query-options {
  margin-top: 16px;
  flex-wrap: wrap;
}

.document-select {
  min-width: 280px;
  flex: 1;
}

.actions,
.tags {
  display: flex;
  gap: 8px;
}

.block {
  margin-top: 20px;
}

.confirmation-card {
  border-color: #e6a23c;
}

.confirmation-actions {
  justify-content: flex-end;
  margin-top: 16px;
}

.answer {
  white-space: pre-wrap;
  line-height: 1.75;
  padding: 16px;
  background: #f7f8fa;
  border-radius: 6px;
}

h3 {
  margin: 20px 0 10px;
  font-size: 15px;
}

pre {
  margin: 0;
  padding: 14px;
  overflow: auto;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  background: #f7f8fa;
  border-radius: 6px;
}

.event-list {
  margin-top: 20px;
}

.event-message {
  margin-left: 10px;
  color: #606266;
}

.boundary-list {
  line-height: 2;
  color: #303133;
}

@media (max-width: 720px) {
  .agent-page {
    padding: 12px;
  }

  .page-header,
  .query-options {
    align-items: stretch;
    flex-direction: column;
  }

  .document-select {
    width: 100%;
    min-width: 0;
  }
}
</style>
