<template>
  <div style="display:flex;justify-content:center;align-items:center;height:100vh;background:#f5f7fa">
    <el-card style="width:420px">
      <template #header>
        <div style="text-align:center;font-size:22px;font-weight:700;color:#1e2a3a">🧠 MeetingMind</div>
        <div style="text-align:center;font-size:13px;color:#999;margin-top:4px">企业级会议智能助手</div>
      </template>

      <el-tabs v-model="tab">
        <el-tab-pane label="登录" name="login">
          <el-form :model="loginForm" label-width="80px" style="margin-top:8px">
            <el-form-item label="用户名">
              <el-input v-model="loginForm.username" placeholder="请输入用户名" @keyup.enter="login" />
            </el-form-item>
            <el-form-item label="密码">
              <el-input v-model="loginForm.password" type="password" placeholder="请输入密码" show-password @keyup.enter="login" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" style="width:100%" :loading="loading" @click="login">登录</el-button>
            </el-form-item>
          </el-form>
        </el-tab-pane>

        <el-tab-pane label="注册" name="register">
          <el-form :model="regForm" label-width="80px" style="margin-top:8px">
            <el-form-item label="用户名"><el-input v-model="regForm.username" /></el-form-item>
            <el-form-item label="邮箱"><el-input v-model="regForm.email" /></el-form-item>
            <el-form-item label="密码"><el-input v-model="regForm.password" type="password" show-password /></el-form-item>
            <el-form-item label="姓名"><el-input v-model="regForm.full_name" placeholder="可选" /></el-form-item>
            <el-form-item label="部门"><el-input v-model="regForm.department" placeholder="可选" /></el-form-item>
            <el-form-item>
              <el-button type="primary" style="width:100%" :loading="loading" @click="register">注册</el-button>
            </el-form-item>
          </el-form>
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { ElMessage } from 'element-plus'

const router = useRouter()
const userStore = useUserStore()
const tab = ref('login')
const loading = ref(false)

const loginForm = reactive({ username: '', password: '' })
const regForm = reactive({ username: '', email: '', password: '', full_name: '', department: '' })

async function login() {
  if (!loginForm.username || !loginForm.password) return ElMessage.warning('请填写完整')
  loading.value = true
  try {
    await userStore.login(loginForm.username, loginForm.password)
    router.push('/meetings')
  } finally {
    loading.value = false
  }
}

async function register() {
  if (!regForm.username || !regForm.email || !regForm.password) return ElMessage.warning('请填写必填项')
  loading.value = true
  try {
    await userStore.register(regForm)
    tab.value = 'login'
    loginForm.username = regForm.username
  } finally {
    loading.value = false
  }
}
</script>
