<template>
  <div class="match-list-page">
    <div class="page-header">
      <h2>{{ t('match.listTitle') }}</h2>
      <p>{{ listSubtitle }}</p>
    </div>

    <el-card class="filter-card" shadow="never">
      <el-row :gutter="16" align="middle">
        <el-col v-if="showStageFilter" :xs="24" :sm="12" :md="5">
          <el-select v-model="filter.stage" :placeholder="stagePlaceholder" clearable @change="loadData">
            <el-option v-for="opt in stageOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
          </el-select>
        </el-col>
        <el-col :xs="12" :sm="6" :md="4">
          <el-select v-model="filter.status" :placeholder="t('match.selectStatus')" clearable @change="loadData">
            <el-option v-for="opt in statusOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
          </el-select>
        </el-col>
        <el-col v-if="showGroups" :xs="12" :sm="6" :md="3">
          <el-select v-model="filter.groupName" :placeholder="t('match.selectGroup')" clearable @change="loadData">
            <el-option v-for="g in groups" :key="g" :label="t('match.groupSuffix', { g })" :value="g" />
          </el-select>
        </el-col>
        <el-col :xs="24" :sm="12" :md="5">
          <el-input v-model="filter.date" type="date" :placeholder="t('match.selectDate')" clearable @change="loadData" />
        </el-col>
        <el-col :xs="24" :sm="12" :md="7" style="text-align:right">
          <span class="total-info">{{ t('match.totalMatches', { n: store.filter.total }) }}</span>
        </el-col>
      </el-row>
    </el-card>

    <div class="match-grid" v-loading="pageLoading">
      <el-empty v-if="!pageLoading && store.list.length === 0" :description="t('match.noMatches')" />
      <MatchCard v-for="m in store.list" :key="m.id" :match="m" show-odds />
    </div>

    <div class="pagination-wrap" v-if="store.filter.total > 20">
      <el-pagination
        v-model:current-page="store.filter.page"
        :page-size="20"
        :total="store.filter.total"
        layout="prev, pager, next"
        @current-change="loadData"
        background
      />
    </div>
  </div>
</template>

<script setup>
import { reactive, ref, computed, onMounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import MatchCard from '@/components/MatchCard.vue'
import { useMatchesStore } from '@/stores/matches'
import { usePredictionsStore } from '@/stores/predictions'
import { useOddsStore } from '@/stores/odds'
import { useCompetitionStore } from '@/stores/competition'
import { useTeamsStore } from '@/stores/teams'
import { getMatchStages } from '@/api/matches'
import { STAGE_KEYS, STATUS_KEYS, stageLabel } from '@/i18n/matchLabels'

const { t } = useI18n()
const store = useMatchesStore()
const predStore = usePredictionsStore()
const oddsStore = useOddsStore()
const compStore = useCompetitionStore()
const teamsStore = useTeamsStore()

const showGroups = computed(() => compStore.features?.groups === true)
const isClubLeague = computed(() => compStore.current?.type === 'club')

const pageLoading = ref(false)
const dynamicStages = ref([])
const groups = ['A','B','C','D','E','F','G','H','I','J','K','L']

const stageOptions = computed(() => {
  if (isClubLeague.value) {
    return dynamicStages.value.map((value) => ({
      value,
      label: stageLabel(t, value),
    }))
  }
  return Object.entries(STAGE_KEYS).map(([value, key]) => ({
    value,
    label: t(`stage.${key}`),
  }))
})

const showStageFilter = computed(() => !isClubLeague.value || dynamicStages.value.length > 0)

const stagePlaceholder = computed(() => (
  isClubLeague.value ? t('match.selectMatchday') : t('match.selectStage')
))

const listSubtitle = computed(() => {
  if (isClubLeague.value && compStore.current?.short_name) {
    return t('match.listSubtitleLeague', { league: compStore.current.short_name })
  }
  return t('match.listSubtitle')
})

const statusOptions = computed(() =>
  Object.entries(STATUS_KEYS).map(([value, key]) => ({ value, label: t(`status.${key}`) }))
)

const filter = reactive({
  stage: '',
  status: '',
  groupName: '',
  date: ''
})

function resetFilters() {
  filter.stage = ''
  filter.status = ''
  filter.groupName = ''
  filter.date = ''
  store.setFilter({ stage: '', status: '', page: 1, size: 20 })
}

async function loadStages() {
  if (!isClubLeague.value) {
    dynamicStages.value = []
    return
  }
  try {
    const res = await getMatchStages()
    dynamicStages.value = Array.isArray(res.data) ? res.data : []
  } catch {
    dynamicStages.value = []
  }
}

async function loadPredictionsForCurrent() {
  const ids = store.list.map(m => m.id)
  if (ids.length) {
    await Promise.all([
      predStore.fetchBatch(ids),
      oddsStore.fetchBatch(ids)
    ])
  }
}

async function loadData() {
  pageLoading.value = true
  try {
    const params = { page: store.filter.page, size: 20 }
    if (filter.stage) params.stage = filter.stage
    if (filter.status) params.status = filter.status
    if (filter.groupName) params.group_name = filter.groupName
    if (filter.date) params.date_from = filter.date
    await store.fetchList(params)
    await loadPredictionsForCurrent()
  } finally {
    pageLoading.value = false
  }
}

watch(
  () => compStore.slug,
  async () => {
    resetFilters()
    await compStore.fetchCurrent().catch(() => null)
    await loadStages()
    await loadData()
  },
)

onMounted(async () => {
  await compStore.fetchCurrent().catch(() => null)
  teamsStore.fetchAll({ size: 48 })
  await loadStages()
  loadData()
})
</script>

<style scoped>
.filter-card { margin-bottom: 20px; border-radius: 8px; }
.match-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 16px;
}
.total-info { color: #999; font-size: 14px; }
.pagination-wrap { display: flex; justify-content: center; margin-top: 24px; }

@media (max-width: 767px) {
  .match-grid {
    grid-template-columns: 1fr;
    gap: 12px;
  }
  .filter-card { margin-bottom: 12px; }
  .total-info { font-size: 12px; }
}
</style>
