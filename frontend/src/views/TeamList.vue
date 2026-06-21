<template>
  <div class="team-list-page">
    <div class="page-header">
      <h2>{{ t('team.listTitle') }}</h2>
      <p>{{ listSubtitle }}</p>
    </div>

    <!-- Filters -->
    <el-card class="filter-card" shadow="never">
      <el-row :gutter="12" align="middle">
        <el-col :xs="24" :sm="12" :md="6">
          <el-input v-model="filter.search" :placeholder="t('team.searchPlaceholder')" clearable @input="loadData">
            <template #prefix><el-icon><Search /></el-icon></template>
          </el-input>
        </el-col>
        <el-col :xs="12" :sm="6" :md="4">
          <el-select v-model="filter.sort" :placeholder="t('team.sort')" @change="loadData">
            <el-option v-for="opt in sortOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
          </el-select>
        </el-col>
        <el-col :xs="12" :sm="6" :md="3">
          <el-select v-model="filter.order" @change="loadData">
            <el-option v-for="opt in orderOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
          </el-select>
        </el-col>
        <el-col v-if="showGroups" :xs="24" :sm="12" :md="4">
          <el-select v-model="filter.groupName" :placeholder="t('team.groupFilter')" clearable @change="loadData">
            <el-option v-for="g in groups" :key="g" :label="formatGroup(t, g)" :value="g" />
          </el-select>
        </el-col>
      </el-row>
    </el-card>

    <!-- Team grid -->
    <div class="team-grid" v-loading="store.loading">
      <el-card v-for="team in store.list" :key="team.id" class="team-card" shadow="hover"
               @click="goTeamDetail(team.id)">
        <div class="team-card-header">
          <div class="team-name-row">
            <TeamBadge :name="team.name" :flag-url="team.flag_url" :size="36" />
            <div class="team-name-info">
              <h4>{{ team.name }}</h4>
              <span class="team-rank">{{ rankLabel(team.rank) }}</span>
            </div>
          </div>
          <el-tag v-if="team.group_name" size="small" type="info">{{ formatGroup(t, team.group_name) }}</el-tag>
        </div>

        <el-divider style="margin: 12px 0" />

        <div class="ability-bars">
          <div class="ability-item">
            <span>{{ t('team.attrAttack') }}</span>
            <el-progress :percentage="team.attack" :stroke-width="6" :color="'#4caf50'" />
          </div>
          <div class="ability-item">
            <span>{{ t('team.attrDefend') }}</span>
            <el-progress :percentage="team.defend" :stroke-width="6" :color="'#2196f3'" />
          </div>
          <div class="ability-item">
            <span>{{ t('team.attrMidfield') }}</span>
            <el-progress :percentage="team.midfield" :stroke-width="6" :color="'#ff9800'" />
          </div>
        </div>

        <div class="team-footer">
          <span>{{ team.tactic }}</span>
          <span class="team-price">{{ team.price }}</span>
        </div>
      </el-card>
    </div>
  </div>
</template>

<script setup>
import { reactive, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useTeamsStore } from '@/stores/teams'
import { useCompetitionStore } from '@/stores/competition'
import TeamBadge from '@/components/TeamBadge.vue'
import { formatGroup } from '@/i18n/helpers'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const store = useTeamsStore()
const compStore = useCompetitionStore()

const showGroups = computed(() => compStore.features?.groups !== false)
const listSubtitle = computed(() => {
  if (compStore.current?.short_name && !compStore.isWorldCup) {
    return t('team.listSubtitleLeague', { league: compStore.current.short_name })
  }
  return t('team.listSubtitle')
})
const groups = ['A','B','C','D','E','F','G','H','I','J','K','L']

function rankLabel(rank) {
  return compStore.isWorldCup ? `FIFA #${rank}` : t('team.leagueRank', { n: rank })
}

function goTeamDetail(id) {
  router.push(`${compStore.basePath}/teams/${id}`)
}

const sortOptions = computed(() => [
  { label: t('team.sortRank'), value: 'rank' },
  { label: t('team.sortAttack'), value: 'attack' },
  { label: t('team.sortDefend'), value: 'defend' },
  { label: t('team.sortMidfield'), value: 'midfield' }
])

const orderOptions = computed(() => [
  { label: t('team.sortAsc'), value: 'asc' },
  { label: t('team.sortDesc'), value: 'desc' }
])

const filter = reactive({
  search: '',
  sort: 'rank',
  order: 'asc',
  groupName: ''
})

let timer = null
function loadData() {
  clearTimeout(timer)
  timer = setTimeout(() => {
    store.fetchAll({
      search: filter.search || undefined,
      sort: filter.sort,
      order: filter.order,
      group_name: filter.groupName || undefined
    })
  }, 300)
}

onMounted(() => loadData())

watch(() => route.params.slug, () => {
  filter.groupName = ''
  filter.search = ''
  loadData()
})
</script>

<style scoped>
.filter-card { margin-bottom: 20px; border-radius: 8px; }
.team-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
}
.team-card { cursor: pointer; border-radius: 12px; }
.team-card:hover { border-color: #1a237e; }
.team-card-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.team-name-row { display: flex; align-items: center; gap: 10px; min-width: 0; flex: 1; }
.team-name-info h4 { font-size: 16px; font-weight: 700; margin: 0; }
.team-rank { font-size: 12px; color: #999; }
.ability-bars { display: flex; flex-direction: column; gap: 8px; }
.ability-item { display: flex; align-items: center; gap: 8px; font-size: 12px; color: #666; }
.ability-item span { width: 30px; text-align: right; }
.ability-item .el-progress { flex: 1; }
.team-footer { display: flex; justify-content: space-between; margin-top: 10px; font-size: 12px; color: #888; }
.team-price { font-weight: 600; color: #e65100; }

@media (max-width: 767px) {
  .team-grid {
    grid-template-columns: 1fr;
    gap: 12px;
  }
  .team-card-header { gap: 8px; }
  .team-name-info h4 { font-size: 14px; }
}
</style>
