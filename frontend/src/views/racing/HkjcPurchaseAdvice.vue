<template>
  <div class="hkjc-purchase-advice">
    <div class="page-header">
      <div class="header-row">
        <div>
          <h2>{{ t('hkjc.purchaseAdviceTitle') }}</h2>
          <p>{{ t('hkjc.purchaseAdviceSubtitle') }}</p>
        </div>
        <el-button type="primary" :loading="loading" @click="loadData">
          {{ t('common.refresh') }}
        </el-button>
      </div>
      <div v-if="plan" class="meta-row">
        <el-tag type="success">{{ t('hkjc.purchaseAdvicePreviewCount', { n: plan.preview_race_count }) }}</el-tag>
        <span v-if="plan.updated_at" class="updated-at">
          {{ t('hkjc.purchaseAdviceUpdatedAt', { time: formatTime(plan.updated_at) }) }}
        </span>
      </div>
    </div>

    <el-alert type="warning" :closable="false" show-icon class="disclaimer-alert" :title="disclaimer" />

    <div v-loading="loading">
      <el-empty
        v-if="!loading && (!plan?.meetings?.length)"
        :description="t('hkjc.emptyData')"
      />

      <template v-else-if="plan">
        <el-card
          v-for="meeting in plan.meetings"
          :key="meeting.meeting_id"
          shadow="never"
          class="meeting-card"
        >
          <template #header>
            <div class="meeting-header">
              <div>
                <h3 class="meeting-title">{{ meeting.venue }} · {{ formatDate(meeting.date) }}</h3>
                <p class="meeting-meta">
                  {{ meeting.track_type }}
                  · {{ t('hkjc.raceCount', { n: meeting.race_count }) }}
                </p>
              </div>
              <div class="meeting-tags">
                <el-tag :type="statusType(meeting.status)" size="small">
                  {{ statusLabel(meeting.status) }}
                </el-tag>
                <el-tag v-if="meeting.display_mode === 'results'" type="info" size="small">
                  {{ t('hkjc.purchaseAdviceResultMode') }}
                </el-tag>
              </div>
            </div>
          </template>

          <el-collapse v-model="expandedRaces[meeting.meeting_id]" accordion>
            <el-collapse-item
              v-for="race in meeting.races"
              :key="race.race_id"
              :name="race.race_id"
            >
              <template #title>
                <div class="race-collapse-title">
                  <span class="race-no">{{ t('hkjc.raceNoShort', { no: race.race_no }) }}</span>
                  <span class="race-info">{{ race.distance_m }}m · {{ race.class }}</span>
                  <el-tag
                    v-if="race.display_mode === 'preview' && race.avoid"
                    type="danger"
                    size="small"
                  >
                    {{ t('hkjc.avoidRace') }}
                  </el-tag>
                  <span v-else-if="race.display_mode === 'result'" class="result-hint">
                    {{ race.result?.winner_name || t('hkjc.pendingResult') }}
                  </span>
                  <span v-else class="top-pick-hint">
                    {{ topPickHint(race) }}
                  </span>
                </div>
              </template>

              <el-alert
                v-if="race.race_summary"
                :type="race.avoid ? 'error' : race.display_mode === 'result' ? 'success' : 'info'"
                :closable="false"
                show-icon
                class="race-summary-alert"
                :title="race.race_summary"
              />

              <el-table
                v-if="race.recommendations?.length"
                :data="race.recommendations"
                stripe
                size="small"
                class="rec-table"
              >
                <el-table-column prop="horse_no" :label="t('hkjc.colHorseNo')" width="60" />
                <el-table-column prop="name" :label="t('hkjc.colHorseName')" min-width="100" />
                <el-table-column prop="jockey" :label="t('hkjc.colJockey')" width="90" />
                <el-table-column :label="t('hkjc.colWinProb')" width="90">
                  <template #default="{ row }">
                    {{ formatProb(row.win_probability) }}
                  </template>
                </el-table-column>
                <el-table-column prop="odds" :label="t('hkjc.colOdds')" width="70" />
                <el-table-column :label="t('hkjc.colPurchaseAdvice')" width="110">
                  <template #default="{ row }">
                    <el-tag :type="tierType(row.tier)" size="small">{{ adviceLabel(row) }}</el-tag>
                  </template>
                </el-table-column>
                <el-table-column :label="t('hkjc.colAnalysis')" min-width="180">
                  <template #default="{ row }">
                    <span class="snippet">{{ row.analysis_snippet }}</span>
                  </template>
                </el-table-column>
                <el-table-column :label="t('hkjc.colAction')" width="90" fixed="right">
                  <template #default>
                    <el-button link type="primary" size="small" @click="goRace(race.race_id)">
                      {{ t('hkjc.viewAnalysis') }}
                    </el-button>
                  </template>
                </el-table-column>
              </el-table>

              <el-empty
                v-else-if="race.display_mode === 'preview'"
                :description="t('hkjc.noPick')"
                :image-size="48"
              />

              <div v-if="race.display_mode === 'result'" class="result-actions">
                <el-button link type="primary" @click="goRace(race.race_id)">
                  {{ t('hkjc.viewResult') }}
                </el-button>
              </div>
            </el-collapse-item>
          </el-collapse>
        </el-card>
      </template>
    </div>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useCompetitionStore } from '@/stores/competition'
