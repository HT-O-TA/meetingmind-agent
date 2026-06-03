<template>
  <div v-loading="loading">
    <el-page-header @back="$router.back()" style="margin-bottom:16px">
      <template #content><span>{{ meeting?.title }}</span></template>
    </el-page-header>

    <el-row :gutter="16" v-if="meeting">
      <el-col :span="16">
        <el-card style="margin-bottom:16px">
          <template #header>基本信息</template>
          <el-descriptions :column="2" border>
            <el-descriptions-item label="状态">
              <el-tag :type="statusType(meeting.status)">{{ statusLabel(meeting.status) }}</el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="类型">{{ meeting.meeting_type }}</el-descriptions-item>
            <el-descriptions-item label="组织者">{{ meeting.organizer_name || '-' }}</el-descriptions-item>
            <el-descriptions-item label="部门">{{ meeting.department || '-' }}</el-descriptions-item>
            <el-descriptions-item label="地点">{{ meeting.location || '-' }}</el-descriptions-item>
            <el-descriptions-item label="参会人员">{{ meeting.participants || '-' }}</el-descriptions-item>
            <el-descriptions-item label="开始时间">{{ formatDate(meeting.start_time) }}</el-descriptions-item>
            <el-descriptions-item label="创建时间">{{ formatDate(meeting.created_at) }}</el-descriptions-item>
          </el-descriptions>
        </el-card>

        <el-card v-if="meeting.raw_transcript" style="margin-bottom:16px">
          <template #header>会议原文</template>
          <pre style="white-space:pre-wrap;font-size:13px;line-height:1.6;max-height:400px;overflow-y:auto">{{ meeting.raw_transcript }}</pre>
        </el-card>

        <el-card v-if="meeting.summary || meeting.minutes">
          <template #header>会议纪要</template>
          <div v-if="meeting.summary"><strong>摘要：</strong><p>{{ meeting.summary }}</p></div>
          <div v-if="meeting.minutes"><strong>纪要：</strong><pre style="white-space:pre-wrap;font-size:13px">{{ meeting.minutes }}</pre></div>
        </el-card>

        <el-card style="margin-top:16px">
          <template #header>
            <div style="display:flex;justify-content:space-between;align-items:center">
              <span>发言记录</span>
              <el-button size="small" type="primary" @click="showSpeechDialog = true">新增</el-button>
            </div>
          </template>
          <div v-if="speeches.length === 0" style="color:#999;text-align:center;padding:20px">暂无发言记录</div>
          <div v-for="s in speeches" :key="s.id" style="margin-bottom:12px;padding:8px;background:#f9f9f9;border-radius:4px">
            <div style="display:flex;justify-content:space-between;align-items:flex-start">
              <div style="flex:1">
                <div style="font-weight:600;color:#409eff;margin-bottom:4px">{{ s.speaker_name }}</div>
                <div style="font-size:13px">{{ s.content }}</div>
              </div>
              <div style="margin-left:8px">
                <el-button size="small" @click="editSpeech(s)">编辑</el-button>
                <el-button size="small" type="danger" @click="deleteSpeech(s.id)">删除</el-button>
              </div>
            </div>
          </div>
        </el-card>
      </el-col>

      <el-col :span="8">
        <el-card>
          <template #header>
            <div style="display:flex;justify-content:space-between;align-items:center">
              <span>待办事项</span>
              <el-button size="small" type="primary" @click="showTodoDialog = true">新增</el-button>
            </div>
          </template>
          <div v-if="todos.length === 0" style="color:#999;text-align:center;padding:20px">暂无待办</div>
          <div v-for="t in todos" :key="t.id" style="margin-bottom:8px;padding:8px;border:1px solid #eee;border-radius:4px">
            <div style="display:flex;justify-content:space-between">
              <span :style="t.status==='done'?'text-decoration:line-through;color:#999':''">{{ t.title }}</span>
              <el-tag :type="priorityType(t.priority)" size="small">{{ t.priority }}</el-tag>
            </div>
            <div style="font-size:12px;color:#999;margin-top:4px">
              {{ t.assignee_name || '未分配' }} · {{ statusLabel2(t.status) }}
            </div>
            <div style="margin-top:6px">
              <el-button size="small" @click="markDone(t)" :disabled="t.status==='done'">完成</el-button>
              <el-button size="small" type="danger" @click="removeTodo(t.id)">删除</el-button>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-dialog v-model="showTodoDialog" title="新增待办" width="400px">
      <el-form :model="todoForm" label-width="80px">
        <el-form-item label="标题"><el-input v-model="todoForm.title" /></el-form-item>
        <el-form-item label="负责人"><el-input v-model="todoForm.assignee_name" /></el-form-item>
        <el-form-item label="优先级">
          <el-select v-model="todoForm.priority">
            <el-option label="高" value="high" /><el-option label="中" value="medium" /><el-option label="低" value="low" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showTodoDialog = false">取消</el-button>
        <el-button type="primary" @click="addTodo">确定</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showSpeechDialog" :title="editingSpeech ? '编辑发言' : '新增发言'" width="500px">
      <el-form :model="speechForm" label-width="80px">
        <el-form-item label="发言人"><el-input v-model="speechForm.speaker_name" /></el-form-item>
        <el-form-item label="内容"><el-input v-model="speechForm.content" type="textarea" :rows="5" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showSpeechDialog = false">取消</el-button>
        <el-button type="primary" @click="saveSpeech">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, reactive } from 'vue'
