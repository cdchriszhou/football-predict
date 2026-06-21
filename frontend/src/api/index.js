import axios from 'axios'
import i18n from '@/i18n'

const TOKEN_KEY = 'worldcup_auth_token'
const SERVER_KEY = 'worldcup_server_url'

function getBaseURL() {
  const server = localStorage.getItem(SERVER_KEY)
  if (server) {
    const trimmed = server.replace(/\/+$/, '')
    try {
      const saved = new URL(trimmed.includes('://') ? trimmed : `http://${trimmed}`)
      const pageOrigin = window.location.origin
      if (
        saved.origin !== pageOrigin
        && (saved.hostname === 'localhost' || saved.hostname === '127.0.0.1')
        && !['localhost', '127.0.0.1'].includes(window.location.hostname)
      ) {
        localStorage.removeItem(SERVER_KEY)
        return '/api/v1'
      }
      return `${saved.origin}/api/v1`
    } catch {
      localStorage.removeItem(SERVER_KEY)
    }
  }
  return '/api/v1'
}

const api = axios.create({
  baseURL: getBaseURL(),
  timeout: 30000,
})

api.interceptors.request.use(
  (config) => {
    config.baseURL = getBaseURL()
    const token = localStorage.getItem(TOKEN_KEY)
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    const slug = localStorage.getItem('worldcup_competition_slug')
    if (slug && !String(config.url || '').includes('/competitions')) {
      if (config.params && typeof config.params === 'object') {
        if (config.params.competition === undefined) {
          config.params.competition = slug
        }
      } else {
        config.params = { competition: slug }
      }
    }
    return config
  },
  (error) => Promise.reject(error)
)

api.interceptors.response.use(
  (response) => response.data,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem(TOKEN_KEY)
      localStorage.removeItem('worldcup_auth_user')
      if (window.location.pathname !== '/login') {
        window.location.href = '/login'
      }
    }
    const msg = error.response?.data?.message || error.message || i18n.global.t('messages.requestFailed')
    console.error('[API Error]', msg)
    return Promise.reject(error)
  }
)

export default api
