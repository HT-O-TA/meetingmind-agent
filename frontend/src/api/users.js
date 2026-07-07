import request from './request'

export const userApi = {
  register: (data) => request.post('/users/register', data),
  login: (data) => request.post('/users/login', data, { timeout: 10000 }),
  getMe: () => request.get('/users/me'),
  updateMe: (data) => request.put('/users/me', data),
  list: (params) => request.get('/users', { params }),
  create: (data) => request.post('/users', data),
  update: (id, data) => request.put(`/users/${id}`, data),
  remove: (id) => request.delete(`/users/${id}`),
  updatePermissions: (id, data) => request.put(`/users/${id}/permissions`, data),
}