import { useRoute } from 'vue-router'
import { meetingApi } from '@/api/meetings'
import { todoApi } from '@/api/todos'
import { ElMessage, ElMessageBox } from 'element-plus'

const route = useRoute()
const meeting = ref(null)
const speeches = ref([])
const todos = ref([])
const loading = ref(false)

// 待办相关
const showTodoDialog = ref(false)
const todoForm = reactive({ title: '', assignee_name: '', priority: 'medium' })

// 发言相关
const showSpeechDialog = ref(false)
const editingSpeech = ref(null)
const speechForm = reactive({ speaker_name: '', content: '' })

const statusType = (s) => ({ draft: 'info', processing: 'warning', completed: 'success', archived: '' }[s] || 'info')
const statusLabel = (s) => ({ draft: '草稿', processing: '处理中', completed: '已完成', archived: '已归档' }[s] || s)
const statusLabel2 = (s) => ({ pending: '待处理', in_progress: '进行中', done: '已完成', cancelled: '已取消' }[s] || s)
const priorityType = (p) => ({ high: 'danger', medium: 'warning', low: 'info' }[p] || '')
const formatDate = (d) => d ? new Date(d).toLocaleString('zh-CN') : '-'

async function load() {
  loading.value = true
  try {
    const id = route.params.id
    const [mRes, sRes, tRes] = await Promise.all([
      meetingApi.get(id),
      meetingApi.listSpeeches(id),
      todoApi.list({ meeting_id: id }),
    ])
    meeting.value = mRes.data
    speeches.value = sRes.data || []
    todos.value = tRes.data || []
  } finally {
    loading.value = false
  }
}

// 待办功能
async function addTodo() {
  if (!todoForm.title) return ElMessage.warning('请输入标题')
  await todoApi.create({ ...todoForm, meeting_id: Number(route.params.id) })
  showTodoDialog.value = false
  todoForm.title = ''; todoForm.assignee_name = ''; todoForm.priority = 'medium'
  const res = await todoApi.list({ meeting_id: route.params.id })
  todos.value = res.data || []
  ElMessage.success('添加成功')
}

async function markDone(t) {
  await todoApi.update(t.id, { status: 'done' })
  t.status = 'done'
}

async function removeTodo(id) {
  await ElMessageBox.confirm('确认删除该待办？', '提示', { type: 'warning' })
  await todoApi.remove(id)
  todos.value = todos.value.filter(t => t.id !== id)
}

// 发言功能
function editSpeech(s) {
  editingSpeech.value = s
  speechForm.speaker_name = s.speaker_name
  speechForm.content = s.content
  showSpeechDialog.value = true
}

async function saveSpeech() {
  if (!speechForm.speaker_name || !speechForm.content) {
    return ElMessage.warning('请填写完整信息')
  }
  
  try {
    if (editingSpeech.value) {
      await meetingApi.updateSpeech(
        Number(route.params.id), 
        editingSpeech.value.id, 
        speechForm
      )
      ElMessage.success('更新成功')
    } else {
      await meetingApi.createSpeech(Number(route.params.id), speechForm)
      ElMessage.success('添加成功')
    }
    showSpeechDialog.value = false
    resetSpeechForm()
    await load()
  } catch (e) {
    ElMessage.error(e.message || '操作失败')
  }
}

async function deleteSpeech(id) {
  await ElMessageBox.confirm('确认删除该发言记录？', '提示', { type: 'warning' })
  await meetingApi.deleteSpeech(Number(route.params.id), id)
  await load()
  ElMessage.success('删除成功')
}

function resetSpeechForm() {
  editingSpeech.value = null
  speechForm.speaker_name = ''
  speechForm.content = ''
}

onMounted(load)
</script>
