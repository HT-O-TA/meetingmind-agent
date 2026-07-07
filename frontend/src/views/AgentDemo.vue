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

          <div style="margin-bottom:12px;display:flex;align-items:center;gap:8px">
            <el-switch
              v-model="enableHumanInTheLoop"
              active-text="已启用人机交互"
              inactive-text="已禁用人机交互"
            />
            <el-tag v-if="enableHumanInTheLoop" type="danger" size="small">⚠️ 高风险操作将需要人工确认</el-tag>
          </div>

          <div style="display:flex;gap:8px;margin-bottom:16px">
            <el-button type="primary" :loading="loading" @click="handleQuery">
              <template #icon><Lightning /></template>
              执行 Agent
            </el-button>
            <el-button @click="query = ''">清空</el-button>
            <el-button @click="resetState">重置</el-button>
          </div>

          <!-- 实时思维链展示（执行中和执行后都显示） -->
          <div v-if="streamingThoughts.length" style="margin-bottom:16px">
            <el-card shadow="never" style="background:#f8fafc;border:1px solid #e2e8f0">
              <template #header>
                <div style="display:flex;justify-content:space-between;align-items:center">
                  <span style="font-weight:600">💬 思考过程</span>
                  <div style="display:flex;gap:8px">
                    <el-tag v-if="isExecuting" type="success" size="small">
                      <el-icon class="animate-spin"><Loading /></el-icon>
                      实时更新中...
                    </el-tag>
                    <el-tag v-else type="info" size="small">执行完成</el-tag>
                  </div>
                </div>
              </template>
              <div style="max-height:400px;overflow-y:auto">
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

          <el-alert
            v-if="hasActiveConfirmation && !result"
            style="margin-bottom:16px"
            type="error"
            title="等待人工确认"
            :closable="false"
          >
            <template #default>
              <div>来源：{{ pendingConfirmationDetails.source || 'intent' }}</div>
              <div>原因：{{ pendingConfirmationDetails.reason || pendingConfirmation.message || '高风险操作需要确认' }}</div>
              <div v-if="pendingConfirmationDetails.tool_name">
                工具：{{ pendingConfirmationDetails.tool_name }}
              </div>
              <div v-else-if="pendingConfirmationDetails.tool_calls && pendingConfirmationDetails.tool_calls.length">
                工具：{{ pendingConfirmationDetails.tool_calls.map(t => t.tool_name).join(', ') }}
              </div>
              <div style="margin-top:10px;display:flex;gap:8px">
                <el-button
                  size="small"
                  type="primary"
                  :loading="confirmationLoading"
                  :disabled="!pendingConfirmationId"
                  @click="handleContinue()"
                >
                  确认并继续
                </el-button>
                <el-button
                  size="small"
                  :loading="confirmationLoading"
                  :disabled="!pendingConfirmationId"
                  @click="handleReject()"
                >
                  拒绝
                </el-button>
              </div>
            </template>
          </el-alert>

          <!-- 最终结果 -->
          <div v-if="result">
            <div style="margin-bottom:16px">
              <el-alert
                :title="`工作流：${getWorkflowName(result.workflow_type || result.task_type)}${result.route_reason ? ' - ' + result.route_reason : ''}`"
                type="info"
                :closable="false"
              >
                <template #default>
                  <span v-if="typeof result.retrieval_confidence === 'number'">
                    检索置信度：{{ Math.round(result.retrieval_confidence * 100) }}%
                  </span>
                  <span v-if="result.citations && result.citations.length" style="margin-left:12px">
                    引用来源：{{ result.citations.length }} 条
                  </span>
                  <span v-if="result.risk_level" style="margin-left:12px">
                    风险等级：{{ getRiskName(result.risk_level) }}
                  </span>
                  <span v-if="result.confirmation_status && result.confirmation_status !== 'not_required'" style="margin-left:12px">
                    确认状态：{{ getConfirmationStatusName(result.confirmation_status) }}
                  </span>
                </template>
              </el-alert>
              <el-alert
                v-if="result.validation_errors && result.validation_errors.length"
                style="margin-top:8px"
                type="warning"
                title="输出校验发现问题"
                :closable="false"
              >
                <template #default>
                  <div v-for="(error, idx) in result.validation_errors" :key="idx">
                    {{ error }}
                  </div>
                </template>
              </el-alert>
              <el-alert
                v-if="hasActiveConfirmation"
                style="margin-top:8px"
                type="error"
                title="等待人工确认"
                :closable="false"
              >
                <template #default>
          <div>来源：{{ pendingConfirmationDetails.source || result.pending_action?.source || 'intent' }}</div>
          <div>原因：{{ pendingConfirmationDetails.reason || result.pending_action?.reason || '高风险操作需要确认' }}</div>
          <div v-if="pendingConfirmationDetails.tool_name">
            工具：{{ pendingConfirmationDetails.tool_name }}
          </div>
          <div v-else-if="result.pending_action?.tool_calls && result.pending_action.tool_calls.length">
            工具：{{ result.pending_action.tool_calls.map(t => t.tool_name).join(', ') }}
          </div>
          <div style="margin-top: 10px;display:flex;gap:8px">
            <el-button
              size="small"
              type="primary"
              :loading="confirmationLoading"
              @click="handleContinue()"
            >
              确认并继续
            </el-button>
            <el-button
              size="small"
              :loading="confirmationLoading"
              @click="handleReject()"
            >
              拒绝
            </el-button>
          </div>
        </template>
              </el-alert>
              <el-card
                v-if="result.policy_results && result.policy_results.length"
                shadow="never"
                style="margin-top:8px"
              >
                <template #header>工具策略结果</template>
                <el-table :data="result.policy_results" border size="small">
                  <el-table-column prop="tool_name" label="工具" width="160" />
                  <el-table-column prop="code" label="策略" width="170">
                    <template #default="{ row }">
                      <el-tag :type="row.allowed ? 'success' : 'danger'" size="small">
                        {{ getPolicyCodeName(row.code) }}
                      </el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column prop="risk_level" label="风险" width="90">
                    <template #default="{ row }">
                      {{ getRiskName(row.risk_level) }}
                    </template>
                  </el-table-column>
                  <el-table-column prop="confirmation_status" label="确认状态" width="130">
                    <template #default="{ row }">
                      {{ getConfirmationStatusName(row.confirmation_status) }}
                    </template>
                  </el-table-column>
                  <el-table-column prop="reason" label="原因" />
                </el-table>
              </el-card>
            </div>
            
            <div v-if="result.plan" style="margin-bottom:16px">
              <el-divider>📋 执行计划（PLAN 阶段）</el-divider>
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

            <el-divider>⚡ 执行结果</el-divider>
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

            <el-card v-if="result.reflection" shadow="never">
              <template #header>🔍 质量评估（REPLAN 阶段）</template>
              <div style="display:flex;align-items:center;margin-bottom:16px">
                <span style="font-weight:600;margin-right:12px">质量评分：</span>
                <el-progress
                  :percentage="Math.round(getQualityScore(result.reflection) * 100)"
                  :color="getScoreColor(getQualityScore(result.reflection))"
                  style="width:200px"
                />
                <span style="margin-left:12px;font-size:18px">{{ (getQualityScore(result.reflection) * 100).toFixed(0) }}%</span>
              </div>

              <!-- 评估参数明细 -->
              <div style="margin-bottom:16px;padding:12px;background:#f8fafc;border-radius:8px">
                <div style="font-weight:600;margin-bottom:12px;color:#409eff">📊 评估参数明细</div>
                
                <!-- 5个通用指标展示 -->
                <div style="margin-bottom:12px">
                  <div style="display:flex;gap:8px;margin-bottom:8px;flex-wrap:wrap">
                    <div v-if="result.reflection.metrics.task_completion != null" style="flex:1;min-width:150px">
                      <div style="font-size:12px;color:#666;margin-bottom:4px">任务达成度 (35%)</div>
                      <el-progress 
                        :percentage="Math.round(result.reflection.metrics.task_completion * 100)" 
                        :color="getScoreColor(result.reflection.metrics.task_completion)"
                        :stroke-width="8"
                        :show-text="false"
                      />
                      <div style="text-align:center;font-size:12px;margin-top:2px">{{ (result.reflection.metrics.task_completion * 100).toFixed(0) }}%</div>
                    </div>
                    <div v-if="result.reflection.metrics.correctness != null" style="flex:1;min-width:150px">
                      <div style="font-size:12px;color:#666;margin-bottom:4px">正确性 (25%)</div>
                      <el-progress 
                        :percentage="Math.round(result.reflection.metrics.correctness * 100)" 
                        :color="getScoreColor(result.reflection.metrics.correctness)"
                        :stroke-width="8"
                        :show-text="false"
                      />
                      <div style="text-align:center;font-size:12px;margin-top:2px">{{ (result.reflection.metrics.correctness * 100).toFixed(0) }}%</div>
                    </div>
                    <div v-if="result.reflection.metrics.process_efficiency != null" style="flex:1;min-width:150px">
                      <div style="font-size:12px;color:#666;margin-bottom:4px">流程效率 (15%)</div>
                      <el-progress 
                        :percentage="Math.round(result.reflection.metrics.process_efficiency * 100)" 
                        :color="getScoreColor(result.reflection.metrics.process_efficiency)"
                        :stroke-width="8"
                        :show-text="false"
                      />
                      <div style="text-align:center;font-size:12px;margin-top:2px">{{ (result.reflection.metrics.process_efficiency * 100).toFixed(0) }}%</div>
                    </div>
                    <div v-if="result.reflection.metrics.expression != null" style="flex:1;min-width:150px">
                      <div style="font-size:12px;color:#666;margin-bottom:4px">表达 (15%)</div>
                      <el-progress 
                        :percentage="Math.round(result.reflection.metrics.expression * 100)" 
                        :color="getScoreColor(result.reflection.metrics.expression)"
                        :stroke-width="8"
                        :show-text="false"
                      />
                      <div style="text-align:center;font-size:12px;margin-top:2px">{{ (result.reflection.metrics.expression * 100).toFixed(0) }}%</div>
                    </div>
                    <div v-if="result.reflection.metrics.risk != null" style="flex:1;min-width:150px">
                      <div style="font-size:12px;color:#666;margin-bottom:4px">风险 (10%)</div>
                      <el-progress 
                        :percentage="Math.round(result.reflection.metrics.risk * 100)" 
                        :color="getScoreColor(result.reflection.metrics.risk)"
                        :stroke-width="8"
                        :show-text="false"
                      />
                      <div style="text-align:center;font-size:12px;margin-top:2px">{{ (result.reflection.metrics.risk * 100).toFixed(0) }}%</div>
                    </div>
                  </div>
                </div>
                
                <el-descriptions :column="2" border>
                  <el-descriptions-item label="用户问题">
                    <span :title="query" style="color:#666">{{ query.length > 50 ? query.slice(0, 50) + '...' : query }}</span>
                  </el-descriptions-item>
                  <el-descriptions-item label="回答内容">
                    <span :title="result.answer" style="color:#666">{{ result.answer ? (result.answer.length > 50 ? result.answer.slice(0, 50) + '...' : result.answer) : '无' }}</span>
                  </el-descriptions-item>
                  <el-descriptions-item label="会议纪要">
                    <span :title="result.minutes" style="color:#666">{{ result.minutes ? (result.minutes.length > 50 ? result.minutes.slice(0, 50) + '...' : result.minutes) : '无' }}</span>
                  </el-descriptions-item>
                  <el-descriptions-item label="待办事项">
                    <el-tag :type="result.todos && result.todos.length > 0 ? 'success' : 'info'" size="small">
                      {{ result.todos ? result.todos.length : 0 }} 个
                    </el-tag>
                  </el-descriptions-item>
                  <el-descriptions-item label="争议点">
                    <el-tag :type="result.controversies && result.controversies.length > 0 ? 'danger' : 'info'" size="small">
                      {{ result.controversies ? result.controversies.length : 0 }} 个
                    </el-tag>
                  </el-descriptions-item>
                  <el-descriptions-item label="需要重试">
                    <el-tag :type="result.reflection.needs_retry ? 'warning' : 'success'" size="small">
                      {{ result.reflection.needs_retry ? '是' : '否' }}
                    </el-tag>
                  </el-descriptions-item>
                </el-descriptions>
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
              查看 Agent 的完整执行过程，包括规划、执行、重新规划三个阶段的思维链
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
                <div style="font-weight:600;color:#f56c6c;margin-bottom:8px">🔍 REPLAN 阶段</div>
                <div style="font-size:14px;color:#666">
                  质量评估 → 缺陷检测 → 重新规划决策 → 循环改进
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
import { ArrowDown, Loading, Promotion, CircleCheck, Warning } from '@element-plus/icons-vue'

