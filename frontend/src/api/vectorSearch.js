import request from './request'

export const vectorSearchApi = {
  search: (data) => request.post('/vector-search/search', data),
  getChunks: (documentId) => request.get(`/vector-search/chunks/${documentId}`),
  getStatus: () => request.get('/vector-search/status'),
}
