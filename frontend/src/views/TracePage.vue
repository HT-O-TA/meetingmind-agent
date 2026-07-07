<template>
  <div class="trace-page">
    <div class="page-header">
      <h1>Agent Trace Dashboard</h1>
      <p class="subtitle">实时监控 Agent 执行链路和性能指标</p>
    </div>

    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-icon">📊</div>
        <div class="stat-info">
          <div class="stat-value">{{ stats.totalRequests || 0 }}</div>
          <div class="stat-label">总请求数</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon">⚡</div>
        <div class="stat-info">
          <div class="stat-value">{{ stats.avgLatency || 0 }}ms</div>
          <div class="stat-label">平均延迟</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon">💰</div>
        <div class="stat-info">
          <div class="stat-value">${{ stats.totalCost || 0 }}</div>
          <div class="stat-label">总费用</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon">✅</div>
        <div class="stat-info">
          <div class="stat-value">{{ stats.successRate || 0 }}%</div>
          <div class="stat-label">成功率</div>
        </div>
      </div>
    </div>

    <div class="main-content">
      <div class="left-panel">
        <div class="panel-header">
          <h2>最近追踪记录</h2>
          <button @click="loadRecentTraces" class="refresh-btn">🔄 刷新</button>
        </div>
        <div class="trace-list">
          <div
            v-for="trace in recentTraces"
            :key="trace.trace_id"
            class="trace-item"
            :class="{ active: selectedTrace?.trace_id === trace.trace_id }"
            @click="selectTrace(trace)"
          >
            <div class="trace-header">
              <span class="trace-id">{{ trace.trace_id }}</span>
              <span class="trace-status" :class="trace.status">
                {{ trace.status === 'success' ? '✓' : '✗' }}
              </span>
            </div>
            <div class="trace-summary">{{ truncate(trace.summary || trace.question, 50) }}</div>
            <div class="trace-meta">
              <span class="meta-item">⏱️ {{ trace.duration_ms }}ms</span>
              <span class="meta-item">💵 ${{ trace.cost_usd }}</span>
              <span class="meta-item">📝 {{ trace.total_tokens }} tokens</span>
            </div>
          </div>
        </div>
      </div>

      <div class="right-panel" v-if="selectedTrace">
        <div class="panel-header">
          <h2>Trace 详情: {{ selectedTrace.trace_id }}</h2>
          <div class="trace-actions">
            <button @click="viewFullTrace(selectedTrace)">📋 查看完整</button>
          </div>
        </div>

        <div class="detail-section">
          <h3>基本信息</h3>
          <div class="info-grid">
            <div class="info-item">
              <label>问题</label>
              <span>{{ selectedTrace.question }}</span>
            </div>
            <div class="info-item">
              <label>回答</label>
              <span>{{ truncate(selectedTrace.answer, 100) }}</span>
            </div>
            <div class="info-item">
              <label>状态</label>
              <span :class="selectedTrace.status">{{ selectedTrace.status }}</span>
            </div>
            <div class="info-item">
              <label>持续时间</label>
              <span>{{ selectedTrace.duration_ms }}ms</span>
            </div>
            <div class="info-item">
              <label>总 Tokens</label>
              <span>{{ selectedTrace.total_tokens }}</span>
            </div>
            <div class="info-item">
              <label>费用</label>
              <span>${{ selectedTrace.cost_usd }}</span>
            </div>
          </div>
        </div>

        <div class="detail-section">
          <h3>执行时间线</h3>
          <div class="timeline">
            <div
              v-for="(step, index) in selectedTrace.steps"
              :key="step.step_id || index"
              class="timeline-item"
            >
              <div class="timeline-dot" :class="step.type"></div>
              <div class="timeline-content">
                <div class="timeline-header">
                  <span class="step-type" :class="step.type">{{ step.type }}</span>
                  <span class="step-status">{{ step.status }}</span>
                  <span class="step-duration">{{ step.latency_ms }}ms</span>
                </div>
                <div class="step-details" v-if="step.prompt || step.tool_name">
                  <div v-if="step.tool_name" class="step-tool">
                    <strong>工具:</strong> {{ step.tool_name }}
                  </div>
                  <div v-if="step.prompt" class="step-prompt">
                    <strong>Prompt:</strong> {{ truncate(step.prompt, 150) }}
                  </div>
                  <div v-if="step.output" class="step-output">
                    <strong>输出:</strong> {{ truncate(step.output, 150) }}
                  </div>
                  <div v-if="step.tokens_used" class="step-tokens">
                    Tokens: {{ step.tokens_used }} | Cost: ${{ step.cost_usd }}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="detail-section">
          <h3>工具调用</h3>
          <div class="tool-calls" v-if="selectedTrace.tool_calls && selectedTrace.tool_calls.length">
            <div
              v-for="(call, index) in selectedTrace.tool_calls"
              :key="index"
              class="tool-call-item"
            >
              <div class="tool-header">
                <span class="tool-name">{{ call.tool_name }}</span>
                <span class="tool-status" :class="call.success">{{ call.success ? '✓' : '✗' }}</span>
              </div>
              <div class="tool-params">
                <strong>参数:</strong> {{ JSON.stringify(call.params) }}
              </div>
              <div class="tool-result">
                <strong>结果:</strong> {{ truncate(JSON.stringify(call.result), 200) }}
              </div>
            </div>
          </div>
          <div v-else class="empty-state">暂无工具调用记录</div>
        </div>

        <div class="detail-section">
          <h3>Token 使用</h3>
          <div class="token-breakdown">
            <div class="token-item">
              <div class="token-bar">
                <div class="token-fill" :style="{ width: (selectedTrace.prompt_tokens / selectedTrace.total_tokens * 100) + '%' }"></div>
              </div>
              <span class="token-label">Prompt: {{ selectedTrace.prompt_tokens }}</span>
            </div>
            <div class="token-item">
              <div class="token-bar answer">
                <div class="token-fill" :style="{ width: (selectedTrace.answer_tokens / selectedTrace.total_tokens * 100) + '%' }"></div>
              </div>
              <span class="token-label">Answer: {{ selectedTrace.answer_tokens }}</span>
            </div>
            <div class="token-item">
              <div class="token-bar tool">
                <div class="token-fill" :style="{ width: ((selectedTrace.total_tokens - selectedTrace.prompt_tokens - selectedTrace.answer_tokens) / selectedTrace.total_tokens * 100) + '%' }"></div>
              </div>
              <span class="token-label">工具: {{ selectedTrace.total_tokens - selectedTrace.prompt_tokens - selectedTrace.answer_tokens }}</span>
            </div>
          </div>
        </div>
      </div>

      <div class="right-panel empty" v-else>
        <div class="empty-content">
          <div class="empty-icon">🔍</div>
          <p>选择一条追踪记录查看详情</p>
        </div>
      </div>
    </div>

    <div class="bottom-section">
      <div class="section-header">
        <h2>性能报告</h2>
      </div>
      <div class="report-grid">
        <div class="report-card">
          <h3>延迟分布</h3>
          <div class="latency-chart">
            <div class="latency-bar">
              <div class="bar-fill p50" :style="{ height: (report.p50_latency_ms / report.p99_latency_ms * 100) + '%' }"></div>
              <span>P50</span>
            </div>
            <div class="latency-bar">
              <div class="bar-fill p95" :style="{ height: (report.p95_latency_ms / report.p99_latency_ms * 100) + '%' }"></div>
              <span>P95</span>
            </div>
            <div class="latency-bar">
              <div class="bar-fill p99" :style="{ height: '100%' }"></div>
              <span>P99</span>
            </div>
          </div>
          <div class="latency-values">
            <span>P50: {{ report.p50_latency_ms }}ms</span>
            <span>P95: {{ report.p95_latency_ms }}ms</span>
            <span>P99: {{ report.p99_latency_ms }}ms</span>
          </div>
        </div>
        <div class="report-card">
          <h3>QPS</h3>
          <div class="qps-display">
            <div class="qps-value">{{ report.qps_1min }}</div>
            <div class="qps-label">1分钟平均</div>
          </div>
          <div class="qps-details">
            <span>5min: {{ report.qps_5min }}</span>
            <span>15min: {{ report.qps_15min }}</span>
          </div>
        </div>
        <div class="report-card">
          <h3>缓存命中率</h3>
          <div class="cache-display">
            <div class="cache-circle">
              <div class="cache-inner" :style="{ '--percent': report.cache_hit_rate * 100 }">
                {{ (report.cache_hit_rate * 100).toFixed(1) }}%
              </div>
            </div>
          </div>
        </div>
        <div class="report-card">
          <h3>成本统计</h3>
          <div class="cost-item">
            <span class="cost-label">今日费用</span>
            <span class="cost-value">${{ costSummary.today_cost_usd }}</span>
          </div>
          <div class="cost-item">
            <span class="cost-label">本月费用</span>
            <span class="cost-value">${{ costSummary.monthly_cost_usd }}</span>
          </div>
          <div class="cost-item">
            <span class="cost-label">模型</span>
            <span class="cost-value">{{ costSummary.current_model }}</span>
          </div>
        </div>
      </div>
    </div>

    <div class="bottom-section">
      <div class="section-header">
        <h2>Agent 评估</h2>
      </div>
      <div class="evaluation-grid">
        <div class="eval-card">
          <div class="eval-icon">🎯</div>
          <div class="eval-info">
            <div class="eval-value">{{ evalReport.task_success_rate }}%</div>
            <div class="eval-label">任务成功率</div>
          </div>
        </div>
        <div class="eval-card">
          <div class="eval-icon">🔧</div>
          <div class="eval-info">
            <div class="eval-value">{{ evalReport.tool_success_rate }}%</div>
            <div class="eval-label">工具成功率</div>
          </div>
        </div>
        <div class="eval-card">
          <div class="eval-icon">📐</div>
          <div class="eval-info">
            <div class="eval-value">{{ evalReport.route_accuracy }}%</div>
            <div class="eval-label">路由准确率</div>
          </div>
        </div>
        <div class="eval-card">
          <div class="eval-icon">🔄</div>
          <div class="eval-info">
            <div class="eval-value">{{ evalReport.avg_reflection_count }}</div>
            <div class="eval-label">平均反思次数</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>import { ref, onMounted } from 'vue';
