import request from './request'

export const embeddingApi = {
  encode: (data) => request.post('/embedding/encode', data),
  batchEncode: (data) => request.post('/embedding/batch-encode', data),
  similarity: (data) => request.post('/embedding/similarity', data),
  status: () => request.get('/embedding/status'),
}
