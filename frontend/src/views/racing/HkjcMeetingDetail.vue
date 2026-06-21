<template>
  <div class="hkjc-meeting-detail">
    <div class="page-header">
      <div class="header-row">
        <div>
          <el-button link type="primary" @click="goBack">{{ t('hkjc.backToMeetings') }}</el-button>
          <div class="title-row">
            <h2>{{ meeting?.venue }} · {{ formatDate(meeting?.date) }}</h2>
            <el-tag v-if="meeting?.status" :type="statusType(meeting.status)" size="small">
              {{ statusLabel(meeting.status) }}
            </el-tag>
          </div>
          <p>{{ meeting?.track_type }} · {{ meeting?.track_rating }} · {{ t('hkjc.raceCount', { n: meeting?.race_count || 0 }) }}</p>
        </div>
        <el-button type="primary" :loading="loading" @click="loadData">{{ t('common.refresh') }}</el-button>
      </div>
    </div>

    <el-alert type="warning" :closable="false" show-icon class="disclaimer-alert" :title="disclaimer" />
    <el-alert
      v-if="meeting?.status === 'SCHEDULED'"
      type="info"
      :closable="false"
      show-icon
      class="schedule-alert"
      :title="t('hkjc.scheduledMeetingHint')"
    />

    <div v-loading="loading">
      <el-card v-if="isResultMode" class="section-card">
        <template #header>
          <span class="card-title">{{ t('hkjc.raceResults') }}</span>
        </template>
        <el-table :data="racePicks" stripe>
          <el-table-column prop="race_no" :label="t('hkjc.colRaceNo')" width="70" />
          <el-table-column :label="t('hkjc.colRaceInfo')" min-width="140">
            <template #default="{ row }">{{ row.distance_m }}m · {{ row.class }}</template>
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
          <el-table-column :label="t('hkjc.colSummary')" min-width="200">
            <template #default="{ row }">
              <span class="summary-text">{{ row.summary }}</span>
            </template>
          </el-table-column>
          <el-table-column :label="t('hkjc.colAction')" width="100" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" @click="goRace(row.race_id)">{{ t('hkjc.viewResult') }}</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <el-card v-else-if="meeting?.status !== 'SCHEDULED'" class="section-card">
        <template #header>
          <span class="card-title">{{ t('hkjc.raceScreening') }}</span>
        </template>
        <el-table :data="racePicks" stripe>
          <el-table-column prop="race_no" :label="t('hkjc.colRaceNo')" width="70" />
          <el-table-column :label="t('hkjc.colRaceInfo')" min-width="140">
            <template #default="{ row }">{{ row.distance_m }}m · {{ row.class }}</template>
          </el-table-column>
          <el-table-column :label="t('hkjc.colCertainty')" width="100">
            <template #default="{ row }">
              <el-tag :type="certaintyType(row.certainty)" size="small">{{ certaintyLabel(row.certainty) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="top_pick" :label="t('hkjc.colTopPick')" min-width="100" />
          <el-table-column :label="t('hkjc.colSummary')" min-width="200">
            <template #default="{ row }">
              <span class="summary-text">{{ row.summary }}</span>
            </template>
          </el-table-column>
          <el-table-column :label="t('hkjc.colAction')" width="100" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" @click="goRace(row.race_id)">{{ t('hkjc.viewAnalysis') }}</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <el-card class="section-card" style="margin-top: 20px">
        <template #header>
          <span class="card-title">{{ t('hkjc.allRaces') }}</span>
        </template>
        <el-table :data="meeting?.races || []" stripe>
          <el-table-column prop="race_no" :label="t('hkjc.colRaceNo')" width="70" />
          <el-table-column prop="name" :label="t('hkjc.colRaceName')" width="90" />
          <el-table-column :label="t('hkjc.colRaceInfo')" min-width="120">
            <template #default="{ row }">{{ row.distance_m }}m · {{ row.class }}</template>
          </el-table-column>
          <el-table-column :label="t('hkjc.colStartTime')" width="160">
            <template #default="{ row }">{{ formatTime(row.start_time) }}</template>
          </el-table-column>
          <el-table-column prop="runner_count" :label="t('hkjc.colRunners')" width="80" />
          <el-table-column v-if="!isResultMode" :label="t('hkjc.colRisk')" width="90">
            <template #default="{ row }">
              <el-tag :type="riskType(row.risk_level)" size="small">{{ riskLabel(row.risk_level) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column :label="t('hkjc.colAction')" width="100" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" @click="goRace(row.id)">
                {{ isResultMode ? t('hkjc.viewResult') : t('hkjc.viewAnalysis') }}
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useCompetitionStore } from '@/stores/competition'
import { useHkjcStore } from '@/stores/hkjc'
import { formatDateTimeInTz } from '@/utils/timezone'

const { t, locale } = useI18n()
const route = useRoute()
const router = useRouter()
const compStore = useCompetitionStore()
const store = useHkjcStore()

const loading = ref(false)
const meeting = ref(null)
const racePicks = ref([])
const displayMode = ref('preview')
const disclaimer = ref('')

const isResultMode = computed(() => displayMode.value === 'results')

function formatDate(d) {
  return d ? d.replace(/-/g, '/') : ''
}

function formatTime(iso) {
  return formatDateTimeInTz(iso, compStore.current?.timezone || 'Asia/Hong_Kong', locale.value)
}

function statusType(s) {
  return { UPCOMING: 'warning', ACTIVE: 'success', SCHEDULED: 'warning', RESULTS: 'info', PAST: 'info' }[s] || 'info'
}

function statusLabel(s) {
  return t(`hkjc.meetingStatus.${s}`) || s
}

function certaintyType(c) {
  return { high: 'success', medium: 'warning', low: 'danger' }[c] || 'info'
}

function certaintyLabel(c) {
  return t(`hkjc.certainty.${c}`) || c
}

function riskType(r) {
  return { low: 'success', medium: 'warning', high: 'danger' }[r] || 'info'
}

function riskLabel(r) {
  return t(`hkjc.risk.${r}`) || r
}

function goBack() {
  router.push(`${compStore.basePath}/meetings`)
}

function goRace(raceId) {
  router.push(`${compStore.basePath}/races/${raceId}`)
}

async function loadData() {
  loading.value = true
  try {
    const data = await store.fetchMeetingDetail(route.params.meetingId, true)
    if (!data) return
    meeting.value = data
    racePicks.value = data.race_picks || []
    displayMode.value = data.display_mode || 'preview'
    disclaimer.value = data.disclaimer || t('hkjc.disclaimer')
  } finally {
    loading.value = false
  }
}

onMounted(loadData)
</script>

<style scoped>
.header-row { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }
.title-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.header-row h2 { margin: 8px 0 0; }
.header-row p { margin: 4px 0 0; }
.disclaimer-alert { margin-bottom: 16px; }
.section-card { border-radius: 12px; }
.card-title { font-size: 16px; font-weight: 700; }
.schedule-alert { margin-bottom: 16px; }
.summary-text { font-size: 13px; color: #606266; }
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
</style>
