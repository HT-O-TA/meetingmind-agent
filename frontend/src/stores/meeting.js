import { defineStore } from 'pinia'
import { ref } from 'vue'
import { meetingApi } from '@/api/meetings'

export const useMeetingStore = defineStore('meeting', () => {
  const meetings = ref([])
  const total = ref(0)
  const loading = ref(false)

  async function fetchMeetings(params) {
    loading.value = true
    try {
      const res = await meetingApi.list(params)
      meetings.value = res.data || []
      total.value = res.total || 0
    } finally {
      loading.value = false
    }
  }

  return { meetings, total, loading, fetchMeetings }
})
