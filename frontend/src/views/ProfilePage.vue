<template>
  <el-card style="max-width:600px;margin:0 auto">
    <template #header><span style="font-size:16px;font-weight:600">个人信息</span></template>

    <div v-if="!userStore.isLoggedIn" style="text-align:center;padding:40px">
      <el-empty description="请先登录">
        <el-button type="primary" @click="$router.push('/login')">去登录</el-button>
      </el-empty>
    </div>

    <el-form v-else :model="form" label-width="80px">
      <el-form-item label="用户名">
        <el-input :value="userStore.userInfo?.username" disabled />
      </el-form-item>
      <el-form-item label="邮箱">
        <el-input :value="userStore.userInfo?.email" disabled />
      </el-form-item>
      <el-form-item label="姓名">
        <el-input v-model="form.full_name" />
      </el-form-item>
      <el-form-item label="部门">
        <el-input v-model="form.department" />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" :loading="saving" @click="save">保存修改</el-button>
      </el-form-item>
    </el-form>
  </el-card>
</template>

<script setup>
import { reactive, ref, watch } from 'vue'
import { useUserStore } from '@/stores/user'
import { userApi } from '@/api/users'
import { ElMessage } from 'element-plus'

const userStore = useUserStore()
const saving = ref(false)
const form = reactive({ full_name: '', department: '' })

watch(() => userStore.userInfo, (info) => {
  if (info) {
    form.full_name = info.full_name || ''
    form.department = info.department || ''
  }
}, { immediate: true })

async function save() {
  saving.value = true
  try {
    const res = await userApi.updateMe(form)
    userStore.userInfo = res.data
    localStorage.setItem('userInfo', JSON.stringify(res.data))
    ElMessage.success('保存成功')
  } finally {
    saving.value = false
  }
}
</script>