const activeTab = ref('qa')
const query = ref('')
const loading = ref(false)
const executed = ref(false)
const result = ref(null)
const thoughts = ref([])
const documents = ref([])
const selectedDocumentIds = ref([])
const enableHumanInTheLoop = ref(false)
const pendingConfirmation = ref(null)
const confirmationLoading = ref(false)
const sseController = ref(null)
const pendingConfirmationId = computed(() => pendingConfirmation.value?.request_id || null)
const pendingConfirmationDetails = computed(() => pendingConfirmation.value?.details || pendingConfirmation.value || {})
const hasFinalOutput = computed(() => {
  const data = result.value
  if (!data) return false
  return Boolean(data.answer || data.minutes || (data.todos && data.todos.length) || (data.controversies && data.controversies.length))
})
const hasActiveConfirmation = computed(() => {
  const data = result.value
  if (data?.confirmation_status === 'approved' || data?.confirmation_status === 'rejected' || data?.confirmation_status === 'not_required') {
    return false
  }
  if (data?.pending_action && (data.confirmation_status === 'required' || data.requires_confirmation)) {
    return true
  }
  return Boolean(pendingConfirmation.value && !hasFinalOutput.value)
})

// 实时执行状态
const isExecuting = ref(false)
const isStreaming = ref(false)
const streamingThoughts = ref([])
const intermediateResults = ref([])
const currentPhase = ref('初始化')
const progressPercent = ref(0)

