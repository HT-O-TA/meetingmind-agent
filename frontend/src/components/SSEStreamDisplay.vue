<template>
  <div class="sse-stream-container">
    <div class="stream-header">
      <span class="stream-title">实时响应</span>
      <div class="stream-controls">
        <el-button
          v-if="isStreaming"
          type="danger"
          size="small"
          @click="stopStream"
        >
          <el-icon><Square /></el-icon>
          停止
        </el-button>
        <el-button
          v-if="!isStreaming && hasContent"
          type="default"
          size="small"
          @click="clearContent"
        >
          <el-icon><Refresh /></el-icon>
          清空
        </el-button>
      </div>
    </div>
    
    <div class="stream-content">
      <div v-if="!hasContent && !isStreaming" class="empty-state">
        <el-icon class="empty-icon"><ChatDotSquare /></el-icon>
        <p>等待响应...</p>
      </div>
      
      <div v-else class="response-content">
        <div
          class="markdown-body"
          v-html="formattedContent"
        />
        
        <div v-if="isStreaming" class="typing-indicator">
          <span class="dot"></span>
          <span class="dot"></span>
          <span class="dot"></span>
        </div>
      </div>
    </div>
    
    <div v-if="error" class="error-message">
      <el-icon><AlertCircle /></el-icon>
      <span>{{ error }}</span>
    </div>
    
    <div class="stream-stats">
      <span class="stat-item">
        <el-icon><Clock /></el-icon>
        {{ formatTime(duration) }}
      </span>
      <span class="stat-item">
        <el-icon><FileText /></el-icon>
        {{ contentLength }} 字符
      </span>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onUnmounted } from 'vue'
import { VideoPause, Refresh, ChatDotSquare, Warning, Clock, Document } from '@element-plus/icons-vue'

const props = defineProps({
  url: {
    type: String,
    default: ''
  },
  method: {
    type: String,
    default: 'GET'
  },
  headers: {
    type: Object,
    default: () => ({})
  },
  body: {
    type: Object,
    default: null
  },
  autoStart: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['streamStart', 'streamEnd', 'streamError', 'tokenReceived'])

const content = ref('')
const isStreaming = ref(false)
const error = ref('')
const startTime = ref(null)
const duration = ref(0)

const hasContent = computed(() => content.value.length > 0)
const contentLength = computed(() => content.value.length)
const formattedContent = computed(() => formatMarkdown(content.value))

let eventSource = null
let timerInterval = null

function formatMarkdown(text) {
  let html = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
  
  html = html.replace(/```(\w+)?\n([\s\S]*?)```/g, (_, lang, code) => {
    return `<pre><code class="language-${lang || 'text'}">${code.trim()}</code></pre>`
  })
  
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>')
  
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>')
  
  html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>')
  html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>')
  html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>')
  
  html = html.replace(/^- (.+)$/gm, '<li>$1</li>')
  html = html.replace(/(<li>.+<\/li>)/g, '<ul>$1</ul>')
  
  html = html.replace(/^(\d+)\. (.+)$/gm, '<li>$1. $2</li>')
  
  html = html.replace(/\n/g, '<br>')
  
  return html
}

function formatTime(ms) {
  if (ms < 1000) return `${ms}ms`
  const seconds = (ms / 1000).toFixed(1)
  return `${seconds}s`
}

function startStream() {
  if (isStreaming.value) return
  
  content.value = ''
  error.value = ''
  isStreaming.value = true
  startTime.value = Date.now()
  
  emit('streamStart')
  
  timerInterval = setInterval(() => {
    if (isStreaming.value && startTime.value) {
      duration.value = Date.now() - startTime.value
    }
  }, 100)
  
  if (props.url.includes('/stream')) {
    startEventSource()
  } else {
    startFetchStream()
  }
}

function startEventSource() {
  try {
    eventSource = new EventSource(props.url, {
      withCredentials: true,
      headers: {
        'Accept': 'text/event-stream',
        ...props.headers
      }
    })
    
    eventSource.onmessage = (event) => {
      if (event.data === '[DONE]') {
        stopStream()
        return
      }
      
      try {
        const data = JSON.parse(event.data)
        if (data.content) {
          content.value += data.content
          emit('tokenReceived', data.content)
        }
      } catch {
        content.value += event.data
        emit('tokenReceived', event.data)
      }
    }
    
    eventSource.onerror = (err) => {
      error.value = `连接错误: ${err.message || '未知错误'}`
      stopStream()
      emit('streamError', error.value)
    }
    
    eventSource.onopen = () => {
      console.log('SSE connection opened')
    }
  } catch (err) {
    error.value = `初始化失败: ${err.message}`
    stopStream()
    emit('streamError', error.value)
  }
}

async function startFetchStream() {
  try {
    const options = {
      method: props.method,
      headers: {
        'Accept': 'text/event-stream',
        'Content-Type': 'application/json',
        ...props.headers
      }
    }
    
    if (props.body) {
      options.body = JSON.stringify(props.body)
    }
    
    const response = await fetch(props.url, options)
    
    if (!response.ok) {
      throw new Error(`HTTP error: ${response.status}`)
    }
    
    const reader = response.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let buffer = ''
    
    while (isStreaming.value) {
      const { done, value } = await reader.read()
      
      if (done) {
        break
      }
      
      buffer += decoder.decode(value, { stream: true })
      
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''
      
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = line.slice(6)
          if (data.trim() === '[DONE]') {
            stopStream()
            return
          }
          try {
            const parsed = JSON.parse(data)
            if (parsed.content) {
              content.value += parsed.content
              emit('tokenReceived', parsed.content)
            }
          } catch {
            content.value += data
            emit('tokenReceived', data)
          }
        }
      }
    }
    
    stopStream()
  } catch (err) {
    error.value = `请求失败: ${err.message}`
    stopStream()
    emit('streamError', error.value)
  }
}

