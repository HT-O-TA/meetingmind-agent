import request from './request'

export const todoApi = {
  list: (params) => request.get('/todos', { params }),
  get: (id) => request.get(`/todos/${Number(id)}`),
  create: (data) => request.post('/todos', data),
  bulkCreate: (data) => request.post('/todos/bulk', data),
  update: (id, data) => request.put(`/todos/${Number(id)}`, data),
  remove: (id) => request.delete(`/todos/${Number(id)}`),
  stats: (params) => request.get('/todos/summary/stats', { params }),
}