import { traceApi } from '@/api/trace';
const stats = ref({});
const recentTraces = ref([]);
const selectedTrace = ref(null);
const report = ref({
 p50_latency_ms: 0,
 p95_latency_ms: 0,
 p99_latency_ms: 0,
 qps_1min: 0,
 qps_5min: 0,
 qps_15min: 0,
 cache_hit_rate: 0,
});
const costSummary = ref({
 today_cost_usd: 0,
 monthly_cost_usd: 0,
 current_model: 'unknown',
});
const evalReport = ref({
 task_success_rate: 0,
 tool_success_rate: 0,
 route_accuracy: 0,
 avg_reflection_count: 0,
});
const truncate = (str, len) => {
 if (!str)
 return '';
 return str.length > len ? str.substring(0, len) + '...' : str;
};
const loadRecentTraces = async () => {
 try {
 const res = await traceApi.getRecentTraces(20);
 recentTraces.value = res.data || [];
 }
 catch (error) {
 console.error('加载追踪记录失败:', error);
 }
};
const selectTrace = (trace) => {
 selectedTrace.value = trace;
};
const viewFullTrace = async (trace) => {
 try {
 const res = await traceApi.getTrace(trace.trace_id);
 selectedTrace.value = res.data;
 }
 catch (error) {
 console.error('加载完整追踪失败:', error);
 }
};
const loadStats = async () => {
 try {
 const res = await traceApi.getTraceStatistics();
 stats.value = res.data || {};
 }
 catch (error) {
 console.error('加载统计数据失败:', error);
 }
};
const loadPerformanceReport = async () => {
 try {
 const res = await traceApi.getPerformanceReport();
 report.value = res.data || {};
 }
 catch (error) {
 console.error('加载性能报告失败:', error);
 }
};
const loadCostSummary = async () => {
 try {
 const res = await traceApi.getCostSummary();
 costSummary.value = res.data || {};
 }
 catch (error) {
 console.error('加载成本摘要失败:', error);
 }
};
const loadEvaluationReport = async () => {
 try {
 const res = await traceApi.getEvaluationReport();
 evalReport.value = res.data || {};
 }
 catch (error) {
 console.error('加载评估报告失败:', error);
 }
};
onMounted(() => {
 loadRecentTraces();
 loadStats();
 loadPerformanceReport();
 loadCostSummary();
 loadEvaluationReport();
});
</script>

