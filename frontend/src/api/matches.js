import api from './index'

export function getMatches(params = {}) {
  return api.get('/matches/list', { params })
}

export function getKnockoutBracket() {
  return api.get('/matches/knockout-bracket', { timeout: 45000 })
}

export function getTodayMatches() {
  return api.get('/matches/today', { timeout: 20000 })
}

export function getRecentResults(hours = 48, limit = 12) {
  return api.get('/matches/recent-results', { params: { hours, limit } })
}

export function getUpcomingMatches(limit = 10) {
  return api.get('/matches/upcoming', { params: { limit } })
}

export function getMatchDates() {
  return api.get('/matches/dates')
}

export function getMatchStages() {
  return api.get('/matches/stages')
}

export function getMatchDetail(id) {
  return api.get(`/matches/${id}`)
}
