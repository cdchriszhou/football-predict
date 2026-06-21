import { defineStore } from 'pinia'
import { login as apiLogin, getMe } from '@/api/auth'
import router from '@/router'
import { canAccessCompetition, accessDeniedMessage } from '@/utils/userAccess'

const TOKEN_KEY = 'worldcup_auth_token'
const USER_KEY = 'worldcup_auth_user'
const ADMIN_KEY = 'worldcup_auth_is_admin'
const ACCESS_KEY = 'worldcup_auth_access'

function loadAccessFromStorage() {
  try {
    const raw = localStorage.getItem(ACCESS_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

function saveAccessToStorage(access) {
  if (access) {
    localStorage.setItem(ACCESS_KEY, JSON.stringify(access))
  } else {
    localStorage.removeItem(ACCESS_KEY)
  }
}

const storedAccess = loadAccessFromStorage()
const ME_CACHE_MS = 60_000

export const useAuthStore = defineStore('auth', {
  state: () => ({
    meFetchedAt: 0,
    token: localStorage.getItem(TOKEN_KEY) || '',
    username: localStorage.getItem(USER_KEY) || '',
    isAdmin: localStorage.getItem(ADMIN_KEY) === 'true',
    accessExpiresAt: storedAccess?.accessExpiresAt ?? null,
    allowedCompetitions: storedAccess?.allowedCompetitions ?? null,
    hasAllCompetitions: storedAccess?.hasAllCompetitions !== false,
    accountExpired: storedAccess?.accountExpired ?? false,
    // Raw DB flag — do not name this canAccessSporttery (getter uses that name).
    sportteryAccessGranted: storedAccess?.sportteryAccessGranted ?? storedAccess?.canAccessSporttery ?? false,
    accessLoaded: !!storedAccess,
  }),

  getters: {
    isAuthenticated: (state) => !!state.token,
    canAccessSporttery: (state) => state.isAdmin || state.sportteryAccessGranted,
  },

  actions: {
    applyAccess(data = {}) {
      const sportteryAccessGranted = !!data.can_access_sporttery
      this.accessExpiresAt = data.access_expires_at ?? null
      this.allowedCompetitions = data.allowed_competitions ?? null
      this.hasAllCompetitions = data.has_all_competitions !== false
      this.accountExpired = !!data.account_expired
      this.sportteryAccessGranted = sportteryAccessGranted
      this.accessLoaded = true
      saveAccessToStorage({
        accessExpiresAt: this.accessExpiresAt,
        allowedCompetitions: this.allowedCompetitions,
        hasAllCompetitions: this.hasAllCompetitions,
        accountExpired: this.accountExpired,
        sportteryAccessGranted,
      })
    },

    canAccessCompetition(slug) {
      return canAccessCompetition({
        isAdmin: this.isAdmin,
        accountExpired: this.accountExpired,
        accessExpiresAt: this.accessExpiresAt,
        hasAllCompetitions: this.hasAllCompetitions,
        allowedCompetitions: this.allowedCompetitions,
      }, slug)
    },

    accessDeniedMessage(slug) {
      return accessDeniedMessage({
        isAdmin: this.isAdmin,
        accountExpired: this.accountExpired,
        accessExpiresAt: this.accessExpiresAt,
      }, slug)
    },

    async fetchMe({ force = false } = {}) {
      if (!this.token) return null
      const now = Date.now()
      if (
        !force
        && this.accessLoaded
        && this.meFetchedAt
        && now - this.meFetchedAt < ME_CACHE_MS
      ) {
        return { code: 200, data: { cached: true } }
      }
      const res = await getMe()
      this.meFetchedAt = now
      if (res.code === 200 && res.data) {
        if (res.data.is_admin != null) {
          this.isAdmin = !!res.data.is_admin
          localStorage.setItem(ADMIN_KEY, this.isAdmin ? 'true' : 'false')
        }
        this.applyAccess(res.data)
      }
      return res
    },

    async login(username, password) {
      const res = await apiLogin(username, password)
      if (res.code !== 200) {
        throw new Error(res.message || '登录失败')
      }
      const { access_token, is_admin, ...accessRest } = res.data
      this.token = access_token
      this.username = username
      this.isAdmin = !!is_admin
      localStorage.setItem(TOKEN_KEY, access_token)
      localStorage.setItem(USER_KEY, username)
      localStorage.setItem(ADMIN_KEY, this.isAdmin ? 'true' : 'false')
      this.applyAccess(accessRest)
      return res
    },

    logout() {
      this.token = ''
      this.username = ''
      this.isAdmin = false
      this.accessExpiresAt = null
      this.allowedCompetitions = null
      this.hasAllCompetitions = true
      this.accountExpired = false
      this.sportteryAccessGranted = false
      this.accessLoaded = false
      localStorage.removeItem(TOKEN_KEY)
      localStorage.removeItem(USER_KEY)
      localStorage.removeItem(ADMIN_KEY)
      localStorage.removeItem(ACCESS_KEY)
      router.push('/login')
    },
  },
})
