import request from './request'

export const userApi = {
  register: (data) => request.post('/users/register', data),
  login: (data) => request.post('/users/login', data, { timeout: 10000 }),
  getMe: () => request.get('/users/me'),
}
