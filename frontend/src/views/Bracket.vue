<template>
  <div class="bracket-page">
    <div class="page-header">
      <h2>{{ t('bracket.title') }}</h2>
      <p>{{ t('bracket.subtitle') }}</p>
    </div>

    <el-card class="bracket-card">
      <el-radio-group v-model="currentStage" class="stage-selector" @change="loadStage">
        <el-radio-button v-for="stage in stages" :key="stage.value" :value="stage.value">{{ stage.label }}</el-radio-button>
      </el-radio-group>

      <el-divider />

      <div v-if="loading" class="empty-bracket" v-loading="true" />
      <div v-else-if="stageMatches.length === 0" class="empty-bracket">
        <el-empty :description="t('bracket.empty')" />
      </div>
      <div v-else class="bracket-tree">
        <div v-for="(match, idx) in stageMatches" :key="match.id" class="bracket-row">
          <span class="bracket-number">{{ idx + 1 }}</span>
          <BracketNode :node="match" />
          <span class="bracket-arrow">→</span>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import BracketNode from '@/components/BracketNode.vue'
import { useMatchesStore } from '@/stores/matches'
import { useCompetitionStore } from '@/stores/competition'
import { bracketStages } from '@/i18n/helpers'

const { t } = useI18n()
const store = useMatchesStore()
const compStore = useCompetitionStore()
const currentStage = ref('1/8决赛')
const loading = ref(false)
const stageList = ref([])

const stages = computed(() => bracketStages(t))

function dedupeMatches(rows) {
  const seen = new Map()
  for (const m of rows || []) {
    const key = `${m.stage}|${m.team_a}|${m.team_b}`
    const prev = seen.get(key)
    if (!prev || (m.id > prev.id)) {
      seen.set(key, m)
    }
  }
  return [...seen.values()].sort((a, b) => {
    const ta = a.match_time || ''
    const tb = b.match_time || ''
    return ta.localeCompare(tb)
  })
}

const stageMatches = computed(() => dedupeMatches(stageList.value))

async function loadStage() {
  loading.value = true
  try {
    await store.fetchList({ stage: currentStage.value, page: 1, size: 32, status: '' })
    stageList.value = [...store.list]
  } finally {
    loading.value = false
  }
}

watch(
  () => compStore.slug,
  () => {
    if (compStore.slug) loadStage()
  },
)

onMounted(loadStage)
</script>

<style scoped>
.bracket-card { border-radius: 12px; }
.stage-selector { margin-bottom: 8px; }
.empty-bracket { padding: 40px 0; min-height: 120px; }
.bracket-tree { display: flex; flex-direction: column; gap: 16px; align-items: center; }
.bracket-row { display: flex; align-items: center; gap: 16px; }
.bracket-number { font-size: 18px; font-weight: 700; color: #1a237e; width: 30px; text-align: right; }
.bracket-arrow { font-size: 20px; color: #ccc; }

@media (max-width: 767px) {
  .stage-selector { display: flex; flex-wrap: wrap; gap: 4px; }
  .stage-selector :deep(.el-radio-button__inner) { padding: 6px 10px; font-size: 12px; }
  .bracket-row { gap: 8px; }
  .bracket-number { font-size: 14px; width: 24px; }
  .bracket-arrow { font-size: 16px; }
}
</style>
