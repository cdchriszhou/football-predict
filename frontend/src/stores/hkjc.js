import { defineStore } from 'pinia'
import {
  getHkjcBacktest,
  getHkjcDashboard,
  getHkjcHorses,
  getHkjcMeetingDetail,
  getHkjcMeetings,
  getHkjcPurchaseAdvice,
  getHkjcRaceDetail,
  getHkjcSyncStatus,
  startHkjcSync,
} from '@/api/hkjc'

const SYNC_POLL_MS = 2000
const SYNC_MAX_WAIT_MS = 600000

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

export const useHkjcStore = defineStore('hkjc', {
  state: () => ({
    dashboard: null,
    meetings: [],
    meetingDetail: null,
    raceDetail: null,
    horses: [],
    backtest: null,
    purchaseAdvice: null,
    loading: false,
    syncing: false,
    syncProgress: '',
  }),

  actions: {
    async fetchDashboard(refresh = false) {
      this.loading = true
      try {
        const res = await getHkjcDashboard(undefined, refresh)
        if (res?.code === 200) this.dashboard = res.data
        return this.dashboard
      } finally {
        this.loading = false
      }
    },

    async fetchMeetings(refresh = false) {
      this.loading = true
      try {
        const res = await getHkjcMeetings(undefined, refresh, 7, 7)
        if (res?.code === 200) {
          const data = res.data
          const list = data?.meetings ?? (Array.isArray(data) ? data : [])
          this.meetings = Array.isArray(list) ? list : []
        }
        return this.meetings
      } finally {
        this.loading = false
      }
    },

    async syncAll(resultDays = 14) {
      if (this.syncing) {
        return null
      }
      this.syncing = true
      this.syncProgress = ''
      try {
        const startRes = await startHkjcSync(undefined, true, resultDays)
        if (startRes?.code !== 200) {
          throw new Error(startRes?.message || '同步失败')
        }
        const deadline = Date.now() + SYNC_MAX_WAIT_MS
        while (Date.now() < deadline) {
          await sleep(SYNC_POLL_MS)
          const st = await getHkjcSyncStatus()
          if (st?.code !== 200) continue
          const data = st.data || {}
          this.syncProgress = data.progress || ''
          if (!data.running) {
            if (data.error) {
              throw new Error(data.error)
            }
            return data.result || data
          }
        }
        throw new Error('同步超时，任务可能仍在后台进行，请稍后刷新页面')
      } finally {
        this.syncing = false
        this.syncProgress = ''
      }
    },

    async fetchMeetingDetail(meetingId, refresh = false) {
      this.loading = true
      try {
        const res = await getHkjcMeetingDetail(meetingId, undefined, refresh)
        if (res?.code === 200) this.meetingDetail = res.data
        return this.meetingDetail
      } finally {
        this.loading = false
      }
    },

    async fetchRaceDetail(raceId, useAi = true) {
      this.loading = true
      try {
        const res = await getHkjcRaceDetail(raceId, undefined, useAi)
        if (res?.code === 200) this.raceDetail = res.data
        return this.raceDetail
      } finally {
        this.loading = false
      }
    },

    async fetchHorses(refresh = false) {
      this.loading = true
      try {
        const res = await getHkjcHorses(undefined, refresh)
        if (res?.code === 200) this.horses = res.data?.horses || []
        return this.horses
      } finally {
        this.loading = false
      }
    },

    async fetchBacktest() {
      this.loading = true
      try {
        const res = await getHkjcBacktest()
        if (res?.code === 200) this.backtest = res.data
        return this.backtest
      } finally {
        this.loading = false
      }
    },

    async fetchPurchaseAdvice(refresh = false) {
      this.loading = true
      try {
        const res = await getHkjcPurchaseAdvice(undefined, refresh)
        if (res?.code === 200) this.purchaseAdvice = res.data
        return this.purchaseAdvice
      } finally {
        this.loading = false
      }
    },
  },
})
