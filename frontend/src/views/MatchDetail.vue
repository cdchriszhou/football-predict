<template>
  <div class="match-detail" v-loading="loading">
    <el-page-header @back="$router.back">
      <template #content>
        <span class="detail-title">{{ match?.team_a }} vs {{ match?.team_b }}</span>
      </template>
    </el-page-header>

    <div v-if="match" class="detail-content">
      <!-- Match info header -->
      <el-card class="match-hero" shadow="hover">
        <div class="hero-content">
          <div class="hero-team">
            <div class="hero-team-row">
              <TeamBadge :name="match.team_a" :flag-url="match.team_a_detail?.flag_url" :size="44" />
              <h3>{{ match.team_a }}</h3>
            </div>
          </div>
          <div class="hero-center">
            <template v-if="isEffectiveMatchStatus(match, 'finished')">
              <span v-if="hasMatchScore(match)" class="hero-score">{{ match.result_a }} - {{ match.result_b }}</span>
              <span v-else class="hero-vs">VS</span>
              <el-tag type="info" size="small" effect="dark" class="hero-status-tag">{{ t('status.finished') }}</el-tag>
            </template>
            <template v-else-if="isEffectiveMatchStatus(match, 'live')">
              <span class="hero-score live">{{ match.result_a }} - {{ match.result_b }}</span>
              <el-tag type="danger" size="small">LIVE</el-tag>
            </template>
            <template v-else>
              <span class="hero-vs">VS</span>
            </template>
            <div class="hero-meta">
              <span>{{ stageLabel(t, match.stage) }}{{ match.group_name ? ' ' + formatGroup(t, match.group_name) : '' }}</span>
              <span v-if="match.season || match.matchday">{{ seasonMeta }}</span>
              <span>{{ formatDateTime(match.match_time) }}</span>
              <span>{{ match.stadium || match.location }}</span>
            </div>
          </div>
          <div class="hero-team">
            <div class="hero-team-row">
              <TeamBadge :name="match.team_b" :flag-url="match.team_b_detail?.flag_url" :size="44" />
              <h3>{{ match.team_b }}</h3>
            </div>
          </div>
        </div>
      </el-card>

      <!-- Tab panels -->
      <el-tabs v-model="activeTab" class="detail-tabs">
        <el-tab-pane :label="t('match.aiPredict')" name="prediction">
          <el-card>
            <div class="predict-header">
              <span class="predict-label">{{ t('match.predictModel') }}</span>
              <el-select v-model="predictModel" size="small" style="width:200px" @change="onModelChange">
                <el-option v-for="opt in modelOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
              </el-select>
            </div>
            <AIPrediction
              :prediction="prediction"
              :loading="predLoading"
              @refresh="loadPrediction(true)"
            />
          </el-card>
        </el-tab-pane>

        <el-tab-pane :label="t('match.dataAnalysis')" name="compare">
          <el-card>
            <TeamCompare :teamA="match.team_a_detail" :teamB="match.team_b_detail" />
          </el-card>
        </el-tab-pane>

        <el-tab-pane :label="t('match.marketOdds')" name="odds">
          <el-card>
            <OddsPanel :odds="odds" />
          </el-card>
        </el-tab-pane>

        <el-tab-pane v-if="authStore.canAccessSporttery" :label="t('match.sporttery')" name="sporttery">
          <el-card>
            <SportteryOddsPanel
              :odds="odds"
              :team-a="match.team_a"
              :team-b="match.team_b"
            />
          </el-card>
        </el-tab-pane>
      </el-tabs>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import AIPrediction from '@/components/AIPrediction.vue'
import TeamCompare from '@/components/TeamCompare.vue'
import OddsPanel from '@/components/OddsPanel.vue'
import SportteryOddsPanel from '@/components/SportteryOddsPanel.vue'
import { useMatchesStore } from '@/stores/matches'
import { usePredictionsStore } from '@/stores/predictions'
import { useOddsStore } from '@/stores/odds'
import { useAuthStore } from '@/stores/auth'
import TeamBadge from '@/components/TeamBadge.vue'
import { useModelOptions, formatGroup } from '@/i18n/helpers'
import { stageLabel } from '@/i18n/matchLabels'
import { hasMatchScore, isEffectiveMatchStatus, effectiveMatchStatus } from '@/utils/matchStatus'

