<template>
  <div class="tournament-page">
    <div class="page-header">
      <h2>{{ t('tournament.title') }}</h2>
      <p>{{ t('tournament.subtitle') }}</p>
    </div>

    <!-- Controls -->
    <div class="predict-controls">
      <div class="control-left">
        <el-select v-model="predictModel" size="default" style="width: 200px" @change="loadPrediction(true)">
          <el-option v-for="opt in modelOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
        </el-select>
        <el-button type="primary" :icon="Refresh" @click="loadPrediction(true)" :loading="loading">
          {{ t('tournament.refresh') }}
        </el-button>
      </div>
      <div v-if="prediction?.model_used && prediction.model_used !== 'rule_engine'" class="model-badge">
        <el-tag type="success" effect="dark" size="small">
          {{ t('models.label') }}: {{ modelLabel(t, prediction.model_used) }}
        </el-tag>
      </div>
    </div>

    <!-- Loading State -->
    <div v-if="loading && !prediction" class="loading-area" v-loading="true">
      <el-skeleton :rows="6" animated />
    </div>

    <!-- Empty State -->
    <el-empty v-else-if="!prediction" :description="t('tournament.noData')" />

    <!-- Prediction Content -->
    <div v-else class="prediction-content">
      <!-- Champion & Runner-up -->
      <el-row :gutter="24" class="final-row">
        <!-- Champion -->
        <el-col :xs="24" :sm="14" class="champion-col">
          <el-card class="champion-card" shadow="hover">
            <div class="crown-badge">
              <el-icon :size="32" color="#ffc107"><TrophyBase /></el-icon>
              <span>{{ t('tournament.champion') }}</span>
            </div>
            <div class="final-team-display">
              <img :src="flagUrl(prediction.champion, 120)" :alt="prediction.champion"
                   class="final-flag champion-flag"
                   @error="onFlagError(prediction.champion, 'champion')" />
              <h2 class="final-team-name">{{ prediction.champion }}</h2>
              <span class="final-rank" v-if="teamInfo(prediction.champion)?.rank">
                FIFA #{{ teamInfo(prediction.champion).rank }}
              </span>
              <div class="final-attr-bars" v-if="teamInfo(prediction.champion)">
                <div class="mini-bar" v-for="attr in miniAttrs" :key="attr.key">
                  <span class="mini-label">{{ attr.label }}</span>
                  <el-progress :percentage="teamInfo(prediction.champion)[attr.key] || 0"
                               :stroke-width="6" :color="attr.color" :show-text="false" />
                </div>
              </div>
            </div>
          </el-card>
        </el-col>

        <!-- Runner-up -->
        <el-col :xs="24" :sm="10" class="runnerup-col">
          <el-card class="runnerup-card" shadow="hover">
            <div class="crown-badge silver">
              <el-icon :size="26" color="#90a4ae"><Medal /></el-icon>
              <span>{{ t('tournament.runnerUp') }}</span>
            </div>
            <div class="final-team-display">
              <img :src="flagUrl(prediction.runner_up, 100)" :alt="prediction.runner_up"
                   class="final-flag runnerup-flag"
                   @error="onFlagError(prediction.runner_up, 'runnerup')" />
              <h3 class="final-team-name">{{ prediction.runner_up }}</h3>
              <span class="final-rank" v-if="teamInfo(prediction.runner_up)?.rank">
                FIFA #{{ teamInfo(prediction.runner_up).rank }}
              </span>
            </div>
          </el-card>
        </el-col>
      </el-row>

      <!-- Final Four -->
      <el-card class="semifinal-card" style="margin-top: 20px">
        <template #header>
          <div class="section-header">
            <el-icon :size="20" color="#1a237e"><Star /></el-icon>
            <span class="card-title">{{ t('tournament.semifinalists') }}</span>
          </div>
        </template>
        <el-row :gutter="16">
          <el-col :xs="12" :sm="6" v-for="team in prediction.semifinalists" :key="team">
            <div class="semi-team-card">
              <img :src="flagUrl(team, 80)" :alt="team" class="semi-flag"
                   @error="onFlagError(team, 'semi' + team)" />
              <span class="semi-name">{{ team }}</span>
              <span class="semi-rank" v-if="teamInfo(team)?.rank">FIFA #{{ teamInfo(team).rank }}</span>
            </div>
          </el-col>
        </el-row>
      </el-card>

      <!-- AI Reasoning -->
      <el-card class="reason-card" style="margin-top: 20px">
        <template #header>
          <div class="section-header">
            <el-icon :size="18" color="#1a237e"><ChatLineSquare /></el-icon>
            <span class="card-title">{{ t('tournament.aiReason') }}</span>
          </div>
        </template>
        <div v-if="prediction.reason" class="reason-text">
          <p v-for="(r, i) in splitReasons" :key="i" class="reason-paragraph">
            {{ r }}
          </p>
        </div>
        <p v-else class="reason-empty">{{ t('tournament.noDetail') }}</p>
        <div class="confidence-row">
          <span class="confidence-label">{{ t('tournament.overallConfidence') }}</span>
          <el-progress
            :percentage="(prediction.confidence || 0) * 100"
            :stroke-width="8"
            :color="confidenceColor"
            style="width: 200px"
          />
          <span class="confidence-value">{{ ((prediction.confidence || 0) * 100).toFixed(0) }}%</span>
        </div>
      </el-card>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, inject, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { Refresh, TrophyBase, Medal, Star, ChatLineSquare } from '@element-plus/icons-vue'
