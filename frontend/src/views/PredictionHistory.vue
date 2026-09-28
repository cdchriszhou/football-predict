<template>
  <div class="predictions-page">
    <div class="page-header">
      <h2>{{ t('predictions.title') }}</h2>
      <p>{{ t('predictions.subtitle') }}</p>
    </div>

    <el-row :gutter="20" v-if="predStore.accuracy">
      <el-col :xs="12" :sm="6" v-for="card in accCards" :key="card.label">
        <el-card class="acc-card" shadow="hover">
          <div class="acc-card-content">
            <span class="acc-value" :style="{ color: card.color }">{{ card.value }}</span>
            <span class="acc-label">{{ card.label }}</span>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-card style="margin-top: 20px" v-loading="loading">
      <template #header>
        <span class="card-title">{{ t('predictions.recentTitle') }}</span>
      </template>
      <el-empty
        v-if="!loading && !predStore.history.length"
        :description="t('predictions.recentEmpty')"
        :image-size="80"
      />
      <div v-else class="history-list">
        <div
          v-for="row in predStore.history"
          :key="row.match_id"
          class="history-row"
          @click="goMatch(row.match_id)"
        >
          <div class="history-meta">
            <span class="history-time">{{ formatTime(row.match_time) }}</span>
            <el-tag v-if="row.result_hit" size="small" type="success" effect="plain">
              {{ t('predictions.resultHit') }}
            </el-tag>
            <el-tag v-else size="small" type="info" effect="plain">
              {{ t('predictions.resultMiss') }}
            </el-tag>
            <el-tag v-if="row.score_hit" size="small" type="warning" effect="plain">
              {{ t('predictions.scoreHit') }}
            </el-tag>
          </div>
          <div class="history-teams">
            <span>{{ displayName(row.team_a) }}</span>
            <strong class="history-score">{{ row.actual_score }}</strong>
            <span>{{ displayName(row.team_b) }}</span>
          </div>
          <div class="history-pred">
            <span class="pred-label">{{ t('predictions.predictedScores') }}</span>
            <span
              v-for="s in (row.predicted_scores || [])"
              :key="s"
              class="pred-badge"
            >{{ s }}</span>
            <span v-if="!(row.predicted_scores || []).length" class="pred-empty">—</span>
          </div>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { usePredictionsStore } from '@/stores/predictions'
import { useCompetitionStore } from '@/stores/competition'

const { t } = useI18n()
const router = useRouter()
const predStore = usePredictionsStore()
const compStore = useCompetitionStore()
const loading = ref(false)

const accCards = computed(() => {
  const a = predStore.accuracy
  if (!a) return []
  return [
    { label: t('predictions.resultAccuracy'), value: `${a.result_accuracy || 0}%`, color: '#4caf50' },
    { label: t('predictions.scoreAccuracy'), value: `${a.score_accuracy || 0}%`, color: '#2196f3' },
    { label: t('predictions.evaluatedCount'), value: t('dashboard.matchUnit', { n: a.total || 0 }), color: '#1a237e' },
    { label: t('predictions.avgConfidence'), value: `${((a.avg_confidence || 0) * 100).toFixed(0)}%`, color: '#ff9800' }
  ]
})

function displayName(name) {
  return name || ''
}

function formatTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return String(iso).slice(0, 16)
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getMonth() + 1}/${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function goMatch(id) {
  const base = compStore.basePath || `/competition/${compStore.slug || 'premier-league'}`
  router.push(`${base}/matches/${id}`)
}

async function load() {
  loading.value = true
  try {
    await Promise.all([
      predStore.fetchAccuracy(30),
      predStore.fetchHistory(30, 40),
    ])
  } finally {
    loading.value = false
  }
}

watch(() => compStore.slug, () => { load() })

onMounted(() => {
  load()
})
</script>

<style scoped>
.acc-card { text-align: center; border-radius: 12px; }
.acc-value { font-size: 32px; font-weight: 800; display: block; }
.acc-label { font-size: 13px; color: #999; }
.card-title { font-size: 15px; font-weight: 700; }
.history-list { display: flex; flex-direction: column; gap: 12px; }
.history-row {
  border: 1px solid #eef0f4;
  border-radius: 10px;
  padding: 12px 14px;
  cursor: pointer;
  transition: background .15s ease;
}
.history-row:hover { background: #f7f9fc; }
.history-meta { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.history-time { font-size: 12px; color: #909399; }
.history-teams {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  font-size: 14px;
  font-weight: 600;
}
.history-score { font-size: 18px; color: #1a237e; }
.history-pred { margin-top: 8px; display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.pred-label { font-size: 12px; color: #909399; margin-right: 4px; }
.pred-badge {
  font-size: 12px;
  background: #eef2ff;
  color: #3949ab;
  border-radius: 999px;
  padding: 2px 8px;
}
.pred-empty { color: #c0c4cc; font-size: 12px; }

@media (max-width: 767px) {
  .acc-value { font-size: 24px; }
  .acc-card { padding: 12px; }
  .history-teams { font-size: 13px; }
}
</style>
