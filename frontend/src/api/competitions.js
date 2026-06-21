import api from './index'

export function getCompetitions() {
  return api.get('/competitions', { timeout: 60000 })
}

export function getCompetitionDetail(slug) {
  return api.get(`/competitions/${slug}`, { timeout: 30000 })
}

export function refreshLeagueData(slug) {
  return api.post(`/admin/crawler/league/${slug}`)
}
