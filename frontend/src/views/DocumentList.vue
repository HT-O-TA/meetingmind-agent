<template>
  <div>
    <el-card shadow="never" style="margin-bottom:16px">
      <el-row :gutter="12" align="middle">
        <el-col :span="5">
          <el-select v-model="filters.file_type" placeholder="文件类型" clearable style="width:100%" @change="load">
            <el-option v-for="t in fileTypes" :key="t" :label="t.toUpperCase()" :value="t" />
          </el-select>
        </el-col>
        <el-col :span="5">
          <el-select v-model="filters.status" placeholder="解析状态" clearable style="width:100%" @change="load">
            <el-option label="已上传" value="uploaded" />
            <el-option label="已解析" value="parsed" />
            <el-option label="解析失败" value="failed" />
          </el-select>
        </el-col>
        <el-col :span="5">
          <el-select v-model="filters.meeting_id" placeholder="关联会议" clearable filterable style="width:100%" @change="load">
            <el-option v-for="m in meetings" :key="m.id" :label="m.title" :value="m.id" />
          </el-select>
        </el-col>
        <el-col :span="4">
          <el-button type="primary" @click="load">查询</el-button>
          <el-button @click="resetFilters">重置</el-button>
        </el-col>
        <el-col :span="5" style="text-align:right">
          <el-button type="primary" @click="showUploadDialog = true">上传文档</el-button>
        </el-col>
      </el-row>
    </el-card>

    <el-dialog v-model="showUploadDialog" title="上传文档" width="600px">
      <el-form :model="uploadForm" label-width="100px">
        <el-form-item label="选择文件" required>
          <el-upload
            ref="uploadRef"
            :auto-upload="false"
            :limit="maxFileCount"
            :accept="acceptExtensions"
            :on-change="onFileChange"
            :on-remove="onFileRemove"
            :file-list="fileList"
            multiple
            style="width:100%"
          >
            <el-button>选择文件</el-button>
            <template #tip><div style="color:#999;font-size:12px">支持 {{ fileTypes.join('/') }}，最大 50MB，最多选择{{ maxFileCount }}个文件</div></template>
          </el-upload>
        </el-form-item>
        <el-form-item v-if="selectedFiles.length > 1" label="批量操作">
          <span style="color:#666;font-size:13px">已选择 {{ selectedFiles.length }} 个文件</span>
        </el-form-item>
        <el-form-item label="关联会议">
          <el-select v-model="uploadForm.meeting_id" placeholder="可选" clearable filterable style="width:100%">
            <el-option v-for="m in meetings" :key="m.id" :label="m.title" :value="m.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="部门">
          <el-input v-model="uploadForm.department" placeholder="可选" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="handleUploadCancel">取消</el-button>
        <el-button type="primary" :loading="uploading" @click="handleUploadConfirm">
          {{ selectedFiles.length > 1 ? '批量上传' : '上传' }}
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showEditDialog" title="编辑文档" width="500px">
      <el-form :model="editForm" label-width="100px">
        <el-form-item label="文件名">
          <el-input :value="editingDocument?.original_filename" disabled />
        </el-form-item>
        <el-form-item label="关联会议">
          <el-select v-model="editForm.meeting_id" placeholder="可选" clearable filterable style="width:100%">
            <el-option v-for="m in meetings" :key="m.id" :label="m.title" :value="m.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="部门">
          <el-input v-model="editForm.department" placeholder="可选" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEditDialog = false">取消</el-button>
        <el-button type="primary" :loading="editing" @click="handleEditConfirm">保存</el-button>
      </template>
    </el-dialog>

    <el-table :data="store.documents" v-loading="store.loading" stripe border>
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="original_filename" label="文件名" min-width="200" />
      <el-table-column prop="file_type" label="类型" width="80">
        <template #default="{ row }">
          <el-tag size="small">{{ row.file_type?.toUpperCase() }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="file_size" label="大小" width="100">
        <template #default="{ row }">{{ formatSize(row.file_size) }}</template>
      </el-table-column>
      <el-table-column prop="status" label="状态" width="90">
        <template #default="{ row }">
          <el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="关联会议" width="150">
        <template #default="{ row }">
          {{ getMeetingTitle(row.meeting_id) }}
        </template>
      </el-table-column>
      <el-table-column prop="department" label="部门" width="100">
        <template #default="{ row }">{{ row.department || '-' }}</template>
      </el-table-column>
      <el-table-column prop="created_at" label="上传时间" width="160">
        <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="140">
        <template #default="{ row }">
          <el-button size="small" @click="editDocument(row)">编辑</el-button>
          <el-button size="small" type="danger" @click="remove(row.id)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      style="margin-top:16px;justify-content:flex-end;display:flex"
      :total="store.total" :page-size="pageSize" :current-page="page"
      layout="total, prev, pager, next"
      @current-change="(p) => { page = p; load() }"
    />
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from 'vue'
import { useDocumentStore } from '@/stores/document'
import { meetingApi } from '@/api/meetings'
import { documentApi } from '@/api/documents'
import { ElMessageBox, ElMessage } from 'element-plus'
import { config } from '@/config'

const store = useDocumentStore()
const page = ref(1)
const pageSize = config.pagination.defaultPageSize
const uploading = ref(false)
const editing = ref(false)
const fileTypes = config.upload.allowedExtensions.map(ext => ext.replace('.', ''))

const maxFileCount = computed(() => config.upload.maxFileCount)
const acceptExtensions = computed(() => config.upload.allowedExtensions.join(','))
const filters = reactive({ file_type: '', status: '', meeting_id: '' })
const meetings = ref([])

const showUploadDialog = ref(false)
const uploadRef = ref()
const selectedFiles = ref([])
const fileList = ref([])
const uploadForm = reactive({ meeting_id: null, department: '' })

const showEditDialog = ref(false)
const editingDocument = ref(null)
const editForm = reactive({ meeting_id: null, department: '' })

const statusType = (s) => ({ uploaded: 'info', parsed: 'success', failed: 'danger' }[s] || '')
const statusLabel = (s) => ({ uploaded: '已上传', parsed: '已解析', failed: '解析失败' }[s] || s)
const formatDate = (d) => d ? new Date(d).toLocaleString('zh-CN') : '-'
const formatSize = (b) => {
  if (!b) return '-'
  if (b < 1024) return b + ' B'
  if (b < 1024 * 1024) return (b / 1024).toFixed(1) + ' KB'
  return (b / 1024 / 1024).toFixed(1) + ' MB'
}

function getMeetingTitle(meetingId) {
  if (!meetingId) return '-'
  const m = meetings.value.find(m => m.id === meetingId)
  return m ? m.title : '-'
}

async function loadMeetings() {
  try {
    const res = await meetingApi.list({ page_size: 100 })
    meetings.value = res.data || []
  } catch (e) {
    console.error('加载会议列表失败', e)
  }
}

function load() {
  const params = { page: page.value, page_size: pageSize }
  if (filters.file_type) params.file_type = filters.file_type
  if (filters.status) params.status = filters.status
  if (filters.meeting_id) params.meeting_id = filters.meeting_id
  store.fetchDocuments(params)
}

function resetFilters() {
  filters.file_type = ''; filters.status = ''; filters.meeting_id = ''
  load()
}

function onFileChange(file) {
  const exists = selectedFiles.value.find(f => f.name === file.name && f.size === file.size)
  if (!exists) {
    selectedFiles.value.push(file.raw)
    fileList.value.push({ name: file.name, size: file.size })
  }
}

function onFileRemove(file) {
  selectedFiles.value = selectedFiles.value.filter(f => !(f.name === file.name && f.size === file.size))
  fileList.value = fileList.value.filter(f => !(f.name === file.name && f.size === file.size))
}

function clearUploadState() {
  selectedFiles.value = []
  fileList.value = []
  uploadForm.meeting_id = null
  uploadForm.department = ''
  if (uploadRef.value) {
    uploadRef.value.clearFiles()
  }
}

async function handleUploadConfirm() {
  if (selectedFiles.value.length === 0) {
    ElMessage.warning('请选择文件')
    return
  }
  uploading.value = true
  try {
    const fd = new FormData()
    if (selectedFiles.value.length > 1) {
      selectedFiles.value.forEach(file => {
        fd.append('files', file)
      })
    } else {
      fd.append('file', selectedFiles.value[0])
    }
    if (uploadForm.meeting_id) fd.append('meeting_id', uploadForm.meeting_id)
    if (uploadForm.department) fd.append('department', uploadForm.department)
    
    let result
    if (selectedFiles.value.length > 1) {
      result = await documentApi.batchUpload(fd)
    } else {
      result = await store.uploadDocument(fd)
    }
    
    if (selectedFiles.value.length > 1) {
      const successCount = result.data.success_count || 0
      const failCount = result.data.fail_count || 0
      if (successCount > 0) {
        ElMessage.success(`批量上传完成，成功 ${successCount} 个${failCount > 0 ? `，失败 ${failCount} 个` : ''}`)
      } else {
        ElMessage.error('批量上传失败')
      }
    } else {
      ElMessage.success('上传成功')
    }
    
    showUploadDialog.value = false
    clearUploadState()
    load()
  } catch (e) {
    ElMessage.error(e.message || '上传失败')
  } finally {
    uploading.value = false
  }
}

function handleUploadCancel() {
  showUploadDialog.value = false
  clearUploadState()
}

function editDocument(doc) {
  editingDocument.value = doc
  editForm.meeting_id = doc.meeting_id
  editForm.department = doc.department
  showEditDialog.value = true
}

async function handleEditConfirm() {
  editing.value = true
  try {
    await documentApi.update(editingDocument.value.id, editForm)
    ElMessage.success('更新成功')
    showEditDialog.value = false
    load()
  } catch (e) {
    ElMessage.error(e.message || '更新失败')
  } finally {
    editing.value = false
  }
}

async function remove(id) {
  await ElMessageBox.confirm('确认删除该文档？', '提示', { type: 'warning' })
  await store.removeDocument(id)
}

onMounted(() => {
  load()
  loadMeetings()
})
</script>