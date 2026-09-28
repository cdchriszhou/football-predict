import api from './index'

export function getPrediction(matchId, model = 'deepseek', refresh = false) {
  return api.get(`/predictions/${matchId}`, { params: { model, refresh } })
}

export function getPredictionsBatch(matchIds) {
  return api.post('/predictions/batch', matchIds)
}

export function getPredictionAccuracy(days = 30) {
  return api.get('/predictions/accuracy/stats', { params: { days } })
}

export function getPredictionHistory(days = 30, limit = 40) {
  return api.get('/predictions/history', { params: { days, limit } })
}

export function getScoreBacktest() {
  return api.get('/predictions/backtest')
}

export function getDailyScoreBacktest(days = 14) {
  return api.get('/predictions/backtest/daily', { params: { days } })
}
