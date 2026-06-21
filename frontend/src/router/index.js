import { createRouter, createWebHistory } from 'vue-router'
import i18n from '@/i18n'

const competitionRoutes = [
  {
    path: '',
    name: 'CompetitionDashboard',
    component: () => import('../views/CompetitionEntry.vue'),
    meta: { titleKey: 'route.dashboard' }
  },
  {
    path: 'matches',
    name: 'MatchList',
    component: () => import('../views/MatchList.vue'),
    meta: { titleKey: 'route.matches', footballOnly: true }
  },
  {
    path: 'matches/:id',
    name: 'MatchDetail',
    component: () => import('../views/MatchDetail.vue'),
    meta: { titleKey: 'route.matchDetail', footballOnly: true }
  },
  {
    path: 'sporttery-plan',
    name: 'SportteryPlan',
    component: () => import('../views/SportteryPlan.vue'),
    meta: { titleKey: 'route.sportteryPlan', footballOnly: true }
  },
  {
    path: 'teams',
    name: 'TeamList',
    component: () => import('../views/TeamList.vue'),
    meta: { titleKey: 'route.teams', footballOnly: true }
  },
  {
    path: 'teams/:id',
    name: 'TeamDetail',
    component: () => import('../views/TeamDetail.vue'),
    meta: { titleKey: 'route.teamDetail', footballOnly: true }
  },
  {
    path: 'bracket',
    name: 'Bracket',
    component: () => import('../views/Bracket.vue'),
    meta: { titleKey: 'route.bracket', feature: 'bracket' }
  },
  {
    path: 'tournament',
    name: 'TournamentPredict',
    component: () => import('../views/TournamentPredict.vue'),
    meta: { titleKey: 'route.tournament', feature: 'tournament' }
  },
  {
    path: 'predictions',
    name: 'Predictions',
    component: () => import('../views/PredictionHistory.vue'),
    meta: { titleKey: 'route.predictions', footballOnly: true }
  },
  {
    path: 'purchase-advice',
    name: 'HkjcPurchaseAdvice',
    component: () => import('../views/racing/HkjcPurchaseAdvice.vue'),
    meta: { titleKey: 'route.hkjcPurchaseAdvice', racingOnly: true }
  },
  {
    path: 'meetings',
    name: 'HkjcMeetings',
    component: () => import('../views/racing/HkjcMeetingList.vue'),
    meta: { titleKey: 'route.hkjcMeetings', racingOnly: true }
  },
  {
    path: 'meetings/:meetingId',
    name: 'HkjcMeetingDetail',
    component: () => import('../views/racing/HkjcMeetingDetail.vue'),
    meta: { titleKey: 'route.hkjcMeetingDetail', racingOnly: true }
  },
  {
    path: 'races/:id',
    name: 'HkjcRaceDetail',
    component: () => import('../views/racing/HkjcRaceDetail.vue'),
    meta: { titleKey: 'route.hkjcRaceDetail', racingOnly: true }
  },
  {
    path: 'horses',
    name: 'HkjcHorses',
    component: () => import('../views/racing/HkjcHorseList.vue'),
    meta: { titleKey: 'route.hkjcHorses', racingOnly: true }
  },
  {
    path: 'backtest',
    name: 'ModelBacktest',
    component: () => import('../views/BacktestEntry.vue'),
    meta: { titleKey: 'route.modelBacktest' }
  },
]

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('../views/Login.vue'),
    meta: { titleKey: 'route.login', public: true }
  },
  {
    path: '/register',
    name: 'Register',
    component: () => import('../views/Register.vue'),
    meta: { titleKey: 'route.register', public: true }
  },
  {
    path: '/forgot-password',
    name: 'ForgotPassword',
    component: () => import('../views/ForgotPassword.vue'),
    meta: { titleKey: 'route.forgotPassword', public: true }
  },
  {
    path: '/reset-password',
    name: 'ResetPassword',
    component: () => import('../views/ResetPassword.vue'),
    meta: { titleKey: 'route.resetPassword', public: true }
  },
  {
    path: '/',
    name: 'CompetitionHome',
    component: () => import('../views/CompetitionHome.vue'),
    meta: { titleKey: 'route.competitionHome', layout: 'portal' }
  },
  {
    path: '/competition/:slug',
    component: () => import('../views/CompetitionShell.vue'),
    children: competitionRoutes,
  },
  {
    path: '/admin',
    name: 'AdminPanel',
    component: () => import('../views/AdminPanel.vue'),
    meta: { titleKey: 'route.admin' }
  },
  // Backward-compatible redirects
  { path: '/matches', redirect: '/competition/worldcup-2026/matches' },
  { path: '/matches/:id', redirect: to => `/competition/worldcup-2026/matches/${to.params.id}` },
  { path: '/sporttery-plan', redirect: '/competition/worldcup-2026/sporttery-plan' },
  { path: '/teams', redirect: '/competition/worldcup-2026/teams' },
  { path: '/teams/:id', redirect: to => `/competition/worldcup-2026/teams/${to.params.id}` },
  { path: '/bracket', redirect: '/competition/worldcup-2026/bracket' },
  { path: '/tournament', redirect: '/competition/worldcup-2026/tournament' },
  { path: '/predictions', redirect: '/competition/worldcup-2026/predictions' },
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

