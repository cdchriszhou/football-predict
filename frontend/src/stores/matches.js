import { defineStore } from 'pinia'
import { getMatches, getMatchDetail, getTodayMatches, getUpcomingMatches, getRecentResults } from '@/api/matches'

export const useMatchesStore = defineStore('matches', {
  state: () => ({
    list: [],
    currentMatch: null,
    todayMatches: [],
    upcomingMatches: [],
    recentResults: [],
    loading: false,
    filter: { stage: '', status: '', page: 1, size: 20, total: 0 }
  }),

  getters: {
    groupedByStage: (state) => {
      const groups = {}
      state.list.forEach(m => {
        const key = m.stage || '未知'
        if (!groups[key]) groups[key] = []
        groups[key].push(m)
      })
      return groups
    },

    liveMatches: (state) => state.list.filter(m => m.status === 'live' || m.status === '进行中'),

    matchCount: (state) => state.list.length
  },

  actions: {
    async fetchList(params = {}) {
      this.loading = true
      try {
        const res = await getMatches({ ...this.filter, ...params })
        this.list = res.data.items
        this.filter.total = res.data.total
      } finally {
        this.loading = false
      }
    },

    async fetchToday() {
      const res = await getTodayMatches()
      if (Array.isArray(res.data)) {
        this.todayMatches = res.data
      }
    },

    async fetchUpcoming(limit = 10) {
      const res = await getUpcomingMatches(limit)
      this.upcomingMatches = res.data
    },

    async fetchRecentResults(hours = 48, limit = 12) {
      const res = await getRecentResults(hours, limit)
      this.recentResults = res.data
    },

    async fetchDetail(id) {
      const res = await getMatchDetail(id)
      this.currentMatch = res.data
      return res.data
    },

    setFilter(filter) {
      Object.assign(this.filter, filter)
    }
  }
})