import { useHkjcStore } from '@/stores/hkjc'
import { formatDateTimeInTz } from '@/utils/timezone'

const { t, locale } = useI18n()
const router = useRouter()
const compStore = useCompetitionStore()
const store = useHkjcStore()

const loading = ref(false)
const plan = ref(null)
const disclaimer = ref('')
const expandedRaces = reactive({})

function formatDate(d) {
  return d ? d.replace(/-/g, '/') : ''
}

function formatTime(iso) {
  if (!iso) return '—'
  return formatDateTimeInTz(iso, compStore.current?.timezone || 'Asia/Hong_Kong', locale.value)
}

function formatProb(p) {
  if (p == null) return '—'
  return `${(p * 100).toFixed(1)}%`
}

function statusType(s) {
  return { UPCOMING: 'warning', ACTIVE: 'success', SCHEDULED: 'warning', RESULTS: 'info', PAST: 'info' }[s] || 'info'
}

function statusLabel(s) {
  return t(`hkjc.meetingStatus.${s}`) || s
}

function tierType(tier) {
  return { primary: 'success', secondary: 'warning', dark_horse: 'info' }[tier] || 'info'
}

function adviceLabel(row) {
  return row.advice || t(`hkjc.tier.${row.tier}`) || row.tier
}

function topPickHint(race) {
  const first = race.recommendations?.[0]
  if (!first) return t('hkjc.noPick')
  return `${first.horse_no} ${first.name}`
}

function goRace(raceId) {
  router.push(`${compStore.basePath}/races/${raceId}`)
}

async function loadData() {
  loading.value = true
  try {
    const data = await store.fetchPurchaseAdvice()
    if (!data) return
    plan.value = data
    disclaimer.value = data.disclaimer || t('hkjc.disclaimer')
    for (const m of data.meetings || []) {
      const firstPreview = m.races?.find((r) => r.display_mode === 'preview')
      if (firstPreview && !expandedRaces[m.meeting_id]) {
        expandedRaces[m.meeting_id] = firstPreview.race_id
      }
    }
  } finally {
    loading.value = false
  }
}

onMounted(loadData)
</script>

<style scoped>
.hkjc-purchase-advice {
  max-width: 1200px;
}
.header-row {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  flex-wrap: wrap;
}
.meta-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 12px;
}
.updated-at {
  color: #909399;
  font-size: 13px;
}
.disclaimer-alert {
  margin-bottom: 16px;
}
.meeting-card {
  margin-bottom: 20px;
  border-radius: 12px;
}
.meeting-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  flex-wrap: wrap;
}
.meeting-title {
  margin: 0;
  font-size: 17px;
  font-weight: 700;
}
.meeting-meta {
  margin: 4px 0 0;
  font-size: 13px;
  color: #909399;
}
.meeting-tags {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.race-collapse-title {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  width: 100%;
  padding-right: 8px;
}
.race-no {
  font-weight: 700;
  color: #006b54;
  min-width: 48px;
}
.race-info {
  color: #606266;
  font-size: 13px;
}
.top-pick-hint,
.result-hint {
  margin-left: auto;
  font-size: 13px;
  color: #303133;
}
.race-summary-alert {
  margin-bottom: 12px;
}
.rec-table {
  margin-top: 4px;
}
.snippet {
  font-size: 13px;
  color: #606266;
}
.result-actions {
  margin-top: 8px;
}
</style>
