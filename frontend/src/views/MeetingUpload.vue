<template>
  <el-card style="max-width:720px;margin:0 auto">
    <template #header><span style="font-size:16px;font-weight:600">新建 / 上传会议</span></template>

    <el-form :model="form" :rules="rules" ref="formRef" label-width="100px">
      <el-form-item label="会议标题" prop="title">
        <el-input v-model="form.title" placeholder="请输入会议标题" />
      </el-form-item>
      <el-form-item label="组织者">
        <el-input v-model="form.organizer_name" placeholder="组织者姓名" />
      </el-form-item>
      <el-form-item label="部门">
        <el-input v-model="form.department" placeholder="所属部门" />
      </el-form-item>
      <el-form-item label="会议类型">
        <el-select v-model="form.meeting_type" style="width:100%">
          <el-option label="通用会议" value="general" />
          <el-option label="项目会议" value="project" />
          <el-option label="周会" value="weekly" />
          <el-option label="人事会议" value="hr" />
        </el-select>
      </el-form-item>
      <el-form-item label="开始时间">
        <el-date-picker v-model="form.start_time" type="datetime" placeholder="选择开始时间" style="width:100%" />
      </el-form-item>
      <el-form-item label="地点">
        <el-input v-model="form.location" placeholder="会议地点" />
      </el-form-item>
      <el-form-item label="参会人员">
        <el-input v-model="form.participants" placeholder="参会人员，逗号分隔" />
      </el-form-item>
      <el-form-item label="会议描述">
        <el-input v-model="form.description" type="textarea" :rows="3" placeholder="会议描述" />
      </el-form-item>
      <el-form-item label="会议文本">
        <el-input v-model="form.raw_transcript" type="textarea" :rows="6" placeholder="粘贴会议转写文本（可选）" />
      </el-form-item>
      <el-form-item label="上传文件">
        <el-upload
          ref="uploadRef"
          :auto-upload="false"
          :limit="1"
          accept=".txt,.pdf,.docx,.md,.csv,.xlsx,.xlsm"
          :on-change="onFileChange"
        >
          <el-button>选择文件</el-button>
          <template #tip><div style="color:#999;font-size:12px">支持 txt/pdf/docx/md/csv/xlsx/xlsm，最大 50MB；不接受图片、视频或传感器文件</div></template>
        </el-upload>
      </el-form-item>
      <el-form-item>
        <el-button type="primary" :loading="loading" @click="submit">提交</el-button>
        <el-button @click="$router.back()">取消</el-button>
      </el-form-item>
    </el-form>
  </el-card>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { meetingApi } from '@/api/meetings'
import { documentApi } from '@/api/documents'
import { ElMessage } from 'element-plus'

const router = useRouter()
const formRef = ref()
const loading = ref(false)
const selectedFile = ref(null)

const form = reactive({
  title: '',
  organizer_name: '',
  department: '',
  meeting_type: 'general',
  start_time: null,
  location: '',
  participants: '',
  description: '',
  raw_transcript: '',
})

const rules = { title: [{ required: true, message: '请输入会议标题', trigger: 'blur' }] }

function onFileChange(file) {
  selectedFile.value = file.raw
}

async function submit() {
  await formRef.value.validate()
  loading.value = true
  try {
    const res = await meetingApi.create(form)
    const meetingId = res.data.id

    if (selectedFile.value) {
      const fd = new FormData()
      fd.append('file', selectedFile.value)
      fd.append('meeting_id', meetingId)
      await documentApi.upload(fd)
    }

    ElMessage.success('创建成功')
    router.push(`/meetings/${meetingId}`)
  } finally {
    loading.value = false
  }
}
</script>
