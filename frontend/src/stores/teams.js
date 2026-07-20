import { defineStore } from 'pinia'
import { getTeams, getTeamsByGroup, getTeamDetail } from '@/api/teams'

export const useTeamsStore = defineStore('teams', {
  state: () => ({
    list: [],
    groups: {},
    currentTeam: null,
    loading: false
  }),

  getters: {
    topTeams: (state) => [...state.list].sort((a, b) => a.rank - b.rank).slice(0, 10),

    teamsById: (state) => {
      const map = {}
      state.list.forEach(t => { map[t.id] = t })
      return map
    },

    teamsByName: (state) => {
      const map = {}
      state.list.forEach(t => { map[t.name] = t })
      return map
    },
  },

  actions: {
    async fetchAll(params = {}) {
      this.loading = true
      try {
        const res = await getTeams({ size: 48, ...params })
        this.list = res.data.items
      } finally {
        this.loading = false
      }
    },

    async fetchGroups() {
      const res = await getTeamsByGroup()
      this.groups = res.data
    },

    async fetchDetail(id) {
      const res = await getTeamDetail(id)
      this.currentTeam = res.data
      return res.data
    }
  }
})
