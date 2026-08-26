<template>
  <el-container style="height: 100vh">
    <el-aside width="220px" style="background:#1e2a3a;display:flex;flex-direction:column">
      <div style="padding:20px 16px;color:#fff;font-size:18px;font-weight:700;border-bottom:1px solid #2d3f52;flex-shrink:0">
        MeetingMind
      </div>
      <el-menu
        :default-active="$route.path"
        router
        background-color="#1e2a3a"
        text-color="#b0bec5"
        active-text-color="#409eff"
        style="flex:1;border-right:none"
      >
        <el-menu-item index="/meetings">
          <el-icon><List /></el-icon><span>会议列表</span>
        </el-menu-item>
        <el-menu-item index="/meetings/upload">
          <el-icon><Upload /></el-icon><span>新建会议</span>
        </el-menu-item>
        <el-menu-item index="/todos">
          <el-icon><Checked /></el-icon><span>待办事项</span>
        </el-menu-item>
        <el-menu-item index="/documents">
          <el-icon><Folder /></el-icon><span>文档库</span>
        </el-menu-item>
        <el-menu-item index="/tasks">
          <el-icon><Clock /></el-icon><span>任务队列</span>
        </el-menu-item>
        <el-menu-item index="/feedback">
          <el-icon><ChatDotSquare /></el-icon><span>反馈管理</span>
        </el-menu-item>
        <el-menu-item index="/agent">
          <el-icon><Cpu /></el-icon><span>Agent演示</span>
        </el-menu-item>
        <el-menu-item index="/trace">
          <el-icon><Monitor /></el-icon><span>Trace监控</span>
        </el-menu-item>
        <el-menu-item index="/query">
          <el-icon><Search /></el-icon><span>智能查询</span>
        </el-menu-item>
      </el-menu>
      <div style="padding:12px 16px;border-top:1px solid #2d3f52">
        <div v-if="userStore.isLoggedIn" style="display:flex;align-items:center;gap:8px">
          <el-avatar :size="28" style="background:#409eff;font-size:12px">
            {{ userStore.userInfo?.username?.[0]?.toUpperCase() }}
          </el-avatar>
          <span style="color:#b0bec5;font-size:13px;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
            {{ userStore.userInfo?.full_name || userStore.userInfo?.username }}
          </span>
          <el-button link style="color:#b0bec5" @click="logout">退出</el-button>
        </div>
        <el-button v-else type="primary" size="small" style="width:100%" @click="$router.push('/login')">
          登录 / 注册
        </el-button>
      </div>
    </el-aside>
    <el-container>
      <el-header style="background:#fff;border-bottom:1px solid #eee;display:flex;align-items:center;padding:0 20px">
        <span style="font-size:15px;color:#333;font-weight:500">{{ pageTitle }}</span>
      </el-header>
      <el-main style="background:#f5f7fa;overflow-y:auto;padding:20px">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { Cpu, List, Upload, Checked, Folder, Search, Clock, ChatDotSquare, Monitor } from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const titleMap = {
  '/meetings': '会议列表',
  '/meetings/upload': '新建会议',
  '/todos': '待办事项',
  '/documents': '文档库',
  '/tasks': '任务队列',
  '/feedback': '反馈管理',
  '/agent': 'Agent智能助手',
  '/trace': 'Trace监控',
  '/query': '智能查询',
}
const pageTitle = computed(() => {
  if (route.path.match(/^\/meetings\/\d+\/edit$/)) return '编辑会议'
  if (route.path.match(/^\/meetings\/\d+$/)) return '会议详情'
  return titleMap[route.path] || 'MeetingMind'
})

function logout() {
  userStore.logout()
  router.push('/login')
}
</script>