<style scoped>
.trace-page {
  padding: 24px;
  background: #f5f7fa;
  min-height: 100vh;
}

.page-header {
  margin-bottom: 24px;
}

.page-header h1 {
  font-size: 28px;
  font-weight: 700;
  color: #1a1a2e;
  margin: 0;
}

.page-header .subtitle {
  color: #6b7280;
  margin: 8px 0 0;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 24px;
}

.stat-card {
  background: white;
  border-radius: 12px;
  padding: 20px;
  display: flex;
  align-items: center;
  gap: 16px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.stat-icon {
  font-size: 32px;
}

.stat-info {
  flex: 1;
}

.stat-value {
  font-size: 24px;
  font-weight: 700;
  color: #1a1a2e;
}

.stat-label {
  font-size: 14px;
  color: #6b7280;
}

.main-content {
  display: grid;
  grid-template-columns: 320px 1fr;
  gap: 20px;
  margin-bottom: 24px;
}

.left-panel, .right-panel {
  background: white;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  overflow: hidden;
}

.right-panel.empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 400px;
}

.empty-content {
  text-align: center;
  color: #9ca3af;
}

.empty-icon {
  font-size: 48px;
  margin-bottom: 16px;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid #e5e7eb;
}

.panel-header h2 {
  font-size: 16px;
  font-weight: 600;
  color: #1a1a2e;
  margin: 0;
}

