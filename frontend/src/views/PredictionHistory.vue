<template>
  <div class="predictions-page">
    <div class="page-header">
      <h2>{{ t('predictions.title') }}</h2>
      <p>{{ t('predictions.subtitle') }}</p>
    </div>

    <!-- Accuracy overview -->
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

    <!-- Accuracy trend (placeholder until per-round API is available) -->
    <el-card style="margin-top: 20px">
      <template #header><span class="card-title">{{ t('predictions.trendTitle') }}</span></template>
      <el-empty :description="t('predictions.trendPlaceholder')" :image-size="80" />
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { usePredictionsStore } from '@/stores/predictions'

const { t } = useI18n()
const predStore = usePredictionsStore()

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

onMounted(() => {
  predStore.fetchAccuracy(30)
})
</script>

<style scoped>
.acc-card { text-align: center; border-radius: 12px; }
.acc-value { font-size: 32px; font-weight: 800; display: block; }
.acc-label { font-size: 13px; color: #999; }
.card-title { font-size: 15px; font-weight: 700; }

@media (max-width: 767px) {
  .acc-value { font-size: 24px; }
  .acc-card { padding: 12px; }
}
</style>
