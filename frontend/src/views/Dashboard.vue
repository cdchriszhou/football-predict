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

    <el-row :gutter="20" style="margin-top: 20px">
      <!-- Today's matches -->
      <el-col :xs="24" :sm="14">
        <el-card class="section-card">
          <template #header>
            <div class="flex-between">
              <span class="card-title">{{ t('dashboard.todayMatches') }}</span>
              <el-button text type="primary" @click="goMatches">{{ t('dashboard.viewFullSchedule') }}</el-button>
            </div>
          </template>
          <el-empty v-if="initialLoading" :description="t('common.loading')" />
          <el-empty v-else-if="loadError && displayTodayMatches.length === 0" :description="loadError" />
          <el-empty v-else-if="displayTodayMatches.length === 0" :description="t('dashboard.noTodayMatches')" />
          <div v-else class="today-matches">
            <MatchCard v-for="m in displayTodayMatches" :key="m.id" :match="m" />
          </div>
        </el-card>
      </el-col>

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

        <el-card class="section-card algo-card" style="margin-top: 20px">
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

    <!-- Recent finished results (World Cup) — skip when all already shown in 今日赛果 -->
    <el-card
      v-if="compStore.isWorldCup && displayedRecentResults.length"
      class="section-card"
      style="margin-top: 20px"
    >
      <template #header>
        <div class="flex-between">
          <span class="card-title">{{ t('dashboard.recentResults') }}</span>
          <el-button text type="primary" @click="goMatches">{{ t('dashboard.viewFullSchedule') }}</el-button>
        </div>
      </template>
      <el-row :gutter="16">
        <el-col
          :xs="24" :sm="12" :lg="8"
          v-for="m in displayedRecentResults"
          :key="'recent-' + m.id"
        >
          <MatchCard :match="m" />
        </el-col>
      </el-row>
    </el-card>

    <!-- Daily score backtest report (World Cup) -->
    <el-card v-if="compStore.isWorldCup" class="section-card daily-report-card" style="margin-top: 20px">
      <template #header>
        <div class="flex-between">
          <div>
            <span class="card-title">{{ t('dashboard.dailyReportTitle') }}</span>
            <span v-if="dailyReport?.computed_at" class="report-updated">
              {{ t('dashboard.dailyReportUpdated', { time: formatReportTime(dailyReport.computed_at) }) }}
            </span>
          </div>
          <el-button text type="primary" @click="goBacktest">{{ t('dashboard.dailyReportDetail') }}</el-button>
        </div>
      </template>
      <div v-loading="dailyReportLoading">
        <el-empty
          v-if="!dailyReportLoading && !dailyReportDays.length"
          :description="t('dashboard.dailyReportEmpty')"
          :image-size="72"
        />
        <template v-else-if="dailyReport">
          <div class="daily-summary">
            <div class="summary-item">
              <span class="summary-label">{{ t('dashboard.dailyReportRolling7d') }}</span>
              <span class="summary-value highlight">{{ dailyReport.summary?.rolling_7d_triple_hit_rate ?? 0 }}%</span>
              <span class="summary-sub">{{ t('scoreBacktest.tripleHitRate') }}</span>
            </div>
            <div class="summary-item">
              <span class="summary-label">{{ t('dashboard.dailyReportRolling7d') }}</span>
              <span class="summary-value">{{ dailyReport.summary?.rolling_7d_primary_hit_rate ?? 0 }}%</span>
              <span class="summary-sub">{{ t('scoreBacktest.primaryHitRate') }}</span>
            </div>
            <div class="summary-item" v-if="dailyReport.today">
              <span class="summary-label">{{ t('dashboard.dailyReportToday') }}</span>
              <span class="summary-value highlight">{{ dailyReport.today.triple_hit_rate }}%</span>
              <span class="summary-sub">
                {{ t('dashboard.dailyReportTodaySub', {
                  primary: dailyReport.today.primary_hits,
                  triple: dailyReport.today.triple_hits,
                  total: dailyReport.today.evaluated,
                }) }}
              </span>
            </div>
          </div>
          <div class="table-responsive">
            <el-table :data="dailyReportDays" stripe size="small" class="daily-table">
              <el-table-column :label="t('dashboard.dailyReportColDate')" min-width="108">
                <template #default="{ row }">{{ formatReportDate(row.date) }}</template>
              </el-table-column>
              <el-table-column :label="t('dashboard.dailyReportColMatches')" width="72" align="center">
                <template #default="{ row }">{{ row.evaluated }}</template>
              </el-table-column>
              <el-table-column :label="t('scoreBacktest.primaryHitRate')" width="100" align="center">
                <template #default="{ row }">
                  {{ row.primary_hits }}/{{ row.evaluated }} ({{ row.primary_hit_rate }}%)
                </template>
              </el-table-column>
              <el-table-column :label="t('scoreBacktest.tripleHitRate')" width="100" align="center">
                <template #default="{ row }">
                  <el-tag :type="row.triple_hit_rate >= 50 ? 'success' : 'info'" size="small">
                    {{ row.triple_hits }}/{{ row.evaluated }} ({{ row.triple_hit_rate }}%)
                  </el-tag>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </template>
      </div>
    </el-card>

    <!-- Upcoming matches -->
    <el-card class="section-card" style="margin-top: 20px">
      <template #header>
        <div class="flex-between">
          <span class="card-title">{{ upcomingSectionTitle }}</span>
          <el-button text type="primary" @click="goMatches">{{ t('dashboard.viewFullSchedule') }}</el-button>
        </div>
      </template>
      <p v-if="compStore.isWorldCup && scheduleTotal > 0" class="schedule-hint">
        {{ t('dashboard.worldCupScheduleHint', { shown: displayedUpcoming.length, total: scheduleTotal }) }}
      </p>
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
import { getDailyScoreBacktest } from '@/api/predictions'
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

