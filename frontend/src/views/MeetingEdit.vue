<template>
  <el-card style="max-width:720px;margin:0 auto" v-loading="loading">
    <template #header>
      <div style="display:flex;justify-content:space-between;align-items:center">
        <span style="font-size:16px;font-weight:600">编辑会议</span>
        <el-button @click="$router.back()">返回</el-button>
      </div>
    </template>

    <el-form v-if="form.title !== undefined" :model="form" :rules="rules" ref="formRef" label-width="100px">
      <el-form-item label="会议标题" prop="title">
        <el-input v-model="form.title" />
      </el-form-item>
      <el-form-item label="状态">
        <el-select v-model="form.status" style="width:100%">
          <el-option label="草稿" value="draft" />
          <el-option label="处理中" value="processing" />
          <el-option label="已完成" value="completed" />
          <el-option label="已归档" value="archived" />
        </el-select>
      </el-form-item>
      <el-form-item label="组织者">
        <el-input v-model="form.organizer_name" />
      </el-form-item>
      <el-form-item label="部门">
        <el-input v-model="form.department" />
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
        <el-date-picker v-model="form.start_time" type="datetime" style="width:100%" />
      </el-form-item>
      <el-form-item label="结束时间">
        <el-date-picker v-model="form.end_time" type="datetime" style="width:100%" />
      </el-form-item>
      <el-form-item label="地点">
        <el-input v-model="form.location" />
      </el-form-item>
      <el-form-item label="参会人员">
        <el-input v-model="form.participants" placeholder="逗号分隔" />
      </el-form-item>
      <el-form-item label="描述">
        <el-input v-model="form.description" type="textarea" :rows="3" />
      </el-form-item>
      <el-form-item label="会议原文">
        <el-input v-model="form.raw_transcript" type="textarea" :rows="6" />
      </el-form-item>
      <el-form-item label="摘要">
        <el-input v-model="form.summary" type="textarea" :rows="3" />
      </el-form-item>
      <el-form-item label="会议纪要">
        <el-input v-model="form.minutes" type="textarea" :rows="5" />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
        <el-button @click="$router.back()">取消</el-button>
      </el-form-item>
    </el-form>
  </el-card>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { meetingApi } from '@/api/meetings'
import { ElMessage } from 'element-plus'

const route = useRoute()
const router = useRouter()
const formRef = ref()
const loading = ref(false)
const saving = ref(false)
const form = reactive({})
const rules = { title: [{ required: true, message: '请输入会议标题', trigger: 'blur' }] }

async function load() {
  loading.value = true
  try {
    const res = await meetingApi.get(route.params.id)
    Object.assign(form, res.data)
  } finally {
    loading.value = false
  }
}

async function save() {
  await formRef.value.validate()
  saving.value = true
  try {
    await meetingApi.update(route.params.id, form)
    ElMessage.success('保存成功')
    router.push(`/meetings/${route.params.id}`)
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>
