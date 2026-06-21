import api from './index'

export function getOdds(matchId) {
  return api.get(`/odds/${matchId}`)
}

export function getLatestOdds() {
  return api.get('/odds/latest/list')
}

export function getOddsBatch(matchIds) {
  return api.post('/odds/batch', matchIds)
}
