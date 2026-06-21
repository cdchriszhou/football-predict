import api from './index'

export function getHkjcDashboard(competition, refresh = false) {
  return api.get('/hkjc/dashboard', { params: { competition, refresh } })
}

export function getHkjcMeetings(competition, refresh = false, pastDays = 7, futureDays = 7) {
  return api.get('/hkjc/meetings', {
    params: { competition, refresh, past_days: pastDays, future_days: futureDays },
    timeout: refresh ? 120000 : 30000,
  })
}

export function getHkjcPurchaseAdvice(competition, refresh = false) {
  return api.get('/hkjc/purchase-advice', { params: { competition, refresh } })
}

export function getHkjcMeetingDetail(meetingId, competition, refresh = false) {
  return api.get(`/hkjc/meetings/${meetingId}`, {
    params: { competition, refresh },
    timeout: refresh ? 120000 : 30000,
  })
}

export function getHkjcRaceDetail(raceId, competition, useAi = true) {
  return api.get(`/hkjc/races/${raceId}`, {
    params: { competition, use_ai: useAi },
    timeout: useAi ? 90000 : 30000,
  })
}

export function getHkjcHorses(competition, refresh = false) {
  return api.get('/hkjc/horses', {
    params: { competition, refresh },
    timeout: refresh ? 120000 : 30000,
  })
}

export function getHkjcBacktest(competition) {
  return api.get('/hkjc/backtest', { params: { competition } })
}

export function startHkjcSync(competition, syncResults = true, resultDays = 14) {
  return api.post('/hkjc/sync', null, {
    params: { competition, sync_results: syncResults, result_days: resultDays },
    timeout: 15000,
  })
}

export function getHkjcSyncStatus(competition) {
  return api.get('/hkjc/sync/status', { params: { competition }, timeout: 10000 })
}

/** @deprecated use startHkjcSync + poll getHkjcSyncStatus */
export function syncHkjcData(competition, syncResults = true, resultDays = 14) {
  return startHkjcSync(competition, syncResults, resultDays)
}
