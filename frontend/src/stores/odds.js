import { defineStore } from 'pinia'
import { getOdds, getLatestOdds, getOddsBatch } from '@/api/odds'
import { hasSportteryOdds } from '@/utils/sporttery'

export const useOddsStore = defineStore('odds', {
  state: () => ({
    cache: {},
    latestList: [],
    loading: false
  }),

  getters: {
    getOddsForMatch: (state) => (matchId) => state.cache[matchId] || null
  },

  actions: {
    async fetchOdds(matchId, refresh = false) {
      const id = Number(matchId)
      const cached = this.cache[id]
      // Keep sporttery CRS/SPF fresh — do not skip fetch when on-sale 竞彩 exists.
      const hasOnSaleSporttery = hasSportteryOdds(cached) && cached.sporttery?.on_sale !== false
      const cacheComplete = cached && (cached.european || cached.macau) && !hasOnSaleSporttery
      if (!refresh && cacheComplete) return cached

      this.loading = true
      try {
        const res = await getOdds(id)
        this.$patch({
          cache: { ...this.cache, [id]: res.data }
        })
        return res.data
      } finally {
        this.loading = false
      }
    },

    async fetchBatch(matchIds) {
      if (!matchIds.length) return
      try {
        const res = await getOddsBatch(matchIds)
        const data = res.data || {}
        if (!Object.keys(data).length) return

        const updates = {}
        Object.entries(data).forEach(([mid, odds]) => {
          updates[Number(mid)] = odds
        })
        this.$patch({ cache: { ...this.cache, ...updates } })
      } catch (e) {
        console.error('[Odds] fetchBatch failed:', e)
      }
    },

    async fetchLatest() {
      const res = await getLatestOdds()
      this.latestList = res.data
      return res.data
    }
  }
})
