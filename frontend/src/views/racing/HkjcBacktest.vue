<template>
  <div class="hkjc-backtest">
    <div class="page-header">
      <div class="header-row">
        <div>
          <h2>{{ t('hkjc.backtestTitle') }}</h2>
          <p>{{ t('hkjc.backtestSubtitle') }}</p>
        </div>
        <el-button type="primary" :loading="loading" @click="loadData">{{ t('common.refresh') }}</el-button>
      </div>
    </div>

    <el-alert type="warning" :closable="false" show-icon class="disclaimer-alert" :title="disclaimer" />

    <div v-loading="loading">
      <el-row :gutter="20" v-if="data">
        <el-col :xs="12" :sm="6" v-for="m in metrics" :key="m.label">
          <div class="stat-card">
            <div class="stat-icon" :style="{ background: m.color }">
              <el-icon :size="24" color="#fff"><DataAnalysis /></el-icon>
            </div>
            <div class="stat-info">
              <span class="stat-value">{{ m.value }}</span>
              <span class="stat-label">{{ m.label }}</span>
            </div>
          </div>
        </el-col>
      </el-row>

      <el-card class="section-card" style="margin-top: 20px">
        <template #header>
          <span class="card-title">{{ t('hkjc.backtestDetailTitle') }}</span>
        </template>
        <el-empty v-if="!meetingDetails.length" :description="t('hkjc.backtestNoDetail')" :image-size="60" />
        <el-collapse v-else v-model="expandedMeetings" accordion>
          <el-collapse-item
            v-for="meeting in meetingDetails"
            :key="meetingKey(meeting)"
            :name="meetingKey(meeting)"
          >
            <template #title>
              <span class="meeting-title">{{ meetingSummary(meeting) }}</span>
            </template>
            <div class="table-responsive">
              <el-table :data="meeting.races" stripe size="small">
                <el-table-column prop="race_no" :label="t('hkjc.backtestColRace')" width="72" />
                <el-table-column :label="t('hkjc.backtestColDataQuality')" width="72" align="center">
                  <template #default="{ row }">
                    <el-tooltip
                      v-if="row.data_quality !== 'racecard'"
                      :content="t('hkjc.backtestDataLimitedHint')"
                      placement="top"
                    >
                      <el-tag type="warning" size="small">{{ t('hkjc.backtestDataLimited') }}</el-tag>
                    </el-tooltip>
                    <el-tag v-else type="success" size="small">{{ t('hkjc.backtestDataRacecard') }}</el-tag>
                  </template>
                </el-table-column>
                <el-table-column :label="t('hkjc.backtestColModelPick')" min-width="140">
                  <template #default="{ row }">
                    <span class="horse-cell">{{ formatHorse(row.model_horse_no, row.model_horse_name) }}</span>
                    <el-tag v-if="row.has_primary_pick" size="small" type="success" class="tier-tag">P</el-tag>
                  </template>
                </el-table-column>
                <el-table-column :label="t('hkjc.backtestColActualWinner')" min-width="140">
                  <template #default="{ row }">
                    {{ formatHorse(row.actual_winner_no, row.actual_winner_name) }}
                  </template>
                </el-table-column>
                <el-table-column :label="t('hkjc.backtestColOdds')" width="100" align="center">
                  <template #default="{ row }">
                    <div class="odds-cell">
                      <span class="odds-line" :title="t('hkjc.backtestOddsModel')">
                        {{ formatOdds(row.model_odds) }}
                      </span>
                      <span class="odds-sep">/</span>
                      <span class="odds-line odds-winner" :title="t('hkjc.backtestOddsWinner')">
                        {{ formatOdds(row.winner_odds) }}
                      </span>
                    </div>
                  </template>
                </el-table-column>
                <el-table-column :label="t('hkjc.backtestColWinProb')" width="88" align="center">
                  <template #default="{ row }">{{ row.model_win_probability }}%</template>
                </el-table-column>
                <el-table-column :label="t('hkjc.backtestColResult')" width="80" align="center">
                  <template #default="{ row }">
                    <el-tag :type="row.win_hit ? 'success' : 'info'" size="small">
                      {{ row.win_hit ? t('hkjc.backtestHit') : t('hkjc.backtestMiss') }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column :label="t('hkjc.backtestColTop3')" width="72" align="center">
                  <template #default="{ row }">
                    {{ row.top_pick_in_top3 ? t('hkjc.backtestYes') : t('hkjc.backtestNo') }}
                  </template>
                </el-table-column>
              </el-table>
            </div>
          </el-collapse-item>
        </el-collapse>
      </el-card>

      <el-card class="section-card" style="margin-top: 20px">
        <template #header>
          <span class="card-title">{{ t('hkjc.backtestNotes') }}</span>
        </template>
        <ul class="notes-list">
          <li v-for="(n, i) in data?.notes || []" :key="i">{{ n }}</li>
        </ul>
        <p class="meta-line">
          {{ t('hkjc.modelVersion') }}: {{ data?.model_version }} ·
          {{ t('hkjc.lastRetrain') }}: {{ formatTime(data?.last_retrain) }}
        </p>
      </el-card>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { DataAnalysis } from '@element-plus/icons-vue'
import { useHkjcStore } from '@/stores/hkjc'
import { formatDateTimeInTz } from '@/utils/timezone'

const { t, locale } = useI18n()
const store = useHkjcStore()

const loading = ref(false)
const data = ref(null)
const disclaimer = ref('')
const expandedMeetings = ref('')

const metrics = computed(() => {
  if (!data.value) return []
  return [
    { label: t('hkjc.winHitRate'), value: `${data.value.win_hit_rate}%`, color: '#006B54' },
    { label: t('hkjc.placeTop3Rate'), value: `${data.value.place_top3_rate}%`, color: '#1a237e' },
    { label: t('hkjc.highConfHit'), value: `${data.value.high_confidence_hit}%`, color: '#e65100' },
    { label: t('hkjc.racesEvaluated'), value: data.value.races_evaluated, color: '#4527a0' },
  ]
})

const meetingDetails = computed(() => data.value?.meetings || [])

function meetingKey(meeting) {
  return `${meeting.meeting_date}-${meeting.venue_code}`
}

function formatMeetingDate(dateStr) {
  if (!dateStr) return '—'
  const parts = dateStr.split('-')
  if (parts.length === 3) return `${parts[0]}/${Number(parts[1])}/${Number(parts[2])}`
  return dateStr
}

function meetingSummary(meeting) {
  const base = t('hkjc.backtestMeetingSummary', {
    date: formatMeetingDate(meeting.meeting_date),
    venue: meeting.venue || meeting.venue_code,
    hits: meeting.win_hits ?? 0,
    total: meeting.evaluated ?? 0,
    rate: meeting.win_hit_rate ?? 0,
  })
  const pre = meeting.racecard_races ?? 0
  const total = meeting.evaluated ?? 0
  if (!total) return base
  return `${base} · ${t('hkjc.backtestMeetingRacecardSummary', { pre, total })}`
}

function formatHorse(no, name) {
  if (!no) return name || '—'
  return name ? `${no} ${name}` : String(no)
}

function formatOdds(value) {
  if (value == null || value === '') return '—'
  const n = Number(value)
  return Number.isFinite(n) ? n.toFixed(1) : '—'
}

function formatTime(iso) {
  return formatDateTimeInTz(iso, 'Asia/Hong_Kong', locale.value)
}

watch(meetingDetails, (list) => {
  if (list.length && !expandedMeetings.value) {
    expandedMeetings.value = meetingKey(list[0])
  }
}, { immediate: true })

async function loadData() {
  loading.value = true
  try {
    data.value = await store.fetchBacktest()
    disclaimer.value = data.value?.disclaimer || t('hkjc.disclaimer')
    if (meetingDetails.value.length) {
      expandedMeetings.value = meetingKey(meetingDetails.value[0])
    }
  } finally {
    loading.value = false
  }
}

onMounted(loadData)
</script>

<style scoped>
.header-row { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }
.header-row h2 { margin: 0; }
.header-row p { margin: 4px 0 0; }
.disclaimer-alert { margin-bottom: 16px; }
.stat-card { display: flex; align-items: center; gap: 16px; margin-bottom: 16px; }
.stat-icon {
  width: 52px; height: 52px; border-radius: 12px;
  display: flex; align-items: center; justify-content: center;
}
.stat-value { font-size: 28px; font-weight: 800; color: #1a237e; }
.stat-label { font-size: 13px; color: #999; }
.section-card { border-radius: 12px; }
.card-title { font-size: 16px; font-weight: 700; }
.meeting-title { font-weight: 600; color: #303133; }
.horse-cell { margin-right: 6px; }
.tier-tag { vertical-align: middle; }
.odds-cell { font-size: 12px; line-height: 1.4; white-space: nowrap; }
.odds-sep { margin: 0 2px; color: #c0c4cc; }
.odds-winner { color: #606266; }
.notes-list { margin: 0; padding-left: 20px; line-height: 1.8; color: #606266; }
.meta-line { margin-top: 16px; font-size: 13px; color: #909399; }
</style>
