import axios from 'axios'
import { ElMessage } from 'element-plus'
import { config } from '@/config'

const request = axios.create({
  baseURL: config.api.baseUrl,
  timeout: config.api.timeout,
})

function normalizeApiUrl(url = '') {
  if (!url.startsWith('/api/v1')) return url
  const normalized = url.slice('/api/v1'.length)
  return normalized || '/'
}

// 请求拦截器 - 添加日志
request.interceptors.request.use((config) => {
  config.url = normalizeApiUrl(config.url)

  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  
  // 打印请求日志
  console.log(`%c[REQUEST] ${config.method?.toUpperCase()} ${config.url}`, 'color: #409eff; font-weight: bold')
  console.log('请求基址:', config.baseURL)
  if (config.data) {
    console.log('请求体:', config.data)
  }
  
  return config
})

// 响应拦截器 - 添加日志
request.interceptors.response.use(
  (res) => {
    // 打印响应日志
    const config = res.config
    console.log(`%c[RESPONSE] ${config.method?.toUpperCase()} ${config.url} [200]`, 'color: #67c23a; font-weight: bold')
    if (res.data) {
      console.log('响应体:', res.data)
    }
    return res.data
  },
  (err) => {
    const config = err.config
    const status = err.response?.status || 500
    const msg = err.code === 'ECONNABORTED'
      ? `请求超时：${config?.baseURL || ''}${config?.url || ''}`
      : err.response?.data?.message || err.message || '请求失败'
    
    // 打印错误日志
    console.log(`%c[ERROR] ${config?.method?.toUpperCase()} ${config?.url} [${status}]`, 'color: #f56c6c; font-weight: bold')
    console.log('错误信息:', msg)
    
    ElMessage.error(msg)
    return Promise.reject(err)
  }
)

export default request
