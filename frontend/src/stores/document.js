import { defineStore } from 'pinia'
import { ref } from 'vue'
import { documentApi } from '@/api/documents'
import { ElMessage } from 'element-plus'

export const useDocumentStore = defineStore('document', () => {
  const documents = ref([])
  const total = ref(0)
  const loading = ref(false)

  async function fetchDocuments(params = {}) {
    loading.value = true
    try {
      const res = await documentApi.list(params)
      documents.value = res.data || []
      total.value = res.total || 0
    } finally {
      loading.value = false
    }
  }

  async function uploadDocument(formData) {
    const res = await documentApi.upload(formData)
    documents.value.unshift(res.data)
    total.value++
    ElMessage.success('上传成功')
    return res.data
  }

  async function removeDocument(id) {
    await documentApi.remove(id)
    documents.value = documents.value.filter(d => d.id !== id)
    total.value--
    ElMessage.success('删除成功')
  }

  return { documents, total, loading, fetchDocuments, uploadDocument, removeDocument }
})
