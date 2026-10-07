// 全局应用状态：立即刷新（POST /api/refresh）+ 运行态轮询（GET /api/refresh/status）、Mock 徽标
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { api, mockMode } from '../api/client'
import type { RefreshStatus } from '../types'

export const useAppStore = defineStore('app', () => {
  const refreshStatus = ref<RefreshStatus | null>(null)
  const refreshing = ref(false)
  const isMock = computed(() => mockMode.value)

  let timer: number | null = null
  let ticks = 0

  async function loadRefreshStatus() {
    refreshStatus.value = await api.getRefreshStatus()
  }

  function stopPolling() {
    if (timer !== null) {
      window.clearInterval(timer)
      timer = null
    }
    refreshing.value = false
  }

  /** 触发立即抓取并每 2s 轮询直至结束（上限约 3 分钟）；结束后回调 onDone */
  async function startRefresh(onDone?: () => void) {
    refreshing.value = true
    try {
      await api.refresh()
      await loadRefreshStatus()
    } catch (e) {
      stopPolling()
      throw e
    }
    ticks = 0
    if (timer !== null) window.clearInterval(timer)
    timer = window.setInterval(async () => {
      ticks += 1
      try {
        await loadRefreshStatus()
      } catch {
        // 单次轮询失败忽略，下一轮重试
      }
      const running = refreshStatus.value ? refreshStatus.value.running : false
      if (!running || ticks > 90) {
        stopPolling()
        onDone?.()
      }
    }, 2000)
  }

  return { refreshStatus, refreshing, isMock, loadRefreshStatus, startRefresh }
})
