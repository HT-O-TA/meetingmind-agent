import request from './request'


export const traceApi = {
  getSpans(limit = 100, operationName = null) {
    return request.get('/trace/spans', {
      params: { limit, operation_name: operationName || undefined },
    })
  },

  getSpan(spanId) {
    return request.get(`/trace/spans/${spanId}`)
  },

  getSummary() {
    return request.get('/trace/summary')
  },
}
