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

  async queryStream(data) {
    const response = await fetch(`${config.api.baseUrl}/agents/query-stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...authHeaders(),
      },
      body: JSON.stringify(data),
    })

    if (!response.ok || !response.body) {
      throw new Error(`流式请求失败: ${response.status}`)
    }

    return response
  },

  batchQuery(data) {
    return request.post('/agents/batch', data)
  },
  
  getPrompts() {
    return request.get('/agents/prompts')
  },
  
  getErrorStats() {
    return request.get('/agents/error-stats')
  },
  
  getMonitorStatus() {
    return request.get('/agents/monitor-status')
  },
}