const TOKEN_KEY = 'worldcup_auth_token'
const ADMIN_KEY = 'worldcup_auth_is_admin'

router.beforeEach(async (to, from, next) => {
  const token = localStorage.getItem(TOKEN_KEY)

  if (to.meta.public) {
    if (token && to.path === '/login') {
      return next('/')
    }
    return next()
  }

  if (!token) {
    return next('/login')
  }

  if (!to.meta.public) {
    const { useAuthStore } = await import('@/stores/auth')
    const authStore = useAuthStore()
    await authStore.fetchMe({ force: false }).catch(() => null)
  }

  if (to.path === '/admin' && localStorage.getItem(ADMIN_KEY) !== 'true') {
    return next('/')
  }

  if (to.params.slug && to.path.startsWith('/competition/')) {
    const { useAuthStore } = await import('@/stores/auth')
    const authStore = useAuthStore()
    if (to.name === 'SportteryPlan' && !authStore.canAccessSporttery) {
      const { ElMessage } = await import('element-plus')
      ElMessage.warning('您暂无体彩购买方案访问权限，请联系管理员开通')
      return next({ name: 'CompetitionDashboard', params: { slug: to.params.slug } })
    }
    if (!authStore.canAccessCompetition(to.params.slug)) {
      const { ElMessage } = await import('element-plus')
      ElMessage.warning(authStore.accessDeniedMessage(to.params.slug))
      return next('/')
    }
  }

  if (to.params.slug && to.path.startsWith('/competition/')) {
    const { useCompetitionStore } = await import('@/stores/competition')
    const compStore = useCompetitionStore()
    if (!compStore.current || compStore.slug !== to.params.slug) {
      compStore.setSlug(to.params.slug)
      await compStore.fetchCurrent(to.params.slug).catch(() => null)
    }
    if (to.meta.feature) {
      const features = compStore.current?.features || {}
      if (!features[to.meta.feature]) {
        return next({ name: 'CompetitionDashboard', params: { slug: to.params.slug } })
      }
    }
    const isRacing = compStore.isRacing
    if (to.meta.racingOnly && !isRacing) {
      return next({ name: 'CompetitionDashboard', params: { slug: to.params.slug } })
    }
    if (to.meta.footballOnly && isRacing) {
      return next({ name: 'CompetitionDashboard', params: { slug: to.params.slug } })
    }
  }

  if (to.params.slug) {
    localStorage.setItem('worldcup_competition_slug', to.params.slug)
  }

  next()
})

router.afterEach((to) => {
  const { t } = i18n.global
  const page = to.meta.titleKey ? t(to.meta.titleKey) : ''
  const appTitle = t('auth.loginTitle')
  document.title = page ? `${page} - ${appTitle}` : appTitle
})

export default router
