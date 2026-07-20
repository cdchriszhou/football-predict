import api from './index'

export function healthCheck() {
  return api.get('/admin/health')
}

export function probeSporttery() {
  return api.get('/admin/sporttery/probe', { timeout: 35000 })
}

export function triggerCrawler(type = null) {
  if (type) {
    return api.post(`/admin/crawler/run/${type}`)
  }
  return api.post('/admin/crawler/run')
}

export function getCrawlerStatus() {
  return api.get('/admin/crawler/status')
}

export function triggerBatchPredict(model = 'auto', competition = 'worldcup-2026') {
  return api.post('/admin/predictions/batch', null, {
    params: { model, competition, background: true },
    timeout: 30000,
  })
}

export function getBatchPredictStatus() {
  return api.get('/admin/predictions/batch/status', { timeout: 15000 })
}

export function getConfig() {
  return api.get('/admin/config')
}

export function saveConfig(data) {
  return api.put('/admin/config', data)
}

export function testApiConnection(model = 'deepseek') {
  return api.post('/admin/config/test', { model })
}

export function testOddsApiConnection() {
  return api.post('/admin/config/test-odds')
}

export function testFootballDataConnection() {
  return api.post('/admin/config/test-football-data')
}

export function generateInviteCode() {
  return api.post('/admin/invite-codes/generate')
}

export function getInviteCodes() {
  return api.get('/admin/invite-codes')
}

export function deleteInviteCode(id) {
  return api.delete(`/admin/invite-codes/${id}`)
}

export function getUsers() {
  return api.get('/admin/users')
}

export function resetUserPassword(userId, newPassword) {
  return api.post(`/admin/users/${userId}/reset-password`, { new_password: newPassword })
}

export function refreshAllData(background = true) {
  return api.post('/data/refresh', null, {
    params: { background },
    timeout: background ? 30000 : 600000,
  })
}

export function getDataRefreshStatus() {
  return api.get('/data/refresh/status', { timeout: 15000 })
}

export function toggleUserActive(userId) {
  return api.post(`/admin/users/${userId}/toggle-active`)
}

export function updateUserAccess(userId, data) {
  return api.patch(`/admin/users/${userId}/access`, data)
}

export function getRuntimeLogs(source = 'backend', lines = 300) {
  return api.get('/admin/runtime-logs', { params: { source, lines } })
}
