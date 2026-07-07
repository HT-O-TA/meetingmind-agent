import request from './request'

export async function submitFeedback(inputText, outputText, rating = null, comment = null, feedbackType = 'user_comment') {
  return request({
    url: '/api/v1/feedback',
    method: 'post',
    params: {
      input_text: inputText,
      output_text: outputText,
      rating,
      comment,
      feedback_type: feedbackType
    }
  })
}

export async function getFeedbacks(feedbackType = null, limit = 20, offset = 0) {
  const params = new URLSearchParams()
  if (feedbackType) params.append('feedback_type', feedbackType)
  if (limit) params.append('limit', limit)
  if (offset) params.append('offset', offset)
  return request({
    url: `/api/v1/feedback?${params.toString()}`,
    method: 'get'
  })
}

export async function addBadCase(inputText, actualOutput, category, expectedOutput = null, priority = 'medium') {
  return request({
    url: '/api/v1/bad-cases',
    method: 'post',
    params: {
      input_text: inputText,
      actual_output: actualOutput,
      category,
      expected_output: expectedOutput,
      priority
    }
  })
}

export async function getBadCases(category = null, status = null, priority = null, limit = 20, offset = 0) {
  const params = new URLSearchParams()
  if (category) params.append('category', category)
  if (status) params.append('status', status)
  if (priority) params.append('priority', priority)
  if (limit) params.append('limit', limit)
  if (offset) params.append('offset', offset)
  return request({
    url: `/api/v1/bad-cases?${params.toString()}`,
    method: 'get'
  })
}

export async function getBadCase(badCaseId) {
  return request({
    url: `/api/v1/bad-cases/${badCaseId}`,
    method: 'get'
  })
}

export async function updateBadCase(badCaseId, updateData) {
  const params = new URLSearchParams()
  if (updateData.expectedOutput !== undefined) params.append('expected_output', updateData.expectedOutput)
  if (updateData.analysis !== undefined) params.append('analysis', updateData.analysis)
  if (updateData.improvementPlan !== undefined) params.append('improvement_plan', updateData.improvementPlan)
  if (updateData.resolutionStatus !== undefined) params.append('resolution_status', updateData.resolutionStatus)
  if (updateData.priority !== undefined) params.append('priority', updateData.priority)
  return request({
    url: `/api/v1/bad-cases/${badCaseId}?${params.toString()}`,
    method: 'put'
  })
}

export async function analyzeBadCase(badCaseId) {
  return request({
    url: `/api/v1/bad-cases/${badCaseId}/analyze`,
    method: 'post'
  })
}

export async function addImprovement(badCaseId, actionType, description, details = null) {
  return request({
    url: `/api/v1/bad-cases/${badCaseId}/improvements`,
    method: 'post',
    params: {
      action_type: actionType,
      description,
      details
    }
  })
}

export async function verifyImprovement(improvementId, result) {
  return request({
    url: `/api/v1/improvements/${improvementId}/verify`,
    method: 'post',
    params: {
      result
    }
  })
}

export async function getPerformanceReport() {
  return request({
    url: '/api/v1/performance',
    method: 'get'
  })
}

export async function analyzeBadCasePatterns(limit = 10) {
  return request({
    url: `/api/v1/bad-cases/patterns?limit=${limit}`,
    method: 'get'
  })
}