import { getTournamentPrediction } from '@/api/tournament'
import { getTeams } from '@/api/teams'
import { flagUrl } from '@/utils/flags'
import { useModelOptions, modelLabel } from '@/i18n/helpers'

const { t } = useI18n()
const modelOptions = useModelOptions()
const isMobile = inject('isMobile', ref(false))

const loading = ref(false)
const predictModel = ref('auto')
const prediction = ref(null)
const teamsMap = ref({})

const teamInfo = (name) => teamsMap.value[name] || null

const miniAttrs = computed(() => [
  { key: 'attack', label: t('team.attrAttack'), color: '#4caf50' },
  { key: 'defend', label: t('team.attrDefend'), color: '#2196f3' },
  { key: 'midfield', label: t('team.attrMidfield'), color: '#ff9800' },
  { key: 'speed', label: t('team.attrSpeed'), color: '#9c27b0' },
  { key: 'physical', label: t('team.attrPhysical'), color: '#e65100' },
])

const splitReasons = computed(() => {
  if (!prediction.value?.reason) return []
  return prediction.value.reason.split(' | ').filter(r => r.trim())
})

const confidenceColor = computed(() => {
  const v = (prediction.value?.confidence || 0) * 100
  if (v >= 70) return '#4caf50'
  if (v >= 50) return '#ff9800'
  return '#f44336'
})

async function loadTeams() {
  try {
    const res = await getTeams({ size: 48 })
    const items = res?.data?.items || res?.items || res || []
    items.forEach(item => { teamsMap.value[item.name] = item })
  } catch { /* non-critical */ }
}

async function loadPrediction(refresh = false) {
  loading.value = true
  try {
    const res = await getTournamentPrediction(predictModel.value, refresh)
    prediction.value = res?.data || res
  } catch {
    prediction.value = null
  } finally {
    loading.value = false
  }
}

function onFlagError() {
  // flag fallback handled by flagUrl returning empty
}

onMounted(async () => {
  await Promise.all([loadTeams(), loadPrediction()])
})
</script>

<style scoped>
.tournament-page { max-width: 1200px; }

/* Controls */
.predict-controls {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  flex-wrap: wrap;
  gap: 12px;
}
.control-left { display: flex; align-items: center; gap: 12px; }

