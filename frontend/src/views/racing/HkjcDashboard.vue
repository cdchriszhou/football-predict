<template>
  <div class="hkjc-dashboard">
    <div class="page-header">
      <div class="header-row">
        <div>
          <h2>{{ t('hkjc.dashboardTitle') }}</h2>
          <p>{{ t('hkjc.dashboardSubtitle') }}</p>
        </div>
        <div class="header-actions">
          <el-button type="primary" :icon="Refresh" :loading="loading" @click="loadData(true)">
            {{ t('common.refresh') }}
          </el-button>
          <el-button :loading="syncing || store.syncing" @click="syncData">
            {{ store.syncProgress || t('hkjc.syncData') }}
          </el-button>
        </div>
      </div>
    </div>

    <el-alert
      type="warning"
      :closable="false"
      show-icon
      class="disclaimer-alert"
      :title="disclaimer"
    />
    <p v-if="dataSource" class="data-source">{{ t('hkjc.dataSource', { source: dataSource }) }}</p>

    <el-alert
      v-if="schedule && schedule.has_meeting_today"
      type="success"
      :closable="false"
      show-icon
      class="schedule-alert"
      :title="t('hkjc.meetingToday', { date: schedule.today_label, venue: schedule.today_venue })"
    />
    <el-alert
      v-else-if="schedule"
      type="info"
      :closable="false"
      show-icon
      class="schedule-alert"
      :title="t('hkjc.noMeetingToday', { date: schedule.today_label })"
    />

    <div v-loading="loading">
      <el-row :gutter="20" class="stats-row">
        <el-col :xs="12" :sm="6" v-for="stat in stats" :key="stat.label">
          <div class="stat-card">
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
        <el-col :xs="24" :sm="14">
          <el-card class="section-card">
            <template #header>
              <div class="flex-between">
                <span class="card-title">{{ recentMeetingTitle }}</span>
                <el-button text type="primary" @click="goMeetings">{{ t('common.viewAll') }}</el-button>
              </div>
            </template>
            <el-empty v-if="!featured" :description="t('common.noData')" />
            <div v-else class="meeting-brief">
              <div class="meeting-meta">
                <el-tag type="success">{{ featured.venue }}</el-tag>
                <span>{{ formatDate(featured.date) }}</span>
                <span>{{ featured.track_type }} · {{ featured.track_rating }}</span>
                <span>{{ t('hkjc.raceCount', { n: featured.race_count }) }}</span>
              </div>
              <el-table :data="meetingWinners" stripe size="small" style="margin-top: 12px">
                <el-table-column prop="race_no" :label="t('hkjc.colRaceNo')" width="70" />
                <el-table-column :label="t('hkjc.colRaceInfo')" min-width="120">
                  <template #default="{ row }">
                    {{ row.distance_m }}m · {{ row.class }}
                  </template>
                </el-table-column>
                <el-table-column :label="t('hkjc.colWinner')" min-width="140">
                  <template #default="{ row }">
                    <span v-if="row.winner_name" class="winner-cell">
                      <span class="winner-no">{{ row.winner_horse_no }}</span>
                      {{ row.winner_name }}
                    </span>
                    <span v-else class="text-muted">{{ t('hkjc.pendingResult') }}</span>
                  </template>
                </el-table-column>
                <el-table-column prop="winner_jockey" :label="t('hkjc.colJockey')" min-width="90" />
                <el-table-column :label="t('hkjc.colOdds')" width="80">
                  <template #default="{ row }">
                    {{ row.winner_odds != null ? row.winner_odds : '—' }}
                  </template>
                </el-table-column>
                <el-table-column :label="t('hkjc.colAction')" width="80" fixed="right">
                  <template #default="{ row }">
                    <el-button
                      v-if="row.race_id"
                      link
                      type="primary"
                      size="small"
                      @click="goRace(row.race_id)"
                    >
                      {{ t('hkjc.viewAnalysis') }}
                    </el-button>
                  </template>
                </el-table-column>
              </el-table>
            </div>
          </el-card>
        </el-col>

        <el-col :xs="24" :sm="10">
          <el-card class="section-card">
            <template #header>
              <span class="card-title">{{ t('hkjc.modelPerformance') }}</span>
            </template>
            <div v-if="backtest" class="backtest-brief">
              <div class="accuracy-circle">
                <el-progress type="dashboard" :percentage="backtest.win_hit_rate || 0"
                             color="#006B54" :stroke-width="12">
                  <template #default="{ percentage }">
                    <span class="accuracy-num">{{ percentage }}%</span>
                  </template>
                </el-progress>
                <p class="accuracy-desc">{{ t('hkjc.winHitRate') }}</p>
              </div>
              <div class="accuracy-detail">
                <div class="detail-item">
                  <span class="label">{{ t('hkjc.placeTop3Rate') }}</span>
                  <span class="value">{{ backtest.place_top3_rate }}%</span>
                </div>
                <div class="detail-item">
                  <span class="label">{{ t('hkjc.highConfHit') }}</span>
                  <span class="value">{{ backtest.high_confidence_hit }}%</span>
                </div>
              </div>
              <el-button text type="primary" @click="goBacktest">{{ t('hkjc.viewBacktest') }}</el-button>
            </div>
          </el-card>

          <el-card class="section-card" style="margin-top: 20px">
            <template #header>
              <span class="card-title">{{ t('hkjc.algoTitle') }}</span>
            </template>
            <ol class="algo-list">
              <li v-for="(step, i) in algoSteps" :key="i">
                <strong>{{ step.title }}</strong>
                <span>{{ step.desc }}</span>
              </li>
            </ol>
          </el-card>
        </el-col>
      </el-row>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Calendar, DataAnalysis, Refresh, TrophyBase } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useCompetitionStore } from '@/stores/competition'
