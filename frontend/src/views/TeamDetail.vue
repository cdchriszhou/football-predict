<template>
  <div class="team-detail" v-loading="loading">
    <el-page-header @back="$router.back">
      <template #content>
        <span class="detail-title">{{ team?.name }}</span>
      </template>
    </el-page-header>

    <div v-if="team" class="detail-content">
      <!-- Team overview -->
      <el-card class="team-overview">
        <el-row :gutter="20">
          <el-col :xs="24" :sm="6" class="team-badge-col">
            <div class="team-title-row">
              <TeamBadge :name="team.name" :flag-url="team.flag_url" :size="56" />
              <h2>{{ team.name }}</h2>
            </div>
            <el-tag v-if="team.group_name" size="small">{{ formatGroup(t, team.group_name) }}</el-tag>
            <el-tag v-if="team.season" size="small" type="info" style="margin-left: 6px">{{ team.season }}{{ t('match.seasonSuffix') }}</el-tag>
          </el-col>
          <el-col :xs="24" :sm="18">
            <el-row :gutter="12">
              <el-col :xs="12" :sm="6" v-for="attr in teamAttrs" :key="attr.key">
                <div class="attr-card">
                  <span class="attr-value">{{ attr.value }}</span>
                  <span class="attr-label">{{ attr.label }}</span>
                </div>
              </el-col>
            </el-row>
          </el-col>
        </el-row>
      </el-card>

      <!-- Ability radar & style -->
      <el-row :gutter="20" style="margin-top: 20px">
        <el-col :xs="24" :sm="12">
          <el-card>
            <template #header><span class="card-title">{{ t('team.radarChart') }}</span></template>
            <div ref="radarRef" class="radar-chart"></div>
          </el-card>
        </el-col>
        <el-col :xs="24" :sm="12">
          <el-card>
            <template #header><span class="card-title">{{ t('team.tacticStyle') }}</span></template>
            <div class="tactic-info">
              <p><strong>{{ t('team.tactic') }}:</strong> {{ team.tactic }}</p>
              <p><strong>{{ t('team.marketValue') }}:</strong> {{ team.price }}</p>
              <p><strong>{{ t('team.fifaRank') }}:</strong> #{{ team.rank }}</p>
            </div>
          </el-card>
        </el-col>
      </el-row>

      <!-- Player roster -->
      <el-card style="margin-top: 20px">
        <template #header><span class="card-title">{{ t('team.roster') }}</span></template>
        <div class="table-responsive">
          <el-table :data="displayPlayers" stripe>
          <el-table-column prop="number" :label="t('team.colNumber')" width="72" align="center">
            <template #default="{ row }">
              <span class="player-number">{{ formatPlayerNumber(row.number) }}</span>
            </template>
          </el-table-column>
          <el-table-column :label="t('team.colName')" min-width="140">
            <template #default="{ row }">{{ playerDisplayName(row, locale) }}</template>
          </el-table-column>
          <el-table-column :label="t('team.colPosition')" width="100">
            <template #default="{ row }">{{ playerPositionLabel(t, row.position) }}</template>
          </el-table-column>
          <el-table-column :label="t('team.colNationality')" width="110">
            <template #default="{ row }">{{ nationalityLabel(t, row.nationality) }}</template>
          </el-table-column>
          <el-table-column prop="age" :label="t('team.colAge')" width="60" />
          <el-table-column prop="status" :label="t('team.colStatus')" width="80">
            <template #default="{ row }">
              <el-tag :type="playerStatusTagType(row.status)" size="small">
                {{ playerStatusLabel(t, row.status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="ability" :label="t('team.colAbility')" width="120">
            <template #default="{ row }">
              <el-progress :percentage="row.ability" :stroke-width="8"
                           :color="row.ability > 80 ? '#4caf50' : row.ability > 70 ? '#ff9800' : '#909399'" />
            </template>
          </el-table-column>
          <el-table-column prop="is_starter" :label="t('team.colStarter')" width="60">
            <template #default="{ row }">
              <el-icon v-if="row.is_starter" color="#4caf50"><Check /></el-icon>
              <el-icon v-else color="#ccc"><Close /></el-icon>
            </template>
          </el-table-column>
        </el-table>
        </div>
      </el-card>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import * as echarts from 'echarts'
import { useTeamsStore } from '@/stores/teams'
import TeamBadge from '@/components/TeamBadge.vue'
import { formatGroup, playerStatusLabel, playerStatusTagType } from '@/i18n/helpers'
import {
  playerDisplayName, playerPositionLabel, nationalityLabel,
  formatPlayerNumber, sortPlayers,
} from '@/i18n/playerLabels'

const { t, locale } = useI18n()
const route = useRoute()
const store = useTeamsStore()

const team = ref(null)
const loading = ref(false)
const radarRef = ref(null)
let chart = null

const teamAttrs = computed(() => {
  if (!team.value) return []
  return [
    { key: 'rank', label: t('team.fifaRank'), value: `#${team.value.rank}` },
    { key: 'attack', label: t('team.attrAttack'), value: team.value.attack },
    { key: 'defend', label: t('team.attrDefend'), value: team.value.defend },
    { key: 'midfield', label: t('team.attrMidfield'), value: team.value.midfield },
    { key: 'speed', label: t('team.attrSpeed'), value: team.value.speed },
    { key: 'physical', label: t('team.attrPhysical'), value: team.value.physical },
    { key: 'tactic', label: t('team.tactic'), value: team.value.tactic },
    { key: 'price', label: t('team.marketValue'), value: team.value.price },
  ]
})

const displayPlayers = computed(() => sortPlayers(team.value?.players || []))

function renderRadar() {
  if (!radarRef.value || !team.value) return
  if (!chart) chart = echarts.init(radarRef.value)
  chart.setOption({
    radar: {
      indicator: [
        { name: t('team.attrAttack'), max: 100 },
        { name: t('team.attrDefend'), max: 100 },
        { name: t('team.attrMidfield'), max: 100 },
        { name: t('team.attrSpeed'), max: 100 },
        { name: t('team.attrPhysical'), max: 100 }
      ]
    },
    series: [{
      type: 'radar',
      data: [{
        value: [team.value.attack, team.value.defend, team.value.midfield, team.value.speed, team.value.physical],
        name: team.value.name,
        areaStyle: { color: 'rgba(26, 35, 126, 0.2)' },
        lineStyle: { color: '#1a237e', width: 2 }
      }]
    }]
  })
}

async function load() {
  loading.value = true
  try {
    team.value = await store.fetchDetail(Number(route.params.id))
    await nextTick()
    renderRadar()
  } finally {
    loading.value = false
  }
}

let resizeHandler = null

watch(locale, () => {
  nextTick(() => renderRadar())
})

onMounted(() => {
  load()
  resizeHandler = () => { if (chart) chart.resize() }
  window.addEventListener('resize', resizeHandler)
})

onUnmounted(() => {
  if (chart) chart.dispose()
  if (resizeHandler) window.removeEventListener('resize', resizeHandler)
})
</script>

<style scoped>
.detail-title { font-size: 20px; font-weight: 700; }
.detail-content { margin-top: 20px; }
.team-overview { border-radius: 12px; }
.team-badge-col { text-align: center; }
.team-title-row {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  margin-bottom: 8px;
}
.team-badge-col h2 { font-size: 22px; margin: 0; text-align: left; }
.attr-card { text-align: center; padding: 12px 8px; background: #f5f7fa; border-radius: 8px; }
.attr-value { font-size: 20px; font-weight: 700; color: #1a237e; display: block; }
.attr-label { font-size: 12px; color: #999; }
.card-title { font-size: 15px; font-weight: 700; }
.tactic-info p { margin: 8px 0; font-size: 14px; }
.radar-chart { height: 320px; }
.player-number {
  font-variant-numeric: tabular-nums;
  font-weight: 600;
  color: #1a237e;
}

@media (max-width: 767px) {
  .detail-title { font-size: 16px; }
  .team-badge-col h2 { font-size: 18px; }
  .attr-value { font-size: 16px; }
  .radar-chart { height: 250px; }
  .tactic-info p { font-size: 13px; }
}
</style>
