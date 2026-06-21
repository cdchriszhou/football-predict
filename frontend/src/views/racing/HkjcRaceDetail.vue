<template>
  <div class="hkjc-race-detail">
    <div class="page-header">
      <div class="header-row">
        <div>
          <el-button link type="primary" @click="goBack">{{ t('hkjc.backToMeeting') }}</el-button>
          <h2>{{ raceTitle }}</h2>
          <p>{{ raceMeta }}</p>
        </div>
        <el-button type="primary" :loading="loading" @click="loadData">{{ t('common.refresh') }}</el-button>
      </div>
    </div>

    <el-alert type="warning" :closable="false" show-icon class="disclaimer-alert" :title="disclaimer" />

    <div v-loading="loading">
      <template v-if="analysis">
        <el-alert
          v-if="isResultMode"
          type="success"
          :closable="false"
          show-icon
          class="summary-alert"
          :title="t('hkjc.raceResultMode')"
          :description="analysis.race_summary"
        />
        <template v-else>
          <el-alert
            v-if="analysis.avoid"
            type="error"
            :closable="false"
            show-icon
            class="avoid-alert"
            :title="t('hkjc.avoidRace')"
            :description="analysis.race_summary"
          />
          <el-alert
            v-else
            type="info"
            :closable="false"
            show-icon
            class="summary-alert"
            :title="analysis.race_summary"
          />
          <el-alert
            v-if="analysis.ai_enabled"
            type="success"
            :closable="false"
            class="ai-alert"
            :title="t('hkjc.aiRankingOn')"
          >
            <template #default>
              <span>{{ t('hkjc.aiRankingDesc', { model: analysis.ai_model || '—' }) }}</span>
              <span v-if="analysis.ai_blend" class="ai-blend">
                · {{ t('hkjc.aiBlendWeights', { quant: Math.round((analysis.ai_blend.quant || 0) * 100), ai: Math.round((analysis.ai_blend.ai || 0) * 100) }) }}
              </span>
            </template>
          </el-alert>
          <el-alert
            v-else-if="analysis.ai_unavailable_reason"
            type="warning"
            :closable="false"
            class="ai-alert"
            :title="analysis.ai_unavailable_reason"
          />

          <el-row :gutter="16" class="pick-row">
            <el-col :xs="24" :sm="8" v-for="block in pickBlocks" :key="block.key">
              <el-card class="section-card pick-card">
                <template #header>
                  <span class="card-title">{{ block.title }}</span>
                </template>
                <el-empty v-if="!block.items.length" :description="t('hkjc.noPick')" />
                <ul v-else class="pick-list">
                  <li v-for="p in block.items" :key="p.horse_no">
                    <span class="horse-no">{{ p.horse_no }}</span>
                    <span class="horse-name">{{ p.name }}</span>
                    <el-tag size="small">{{ (p.win_probability * 100).toFixed(1) }}%</el-tag>
                  </li>
                </ul>
              </el-card>
            </el-col>
          </el-row>
        </template>

        <el-card class="section-card" style="margin-top: 20px">
          <template #header>
            <span class="card-title">{{ isResultMode ? t('hkjc.finishingOrder') : t('hkjc.powerRanking') }}</span>
          </template>
          <el-table :data="analysis.rankings" stripe>
            <el-table-column
              :prop="isResultMode ? 'placing' : 'model_rank'"
              :label="isResultMode ? t('hkjc.colPlacing') : t('hkjc.colRank')"
              width="60"
            />
            <el-table-column prop="horse_no" :label="t('hkjc.colHorseNo')" width="60" />
            <el-table-column prop="name" :label="t('hkjc.colHorseName')" min-width="100" />
            <el-table-column prop="jockey" :label="t('hkjc.colJockey')" width="90" />
            <el-table-column prop="trainer" :label="t('hkjc.colTrainer')" width="90" />
            <el-table-column prop="draw" :label="t('hkjc.colDraw')" width="60" />
            <template v-if="!isResultMode">
              <el-table-column :label="t('hkjc.colWinProb')" width="90">
                <template #default="{ row }">{{ (row.win_probability * 100).toFixed(1) }}%</template>
              </el-table-column>
              <el-table-column
                v-if="analysis.ai_enabled"
                :label="t('hkjc.colAiWinProb')"
                width="88"
              >
                <template #default="{ row }">
                  {{ row.ai_win_probability != null ? (row.ai_win_probability * 100).toFixed(1) + '%' : '—' }}
                </template>
              </el-table-column>
              <el-table-column :label="t('hkjc.colPlaceProb')" width="90">
                <template #default="{ row }">{{ (row.place_probability * 100).toFixed(1) }}%</template>
              </el-table-column>
              <el-table-column prop="odds" :label="t('hkjc.colOdds')" width="70" />
              <el-table-column :label="t('hkjc.colTier')" width="90">
                <template #default="{ row }">
                  <el-tag :type="tierType(row.tier)" size="small">{{ tierLabel(row.tier) }}</el-tag>
                </template>
              </el-table-column>
            </template>
            <el-table-column v-else prop="odds" :label="t('hkjc.colOdds')" width="70" />
            <el-table-column :label="isResultMode ? t('hkjc.colSummary') : t('hkjc.colAnalysis')" min-width="200">
              <template #default="{ row }">
                <span class="snippet">{{ row.analysis_snippet }}</span>
                <p v-if="!isResultMode && row.ai_reason" class="ai-reason">{{ row.ai_reason }}</p>
                <div v-if="!isResultMode && row.risk_flags?.length" class="risk-flags">
                  <el-tag v-for="(f, i) in row.risk_flags" :key="i" type="warning" size="small">{{ f }}</el-tag>
                </div>
              </template>
            </el-table-column>
            <el-table-column v-if="!isResultMode" :label="t('hkjc.colFactors')" width="90" fixed="right">
              <template #default="{ row }">
                <el-popover v-if="row.feature_breakdown?.length" placement="left" :width="320" trigger="click">
                  <template #reference>
                    <el-button link type="primary" size="small">{{ t('hkjc.viewFactors') }}</el-button>
                  </template>
                  <div class="factor-popover">
                    <p class="factor-title">{{ row.name }}</p>
                    <div v-for="f in row.feature_breakdown" :key="f.key" class="factor-line">
                      <span>{{ factorLabel(f.key) }}</span>
                      <span>{{ (f.contribution * 100).toFixed(1) }}%</span>
                    </div>
                  </div>
                </el-popover>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </template>
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
const race = ref(null)
const meeting = ref(null)
const analysis = ref(null)
const disclaimer = ref('')

