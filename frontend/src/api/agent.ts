import request from './request'
import { config } from '@/config'

export interface AgentQueryRequest {
  question: string
  meeting_id?: number
  document_ids?: number[]
  session_id?: string
  enable_memory?: boolean
  enable_tool_calling?: boolean
  enable_human_in_the_loop?: boolean
}

export interface AgentResponse {
  success: boolean
  task_type: string
  answer: string
  minutes?: string
  todos?: any[]
  controversies?: any[]
  error?: string
}

export interface ToolInfo {
  name: string
  description: string
  category: string
  parameters?: any[]
}

const agentApi = {
  query(payload: AgentQueryRequest): Promise<AgentResponse> {
    return request.post('/agents/query', payload)
  },

  async queryStream(
    payload: AgentQueryRequest,
    onMessage: (data: any) => void,
    signal?: AbortSignal
  ): Promise<void> {
    const token = localStorage.getItem('token')
    const response = await fetch(`${config.api.baseUrl}/agents/query-stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(payload),
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
            // Ignore malformed events; the UI can fall back to normal query.
          }
        }
      } catch (e: any) {
        if (e.name === 'AbortError') {
          return
        }
        throw e
      }
    }
  },

  batchQuery(requests: AgentQueryRequest[]): Promise<AgentResponse[]> {
    return request.post('/agents/batch', { questions: requests.map(r => r.question) })
      .then(res => res.results)
  },

  clearMemory(sessionId: string): Promise<{ message: string }> {
    return request.post('/agents/memory', {
      session_id: sessionId,
      action: 'clear'
    })
  },

  getMemoryStats(sessionId?: string): Promise<{ stats: any }> {
    return request.get('/agents/memory/stats', {
      params: { session_id: sessionId }
    })
  },

  getTools(): Promise<{ tools: ToolInfo[] }> {
    return request.get('/agents/tools')
  },

  getPrompts(): Promise<{ templates: any[] }> {
    return request.get('/agents/prompts')
  },

  getArchitecture(): Promise<any> {
    return request.get('/agents/architecture')
  },

  getPendingConfirmations(): Promise<{ pending_requests: any[] }> {
    return request.get('/agents/confirmations/pending')
  },

  respondToConfirmation(requestId: string, response: string): Promise<any> {
    return request.post('/agents/confirmations/respond', {
      request_id: requestId,
      response
    })
  },

  getRecentErrors(limit: number = 20): Promise<{ errors: any[] }> {
    return request.get('/agents/errors/recent', {
      params: { limit }
    })
  },

  getMonitorStatus(): Promise<any> {
    return request.get('/agents/monitor/status')
  }
}

export default agentApi
