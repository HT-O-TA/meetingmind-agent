import request from './request'

export const documentApi = {
  list: (params) => request.get('/documents', { params }),
  get: (id) => request.get(`/documents/${Number(id)}`),
  update: (id, data) => request.put(`/documents/${Number(id)}`, data),
  remove: (id) => request.delete(`/documents/${Number(id)}`),
  upload: (formData) =>
    request.post('/documents/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }),
  batchUpload: (formData) =>
    request.post('/documents/batch-upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }),
}
