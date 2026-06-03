import request from './request'

export const meetingApi = {
  list: (params) => request.get('/meetings', { params }),
  get: (id) => request.get(`/meetings/${Number(id)}`),
  create: (data) => request.post('/meetings', data),
  update: (id, data) => request.put(`/meetings/${Number(id)}`, data),
  updateStatus: (id, status) => request.patch(`/meetings/${Number(id)}/status`, null, { params: { status } }),
  remove: (id) => request.delete(`/meetings/${Number(id)}`),
  listSpeeches: (id) => request.get(`/meetings/${Number(id)}/speeches`),
  createSpeech: (id, data) => request.post(`/meetings/${Number(id)}/speeches`, data),
  bulkCreateSpeeches: (id, data) => request.post(`/meetings/${Number(id)}/speeches/bulk`, data),
  updateSpeech: (meetingId, speechId, data) => request.put(`/meetings/${Number(meetingId)}/speeches/${Number(speechId)}`, data),
  deleteSpeech: (meetingId, speechId) => request.delete(`/meetings/${Number(meetingId)}/speeches/${Number(speechId)}`),
}
