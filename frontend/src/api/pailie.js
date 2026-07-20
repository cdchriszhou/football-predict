import api from './index'

export function getPailieCatalog() {
  return api.get('/pailie/catalog')
}

export function getPailieHistory(params = {}) {
  return api.get('/pailie/history', { params })
}

export function getPailieRecommend(params = {}) {
  return api.get('/pailie/recommend', { params })
}
