<template>
  <div class="sporttery-plan-page">
    <div class="page-header">
      <div class="header-row">
        <div>
          <h2>{{ pageTitle }}</h2>
          <p>{{ pageSubtitle }}</p>
        </div>
        <el-button type="primary" :loading="loading" @click="loadPlan">
          {{ t('sportteryPlan.refresh') }}
        </el-button>
      </div>
      <div v-if="plan" class="meta-row">
        <el-tag type="success">{{ t('sportteryPlan.onSaleCount', { n: plan.on_sale_count }) }}</el-tag>
        <el-tag v-if="plan.parlays?.length" type="warning">
          {{ t('sportteryPlan.parlayCount', { n: plan.parlays.length }) }}
        </el-tag>
        <span class="updated-at">{{ t('sportteryPlan.updatedAt', { time: formatTime(plan.updated_at) }) }}</span>
      </div>
    </div>

    <el-alert
      v-if="plan?.empty_reason === 'sporttery_unreachable'"
      type="error"
      :closable="false"
      show-icon
      class="disclaimer-alert"
      :title="t('sportteryPlan.emptyTitleUnreachable')"
      :description="sportteryErrorHint"
    />

    <el-alert
      type="warning"
      :closable="false"
      show-icon
      class="disclaimer-alert"
      :title="t('sportteryPlan.disclaimer')"
    />

    <div v-loading="loading">
      <el-empty
        v-if="!loading && (!plan || plan.on_sale_count === 0)"
        :description="emptyTitle"
      >
        <p class="empty-hint">{{ emptyHint }}</p>
      </el-empty>

      <template v-else-if="plan">
        <section class="plan-section">
          <h3 class="section-title">{{ t('sportteryPlan.singleTitle') }}</h3>
          <p class="section-hint">{{ t('sportteryPlan.singleHint') }}</p>
          <el-row :gutter="16" class="plan-grid">
            <el-col
              v-for="row in plan.singles"
              :key="row.match_num || `${row.team_a}-${row.team_b}`"
              :xs="24"
              :sm="12"
              :lg="8"
            >
              <SportteryPlanCard :pick="row" />
            </el-col>
          </el-row>
        </section>

        <section v-if="plan.parlays?.length" class="plan-section">
          <h3 class="section-title">{{ t('sportteryPlan.parlayTitle') }}</h3>
          <p class="section-hint">{{ parlaySectionHint }}</p>
          <el-row :gutter="16" class="plan-grid">
            <el-col
              v-for="(parlay, idx) in plan.parlays"
              :key="idx"
              :xs="24"
              :sm="12"
              :lg="8"
            >
              <SportteryParlayCard :parlay="parlay" />
            </el-col>
          </el-row>
        </section>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { getTodaySportteryPlan } from '@/api/sporttery'
import { useCompetitionStore } from '@/stores/competition'
import SportteryPlanCard from '@/components/SportteryPlanCard.vue'
import SportteryParlayCard from '@/components/SportteryParlayCard.vue'

const { t } = useI18n()
const compStore = useCompetitionStore()
const loading = ref(false)
const plan = ref(null)

const competitionName = computed(() => {
  const key = compStore.current?.name_key
  return key ? t(`competition.names.${key}`) : ''
})

const pageTitle = computed(() => {
  if (!competitionName.value) return t('sportteryPlan.title')
  return t('sportteryPlan.titleWithCompetition', { name: competitionName.value })
})

const pageSubtitle = computed(() => {
  if (compStore.isWorldCup && competitionName.value) {
    return t('sportteryPlan.subtitleWithCompetition', { name: competitionName.value })
  }
  const league = compStore.current?.short_name || competitionName.value
  if (league) return t('sportteryPlan.subtitleLeague', { league })
  return t('sportteryPlan.subtitle')
})

const emptyTitle = computed(() => {
  const reason = plan.value?.empty_reason
  if (reason === 'today_no_on_sale' || reason === 'no_on_sale') {
    return t('sportteryPlan.emptyTitleToday')
  }
  if (!competitionName.value) return t('sportteryPlan.emptyTitle')
  return t('sportteryPlan.emptyTitleWithCompetition', { name: competitionName.value })
})

const parlaySectionHint = computed(() => {
  const n = plan.value?.on_sale_count ?? 0
  const folds = plan.value?.parlay_folds ?? []
  if (n < 3) {
    return t('sportteryPlan.parlayHintOnlyTwo', { n })
  }
  if (folds.includes(5)) {
    return t('sportteryPlan.parlayHintMulti')
  }
  if (folds.includes(4)) {
    return t('sportteryPlan.parlayHintWith4')
  }
  if (folds.includes(3)) {
    return t('sportteryPlan.parlayHintWith3')
  }
  return t('sportteryPlan.parlayHint')
})

const sportteryErrorHint = computed(() => {
  const err = plan.value?.sporttery_status?.last_error
  const base = t('sportteryPlan.emptyHintUnreachable')
  return err ? `${base}（${err}）` : base
})

const emptyHint = computed(() => {
  const reason = plan.value?.empty_reason
  if (reason === 'sporttery_unreachable') {
    return sportteryErrorHint.value
  }
  if (reason === 'no_score_odds') {
    return t('sportteryPlan.emptyHintNoScoreOdds')
  }
  if (reason === 'today_no_on_sale' || reason === 'no_on_sale') {
    return t('sportteryPlan.emptyHintToday')
  }
  if (compStore.isWorldCup && competitionName.value) {
    return t('sportteryPlan.emptyHintWithCompetition', { name: competitionName.value })
  }
  const league = compStore.current?.short_name || competitionName.value
  if (league) return t('sportteryPlan.emptyHintLeague', { league })
  return t('sportteryPlan.emptyHint')
})

function formatTime(iso) {
  if (!iso) return '-'
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

async function loadPlan() {
  loading.value = true
  plan.value = null
  try {
    const res = await getTodaySportteryPlan(compStore.slug)
    plan.value = res.data || res
  } catch (e) {
    console.error(e)
    const status = e?.response?.status
    if (status === 403) {
      ElMessage.warning(t('sportteryPlan.noAccess'))
    } else {
      ElMessage.error(t('messages.requestFailed'))
    }
  } finally {
    loading.value = false
  }
}

watch(() => compStore.slug, loadPlan)
onMounted(loadPlan)
</script>

<style scoped>
.sporttery-plan-page {
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
  flex-wrap: wrap;
}
.updated-at {
  color: #909399;
  font-size: 13px;
}
.disclaimer-alert {
  margin-bottom: 20px;
}
.plan-section {
  margin-bottom: 28px;
}
.section-title {
  margin: 0 0 6px;
  font-size: 17px;
  font-weight: 600;
  color: #303133;
}
.section-hint {
  font-size: 13px;
  color: #909399;
  margin: 0 0 16px;
}
.plan-grid :deep(.el-col) {
  margin-bottom: 16px;
}
.empty-hint {
  color: #909399;
  font-size: 14px;
  max-width: 420px;
  margin: 8px auto 0;
}
</style>
