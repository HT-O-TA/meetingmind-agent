<template>
  <div>
    <el-card shadow="never" style="margin-bottom:16px">
      <el-row :gutter="12" align="middle">
        <el-col :span="8">
          <el-input v-model="filters.keyword" placeholder="搜索用户名/邮箱/姓名" clearable @keyup.enter="load" />
        </el-col>
        <el-col :span="6">
          <el-button type="primary" @click="load">查询</el-button>
          <el-button @click="resetFilters">重置</el-button>
        </el-col>
        <el-col :span="10" style="text-align:right">
          <el-button type="primary" @click="showAddDialog = true">新增用户</el-button>
        </el-col>
      </el-row>
    </el-card>

    <el-table :data="users" v-loading="loading" stripe border>
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="username" label="用户名" width="120" />
      <el-table-column prop="email" label="邮箱" width="200" />
      <el-table-column prop="full_name" label="姓名" width="120">
        <template #default="{ row }">{{ row.full_name || '-' }}</template>
      </el-table-column>
      <el-table-column prop="department" label="部门" width="120">
        <template #default="{ row }">{{ row.department || '-' }}</template>
      </el-table-column>
      <el-table-column prop="role" label="角色" width="100">
        <template #default="{ row }">
          <el-tag :type="getRoleTagType(row.role)" size="small">{{ getRoleLabel(row.role) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="注册时间" width="160">
        <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="200">
        <template #default="{ row }">
          <el-button size="small" @click="editUser(row)">编辑</el-button>
          <el-button size="small" @click="managePermissions(row)">权限</el-button>
          <el-button size="small" type="danger" @click="deleteUser(row.id)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      style="margin-top:16px;justify-content:flex-end;display:flex"
      :total="total" :page-size="pageSize" :current-page="page"
      layout="total, prev, pager, next"
      @current-change="(p) => { page = p; load() }"
    />

    <el-dialog v-model="showAddDialog" :title="editingUser ? '编辑用户' : '新增用户'" width="500px">
      <el-form :model="userForm" label-width="100px">
        <el-form-item label="用户名" required>
          <el-input v-model="userForm.username" :disabled="!!editingUser" />
        </el-form-item>
        <el-form-item label="邮箱" required>
          <el-input v-model="userForm.email" type="email" />
        </el-form-item>
        <el-form-item label="密码" :required="!editingUser">
          <el-input v-model="userForm.password" type="password" :placeholder="editingUser ? '不填则保持不变' : '请输入密码'" />
        </el-form-item>
        <el-form-item label="姓名">
          <el-input v-model="userForm.full_name" />
        </el-form-item>
        <el-form-item label="部门">
          <el-input v-model="userForm.department" />
        </el-form-item>
        <el-form-item label="角色" required>
          <el-select v-model="userForm.role">
            <el-option label="管理员" value="admin" />
            <el-option label="普通用户" value="user" />
            <el-option label="只读用户" value="readonly" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="closeDialog">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveUser">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showPermissionDialog" title="权限管理" width="600px">
      <div v-if="currentUser">
        <div style="margin-bottom: 16px; padding: 12px; background: #f5f7fa; border-radius: 4px;">
          <div><strong>用户：</strong>{{ currentUser.username }}</div>
          <div><strong>当前角色：</strong>{{ getRoleLabel(currentUser.role) }}</div>
        </div>

        <div class="permission-section">
          <h4 style="margin-bottom: 12px;">功能权限</h4>
          <el-tree
            :data="permissionTree"
            show-checkbox
            default-expand-all
            node-key="id"
            :checked-keys="selectedPermissions"
            @check-change="handlePermissionChange"
          />
        </div>
      </div>
      <template #footer>
        <el-button @click="showPermissionDialog = false">取消</el-button>
        <el-button type="primary" :loading="savingPermissions" @click="savePermissions">保存权限</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { userApi } from '@/api/users'
import { ElMessage, ElMessageBox } from 'element-plus'

const users = ref([])
const loading = ref(false)
const page = ref(1)
const pageSize = 20
const total = ref(0)
const filters = reactive({ keyword: '' })

const showAddDialog = ref(false)
const showPermissionDialog = ref(false)
const editingUser = ref(null)
const currentUser = ref(null)
const saving = ref(false)
const savingPermissions = ref(false)

const userForm = reactive({
  username: '',
  email: '',
  password: '',
  full_name: '',
  department: '',
  role: 'user'
})

const selectedPermissions = ref([])

const permissionTree = ref([
  {
    id: 'meeting',
    label: '会议管理',
    children: [
      { id: 'meeting_view', label: '查看会议' },
      { id: 'meeting_create', label: '创建会议' },
      { id: 'meeting_edit', label: '编辑会议' },
      { id: 'meeting_delete', label: '删除会议' },
      { id: 'meeting_ai', label: 'AI处理' }
    ]
  },
  {
    id: 'document',
    label: '文档管理',
    children: [
      { id: 'document_view', label: '查看文档' },
      { id: 'document_upload', label: '上传文档' },
      { id: 'document_edit', label: '编辑文档' },
      { id: 'document_delete', label: '删除文档' }
    ]
  },
  {
    id: 'graph',
    label: '知识图谱',
    children: [
      { id: 'graph_view', label: '查看图谱' },
      { id: 'graph_build', label: '构建图谱' },
      { id: 'graph_manage', label: '图谱管理' }
    ]
  },
  {
    id: 'feedback',
    label: '反馈管理',
    children: [
      { id: 'feedback_view', label: '查看反馈' },
      { id: 'feedback_analyze', label: '分析反馈' }
    ]
  },
  {
    id: 'user',
    label: '用户管理',
    children: [
      { id: 'user_view', label: '查看用户' },
      { id: 'user_create', label: '创建用户' },
      { id: 'user_edit', label: '编辑用户' },
      { id: 'user_delete', label: '删除用户' },
      { id: 'user_permission', label: '权限管理' }
    ]
  }
])

const rolePermissions = {
  admin: [
    'meeting_view', 'meeting_create', 'meeting_edit', 'meeting_delete', 'meeting_ai',
    'document_view', 'document_upload', 'document_edit', 'document_delete',
    'graph_view', 'graph_build', 'graph_manage',
    'feedback_view', 'feedback_analyze',
    'user_view', 'user_create', 'user_edit', 'user_delete', 'user_permission'
  ],
  user: [
    'meeting_view', 'meeting_create', 'meeting_edit', 'meeting_ai',
    'document_view', 'document_upload', 'document_edit',
    'graph_view',
    'feedback_view'
  ],
  readonly: [
    'meeting_view',
    'document_view',
    'graph_view',
    'feedback_view'
  ]
}

function formatDate(d) {
  if (!d) return '-'
  return new Date(d).toLocaleString('zh-CN')
}

function getRoleLabel(role) {
  const map = { admin: '管理员', user: '普通用户', readonly: '只读用户' }
  return map[role] || role
}

function getRoleTagType(role) {
  const map = { admin: 'danger', user: 'info', readonly: 'warning' }
  return map[role] || 'info'
}

async function load() {
  loading.value = true
  try {
    const params = { page: page.value, page_size: pageSize }
    if (filters.keyword) params.keyword = filters.keyword
    const res = await userApi.list(params)
    users.value = res.data || []
    total.value = res.total || 0
  } catch (e) {
    ElMessage.error('加载用户列表失败')
  } finally {
    loading.value = false
  }
}

function resetFilters() {
  filters.keyword = ''
  load()
}

function editUser(user) {
  editingUser.value = user
  userForm.username = user.username
  userForm.email = user.email
  userForm.password = ''
  userForm.full_name = user.full_name || ''
  userForm.department = user.department || ''
  userForm.role = user.role || 'user'
  showAddDialog.value = true
}

function closeDialog() {
  showAddDialog.value = false
  editingUser.value = null
  userForm.username = ''
  userForm.email = ''
  userForm.password = ''
  userForm.full_name = ''
  userForm.department = ''
  userForm.role = 'user'
}

async function saveUser() {
  if (!userForm.username || !userForm.email) {
    return ElMessage.warning('请填写用户名和邮箱')
  }
  if (!editingUser.value && !userForm.password) {
    return ElMessage.warning('请设置密码')
  }

  saving.value = true
  try {
    const data = {
      username: userForm.username,
      email: userForm.email,
      full_name: userForm.full_name,
      department: userForm.department,
      role: userForm.role
    }
    if (userForm.password) {
      data.password = userForm.password
    }

    if (editingUser.value) {
      await userApi.update(editingUser.value.id, data)
      ElMessage.success('更新成功')
    } else {
      await userApi.create(data)
      ElMessage.success('创建成功')
    }

    closeDialog()
    load()
  } catch (e) {
    ElMessage.error(e.message || '操作失败')
  } finally {
    saving.value = false
  }
}

async function deleteUser(id) {
  await ElMessageBox.confirm('确认删除该用户？', '提示', { type: 'warning' })
  try {
    await userApi.remove(id)
    ElMessage.success('删除成功')
    load()
  } catch (e) {
    ElMessage.error(e.message || '删除失败')
  }
}

function managePermissions(user) {
  currentUser.value = user
  selectedPermissions.value = rolePermissions[user.role] || []
  showPermissionDialog.value = true
}

function handlePermissionChange(data, checked) {
  const index = selectedPermissions.value.indexOf(data.id)
  if (checked && index === -1) {
    selectedPermissions.value.push(data.id)
  } else if (!checked && index > -1) {
    selectedPermissions.value.splice(index, 1)
  }
}

async function savePermissions() {
  if (!currentUser.value) return

  savingPermissions.value = true
  try {
    await userApi.updatePermissions(currentUser.value.id, { permissions: selectedPermissions.value })
    ElMessage.success('权限保存成功')
    showPermissionDialog.value = false
  } catch (e) {
    ElMessage.error(e.message || '保存失败')
  } finally {
    savingPermissions.value = false
  }
}

onMounted(() => {
  load()
})
</script>

<style scoped>
.permission-section {
  max-height: 400px;
  overflow-y: auto;
}
</style>
