import request from './request'

export async function listTasks(taskType = '', status = '', limit = 100) {
  const params = new URLSearchParams()
  if (taskType) params.append('task_type', taskType)
  if (status) params.append('status', status)
  if (limit) params.append('limit', limit)
  return request({
    url: `/api/v1/tasks/?${params.toString()}`,
    method: 'get'
  })
}

export async function getTaskStatus(taskId) {
  return request({
    url: `/api/v1/tasks/${taskId}`,
    method: 'get'
  })
}

export async function cancelTask(taskId) {
  return request({
    url: `/api/v1/tasks/${taskId}`,
    method: 'delete'
  })
}

export async function deleteTask(taskId) {
  return request({
    url: `/api/v1/tasks/${taskId}/purge`,
    method: 'delete'
  })
}

export async function createDocumentTask(documentId, filePath, metadata = null) {
  return request({
    url: '/api/v1/tasks/documents',
    method: 'post',
    data: {
      document_id: documentId,
      file_path: filePath,
      metadata
    }
  })
}

export async function waitTaskComplete(taskId, timeout = 300) {
  return request({
    url: `/api/v1/tasks/${taskId}/wait?timeout=${timeout}`,
    method: 'get'
  })
}