function goBacktest() {
  router.push(`${compStore.basePath}/backtest`)
}

const dailyReport = ref(null)
const dailyReportLoading = ref(false)

const dailyReportDays = computed(() => {
  const days = dailyReport.value?.days
  if (!Array.isArray(days)) return []
  return [...days].reverse()
})

function formatReportDate(dateStr) {
  if (!dateStr) return '—'
  const d = new Date(`${dateStr}T12:00:00`)
  if (Number.isNaN(d.getTime())) return dateStr
  return d.toLocaleDateString(locale.value, { month: 'short', day: 'numeric' })
}

function formatReportTime(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString(locale.value, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

async function loadDailyReport() {
  if (!compStore.isWorldCup) {
    dailyReport.value = null
    return
  }
  dailyReportLoading.value = true
  try {
    const res = await getDailyScoreBacktest(30)
    dailyReport.value = res.data || null
  } catch {
    dailyReport.value = null
  } finally {
    dailyReportLoading.value = false
  }
}

const dashboardTitle = computed(() => {
  const key = compStore.current?.name_key
  if (!key) return t('dashboard.title')
  return t('dashboard.titleWithCompetition', {
    name: t(`competition.names.${key}`),
  })
})

const dashboardSubtitle = computed(() => {
  if (compStore.isWorldCup) return t('dashboard.subtitle')
  const league = compStore.current?.short_name
  return league ? t('dashboard.subtitleLeague', { league }) : t('dashboard.subtitle')
})

const seasonEnded = computed(() => compStore.current?.season_status === 'ended')
const isClubLeague = computed(() => compStore.current?.type === 'club')

const scheduleTotal = computed(() => Number(statValues.value.total) || 0)

function beijingDateKey(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' })
}

const beijingTodayKey = computed(() =>
  new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' }),
)

/** Today's results: prefer finished/live matches; fall back to full schedule. */
const displayTodayMatches = computed(() => {
  const todayKey = beijingTodayKey.value
  const byId = new Map()
  for (const m of store.todayMatches) {
    if (beijingDateKey(m.match_time) === todayKey) byId.set(m.id, m)
  }
  // Rest day / empty today: show latest finished results, but keep one section only
  // (exclude them from 「最近赛果」 via displayedRecentResults).
  if (!byId.size && compStore.isWorldCup) {
    for (const m of store.todayMatches) {
      byId.set(m.id, m)
    }
  }
  if (!byId.size && compStore.isWorldCup) {
    for (const m of store.recentResults) {
      byId.set(m.id, m)
    }
  }
  const rows = [...byId.values()].sort(
    (a, b) => new Date(a.match_time || 0) - new Date(b.match_time || 0),
  )
  // Dedupe by stage + team pair in case API returns placeholder + advanced rows.
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
  const withScore = deduped.filter(
    (m) => isEffectiveMatchStatus(m, 'finished') || isEffectiveMatchStatus(m, 'live'),
  )
  return withScore.length ? withScore : deduped
})

/** Recent results excluding matches already shown under 「今日赛果」. */
const displayedRecentResults = computed(() => {
  const todayIds = new Set(displayTodayMatches.value.map((m) => m.id))
  const seenPairs = new Set(
    displayTodayMatches.value.map((m) =>
      [m.stage || '', [m.team_a || '', m.team_b || ''].map(String).sort().join('|')].join('::'),
    ),
  )
  return store.recentResults.filter((m) => {
    if (todayIds.has(m.id)) return false
    const pairKey = [m.stage || '', [m.team_a || '', m.team_b || ''].map(String).sort().join('|')].join('::')
    return !seenPairs.has(pairKey)
  })
})

const upcomingPreviewLimit = computed(() => (compStore.isWorldCup ? 12 : 6))

const displayedUpcoming = computed(() =>
  store.upcomingMatches.slice(0, upcomingPreviewLimit.value),
)

const upcomingSectionTitle = computed(() => {
  if (compStore.isWorldCup) return t('dashboard.upcomingWorldCup')
  return t('dashboard.upcoming')
})

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
    { key: 'upcoming', p: store.fetchUpcoming(compStore.isWorldCup ? 50 : 12) },
    { key: 'accuracy', p: predStore.fetchAccuracy(30) },
  ]
  if (compStore.isWorldCup) {
    dataCalls.push(
      { key: 'recentResults', p: store.fetchRecentResults(72, 12) },
      { key: 'dailyReport', p: loadDailyReport() },
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
  const ids = [...store.todayMatches, ...store.upcomingMatches].map(m => m.id)
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
  }) || (compStore.isWorldCup && store.todayMatches.length > 0)
}

async function refreshMatchScores() {
  try {
    await Promise.all([
      store.fetchToday(),
      store.fetchUpcoming(compStore.isWorldCup ? 50 : 12),
      compStore.isWorldCup ? store.fetchRecentResults(72, 12) : Promise.resolve(),
      compStore.isWorldCup ? loadDailyReport() : Promise.resolve(),
    ])
  } catch {
    /* ignore transient poll errors */
  }
}

function syncScorePolling() {
  clearInterval(scorePollTimer)
  if (compStore.isWorldCup || needsScoreRefresh()) {
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
.today-matches { display: flex; flex-direction: column; gap: 12px; }
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