/* Champion */
.champion-card { border: 2px solid #ffc107; border-radius: 16px; text-align: center; }
.champion-card :deep(.el-card__body) { padding: 24px; }
.crown-badge {
  display: inline-flex; align-items: center; gap: 8px;
  background: linear-gradient(135deg, #fff8e1, #ffecb3);
  padding: 6px 16px; border-radius: 20px; margin-bottom: 16px;
  font-weight: 700; color: #f57f17;
}
.crown-badge.silver {
  background: linear-gradient(135deg, #f5f5f5, #e0e0e0);
  color: #616161;
}
.final-team-display {
  display: flex; flex-direction: column; align-items: center; gap: 8px;
}
.champion-flag { width: 100px; height: 66px; border-radius: 6px; object-fit: cover; box-shadow: 0 3px 10px rgba(0,0,0,0.2); background: #f0f0f0; }
.runnerup-flag { width: 80px; height: 54px; border-radius: 6px; object-fit: cover; box-shadow: 0 2px 8px rgba(0,0,0,0.15); background: #f0f0f0; }
.final-team-name { font-size: 24px; font-weight: 800; margin: 4px 0; }
.runnerup-col .final-team-name { font-size: 20px; }
.final-rank { font-size: 13px; color: #999; }

.final-attr-bars { width: 100%; max-width: 320px; margin-top: 12px; display: flex; flex-direction: column; gap: 6px; }
.mini-bar { display: flex; align-items: center; gap: 8px; }
.mini-label { width: 28px; font-size: 12px; color: #666; text-align: right; flex-shrink: 0; }
.mini-bar :deep(.el-progress) { flex: 1; }

/* Runner-up */
.runnerup-card { border: 2px solid #b0bec5; border-radius: 16px; text-align: center; }
.runnerup-card :deep(.el-card__body) { padding: 20px; }

/* Section */
.section-header { display: flex; align-items: center; gap: 8px; }
.card-title { font-size: 16px; font-weight: 700; }

/* Semifinal grid */
.semifinal-card { border-radius: 12px; }
.semi-team-card {
  display: flex; flex-direction: column; align-items: center; gap: 6px;
  padding: 16px 8px; background: #f5f7fa; border-radius: 12px;
  text-align: center; transition: transform 0.2s;
}
.semi-team-card:hover { transform: translateY(-2px); }
.semi-flag { width: 64px; height: 42px; border-radius: 4px; object-fit: cover; box-shadow: 0 1px 4px rgba(0,0,0,0.15); background: #f0f0f0; }
.semi-name { font-size: 15px; font-weight: 700; }
.semi-rank { font-size: 12px; color: #999; }

/* Reason */
.reason-card { border-radius: 12px; }
.reason-text { line-height: 1.8; }
.reason-paragraph { margin: 6px 0; font-size: 14px; color: #444; }
.reason-empty { color: #999; font-size: 14px; }
.confidence-row { display: flex; align-items: center; gap: 12px; margin-top: 16px; padding-top: 12px; border-top: 1px solid #eee; }
.confidence-label { font-size: 13px; color: #666; }
.confidence-value { font-size: 16px; font-weight: 700; color: #1a237e; }

.model-badge { flex-shrink: 0; }
.loading-area { padding: 40px 0; }

@media (max-width: 767px) {
  .predict-controls { flex-direction: column; align-items: stretch; }
  .control-left { flex-direction: column; align-items: stretch; }
  .control-left .el-select { width: 100% !important; }
  .champion-flag { width: 80px; height: 54px; }
  .runnerup-flag { width: 64px; height: 42px; }
  .final-team-name { font-size: 20px; }
  .runnerup-col .final-team-name { font-size: 18px; }
  .semi-flag { width: 48px; height: 32px; }
  .semi-name { font-size: 13px; }
  .confidence-row { flex-wrap: wrap; }
  .confidence-row .el-progress { width: 140px !important; }
}
</style>