const phaseNames = { plan: '规划', execute: '执行', reflect: '反思', replan: '重新规划' }
const agentNames = {
  route_agent: '路由 Agent',
  simple_qa_node: '问答工作流',
  minutes_node: '纪要工作流',
  todos_node: '待办工作流',
  controversy_node: '争议分析工作流',
  plan_agent: '规划 Agent',
  execute_agent: '执行 Agent',
  reflect_agent: '反思 Agent',
  replan_agent: '重新规划 Agent',
  qa_sub_agent: '问答子 Agent',
  minutes_sub_agent: '纪要子 Agent',
  todo_sub_agent: '待办子 Agent',
  controversy_sub_agent: '争议点子 Agent',
}

const progressColor = computed(() => {
  if (currentPhase.value === '规划') return '#409eff'
  if (currentPhase.value === '执行') return '#67c23a'
  if (currentPhase.value === '反思' || currentPhase.value === '重新规划') return '#f56c6c'
  return '#909399'
})

function getQualityScore(reflection) {
  if (!reflection) return 0
  if (typeof reflection.overall_score === 'number' && !isNaN(reflection.overall_score)) {
    return reflection.overall_score
  }
  if (typeof reflection.quality_score === 'number' && !isNaN(reflection.quality_score)) {
    return reflection.quality_score
  }
  return 0
}