function stopStream() {
  isStreaming.value = false
  
  if (eventSource) {
    eventSource.close()
    eventSource = null
  }
  
  if (timerInterval) {
    clearInterval(timerInterval)
    timerInterval = null
  }
  
  if (startTime.value) {
    duration.value = Date.now() - startTime.value
  }
  
  emit('streamEnd', content.value)
}

function clearContent() {
  content.value = ''
  duration.value = 0
  startTime.value = null
  error.value = ''
}

watch(() => props.autoStart, (newVal) => {
  if (newVal) {
    startStream()
  }
})

onUnmounted(() => {
  stopStream()
})

defineExpose({
  startStream,
  stopStream,
  clearContent,
  content
})
</script>

<style scoped>
.sse-stream-container {
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  overflow: hidden;
}

.stream-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid #eee;
  background: #fafafa;
}

.stream-title {
  font-size: 14px;
  font-weight: 500;
  color: #333;
}

.stream-controls {
  display: flex;
  gap: 8px;
}

.stream-content {
  min-height: 200px;
  max-height: 500px;
  overflow-y: auto;
  padding: 16px;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px;
  color: #999;
}

.empty-icon {
  font-size: 48px;
  margin-bottom: 12px;
}

.empty-state p {
  margin: 0;
  font-size: 14px;
}

.response-content {
  position: relative;
}

.markdown-body {
  font-size: 14px;
  line-height: 1.7;
  color: #333;
  white-space: pre-wrap;
  word-break: break-word;
}

.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3) {
  margin-top: 16px;
  margin-bottom: 8px;
  font-weight: 600;
}

.markdown-body :deep(h1) {
  font-size: 20px;
  border-bottom: 1px solid #eee;
  padding-bottom: 8px;
}

.markdown-body :deep(h2) {
  font-size: 16px;
}

.markdown-body :deep(h3) {
  font-size: 14px;
}

.markdown-body :deep(strong) {
  font-weight: 600;
  color: #333;
}

.markdown-body :deep(em) {
  font-style: italic;
}

.markdown-body :deep(code) {
  background: #f4f4f4;
  padding: 2px 6px;
  border-radius: 4px;
  font-family: monospace;
  font-size: 13px;
  color: #c7254e;
}

.markdown-body :deep(pre) {
  background: #1e1e1e;
  padding: 16px;
  border-radius: 8px;
  overflow-x: auto;
  margin: 12px 0;
}

.markdown-body :deep(pre code) {
  background: none;
  color: #ccc;
  padding: 0;
  font-size: 13px;
}

.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  margin: 8px 0;
  padding-left: 24px;
}

.markdown-body :deep(li) {
  margin-bottom: 4px;
}

.typing-indicator {
  display: inline-flex;
  gap: 4px;
  margin-left: 4px;
}

.typing-indicator .dot {
  width: 6px;
  height: 6px;
  background: #409eff;
  border-radius: 50%;
  animation: typing 1.4s infinite ease-in-out;
}

.typing-indicator .dot:nth-child(1) { animation-delay: 0s; }
.typing-indicator .dot:nth-child(2) { animation-delay: 0.2s; }
.typing-indicator .dot:nth-child(3) { animation-delay: 0.4s; }

@keyframes typing {
  0%, 80%, 100% { transform: scale(0.6); opacity: 0.5; }
  40% { transform: scale(1); opacity: 1; }
}

.error-message {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  background: #fef0f0;
  color: #f56c6c;
  font-size: 13px;
}

.stream-stats {
  display: flex;
  gap: 24px;
  padding: 12px 16px;
  border-top: 1px solid #eee;
  background: #fafafa;
}

.stat-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #999;
}
</style>
