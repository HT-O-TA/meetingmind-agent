import request from './request'
import { config } from '@/config'

function authHeaders() {
  const token = localStorage.getItem('token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export const agentApi = {
  query(data) {
    return request.post('/agents/query', data)
  },

  async queryStream(data, onMessage, signal) {
    const response = await fetch(`${config.api.baseUrl}/agents/query-stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...authHeaders(),
      },
      body: JSON.stringify(data),
      signal,
    })

    if (!response.ok || !response.body) {
      throw new Error(`流式请求失败: ${response.status}`)
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      try {
        const { done, value } = await reader.read()
        if (done) {
          buffer += decoder.decode()
          return
        }

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          const trimmed = line.trim()
          if (!trimmed.startsWith('data: ')) continue
          const dataStr = trimmed.slice(6)
          if (dataStr === '[DONE]') return

          try {
            onMessage(JSON.parse(dataStr))
          } catch (e) {
            // Ignore malformed events
          }
        }
      } catch (e) {
        if (e.name === 'AbortError') {
          return
        }
        throw e
      }
    }
  },

  batchQuery(data) {
    return request.post('/agents/batch', data)
  },
  
  getPrompts() {
    return request.get('/agents/prompts')
  },
  
  getErrorStats() {
    return request.get('/agents/errors/recent')
  },
  
  getMonitorStatus() {
    return request.get('/agents/monitor/status')
  },

  getPendingConfirmations() {
    return request.get('/agents/confirmations/pending')
  },

  respondConfirmation(requestId, response) {
    return request.post('/agents/confirmations/respond', {
      request_id: requestId,
      response,
    })
  },

  resumeConfirmation(requestId, response = 'approved') {
    return request.post('/agents/confirmations/resume', {
      request_id: requestId,
      response,
    })
  },
}