function getPhaseName(phase) { return phaseNames[phase] || phase }
function getAgentName(agentId) { return agentNames[agentId] || agentId }
function getPhaseColor(phase) {
  return { plan: '#409eff', execute: '#67c23a', reflect: '#f56c6c', replan: '#f56c6c' }[phase] || '#909399'
}
function getPhaseTagType(phase) {
  return { plan: 'info', execute: 'success', reflect: 'danger', replan: 'danger' }[phase] || 'info'
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

function getWorkflowName(type) {
  return {
    simple_qa: '简单问答',
    minutes: '会议纪要',
    todo: '待办提取',
    controversy: '争议分析',
    complex: '复杂规划',
    qa: '问答',
    multi: '复杂任务',
  }[type] || type || '未知'
}

function getRiskName(level) {
  return {
    low: '低',
    medium: '中',
    high: '高',
    critical: '严重',
  }[level] || level
}

function getConfirmationStatusName(status) {
  return {
    not_required: '无需确认',
    required: '需要确认',
    required_but_disabled: '需要确认但未启用',
    approved: '已确认',
    rejected: '已拒绝',
  }[status] || status
}

function getPolicyCodeName(code) {
  return {
    allowed: '已放行',
    policy_denied: '策略拒绝',
    confirmation_required: '需要确认',
    tool_not_found: '工具不存在',
    non_idempotent_limited: '限制重试',
  }[code] || code
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
  resetExecutionState()
}

function resetExecutionState() {
  // 取消正在进行的 SSE 连接
  if (sseController.value) {
    sseController.value.abort()
    sseController.value = null
  }
  
  result.value = null
  thoughts.value = []
  streamingThoughts.value = []
  intermediateResults.value = []
  pendingConfirmation.value = null
  executed.value = false
  isExecuting.value = false
  isStreaming.value = false
  currentPhase.value = '初始化'
  progressPercent.value = 0
}

async function handleQuery() {
  const question = query.value.trim()
  if (!question) {
    ElMessage.warning('请输入问题')
    return
  }

  resetExecutionState()
  loading.value = true
  isExecuting.value = true

  try {
    const payload = {
      question,
      enable_human_in_the_loop: enableHumanInTheLoop.value,
      enable_tool_calling: true
    }
    if (selectedDocumentIds.value.length > 0) {
      payload.document_ids = selectedDocumentIds.value
    }

    // 创建 AbortController 用于取消 SSE 连接
    sseController.value = new AbortController()

    // 尝试使用流式API
    try {
      await agentApi.queryStream(payload, (data) => {
        handleStreamEvent(data)
      }, sseController.value.signal)
    } catch (streamErr) {
      if (streamErr.name === 'AbortError') {
        return
      }
      console.warn('流式API不可用，使用普通API', streamErr)
      const res = await agentApi.query(payload)
      await handleNonStreamResponse(res)
    }

    executed.value = true
    if (!pendingConfirmation.value) {
      ElMessage.success('Agent 执行成功')
    }
  } catch (e) {
    ElMessage.error('Agent 执行失败: ' + (e.message || '未知错误'))
  } finally {
    loading.value = false
    isExecuting.value = false
    isStreaming.value = false
    sseController.value = null
  }
}

async function handleStreamResponse(stream) {
  const reader = stream.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  isStreaming.value = true

  const parseBufferedEvents = () => {
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    for (const line of lines) {
      const trimmed = line.trim()
      if (!trimmed.startsWith('data: ')) continue

      const dataStr = trimmed.slice(6)
      if (dataStr === '[DONE]') {
        progressPercent.value = 100
        return true
      }

      const data = JSON.parse(dataStr)
      handleStreamEvent(data)
    }

    return false
  }

  while (true) {
    const { done, value } = await reader.read()
    if (done) {
      buffer += decoder.decode()
      if (buffer.trim()) {
        buffer += '\n'
        parseBufferedEvents()
      }
      break
    }

    try {
      buffer += decoder.decode(value, { stream: true })
      if (parseBufferedEvents()) return
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
    currentPhase.value = '完成'
    if (!data.data?.pending_action || data.data?.confirmation_status !== 'required') {
      pendingConfirmation.value = null
    } else {
      if (data.data.pending_action.request_id) {
        pendingConfirmation.value = {
          request_id: data.data.pending_action.request_id,
          details: data.data.pending_action
        }
      } else {
        loadPendingConfirmation()
      }
    }
  } else if (data.type === 'confirmation_required') {
    pendingConfirmation.value = data.data
    loading.value = false
    currentPhase.value = '等待确认'
    ElMessage.warning('高风险操作需要人工确认')
  } else if (data.type === 'error') {
    throw new Error(data.data?.message || 'Agent 流式执行失败')
  }
}

function updateProgress(phase) {
  if (phase === 'plan') {
    currentPhase.value = '规划'
    progressPercent.value = Math.min(progressPercent.value + 5, 33)
  } else if (phase === 'execute') {
    currentPhase.value = '执行'
    progressPercent.value = Math.min(progressPercent.value + 10, 66)
  } else if (phase === 'reflect' || phase === 'replan') {
    currentPhase.value = phase === 'replan' ? '重新规划' : '反思'
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
    currentPhase.value = '重新规划'
    progressPercent.value = 100
  }
  if (data?.pending_action) {
    // 直接使用 pending_action 中的数据
    if (data.confirmation_status !== 'required') {
      pendingConfirmation.value = null
    } else if (data.pending_action.request_id) {
      pendingConfirmation.value = {
        request_id: data.pending_action.request_id,
        details: data.pending_action
      }
    } else {
      await loadPendingConfirmation()
    }
  } else {
    pendingConfirmation.value = null
  }
}

async function loadPendingConfirmation() {
  try {
    const res = await agentApi.getPendingConfirmations()
    const requests = res?.data?.pending_requests || res?.pending_requests || []
    const questionText = result.value?.pending_action?.question || query.value
    pendingConfirmation.value = requests.find(req => req.details?.question === questionText) || requests[0] || null
  } catch (err) {
    console.warn('加载待确认请求失败', err)
  }
}

async function handleContinue() {
  confirmationLoading.value = true
  try {
    if (pendingConfirmationId.value) {
      const res = await agentApi.resumeConfirmation(pendingConfirmationId.value, 'approved')
      const data = res?.data || res
      
      if (data.success) {
        // live_request 模式：原 SSE 连接会继续返回结果，只需清空确认状态
        if (data.mode === 'live_request') {
          pendingConfirmation.value = null
          loading.value = true
          isExecuting.value = true
          currentPhase.value = '执行'
          ElMessage.success('已确认，Agent 将继续执行')
          
          // 添加超时处理：如果30秒内没有收到数据，自动重新执行
          setTimeout(() => {
            if (loading.value && currentPhase.value === '执行' && !pendingConfirmation.value) {
              ElMessage.warning('连接超时，正在重新执行...')
              handleQuery()
            }
          }, 30000)
          
          return
        }
        
        // snapshot 模式：直接使用返回的结果
        if (data.mode === 'snapshot' && data.result) {
          result.value = data.result
          thoughts.value = data.result.thoughts || []
          streamingThoughts.value = data.result.thoughts || []
          pendingConfirmation.value = null
          ElMessage.success('已从确认点恢复执行')
          return
        }
      }
    }
    
    // 回退：直接重新执行，禁用确认
    const question = result.value?.pending_action?.question || query.value
    const newPayload = {
      question,
      document_ids: selectedDocumentIds.value.length > 0 ? selectedDocumentIds.value : undefined,
      enable_human_in_the_loop: false,
      enable_tool_calling: true
    }
    const newRes = await agentApi.query(newPayload)
    await handleNonStreamResponse(newRes)
    pendingConfirmation.value = null
    ElMessage.success('已继续执行')
  } catch (err) {
    ElMessage.error('处理失败: ' + (err.message || '未知错误'))
  } finally {
    confirmationLoading.value = false
  }
}

function handleReject() {
  if (pendingConfirmationId.value) {
    agentApi.resumeConfirmation(pendingConfirmationId.value, 'rejected').catch(() => {})
  }
  pendingConfirmation.value = null
  if (result.value?.pending_action) {
    result.value.pending_action = null
  }
  loading.value = false
  isExecuting.value = false
  ElMessage.info('已拒绝')
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
