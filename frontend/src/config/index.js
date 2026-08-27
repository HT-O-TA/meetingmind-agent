/**
 * 前端配置文件
 * 所有可配置项统一管理
 * 
 * 配置优先级：
 * 1. 前端组件传入的参数（最高优先级）
 * 2. 本配置文件中的默认值
 * 3. 后端配置（通过API获取时）
 */

function getDefaultApiBaseUrl() {
  const envBaseUrl = import.meta.env.VITE_API_BASE_URL
  if (envBaseUrl) return envBaseUrl

  if (typeof window === 'undefined') return '/api/v1'

  const { protocol, hostname, port } = window.location
  if (protocol === 'file:') return 'http://127.0.0.1:8000/api/v1'

  if ((hostname === 'localhost' || hostname === '127.0.0.1') && port === '5173') {
    return 'http://127.0.0.1:8000/api/v1'
  }

  return '/api/v1'
}

export const config = {
  // 文件上传配置
  upload: {
    maxFileSize: 52428800, // 50MB（与后端 MAX_FILE_SIZE 一致）
    maxFileCount: 50, // 单次批量上传最大文件数（与后端 MAX_FILE_COUNT 一致）
    allowedExtensions: ['.txt', '.pdf', '.docx', '.md', '.csv', '.xlsx', '.xlsm'], // 允许上传的文件格式（与后端 ALLOWED_FILE_EXTENSIONS 一致）
  },
  
  // API配置
  api: {
    baseUrl: getDefaultApiBaseUrl(), // API基础路径
    timeout: 60000, // 请求超时时间（毫秒）
  },
  
  // 分页配置
  pagination: {
    defaultPageSize: 20, // 默认每页显示数量
    pageSizes: [10, 20, 50, 100], // 可选的每页数量
  },
  
  // 检索配置
  search: {
    defaultTopK: 2, // 默认返回结果数量（与后端 TOP_K_DEFAULT 一致，根据平均相关文档数1.18向上取整）
    similarityThreshold: 0.7, // 相似度阈值（与后端 SIMILARITY_THRESHOLD 一致）
    chunkSize: 512, // 文本切片大小（与后端 CHUNK_SIZE 一致）
    chunkOverlap: 64, // 切片重叠大小（与后端 CHUNK_OVERLAP 一致）
  },
  
  // LLM配置
  llm: {
    maxContextChars: 3000, // 传入LLM的最大上下文字符数（与后端 LLM_MAX_CONTEXT_CHARS 一致）
  },
  
  // UI配置
  ui: {
    tableHeight: 'calc(100vh - 280px)', // 表格高度
    dialogWidth: '500px', // 默认对话框宽度
  },
}

export default config
