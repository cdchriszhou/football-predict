<template>
  <div class="hkjc-meetings">
    <div class="page-header">
      <div class="header-row">
        <div>
          <h2>{{ t('hkjc.meetingsTitle') }}</h2>
          <p>{{ t('hkjc.meetingsSubtitle') }}</p>
          <p class="meetings-window-hint">{{ t('hkjc.meetingsWindowHint') }}</p>
        </div>
        <el-button type="primary" :loading="loading" @click="loadData(true)">{{ t('common.refresh') }}</el-button>
      </div>
    </div>

    <el-alert type="warning" :closable="false" show-icon class="disclaimer-alert" :title="disclaimer" />

    <div v-loading="loading">
      <el-empty v-if="!loading && !meetings.length" :description="t('common.noData')" />
      <el-row v-else :gutter="20">
        <el-col :xs="24" :sm="12" v-for="m in meetings" :key="m.id">
          <el-card class="section-card meeting-card" shadow="hover" @click="goMeeting(m.id)">
            <div class="meeting-head">
              <h3>{{ m.venue }}</h3>
              <div class="meeting-tags-head">
                <el-tag v-if="m.status" :type="statusType(m.status)" size="small">
                  {{ statusLabel(m.status) }}
                </el-tag>
                <el-tag v-if="m.featured" type="success" size="small">{{ t('hkjc.featured') }}</el-tag>
              </div>
            </div>
            <p class="meeting-date">{{ formatDate(m.date) }}</p>
            <div class="meeting-tags">
              <el-tag size="small">{{ m.track_type }}</el-tag>
              <el-tag size="small" type="info">{{ m.track_rating }}</el-tag>
              <el-tag size="small" :type="riskType(m.meeting_risk)">{{ riskLabel(m.meeting_risk) }}</el-tag>
            </div>
            <p class="meeting-info">
              {{ t('hkjc.raceCount', { n: m.race_count }) }}
              <template v-if="m.weather"> · {{ m.weather }}</template>
              <template v-if="m.temperature_c != null && m.temperature_c !== ''"> · {{ m.temperature_c }}°C</template>
            </p>
          </el-card>
        </el-col>
      </el-row>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useCompetitionStore } from '@/stores/competition'
import { useHkjcStore } from '@/stores/hkjc'

const { t } = useI18n()
const router = useRouter()
const compStore = useCompetitionStore()
const store = useHkjcStore()

const loading = ref(false)
const meetings = ref([])
const disclaimer = ref('')

function formatDate(d) {
  return d ? d.replace(/-/g, '/') : ''
}

function riskType(r) {
  return { low: 'success', medium: 'warning', high: 'danger' }[r] || 'info'
}

function riskLabel(r) {
  return t(`hkjc.risk.${r}`) || r
}

function statusType(s) {
  return { UPCOMING: 'warning', ACTIVE: 'success', SCHEDULED: 'warning', RESULTS: 'info', PAST: 'info' }[s] || 'info'
}

function statusLabel(s) {
  return t(`hkjc.meetingStatus.${s}`) || s
}

function goMeeting(id) {
  router.push(`${compStore.basePath}/meetings/${id}`)
}

async function loadData(refresh = false) {
  loading.value = true
  try {
    await store.fetchMeetings(refresh)
    meetings.value = store.meetings || []
    disclaimer.value = t('hkjc.disclaimer')
  } finally {
    loading.value = false
  }
}

onMounted(() => loadData(false))
</script>

<style scoped>
.header-row { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }
.header-row h2 { margin: 0; }
.header-row p { margin: 4px 0 0; }
.meetings-window-hint { margin: 6px 0 0; font-size: 13px; color: #909399; }
.disclaimer-alert { margin-bottom: 16px; }
.section-card { border-radius: 12px; margin-bottom: 20px; cursor: pointer; }
.meeting-head { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.meeting-tags-head { display: flex; gap: 6px; flex-wrap: wrap; justify-content: flex-end; }
.meeting-head h3 { margin: 0; font-size: 18px; color: #006B54; }
.meeting-date { color: #606266; font-size: 14px; margin: 8px 0; }
.meeting-tags { display: flex; gap: 8px; flex-wrap: wrap; }
.meeting-info { font-size: 13px; color: #909399; margin: 12px 0 0; }
</style>
