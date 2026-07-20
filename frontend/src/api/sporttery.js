import api from './index'

export function getTodaySportteryPlan(competition) {
  return api.get('/sporttery/plan/today', {
    params: { competition },
  })
}
