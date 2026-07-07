import request from './request'

export const traceApi = {
  getTraces(params = {}) {
    return request({
      url: '/api/v1/trace/',
      method: 'get',
      params,
    })
  },

  getTrace(traceId) {
    return request({
      url: `/api/v1/trace/${traceId}`,
      method: 'get',
    })
  },

  getTraceBySession(sessionId) {
    return request({
      url: `/api/v1/trace/session/${sessionId}`,
      method: 'get',
    })
  },

  getRecentTraces(limit = 20) {
    return request({
      url: '/api/v1/trace/recent',
      method: 'get',
      params: { limit },
    })
  },

  getTraceStatistics() {
    return request({
      url: '/api/v1/trace/statistics',
      method: 'get',
    })
  },

  getPerformanceReport() {
    return request({
      url: '/api/v1/performance/report',
      method: 'get',
    })
  },

  getAgentStats() {
    return request({
      url: '/api/v1/agent/stats',
      method: 'get',
    })
  },

  getCostSummary() {
    return request({
      url: '/api/v1/cost/summary',
      method: 'get',
    })
  },

  getEvaluationResults(params = {}) {
    return request({
      url: '/api/v1/evaluation/',
      method: 'get',
      params,
    })
  },

  getEvaluationReport() {
    return request({
      url: '/api/v1/evaluation/report',
      method: 'get',
    })
  },
}