.refresh-btn {
  background: #f3f4f6;
  border: none;
  border-radius: 8px;
  padding: 8px 12px;
  font-size: 14px;
  cursor: pointer;
}

.trace-list {
  max-height: 600px;
  overflow-y: auto;
}

.trace-item {
  padding: 16px;
  border-bottom: 1px solid #f3f4f6;
  cursor: pointer;
  transition: background 0.2s;
}

.trace-item:hover, .trace-item.active {
  background: #f9fafb;
}

.trace-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.trace-id {
  font-size: 12px;
  font-family: monospace;
  color: #6b7280;
}

.trace-status {
  font-size: 14px;
}

.trace-status.success {
  color: #10b981;
}

.trace-status.failed {
  color: #ef4444;
}

.trace-summary {
  font-size: 14px;
  color: #1a1a2e;
  margin-bottom: 8px;
}

.trace-meta {
  display: flex;
  gap: 12px;
}

.meta-item {
  font-size: 12px;
  color: #9ca3af;
}

.detail-section {
  padding: 20px;
  border-bottom: 1px solid #f3f4f6;
}

.detail-section:last-child {
  border-bottom: none;
}

.detail-section h3 {
  font-size: 14px;
  font-weight: 600;
  color: #1a1a2e;
  margin: 0 0 16px;
}

.info-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.info-item {
  background: #f9fafb;
  border-radius: 8px;
  padding: 12px;
}

.info-item label {
  display: block;
  font-size: 12px;
  color: #9ca3af;
  margin-bottom: 4px;
}

.info-item span {
  font-size: 14px;
  color: #1a1a2e;
  word-break: break-all;
}

.timeline {
  position: relative;
  padding-left: 24px;
}

.timeline::before {
  content: '';
  position: absolute;
  left: 6px;
  top: 0;
  bottom: 0;
  width: 2px;
  background: #e5e7eb;
}

.timeline-item {
  position: relative;
  margin-bottom: 20px;
}

.timeline-dot {
  position: absolute;
  left: -20px;
  top: 4px;
  width: 12px;
  height: 12px;
  border-radius: 50%;
}

.timeline-dot.planner {
  background: #8b5cf6;
}

.timeline-dot.retriever {
  background: #3b82f6;
}

.timeline-dot.tool {
  background: #10b981;
}

.timeline-dot.llm {
  background: #f59e0b;
}

.timeline-dot.reflection {
  background: #ef4444;
}

.timeline-content {
  background: #f9fafb;
  border-radius: 8px;
  padding: 12px;
}

.timeline-header {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
}

.step-type {
  font-size: 12px;
  font-weight: 500;
  padding: 2px 8px;
  border-radius: 4px;
}

.step-type.planner {
  background: #ede9fe;
  color: #7c3aed;
}

.step-type.retriever {
  background: #dbeafe;
  color: #2563eb;
}

.step-type.tool {
  background: #d1fae5;
  color: #059669;
}

.step-type.llm {
  background: #fef3c7;
  color: #d97706;
}

.step-type.reflection {
  background: #fee2e2;
  color: #dc2626;
}

.step-status {
  font-size: 12px;
  color: #10b981;
}