const isResultMode = computed(() => analysis.value?.mode === 'result')

const raceTitle = computed(() => {
  if (!race.value) return ''
  return t('hkjc.raceTitle', { no: race.value.race_no, name: race.value.name || '' })
})

const raceMeta = computed(() => {
  if (!race.value) return ''
  const time = formatDateTimeInTz(race.value.start_time, compStore.current?.timezone || 'Asia/Hong_Kong', locale.value)
  return `${meeting.value?.venue || ''} · ${race.value.distance_m}m · ${race.value.class} · ${time}`
})

const pickBlocks = computed(() => {
  const picks = analysis.value?.picks || {}
  return [
    { key: 'primary', title: t('hkjc.tier.primary'), items: picks.primary || [] },
    { key: 'secondary', title: t('hkjc.tier.secondary'), items: picks.secondary || [] },
    { key: 'dark_horse', title: t('hkjc.tier.dark_horse'), items: picks.dark_horse || [] },
  ]
})

function tierType(tier) {
  return { primary: 'success', secondary: 'warning', dark_horse: 'info', exclude: 'danger' }[tier] || 'info'
}

function tierLabel(tier) {
  return t(`hkjc.tier.${tier}`) || tier
}

function factorLabel(key) {
  return t(`hkjc.factors.${key}`) || key
}

function goBack() {
  if (meeting.value?.id) {
    router.push(`${compStore.basePath}/meetings/${meeting.value.id}`)
  } else {
    router.push(`${compStore.basePath}/meetings`)
  }
}

async function loadData() {
  loading.value = true
  try {
    const data = await store.fetchRaceDetail(route.params.id)
    if (!data) return
    race.value = data.race
    meeting.value = data.meeting
    analysis.value = data.analysis
    disclaimer.value = data.disclaimer || t('hkjc.disclaimer')
  } finally {
    loading.value = false
  }
}

onMounted(loadData)
</script>

<style scoped>
.header-row { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }
.header-row h2 { margin: 8px 0 0; }
.header-row p { margin: 4px 0 0; color: #606266; font-size: 14px; }
.disclaimer-alert { margin-bottom: 16px; }
.avoid-alert, .summary-alert, .ai-alert { margin-bottom: 16px; }
.ai-blend { color: #606266; font-size: 13px; }
.ai-reason { margin: 4px 0 0; font-size: 12px; color: #006B54; }
.pick-row { margin-top: 4px; }
.section-card { border-radius: 12px; margin-bottom: 16px; }
.card-title { font-size: 16px; font-weight: 700; }
.pick-list { list-style: none; padding: 0; margin: 0; }
.pick-list li { display: flex; align-items: center; gap: 10px; padding: 8px 0; border-bottom: 1px solid #f0f0f0; }
.horse-no { font-weight: 700; color: #006B54; min-width: 24px; }
.horse-name { flex: 1; }
.snippet { font-size: 13px; color: #606266; }
.risk-flags { margin-top: 6px; display: flex; flex-wrap: wrap; gap: 4px; }
.factor-popover { font-size: 13px; }
.factor-title { font-weight: 700; margin: 0 0 8px; }
.factor-line { display: flex; justify-content: space-between; padding: 4px 0; border-bottom: 1px solid #f5f5f5; }
</style>
