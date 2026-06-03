import request from './request'

export const userApi = {
  register: (data) => request.post('/users/register', data),
  login: (data) => request.post('/users/login', data),
  getMe: () => request.get('/users/me'),
  updateMe: (data) => request.put('/users/me', data),
  list: (params) => request.get('/users', { params }),
}
