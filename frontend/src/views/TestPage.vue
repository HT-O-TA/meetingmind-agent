<template>
  <div class="test-page">
    <div class="page-header">
      <h1>Agent 测试面板</h1>
      <p class="subtitle">查看和运行 Agent 行为测试与工具调用测试</p>
    </div>

    <div class="test-controls">
      <button @click="runAllTests" :disabled="isRunning" class="btn btn-primary">
        <span v-if="isRunning">运行中...</span>
        <span v-else>运行全部测试</span>
      </button>
      <button @click="runToolTests" :disabled="isRunning" class="btn btn-secondary">
        运行工具调用测试
      </button>
      <button @click="runAgentTests" :disabled="isRunning" class="btn btn-secondary">
        运行Agent行为测试
      </button>
      <button @click="clearResults" class="btn btn-outline">
        清空结果
      </button>
    </div>

    <div v-if="testSummary" class="summary-cards">
      <div class="summary-card" :class="testSummary.success ? 'success' : 'error'">
        <div class="summary-icon">{{ testSummary.success ? '✓' : '✗' }}</div>
        <div class="summary-content">
          <div class="summary-title">{{ testSummary.success ? '全部通过' : '有失败' }}</div>
          <div class="summary-text">
            运行 {{ testSummary.tests_run }} 个测试，
            <span class="passed">{{ testSummary.tests_passed }} 通过</span>，
            <span class="failed">{{ testSummary.tests_failed }} 失败</span>
          </div>
          <div class="summary-duration">耗时: {{ testSummary.duration }}</div>
        </div>
      </div>
    </div>

    <div class="test-results">
      <div class="result-section">
        <h2>测试输出</h2>
        <div class="output-container">
          <pre class="output-text">{{ outputText }}</pre>
        </div>
      </div>

      <div v-if="testResults.length > 0" class="result-section">
        <h2>测试详情</h2>
        <div class="test-list">
          <div 
            v-for="(result, index) in testResults" 
            :key="index" 
            class="test-item"
            :class="result.status"
          >
            <span class="test-status">{{ result.status === 'passed' ? '✓' : '✗' }}</span>
            <span class="test-name">{{ result.name }}</span>
            <span class="test-time">{{ result.time }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import request from '../api/request'

const isRunning = ref(false)
const testSummary = ref(null)
const outputText = ref('')
const testResults = ref([])

const runAllTests = async () => {
  isRunning.value = true
  outputText.value = '正在运行单元测试...\n'
  testResults.value = []
  
  try {
    const response = await request.get('/api/v1/tests/run-unit-tests')
    testSummary.value = response.data.summary
    
    if (response.data.stdout) {
      outputText.value = response.data.stdout
      parseTestResults(response.data.stdout)
    }
    
    if (response.data.stderr) {
      outputText.value += '\n错误输出:\n' + response.data.stderr
    }
  } catch (error) {
    outputText.value = '测试运行失败: ' + (error.message || error)
  } finally {
    isRunning.value = false
  }
}

const runToolTests = async () => {
  isRunning.value = true
  outputText.value = '正在运行工具调用测试...\n'
  
  try {
    const response = await request.get('/api/v1/tests/run-tool-tests')
    
    if (response.data.stdout) {
      outputText.value = response.data.stdout
      parseTestResults(response.data.stdout)
    }
    
    if (response.data.stderr) {
      outputText.value += '\n错误输出:\n' + response.data.stderr
    }
  } catch (error) {
    outputText.value = '测试运行失败: ' + (error.message || error)
  } finally {
    isRunning.value = false
  }
}

const runAgentTests = async () => {
  isRunning.value = true
  outputText.value = '正在运行Agent行为测试...\n'
  
  try {
    const response = await request.get('/api/v1/tests/run-agent-tests')
    
    if (response.data.stdout) {
      outputText.value = response.data.stdout
      parseTestResults(response.data.stdout)
    }
    
    if (response.data.stderr) {
      outputText.value += '\n错误输出:\n' + response.data.stderr
    }
  } catch (error) {
    outputText.value = '测试运行失败: ' + (error.message || error)
  } finally {
    isRunning.value = false
  }
}

const parseTestResults = (stdout) => {
  const lines = stdout.split('\n')
  testResults.value = []
  
  lines.forEach(line => {
    if (line.includes('PASSED') || line.includes('FAILED')) {
      const parts = line.split('::')
      if (parts.length >= 2) {
        const testName = parts.slice(1).join('::').trim()
        const status = line.includes('PASSED') ? 'passed' : 'failed'
        const timeMatch = line.match(/\((\d+\.\d+)s\)/)
        const time = timeMatch ? timeMatch[1] + 's' : ''
        
        testResults.value.push({
          name: testName.replace('PASSED', '').replace('FAILED', '').trim(),
          status,
          time
        })
      }
    }
  })
}

const clearResults = () => {
  outputText.value = ''
  testResults.value = []
  testSummary.value = null
}
</script>

<style scoped>
.test-page {
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

.test-controls {
  display: flex;
  gap: 12px;
  margin-bottom: 24px;
  flex-wrap: wrap;
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

.summary-cards {
  display: flex;
  gap: 16px;
  margin-bottom: 24px;
}

.summary-card {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 20px;
  border-radius: 12px;
  background: #fff;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}

.summary-card.success {
  border-left: 4px solid #10b981;
}

.summary-card.error {
  border-left: 4px solid #ef4444;
}

.summary-icon {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  font-weight: bold;
}

.summary-card.success .summary-icon {
  background: #dcfce7;
  color: #10b981;
}

.summary-card.error .summary-icon {
  background: #fee2e2;
  color: #ef4444;
}

.summary-content {
  flex: 1;
}

.summary-title {
  font-size: 16px;
  font-weight: 600;
  color: #1a1a2e;
  margin-bottom: 4px;
}

.summary-text {
  font-size: 14px;
  color: #666;
  margin-bottom: 4px;
}

.summary-text .passed {
  color: #10b981;
  font-weight: 500;
}

.summary-text .failed {
  color: #ef4444;
  font-weight: 500;
}

.summary-duration {
  font-size: 12px;
  color: #999;
}

.test-results {
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  overflow: hidden;
}

.result-section {
  padding: 20px;
  border-bottom: 1px solid #f0f0f0;
}

.result-section:last-child {
  border-bottom: none;
}

.result-section h2 {
  font-size: 16px;
  font-weight: 600;
  color: #1a1a2e;
  margin: 0 0 16px 0;
}

.output-container {
  background: #1e1e1e;
  border-radius: 8px;
  overflow: hidden;
  max-height: 400px;
  overflow-y: auto;
}

.output-text {
  padding: 16px;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 13px;
  color: #d4d4d4;
  white-space: pre-wrap;
  margin: 0;
}

.test-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.test-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 16px;
  border-radius: 8px;
  background: #f8f9fa;
}

.test-item.passed {
  border-left: 3px solid #10b981;
}

.test-item.failed {
  border-left: 3px solid #ef4444;
}

.test-status {
  font-size: 16px;
  font-weight: bold;
  width: 24px;
}

.test-item.passed .test-status {
  color: #10b981;
}

.test-item.failed .test-status {
  color: #ef4444;
}

.test-name {
  flex: 1;
  font-size: 14px;
  color: #333;
}

.test-time {
  font-size: 12px;
  color: #999;
}

@media (max-width: 768px) {
  .test-controls {
    flex-direction: column;
  }
  
  .btn {
    width: 100%;
  }
  
  .summary-cards {
    flex-direction: column;
  }
}
</style>