import { useHkjcStore } from '@/stores/hkjc'

const { t, tm } = useI18n()
const router = useRouter()
const compStore = useCompetitionStore()
const store = useHkjcStore()

const loading = ref(false)
const syncing = ref(false)
const disclaimer = ref('')
const dataSource = ref('')
const featured = ref(null)
const meetingWinners = ref([])
const backtest = ref(null)
const dashStats = ref({})
const schedule = ref(null)

const algoSteps = computed(() => tm('hkjc.algoSteps') || [])

const recentMeetingTitle = computed(() => {
  const label = schedule.value?.recent_meeting_label
  if (label) {
    return t('hkjc.recentMeeting', { label })
  }
  return t('hkjc.recentMeetingFallback')
})
const stats = computed(() => [
  { label: t('hkjc.statMeetings'), value: dashStats.value.meetings ?? '—', icon: Calendar, color: '#006B54' },
  { label: t('hkjc.statRaces'), value: dashStats.value.total_races ?? '—', icon: TrophyBase, color: '#1a237e' },
  { label: t('hkjc.statHorses'), value: dashStats.value.horses ?? '—', icon: DataAnalysis, color: '#e65100' },
  { label: t('hkjc.statWinRate'), value: dashStats.value.model_hit_rate ? `${dashStats.value.model_hit_rate}%` : '—', icon: DataAnalysis, color: '#4527a0' },
])

function formatDate(d) {
  if (!d) return ''
  return d.replace(/-/g, '/')
}

function goMeetings() {
  router.push(`${compStore.basePath}/meetings`)
}

function goRace(raceId) {
  router.push(`${compStore.basePath}/races/${raceId}`)
}

function goBacktest() {
  router.push(`${compStore.basePath}/backtest`)
}

async function loadData(refresh = false) {
  loading.value = true
  try {
    const data = await store.fetchDashboard(refresh)
    if (!data) return
    disclaimer.value = data.disclaimer || t('hkjc.disclaimer')
    dataSource.value = data.data_source || ''
    featured.value = data.featured_meeting
    meetingWinners.value = data.meeting_winners || []
    backtest.value = data.backtest
    dashStats.value = data.stats || {}
    schedule.value = data.schedule || null
  } finally {
    loading.value = false
  }
}

async function syncData() {
  if (store.syncing) {
    ElMessage.warning(t('hkjc.syncAlreadyRunning'))
    return
  }
  syncing.value = true
  ElMessage.info(t('hkjc.syncingBackground'))
  store.syncAll(14)
    .then(async () => {
      ElMessage.success(t('hkjc.syncDone'))
      await loadData(true)
    })
    .catch((e) => {
      const detail = e?.response?.data?.detail
      const msg = (typeof detail === 'string' ? detail : null)
        || e?.response?.data?.message
        || e?.message
        || t('hkjc.syncFailed')
      ElMessage.error(msg)
    })
    .finally(() => {
      syncing.value = false
    })
}

onMounted(() => loadData(false))
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
.header-actions { display: flex; gap: 8px; flex-shrink: 0; flex-wrap: wrap; }
.disclaimer-alert { margin-bottom: 8px; }
.data-source { font-size: 13px; color: #909399; margin: 0 0 12px; }
.schedule-alert { margin-bottom: 16px; }
.stats-row { margin-bottom: 4px; }
.stat-card { display: flex; align-items: center; gap: 16px; }
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
.flex-between { display: flex; justify-content: space-between; align-items: center; }
.meeting-meta { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; font-size: 13px; color: #606266; }
.winner-cell { font-weight: 600; color: #303133; }
.winner-no {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 22px;
  height: 22px;
  margin-right: 6px;
  border-radius: 4px;
  background: #006B54;
  color: #fff;
  font-size: 12px;
  font-weight: 700;
}
.text-muted { color: #c0c4cc; font-size: 13px; }
.accuracy-circle { text-align: center; padding: 10px 0; }
.accuracy-num { font-size: 28px; font-weight: 800; }
.accuracy-desc { font-size: 13px; color: #666; margin-top: 8px; }
.accuracy-detail { display: flex; justify-content: center; gap: 40px; margin-top: 12px; }
.detail-item { display: flex; flex-direction: column; align-items: center; }
.detail-item .label { font-size: 12px; color: #999; }
.detail-item .value { font-size: 18px; font-weight: 700; color: #006B54; }
.algo-list { margin: 0; padding-left: 20px; font-size: 13px; line-height: 1.7; color: #606266; }
.algo-list li { margin-bottom: 8px; }
.algo-list strong { display: block; color: #303133; margin-bottom: 2px; }
</style>
