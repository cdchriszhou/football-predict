import api from './index'

/** Public health probe — no admin auth required. */
export function getSystemHealth() {
  return api.get('/system/health', { timeout: 10000 })
}