const { t, locale } = useI18n()
const modelOptions = useModelOptions()
const route = useRoute()
const matchStore = useMatchesStore()
const predStore = usePredictionsStore()
const authStore = useAuthStore()
const oddsStore = useOddsStore()

const match = ref(null)
const prediction = ref(null)
const odds = ref(null)
const loading = ref(false)
const predLoading = ref(false)
const activeTab = ref('prediction')
const predictModel = ref('auto')

async function load() {
  loading.value = true
  try {
    const matchId = Number(route.params.id)
    match.value = await matchStore.fetchDetail(matchId)
    await Promise.all([loadPrediction(false), loadOdds()])
  } finally {
    loading.value = false
  }
}

async function loadPrediction(refresh = false) {
  predLoading.value = true
  try {
    prediction.value = await predStore.fetchPrediction(Number(route.params.id), predictModel.value, refresh)
  } finally {
    predLoading.value = false
  }
}

function onModelChange() {
  loadPrediction(true)
}

async function loadOdds() {
  const id = Number(route.params.id)
  odds.value = await oddsStore.fetchOdds(id, true)
}

const seasonMeta = computed(() => {
  if (!match.value) return ''
  const parts = []
  if (match.value.season) parts.push(`${match.value.season}${t('match.seasonSuffix')}`)
  if (match.value.matchday) parts.push(t('match.matchdayRound', { n: match.value.matchday }))
  return parts.join(' · ')
})

function formatDateTime(time) {
  if (!time) return ''
  return new Date(time).toLocaleString(locale.value)
}

async function refreshMatchOnly() {
  const matchId = Number(route.params.id)
  match.value = await matchStore.fetchDetail(matchId)
}

let livePollTimer = null

function syncLivePolling() {
  clearInterval(livePollTimer)
  const st = match.value ? effectiveMatchStatus(match.value) : 'upcoming'
  if (st === 'live' || (st === 'finished' && !hasMatchScore(match.value))) {
    livePollTimer = setInterval(refreshMatchOnly, 30_000)
  }
}

onMounted(async () => {
  await load()
  syncLivePolling()
})

onUnmounted(() => {
  clearInterval(livePollTimer)
})
</script>

<style scoped>
.detail-title { font-size: 20px; font-weight: 700; }
.detail-content { margin-top: 20px; }
.match-hero { margin-bottom: 20px; border-radius: 16px; }
.hero-content { display: flex; align-items: center; justify-content: space-around; padding: 20px 0; }
.hero-team { display: flex; flex-direction: column; align-items: center; gap: 10px; max-width: 220px; }
.hero-team-row { display: flex; align-items: center; justify-content: center; gap: 10px; }
.hero-team h3 { font-size: 20px; font-weight: 700; margin: 0; text-align: left; line-height: 1.3; }
.hero-center { text-align: center; }
.hero-score { font-size: 42px; font-weight: 900; }
.hero-score.live { color: #f44336; animation: pulse 1s infinite; }
.hero-vs { font-size: 36px; font-weight: 800; color: #1a237e; }
.hero-status-tag { margin-top: 8px; }
.hero-meta { display: flex; gap: 12px; font-size: 13px; color: #999; margin-top: 8px; justify-content: center; }
.detail-tabs { margin-top: 8px; }
.predict-header { display: flex; align-items: center; gap: 10px; margin-bottom: 16px; }
.predict-label { font-size: 13px; color: #666; font-weight: 600; }

@media (max-width: 767px) {
  .detail-title { font-size: 16px; }
  .hero-content { flex-direction: column; gap: 16px; padding: 12px 0; }
  .hero-team h3 { font-size: 16px; }
  .hero-score { font-size: 32px; }
  .hero-vs { font-size: 28px; }
  .hero-meta { flex-direction: column; gap: 4px; font-size: 12px; }
  .predict-header { flex-direction: column; align-items: flex-start; gap: 8px; }
  .predict-header :deep(.el-select) { width: 100% !important; }
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}
</style>
