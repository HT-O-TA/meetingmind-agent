import request from './request'

export const ragApi = {
  ask: (data) => request.post('/rag/ask', data),
}
