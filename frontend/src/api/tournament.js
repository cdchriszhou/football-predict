import api from './index'

export function getTournamentPrediction(model = 'auto', refresh = false) {
  return api.get('/tournament/predictions', { params: { model, refresh } })
}