.step-duration {
  font-size: 12px;
  color: #6b7280;
  margin-left: auto;
}

.step-details {
  font-size: 13px;
  color: #4b5563;
}

.step-tool, .step-prompt, .step-output, .step-tokens {
  margin-bottom: 4px;
}

.tool-calls {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.tool-call-item {
  background: #f9fafb;
  border-radius: 8px;
  padding: 12px;
}

.tool-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.tool-name {
  font-size: 14px;
  font-weight: 600;
  color: #1a1a2e;
}

.tool-status {
  font-size: 14px;
}

.tool-status.true {
  color: #10b981;
}

.tool-status.false {
  color: #ef4444;
}

.tool-params, .tool-result {
  font-size: 13px;
  color: #4b5563;
  margin-bottom: 4px;
  word-break: break-all;
}

.token-breakdown {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.token-item {
  display: flex;
  align-items: center;
  gap: 12px;
}

.token-bar {
  flex: 1;
  height: 20px;
  background: #e5e7eb;
  border-radius: 4px;
  overflow: hidden;
}

.token-fill {
  height: 100%;
  background: #8b5cf6;
  border-radius: 4px;
  transition: width 0.3s;
}

.token-bar.answer .token-fill {
  background: #3b82f6;
}

.token-bar.tool .token-fill {
  background: #10b981;
}

.token-label {
  font-size: 13px;
  color: #6b7280;
  min-width: 100px;
}

.bottom-section {
  background: white;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  padding: 20px;
  margin-bottom: 24px;
}

.section-header h2 {
  font-size: 18px;
  font-weight: 600;
  color: #1a1a2e;
  margin: 0 0 16px;
}

.report-grid, .evaluation-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}

.report-card, .eval-card {
  background: #f9fafb;
  border-radius: 8px;
  padding: 16px;
  text-align: center;
}

.report-card h3 {
  font-size: 14px;
  font-weight: 600;
  color: #6b7280;
  margin: 0 0 12px;
}

.latency-chart {
  display: flex;
  justify-content: center;
  gap: 24px;
  height: 80px;
  align-items: flex-end;
  margin-bottom: 12px;
}

.latency-bar {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

.bar-fill {
  width: 30px;
  border-radius: 4px;
  transition: height 0.3s;
}

.bar-fill.p50 {
  background: #10b981;
}

.bar-fill.p95 {
  background: #f59e0b;
}

.bar-fill.p99 {
  background: #ef4444;
}

.latency-values {
  display: flex;
  justify-content: center;
  gap: 24px;
  font-size: 12px;
  color: #6b7280;
}

.qps-display {
  margin-bottom: 8px;
}

.qps-value {
  font-size: 32px;
  font-weight: 700;
  color: #3b82f6;
}

.qps-label {
  font-size: 12px;
  color: #6b7280;
}

.qps-details {
  display: flex;
  justify-content: center;
  gap: 16px;
  font-size: 12px;
  color: #6b7280;
}

.cache-circle {
  width: 80px;
  height: 80px;
  border-radius: 50%;
  background: conic-gradient(
    #3b82f6 calc(var(--percent) * 1%),
    #e5e7eb calc(var(--percent) * 1%)
  );
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 8px;
}

.cache-inner {
  width: 60px;
  height: 60px;
  border-radius: 50%;
  background: white;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 700;
  color: #3b82f6;
}

.cost-item {
  display: flex;
  justify-content: space-between;
  padding: 8px 0;
  border-bottom: 1px solid #e5e7eb;
}

.cost-item:last-child {
  border-bottom: none;
}

.cost-label {
  font-size: 13px;
  color: #6b7280;
}

.cost-value {
  font-size: 13px;
  font-weight: 600;
  color: #1a1a2e;
}

.eval-icon {
  font-size: 28px;
  margin-bottom: 8px;
}

.eval-value {
  font-size: 24px;
  font-weight: 700;
  color: #1a1a2e;
}

.eval-label {
  font-size: 13px;
  color: #6b7280;
}

.trace-actions {
  display: flex;
  gap: 8px;
}

.trace-actions button {
  background: #3b82f6;
  color: white;
  border: none;
  border-radius: 8px;
  padding: 6px 12px;
  font-size: 13px;
  cursor: pointer;
}

.empty-state {
  text-align: center;
  color: #9ca3af;
  padding: 20px;
}
</style>
