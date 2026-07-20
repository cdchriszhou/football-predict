import { defineStore } from 'pinia'
import { getCompetitions, getCompetitionDetail } from '@/api/competitions'
import { FALLBACK_COMPETITIONS, findCompetitionMeta, normalizeCompetition } from '@/data/competitions'

const STORAGE_KEY = 'worldcup_competition_slug'
const REMOVED_SLUGS = new Set(['hong-kong-racing'])

function sanitizeSlug(slug) {
  if (!slug || REMOVED_SLUGS.has(slug)) return 'worldcup-2026'
  return slug
}

export const useCompetitionStore = defineStore('competition', {
  state: () => ({
    list: [],
    current: null,
    slug: sanitizeSlug(localStorage.getItem(STORAGE_KEY)),
    loading: false,
    listFromFallback: false,
    listError: '',
  }),

  getters: {
    features: (state) => state.current?.features || {},
    isWorldCup: (state) => state.slug === 'worldcup-2026',
    basePath: (state) => `/competition/${state.slug}`,
  },

  actions: {
    setSlug(slug) {
      this.slug = sanitizeSlug(slug)
      localStorage.setItem(STORAGE_KEY, this.slug)
    },

    async fetchList() {
      this.loading = true
      this.listFromFallback = false
      this.listError = ''
      try {
        const res = await getCompetitions()
        if (res?.code !== 200) {
          throw new Error(res?.message || 'Failed to load competitions')
        }
        const rows = Array.isArray(res.data) ? res.data : []
        if (!rows.length) {
          throw new Error('Empty competition list')
        }
        this.list = rows.map(normalizeCompetition)
        return this.list
      } catch (err) {
        const body = err?.response?.data
        const msg = (typeof body === 'object' && body?.message) || err?.message || 'Failed to load competitions'
        console.warn('[competition] fetchList failed, using fallback:', msg)
        this.listFromFallback = true
        this.listError = msg
        this.list = FALLBACK_COMPETITIONS.map(normalizeCompetition)
        return this.list
      } finally {
        this.loading = false
      }
    },

    async fetchDetail(slug) {
      const res = await getCompetitionDetail(slug)
      return res.data
    },

    async fetchCurrent(slug) {
      const target = slug || this.slug
      this.setSlug(target)
      const cached = findCompetitionMeta(target, this.list)
      if (cached && (!this.current || this.current.slug !== target)) {
        this.current = cached
      }
      try {
        const detail = await this.fetchDetail(target)
        if (detail) {
          this.current = normalizeCompetition(detail)
        }
      } catch (err) {
        if (!this.current) {
          const fallback = findCompetitionMeta(target, this.list)
          if (fallback) {
            this.current = fallback
            return this.current
          }
        }
        throw err
      }
      return this.current
    },

    clearCurrent() {
      this.current = null
    },
  },
})
