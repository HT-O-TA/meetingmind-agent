import request from './request'

export async function getGraphStatistics() {
  return request({
    url: '/api/v1/graph/statistics',
    method: 'get'
  })
}

export async function getEntitySubgraph(entityName, depth = 2) {
  return request({
    url: `/api/v1/graph/entity/${encodeURIComponent(entityName)}?depth=${depth}`,
    method: 'get'
  })
}

export async function buildGraph() {
  return request({
    url: '/api/v1/graph/build',
    method: 'post'
  })
}

export async function saveGraph() {
  return request({
    url: '/api/v1/graph/save',
    method: 'post'
  })
}

export async function loadGraph() {
  return request({
    url: '/api/v1/graph/load',
    method: 'post'
  })
}

export async function syncGraph() {
  return request({
    url: '/api/v1/graph/sync',
    method: 'post'
  })
}

export async function clearGraph() {
  return request({
    url: '/api/v1/graph/clear',
    method: 'delete'
  })
}

export async function buildAndSaveGraph() {
  return request({
    url: '/api/v1/graph/build-and-save',
    method: 'post'
  })
}

export async function searchGraphEntities(query) {
  return request({
    url: `/api/v1/graph/search?query=${encodeURIComponent(query)}`,
    method: 'get'
  })
}
