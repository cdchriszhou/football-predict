<template>
  <div class="dashboard">
    <div class="page-header">
      <div class="header-row">
        <div>
          <h2>{{ dashboardTitle }}</h2>
          <p>{{ dashboardSubtitle }}</p>
        </div>
        <el-button
          type="primary"
          :icon="Refresh"
          :loading="updating"
          @click="manualUpdate"
        >
          {{ updating ? (updatePhase || t('dashboard.updating')) : t('dashboard.manualUpdate') }}
        </el-button>
      </div>
    </div>

    <!-- Stats row -->
    <el-row :gutter="20" class="stats-row">
      <el-col :xs="12" :sm="6" v-for="stat in stats" :key="stat.label">
        <div
          class="stat-card"
          :class="{ 'stat-card--clickable': stat.onClick }"
          @click="stat.onClick?.()"
        >
          <div class="stat-icon" :style="{ background: stat.color }">
            <el-icon :size="24" color="#fff"><component :is="stat.icon" /></el-icon>
          </div>
          <div class="stat-info">
            <span class="stat-value">{{ stat.value }}</span>
            <span class="stat-label">{{ stat.label }}</span>
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- This week's finished / live results -->
    <el-card class="section-card" style="margin-top: 20px">
      <template #header>
        <div class="flex-between">
          <span class="card-title">{{ t('dashboard.weekResults') }}</span>
          <el-button text type="primary" @click="goMatches">{{ t('dashboard.viewFullSchedule') }}</el-button>
        </div>
      </template>
      <el-empty v-if="initialLoading" :description="t('common.loading')" />
      <el-empty v-else-if="loadError && displayWeekResults.length === 0" :description="loadError" />
      <el-empty v-else-if="displayWeekResults.length === 0" :description="t('dashboard.noWeekResults')" />
      <el-row v-else :gutter="16">
        <el-col
          :xs="24" :sm="12" :lg="8"
          v-for="m in displayWeekResults"
          :key="'week-' + m.id"
        >
          <MatchCard :match="m" />
        </el-col>
      </el-row>
    </el-card>

    <el-row :gutter="20" style="margin-top: 20px">
      <!-- Prediction accuracy + Algorithm -->
      <el-col :xs="24" :sm="10">
        <el-card class="section-card">
          <template #header>
            <span class="card-title">{{ t('dashboard.accuracy') }}</span>
          </template>
          <div v-if="predStore.accuracy" class="accuracy-display">
            <div class="accuracy-circle">
              <el-progress type="dashboard" :percentage="predStore.accuracy.result_accuracy || 0"
                           :color="customColors" :stroke-width="12">
                <template #default="{ percentage }">
                  <span class="accuracy-num">{{ percentage }}%</span>
                </template>
              </el-progress>
              <p class="accuracy-desc">{{ t('dashboard.resultAccuracy') }}</p>
            </div>
            <div class="accuracy-detail">
              <div class="detail-item">
                <span class="label">{{ t('dashboard.scoreAccuracy') }}</span>
                <span class="value">{{ predStore.accuracy.score_accuracy || 0 }}%</span>
              </div>
              <div class="detail-item">
                <span class="label">{{ t('dashboard.evaluatedCount') }}</span>
                <span class="value">{{ t('dashboard.matchUnit', { n: predStore.accuracy.total || 0 }) }}</span>
              </div>
            </div>
          </div>
          <el-empty v-else :description="t('dashboard.noPredictionData')" :image-size="80" />
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="14">
        <el-card class="section-card algo-card">
          <template #header>
            <span class="card-title">{{ t('dashboard.algoTitle') }}</span>
          </template>
          <div class="algo-content">
            <p class="algo-intro">{{ t('dashboard.algoIntro') }}</p>
            <ol class="algo-list">
              <li v-for="(step, idx) in algoSteps" :key="idx">
                <strong>{{ step.title }}</strong>: {{ step.desc }}
              </li>
            </ol>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- League standings (club competitions only) -->
    <el-row v-if="isClubLeague" :gutter="20" style="margin-top: 20px">
      <el-col :span="24">
        <LeagueStandingsCard
          :rows="standings"
          :season="standingsSeason"
          :title="standingsTitle"
          :loading="standingsLoading"
          @view-all="goTeams"
          @select-team="goTeamDetail"
        />
      </el-col>
    </el-row>

    <!-- Upcoming matches -->
    <el-card class="section-card" style="margin-top: 20px">
      <template #header>
        <div class="flex-between">
          <span class="card-title">{{ upcomingSectionTitle }}</span>
          <el-button text type="primary" @click="goMatches">{{ t('dashboard.viewFullSchedule') }}</el-button>
        </div>
      </template>
      <el-empty
        v-if="seasonEnded"
        :description="t('dashboard.seasonEnded')"
      />
      <el-empty
        v-else-if="displayedUpcoming.length === 0"
        :description="t('dashboard.noUpcomingMatches')"
      >
        <el-button v-if="scheduleTotal > 0" type="primary" @click="goMatches">
          {{ t('dashboard.viewFullSchedule') }}
        </el-button>
      </el-empty>
      <el-row v-else :gutter="16">
        <el-col
          :xs="24" :sm="12" :lg="8"
          v-for="m in displayedUpcoming"
          :key="m.id"
        >
          <MatchCard :match="m" />
        </el-col>
      </el-row>
    </el-card>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { TrophyBase, Flag, TrendCharts, DataAnalysis, Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import MatchCard from '@/components/MatchCard.vue'
import LeagueStandingsCard from '@/components/LeagueStandingsCard.vue'
import { useMatchesStore } from '@/stores/matches'
import { usePredictionsStore } from '@/stores/predictions'
import { useCompetitionStore } from '@/stores/competition'
import { getTeamStandings } from '@/api/teams'
import { refreshAllData, getDataRefreshStatus } from '@/api/admin'
import { refreshLeagueData } from '@/api/competitions'
import { useRouter } from 'vue-router'
import { effectiveMatchStatus, hasMatchScore, isEffectiveMatchStatus } from '@/utils/matchStatus'

const { t, tm, locale } = useI18n()
const router = useRouter()
const store = useMatchesStore()
const predStore = usePredictionsStore()
const compStore = useCompetitionStore()

const initialLoading = ref(true)
const loadError = ref('')

function goMatches() {
  router.push(`${compStore.basePath}/matches`)
}

function goTeams() {
  router.push(`${compStore.basePath}/teams`)
}

function goTeamDetail(id) {
  router.push(`${compStore.basePath}/teams/${id}`)
}

const dashboardTitle = computed(() => {
  const key = compStore.current?.name_key
  if (!key) return t('dashboard.title')
  return t('dashboard.titleWithCompetition', {
    name: t(`competition.names.${key}`),
  })
})

const dashboardSubtitle = computed(() => {
  const league = compStore.current?.short_name
  return league ? t('dashboard.subtitleLeague', { league }) : t('dashboard.subtitle')
})

const seasonEnded = computed(() => compStore.current?.season_status === 'ended')
const isClubLeague = computed(() => compStore.current?.type === 'club')
const isFootball = computed(() => isClubLeague.value)

const scheduleTotal = computed(() => Number(statValues.value.total) || 0)

function beijingDateKey(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' })
}

/** Beijing calendar week Mon–Sun as YYYY-MM-DD keys. */
function beijingWeekBounds(now = new Date()) {
  const todayKey = now.toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' })
  const [y, m, d] = todayKey.split('-').map(Number)
  const localNoon = new Date(now.toLocaleString('en-US', { timeZone: 'Asia/Shanghai' }))
  const sun0 = localNoon.getDay() // 0=Sun … 6=Sat
  const monOffset = sun0 === 0 ? 6 : sun0 - 1
  const monday = new Date(Date.UTC(y, m - 1, d - monOffset))
  const sunday = new Date(Date.UTC(y, m - 1, d - monOffset + 6))
  return {
    startKey: monday.toISOString().slice(0, 10),
    endKey: sunday.toISOString().slice(0, 10),
  }
}

/** This week's finished/live results (Beijing Mon–Sun). */
const displayWeekResults = computed(() => {
  const { startKey, endKey } = beijingWeekBounds()
  const isScoredOrLive = (m) => (
    isEffectiveMatchStatus(m, 'finished') || isEffectiveMatchStatus(m, 'live')
  )
  const byId = new Map()
  for (const m of [...store.todayMatches, ...store.recentResults]) {
    const day = beijingDateKey(m.match_time)
    if (!day || day < startKey || day > endKey) continue
    if (!isScoredOrLive(m)) continue
    byId.set(m.id, m)
  }
  const rows = [...byId.values()].sort(
    (a, b) => new Date(a.match_time || 0) - new Date(b.match_time || 0),
  )
  const seenPairs = new Set()
  const deduped = []
  for (const m of rows) {
    const pairKey = [
      m.stage || '',
      [m.team_a || '', m.team_b || ''].map(String).sort().join('|'),
      beijingDateKey(m.match_time),
    ].join('::')
    if (seenPairs.has(pairKey)) continue
    seenPairs.add(pairKey)
    deduped.push(m)
  }
  return deduped
})

const upcomingPreviewLimit = computed(() => 6)

const displayedUpcoming = computed(() =>
  store.upcomingMatches.slice(0, upcomingPreviewLimit.value),
)

const upcomingSectionTitle = computed(() => t('dashboard.upcoming'))

const standings = ref([])
const standingsLoading = ref(false)

const standingsSeason = computed(() => standings.value[0]?.season || compStore.current?.season || '')
const standingsTitle = computed(() => {
  const league = compStore.current?.short_name
  return league
    ? t('dashboard.standingsTitleLeague', { league })
    : t('dashboard.standingsTitle')
})

const algoSteps = computed(() => {
  const steps = tm('dashboard.algoSteps')
  return Array.isArray(steps) ? steps : []
})

const customColors = [
  { color: '#f44336', percentage: 50 },
  { color: '#ff9800', percentage: 70 },
  { color: '#4caf50', percentage: 100 }
]

const statValues = ref({
  total: 0,
  teams: 0,
  predicted: 0,
  updateTime: '—'
})

const stats = computed(() => [
  { label: t('dashboard.statTotalMatches'), value: statValues.value.total, icon: 'TrophyBase', color: '#1a237e' },
  { label: t('dashboard.statTeams'), value: statValues.value.teams, icon: 'Flag', color: '#0d47a1', onClick: goTeams },
  { label: t('dashboard.statPredicted'), value: statValues.value.predicted, icon: 'TrendCharts', color: '#00838f' },
  { label: t('dashboard.statUpdateTime'), value: statValues.value.updateTime, icon: 'DataAnalysis', color: '#e65100' }
])

const updating = ref(false)
const updatePhase = ref('')

async function loadStandings() {
  if (!isClubLeague.value) {
    standings.value = []
    return
  }
  standingsLoading.value = true
  try {
    const res = await getTeamStandings()
    standings.value = Array.isArray(res.data) ? res.data : []
  } catch {
    standings.value = []
  } finally {
    standingsLoading.value = false
  }
}

async function loadDashboard() {
  initialLoading.value = true
  loadError.value = ''

  // Separate data calls (all must succeed for meaningful dashboard) from setup calls
  const dataCalls = [
    { key: 'today', p: store.fetchToday() },
    { key: 'upcoming', p: store.fetchUpcoming(12) },
    { key: 'accuracy', p: predStore.fetchAccuracy(30) },
  ]
  if (isFootball.value) {
    dataCalls.push(
      { key: 'recentResults', p: store.fetchRecentResults(168, 50) },
    )
  }
  const settled = await Promise.allSettled([
    ...dataCalls.map((d) => d.p),
    compStore.fetchCurrent().catch(() => null),
  ])

  // Check data-call failures (exclude the always-resolved fetchCurrent)
  const dataFailed = []
  for (let i = 0; i < dataCalls.length; i++) {
    const r = settled[i]
    if (r.status === 'rejected') {
      const err = r.reason
      const status = err?.response?.status || 'network'
      console.warn(`[dashboard] ${dataCalls[i].key} failed (HTTP ${status}):`, err?.message || err)
      dataFailed.push(dataCalls[i].key)
    }
  }

  if (dataFailed.length === dataCalls.length) {
    // All data APIs failed — likely a connectivity or auth issue
    console.error('[dashboard] All data APIs failed:', dataFailed)
    loadError.value = t('dashboard.loadFailed')
    ElMessage.warning(t('dashboard.loadFailed'))
    initialLoading.value = false
    return
  }
  if (dataFailed.length) {
    console.warn('[dashboard] partial load failures:', dataFailed)
    const scoreKeys = ['today', 'recentResults']
    if (dataFailed.some((k) => scoreKeys.includes(k))) {
      ElMessage.warning(t('dashboard.scoreLoadPartial'))
    }
  }

  await loadStandings()
  if (compStore.current?.stats) {
    statValues.value.total = compStore.current.stats.matches || 0
    statValues.value.teams = compStore.current.stats.teams || 0
  }
  const ids = [...displayWeekResults.value, ...store.upcomingMatches].map(m => m.id)
  if (ids.length) await predStore.fetchBatch(ids)
  statValues.value.predicted = Object.keys(predStore.cache).length || '—'
  statValues.value.updateTime = new Date().toLocaleString(locale.value)
  syncScorePolling()
  initialLoading.value = false
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

const phaseLabels = {
  schedule: () => t('dashboard.updatePartSchedule'),
  team: () => t('dashboard.updatePartTeam'),
  odds: () => t('dashboard.updatePartOdds'),
  predictions: () => t('dashboard.updatePartPredicting'),
}

async function pollDataRefresh() {
  const maxPolls = 600
  for (let i = 0; i < maxPolls; i++) {
    const res = await getDataRefreshStatus()
    const s = res.data || {}
    const intervalMs = s.phase === 'predictions' ? 4000 : 2500
    if (s.running) {
      updatePhase.value = phaseLabels[s.phase]?.() || t('dashboard.updating')
      await sleep(intervalMs)
      continue
    }
    if (s.error) {
      throw new Error(s.error)
    }
    const parts = []
    if (s.schedule?.status !== 'failed') parts.push(t('dashboard.updatePartSchedule'))
    if (s.team?.status !== 'failed') parts.push(t('dashboard.updatePartTeam'))
    if (s.odds?.status !== 'failed') parts.push(t('dashboard.updatePartOdds'))
    const predCount = s.predictions?.count || 0
    if (s.predictions?.status !== 'failed') {
      parts.push(t('dashboard.updatePartPredict', { n: predCount }))
    }
    if (parts.length) {
      ElMessage.success(t('dashboard.updateDone', { parts: parts.join('、') }))
    } else {
      ElMessage.success(t('dashboard.updateDoneSimple'))
    }
    return
  }
  throw new Error(t('dashboard.refreshTimeout'))
}

async function manualUpdate() {
  updating.value = true
  updatePhase.value = ''
  try {
    ElMessage.info(t('dashboard.updatingData'))
    if (compStore.current?.type === 'club') {
      const res = await refreshLeagueData(compStore.slug)
      if (res.code === 200) {
        ElMessage.success(t('dashboard.updateDoneSimple'))
      }
    } else {
      const res = await refreshAllData(true)
      if (res.code === 409) {
        ElMessage.warning(res.message || t('dashboard.refreshAlreadyRunning'))
      } else if (res.code !== 200) {
        throw new Error(res.message || t('dashboard.updateFailed'))
      }
      await pollDataRefresh()
    }
    await loadDashboard()
  } catch (e) {
    const msg = e.response?.data?.message || e.message || t('dashboard.updateFailed')
    ElMessage.error(msg)
  } finally {
    updating.value = false
    updatePhase.value = ''
  }
}

watch(
  () => compStore.slug,
  (slug) => {
    if (slug) loadDashboard()
  },
  { immediate: true },
)

const SCORE_POLL_MS = 15_000
let scorePollTimer = null

function needsScoreRefresh() {
  const matches = [
    ...store.todayMatches,
    ...store.recentResults,
    ...store.upcomingMatches.slice(0, 6),
  ]
  return matches.some((m) => {
    const st = effectiveMatchStatus(m)
    return st === 'live' || (st === 'finished' && !hasMatchScore(m))
  }) || (isFootball.value && (store.todayMatches.length > 0 || store.recentResults.length > 0))
}

async function refreshMatchScores() {
  try {
    await Promise.all([
      store.fetchToday(),
      store.fetchUpcoming(12),
      isFootball.value ? store.fetchRecentResults(168, 50) : Promise.resolve(),
    ])
  } catch {
    /* ignore transient poll errors */
  }
}

function syncScorePolling() {
  clearInterval(scorePollTimer)
  if (isFootball.value || needsScoreRefresh()) {
    scorePollTimer = setInterval(refreshMatchScores, SCORE_POLL_MS)
  }
}

watch(
  () => [store.todayMatches, store.upcomingMatches],
  () => syncScorePolling(),
  { deep: true },
)

onMounted(() => {
  syncScorePolling()
})

onUnmounted(() => {
  clearInterval(scorePollTimer)
})
</script>

<style scoped>
.header-row {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
}
.header-row h2 { margin: 0; }
.header-row p { margin: 4px 0 0; }
.stats-row { margin-bottom: 4px; }
.stat-card { display: flex; align-items: center; gap: 16px; }
.stat-card--clickable { cursor: pointer; }
.stat-card--clickable:active { transform: translateY(0); }
.stat-icon {
  width: 52px; height: 52px;
  border-radius: 12px;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.stat-info { display: flex; flex-direction: column; }
.stat-value { font-size: 28px; font-weight: 800; color: #1a237e; }
.stat-label { font-size: 13px; color: #999; margin-top: 2px; }
.section-card { border-radius: 12px; }
.card-title { font-size: 16px; font-weight: 700; }
.flex-between { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.schedule-hint { margin: 0 0 12px; font-size: 13px; color: #909399; line-height: 1.5; }
.section-card :deep(.el-col) { margin-bottom: 16px; }
.accuracy-display { text-align: center; padding: 10px 0; }
.accuracy-num { font-size: 28px; font-weight: 800; }
.accuracy-desc { font-size: 13px; color: #666; margin-top: 8px; }
.accuracy-detail { display: flex; justify-content: center; gap: 40px; margin-top: 12px; }
.detail-item { text-align: center; }
.detail-item .label { font-size: 12px; color: #999; display: block; }
.detail-item .value { font-size: 18px; font-weight: 700; color: #1a237e; }

.daily-report-card .report-updated {
  display: block;
  font-size: 12px;
  font-weight: 400;
  color: #909399;
  margin-top: 4px;
}
.daily-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 24px;
  margin-bottom: 16px;
  padding: 4px 0 8px;
}
.summary-item { display: flex; flex-direction: column; min-width: 120px; }
.summary-label { font-size: 12px; color: #909399; }
.summary-value { font-size: 24px; font-weight: 800; color: #1a237e; line-height: 1.2; }
.summary-value.highlight { color: #00838f; }
.summary-sub { font-size: 12px; color: #666; margin-top: 4px; }
.daily-table { margin-top: 4px; }

.algo-card { max-height: 480px; display: flex; flex-direction: column; }
.algo-card :deep(.el-card__body) { flex: 1; overflow: hidden; padding: 16px; }
.algo-content { max-height: 360px; overflow-y: auto; padding-right: 4px; }
.algo-intro { font-size: 14px; font-weight: 600; color: #1d1d1f; margin: 0 0 10px; }
.algo-list { margin: 0; padding-left: 20px; font-size: 13px; color: #555; line-height: 1.85; }
.algo-list li { margin-bottom: 6px; }
.algo-list strong { color: #1a237e; font-weight: 600; }

@media (max-width: 767px) {
  .header-row { flex-direction: column; gap: 12px; }
  .header-row .el-button { width: 100%; }
  .stat-value { font-size: 22px; }
  .stat-icon { width: 40px; height: 40px; }
  .stat-card { gap: 10px; }
  .accuracy-detail { gap: 20px; }
  .accuracy-display { padding: 0; }
  .section-card { margin-top: 12px !important; }
  .algo-card { max-height: none; }
  .algo-content { max-height: none; overflow-y: visible; }
}
</style>
