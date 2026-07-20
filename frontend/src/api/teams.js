import api from './index'

export function getTeamStandings() {
  return api.get('/teams/standings')
}

export function getTeams(params = {}) {
  return api.get('/teams/list', { params })
}

export function getTeamsByGroup() {
  return api.get('/teams/groups')
}

export function getTeamDetail(id) {
  return api.get(`/teams/${id}`)
}
