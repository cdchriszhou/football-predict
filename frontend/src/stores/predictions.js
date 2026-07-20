import { defineStore } from 'pinia'
import { getPrediction, getPredictionsBatch, getPredictionAccuracy } from '@/api/predictions'

export const usePredictionsStore = defineStore('predictions', {
  state: () => ({
    cache: {},
    accuracy: null,
    loading: false
  }),

  getters: {
    getPredictionForMatch: (state) => (matchId) => {
      return state.cache[`${matchId}_latest`] || null
    }
  },

  actions: {
    async fetchPrediction(matchId, model = 'auto', refresh = false) {
      const cacheKey = `${matchId}_${model}`
      if (!refresh && this.cache[cacheKey]) {
        return this.cache[cacheKey]
      }

      this.loading = true
      try {
        const res = await getPrediction(matchId, model, refresh)
        // Use $patch with spread to guarantee reactivity across all consumers
        this.$patch({
          cache: {
            ...this.cache,
            [cacheKey]: res.data,
            [`${matchId}_latest`]: res.data
          }
        })
        return res.data
      } finally {
        this.loading = false
      }
    },

    async fetchBatch(matchIds) {
      if (!matchIds.length) return
      try {
        const res = await getPredictionsBatch(matchIds)
        const updates = {}
        Object.entries(res.data).forEach(([mid, pred]) => {
          updates[`${mid}_latest`] = pred
        })
        if (Object.keys(updates).length) {
          this.$patch({ cache: { ...this.cache, ...updates } })
        }
      } catch (e) {
        console.error('[Predictions] fetchBatch failed:', e)
      }
    },

    async fetchAccuracy(days = 30) {
      const res = await getPredictionAccuracy(days)
      this.accuracy = res.data
      return res.data
    }
  }
})
