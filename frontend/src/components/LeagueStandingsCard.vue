<template>
  <el-card class="section-card standings-card" v-loading="loading">
    <template #header>
      <div class="flex-between">
        <div>
          <span class="card-title">{{ title }}</span>
          <span v-if="season" class="season-tag">{{ season }}{{ t('match.seasonSuffix') }}</span>
        </div>
        <el-button text type="primary" @click="$emit('viewAll')">{{ t('common.viewAll') }}</el-button>
      </div>
    </template>

    <el-empty v-if="!loading && !rows.length" :description="t('dashboard.noStandings')" />

    <div v-else class="table-responsive">
      <el-table :data="rows" stripe size="small" class="standings-table" @row-click="onRowClick">
        <el-table-column prop="rank" :label="t('dashboard.standColRank')" width="52" align="center">
          <template #default="{ row }">
            <span class="rank-cell" :class="rankClass(row.rank)">{{ row.rank }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="t('dashboard.standColTeam')" min-width="140">
          <template #default="{ row }">
            <div class="team-cell">
              <TeamBadge :name="row.name" :flag-url="row.flag_url" :size="22" />
              <span class="team-name">{{ teamName(row) }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="played" :label="t('dashboard.standColPlayed')" width="44" align="center">
          <template #default="{ row }">{{ stat(row.played) }}</template>
        </el-table-column>
        <el-table-column prop="won" :label="t('dashboard.standColWon')" width="40" align="center">
          <template #default="{ row }">{{ stat(row.won) }}</template>
        </el-table-column>
        <el-table-column prop="draw" :label="t('dashboard.standColDraw')" width="40" align="center">
          <template #default="{ row }">{{ stat(row.draw) }}</template>
        </el-table-column>
        <el-table-column prop="lost" :label="t('dashboard.standColLost')" width="40" align="center">
          <template #default="{ row }">{{ stat(row.lost) }}</template>
        </el-table-column>
        <el-table-column prop="goal_diff" :label="t('dashboard.standColGd')" width="48" align="center">
          <template #default="{ row }">{{ formatGd(row.goal_diff) }}</template>
        </el-table-column>
        <el-table-column prop="points" :label="t('dashboard.standColPts')" width="48" align="center">
          <template #default="{ row }">
            <span class="pts-cell">{{ stat(row.points) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </el-card>
</template>

<script setup>
import { useI18n } from 'vue-i18n'
import TeamBadge from '@/components/TeamBadge.vue'

defineProps({
  rows: { type: Array, default: () => [] },
  season: { type: String, default: '' },
  title: { type: String, default: '' },
  loading: { type: Boolean, default: false },
})

const emit = defineEmits(['viewAll', 'selectTeam'])

const { t, locale } = useI18n()

function teamName(row) {
  if (locale.value === 'en') return row.name_en || row.name
  return row.name || row.name_en
}

function stat(val) {
  return val ?? '—'
}

function formatGd(val) {
  if (val === null || val === undefined) return '—'
  return val > 0 ? `+${val}` : String(val)
}

function rankClass(rank) {
  if (rank === 1) return 'rank-cell--gold'
  if (rank <= 4) return 'rank-cell--top'
  if (rank >= 18) return 'rank-cell--bottom'
  return ''
}

function onRowClick(row) {
  if (row?.id) emit('selectTeam', row.id)
}
</script>

<style scoped>
.standings-card :deep(.el-card__body) {
  padding-top: 8px;
}
.season-tag {
  margin-left: 8px;
  font-size: 12px;
  color: #909399;
  font-weight: 500;
}
.standings-table {
  width: 100%;
}
.standings-table :deep(.el-table__row) {
  cursor: pointer;
}
.rank-cell {
  display: inline-block;
  min-width: 22px;
  font-weight: 700;
  color: #606266;
}
.rank-cell--gold { color: #e6a23c; }
.rank-cell--top { color: #1a237e; }
.rank-cell--bottom { color: #909399; }
.team-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}
.team-name {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.pts-cell {
  font-weight: 800;
  color: #1a237e;
}
@media (max-width: 767px) {
  .team-name { font-size: 12px; }
}
</style>
