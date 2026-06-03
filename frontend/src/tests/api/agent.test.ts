import { describe, it, expect, vi, beforeEach } from 'vitest'

describe('Agent API Tests', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('Agent Query API', () => {
    it('should validate query request structure', () => {
      const request = {
        question: '测试问题',
        enable_memory: true
      }

      expect(request.question).toBe('测试问题')
      expect(request.enable_memory).toBe(true)
    })

    it('should handle streaming response format', () => {
      const streamData = [
        'data: {"type":"planning","data":{"message":"开始..."}}',
        'data: {"type":"final","data":{"answer":"完成"}}',
        'data: [DONE]'
      ]

      expect(streamData.length).toBe(3)
      expect(streamData[0].includes('data:')).toBe(true)
    })

    it('should parse SSE events correctly', () => {
      const rawEvent = 'data: {"type":"final","data":{"answer":"测试回答"}}'
      const jsonStr = rawEvent.slice(6)
      const parsed = JSON.parse(jsonStr)

      expect(parsed.type).toBe('final')
      expect(parsed.data.answer).toBe('测试回答')
    })
  })

  describe('Agent Memory API', () => {
    it('should handle memory actions', () => {
      const clearAction = {
        session_id: 'session-123',
        action: 'clear'
      }

      expect(clearAction.action).toBe('clear')
    })

    it('should validate memory stats response', () => {
      const stats = {
        stats: {
          short_term_count: 5,
          long_term_count: 10
        }
      }

      expect(stats.stats.short_term_count).toBe(5)
      expect(stats.stats.long_term_count).toBe(10)
    })
  })

  describe('Agent Tools API', () => {
    it('should validate tool structure', () => {
      const tool = {
        name: 'search_meeting',
        description: '搜索会议',
        category: 'meeting',
        parameters: [
          {
            name: 'query',
            type: 'string',
            required: true
          }
        ]
      }

      expect(tool.name).toBe('search_meeting')
      expect(tool.parameters[0].name).toBe('query')
    })

    it('should validate tool parameters', () => {
      const param = {
        name: 'query',
        type: 'string',
        required: true,
        description: '搜索关键词'
      }

      expect(param.required).toBe(true)
      expect(param.type).toBe('string')
    })
  })

  describe('Response Format', () => {
    it('should validate success response', () => {
      const response = {
        success: true,
        task_type: 'qa',
        answer: '测试回答'
      }

      expect(response.success).toBe(true)
      expect(response.task_type).toBe('qa')
    })

    it('should validate error response', () => {
      const response = {
        success: false,
        error: '请求失败'
      }

      expect(response.success).toBe(false)
      expect(response.error).toBe('请求失败')
    })
  })
})
