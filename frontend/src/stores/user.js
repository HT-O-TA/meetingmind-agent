import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { userApi } from '@/api/users'
import { ElMessage } from 'element-plus'

export const useUserStore = defineStore('user', () => {
  const token = ref(localStorage.getItem('token') || '')
  const userInfo = ref(JSON.parse(localStorage.getItem('userInfo') || 'null'))
  const isTokenValidated = ref(false)

  const isLoggedIn = computed(() => !!token.value && isTokenValidated.value)

  async function login(username, password) {
    const res = await userApi.login({ username, password })
    token.value = res.data.access_token
    userInfo.value = res.data.user
    isTokenValidated.value = true
    localStorage.setItem('token', token.value)
    localStorage.setItem('userInfo', JSON.stringify(userInfo.value))
    ElMessage.success('登录成功')
    return res.data
  }

  async function register(data) {
    const res = await userApi.register(data)
    ElMessage.success('注册成功，请登录')
    return res.data
  }

  function logout() {
    token.value = ''
    userInfo.value = null
    isTokenValidated.value = false
    localStorage.removeItem('token')
    localStorage.removeItem('userInfo')
  }

  async function fetchMe() {
    if (!token.value) {
      isTokenValidated.value = false
      return
    }
    try {
      const res = await userApi.getMe()
      userInfo.value = res.data
      isTokenValidated.value = true
      localStorage.setItem('userInfo', JSON.stringify(userInfo.value))
    } catch {
      logout()
    }
  }

  async function validateToken() {
    if (!token.value) {
      isTokenValidated.value = false
      return false
    }
    try {
      await userApi.getMe()
      isTokenValidated.value = true
      return true
    } catch {
      logout()
      return false
    }
  }

  return { token, userInfo, isLoggedIn, isTokenValidated, login, register, logout, fetchMe, validateToken }
})