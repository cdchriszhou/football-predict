<template>
  <div class="ai-prediction">
    <div v-if="loading" class="loading-state">
      <el-skeleton :rows="5" animated />
    </div>

    <template v-else-if="prediction">
      <!-- Probability bars -->
      <div class="prob-section">
        <div class="prob-row">
          <span class="prob-label">{{ t('match.win') }}</span>
          <el-progress :percentage="prediction.win_rate" :color="'#4caf50'" :stroke-width="10" :show-text="false" />
          <span class="prob-value text-win">{{ prediction.win_rate }}%</span>
        </div>
        <div class="prob-row">
          <span class="prob-label">{{ t('match.draw') }}</span>
          <el-progress :percentage="prediction.draw_rate" :color="'#ff9800'" :stroke-width="10" :show-text="false" />
          <span class="prob-value text-draw">{{ prediction.draw_rate }}%</span>
        </div>
        <div class="prob-row">
          <span class="prob-label">{{ t('match.lose') }}</span>
          <el-progress :percentage="prediction.lose_rate" :color="'#f44336'" :stroke-width="10" :show-text="false" />
          <span class="prob-value text-lose">{{ prediction.lose_rate }}%</span>
        </div>
      </div>

      <!-- Key predictions -->
      <el-divider />
      <div class="key-results">
        <div class="result-item scores-item">
          <span class="result-label">{{ t('match.likelyScores') }}</span>
          <div class="scores-row">
            <span
              v-for="(s, i) in displayScores"
              :key="i"
              class="score-badge"
              :class="'score-rank-' + i"
            >{{ s }}</span>
          </div>
        </div>
        <div v-if="upsetScore" class="result-item upset-item">
          <span class="result-label">{{ t('match.upsetScore') }}</span>
          <span class="score-badge upset-badge">{{ upsetScore }}</span>
        </div>
        <div class="result-item">
          <span class="result-label">{{ t('predict.handicapResult') }}</span>
          <span class="result-value">{{ prediction.handicap_result || '—' }}</span>
        </div>
        <div class="result-item">
          <span class="result-label">{{ t('predict.totalGoals') }}</span>
          <span class="result-value">{{ prediction.total_goals || '—' }}</span>
        </div>
      </div>

      <!-- Reason -->
      <el-divider />
      <div class="reason-section">
        <div class="reason-header">
          <el-icon><ChatDotRound /></el-icon>
          <span>{{ t('predict.aiReason') }}</span>
          <el-tag size="small" :type="modelTagType">{{ modelDisplay }}</el-tag>
        </div>
        <p class="reason-text">{{ prediction.reason }}</p>
      </div>

      <!-- Confidence -->
      <div class="confidence">
        <span>{{ t('predict.confidence') }}: </span>
        <el-rate :model-value="Math.round(prediction.confidence * 5)" disabled show-score
                 :score-template="`${(prediction.confidence * 100).toFixed(0)}%`" />
      </div>

      <el-button type="primary" plain size="small" @click="$emit('refresh')" :loading="loading">
        {{ t('predict.refresh') }}
      </el-button>
    </template>

    <el-empty v-else :description="t('predict.noData')" />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { modelLabel } from '@/i18n/helpers'
import { parseLikelyScores, parseUpsetScore } from '@/utils/scorePrediction'

const props = defineProps({
  prediction: { type: Object, default: null },
  loading: { type: Boolean, default: false }
})

defineEmits(['refresh'])

const { t } = useI18n()

const displayScores = computed(() => parseLikelyScores(props.prediction))
const upsetScore = computed(() => parseUpsetScore(props.prediction))

const modelDisplay = computed(() => {
  if (!props.prediction?.model_used) return ''
  return modelLabel(t, props.prediction.model_used)
})

const modelTagType = computed(() => {
  if (!props.prediction?.model_used) return 'info'
  const name = props.prediction.model_used
  if (name === 'rule_engine') return 'info'
  if (name.includes('+')) return 'success'
  return ''
})
</script>

<style scoped>
.ai-prediction { padding: 8px 0; }
.prob-section { margin-bottom: 8px; }
.prob-row { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.prob-row :deep(.el-progress) { flex: 1; min-width: 0; }
.prob-label { width: 20px; flex-shrink: 0; font-weight: 600; text-align: center; }
.prob-value { width: 48px; flex-shrink: 0; text-align: right; font-size: 14px; }
.key-results {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  align-items: start;
}
.result-item { text-align: center; }
.result-label { font-size: 12px; color: #999; display: block; margin-bottom: 4px; }
.result-value { font-size: 20px; font-weight: 700; color: #1a237e; }
.scores-item { min-width: 140px; }
.scores-row { display: flex; gap: 6px; justify-content: center; flex-wrap: wrap; }
.score-badge {
  display: inline-block; padding: 2px 10px; border-radius: 12px;
  font-size: 15px; font-weight: 700; color: #fff;
}
.score-rank-0 { background: #4caf50; font-size: 16px; }
.score-rank-1 { background: #78909c; font-size: 14px; }
.upset-badge { background: #c62828; }
.reason-header { display: flex; align-items: center; gap: 6px; margin-bottom: 8px; font-weight: 600; }
.reason-text { font-size: 13px; color: #555; line-height: 1.7; }
.confidence { display: flex; align-items: center; gap: 8px; margin: 12px 0; font-size: 13px; color: #666; }
.loading-state { padding: 20px; }

@media (max-width: 767px) {
  .key-results { grid-template-columns: repeat(2, 1fr); gap: 12px; }
  .result-value { font-size: 16px; }
  .reason-text { font-size: 12px; }
  .prob-row { gap: 6px; }
  .prob-label { width: 16px; font-size: 12px; }
  .prob-value { width: 42px; font-size: 12px; }
}
</style>
