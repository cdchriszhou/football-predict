<template>
  <div class="score-backtest">
    <div class="page-header">
      <div class="header-row">
        <div>
          <h2>{{ t('scoreBacktest.title') }}</h2>
          <p>{{ t('scoreBacktest.subtitle') }}</p>
        </div>
        <el-button type="primary" :loading="loading" @click="loadData">{{ t('common.refresh') }}</el-button>
      </div>
    </div>

    <el-alert type="warning" :closable="false" show-icon class="disclaimer-alert" :title="disclaimer" />

    <div v-loading="loading">
      <el-row :gutter="20" v-if="data">
        <el-col :xs="12" :sm="6" v-for="m in metrics" :key="m.label">
          <div class="stat-card">
            <div class="stat-icon" :style="{ background: m.color }">
              <el-icon :size="24" color="#fff"><DataAnalysis /></el-icon>
            </div>
            <div class="stat-info">
              <span class="stat-value">{{ m.value }}</span>
              <span class="stat-label">{{ m.label }}</span>
            </div>
          </div>
        </el-col>
      </el-row>

      <el-card class="section-card" style="margin-top: 20px">
        <template #header>
          <span class="card-title">{{ t('scoreBacktest.detailTitle') }}</span>
        </template>
        <el-empty
          v-if="!groups.length"
          :description="emptyHint"
          :image-size="60"
        />
        <el-collapse v-else v-model="expandedGroups" accordion>
          <el-collapse-item
            v-for="group in groups"
            :key="group.group_key"
            :name="group.group_key"
          >
            <template #title>
              <span class="group-title">{{ groupSummary(group) }}</span>
            </template>
            <div class="table-responsive">
              <el-table :data="group.matches" stripe size="small">
                <el-table-column :label="t('scoreBacktest.colDate')" width="100">
                  <template #default="{ row }">{{ formatMatchDate(row.match_time) }}</template>
                </el-table-column>
                <el-table-column :label="t('scoreBacktest.colMatch')" min-width="160">
                  <template #default="{ row }">
                    {{ row.team_a }} vs {{ row.team_b }}
                  </template>
                </el-table-column>
                <el-table-column prop="actual_score" :label="t('scoreBacktest.colActual')" width="72" align="center" />
                <el-table-column prop="primary_pick" :label="t('scoreBacktest.colPrimary')" width="72" align="center" />
                <el-table-column prop="secondary_pick" :label="t('scoreBacktest.colSecondary')" width="72" align="center" />
                <el-table-column :label="t('scoreBacktest.colUpset')" width="80" align="center">
                  <template #default="{ row }">{{ row.upset_pick || '—' }}</template>
                </el-table-column>
                <el-table-column :label="t('scoreBacktest.colPrimaryHit')" width="88" align="center">
                  <template #default="{ row }">
                    <el-tag :type="row.primary_hit ? 'success' : 'info'" size="small">
                      {{ row.primary_hit ? t('scoreBacktest.hit') : t('scoreBacktest.miss') }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column :label="t('scoreBacktest.colTripleHit')" width="88" align="center">
                  <template #default="{ row }">
                    <el-tag :type="row.triple_hit ? 'success' : 'info'" size="small">
                      {{ row.triple_hit ? t('scoreBacktest.hit') : t('scoreBacktest.miss') }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column :label="t('scoreBacktest.colLocation')" min-width="120" show-overflow-tooltip>
                  <template #default="{ row }">{{ row.location || '—' }}</template>
                </el-table-column>
              </el-table>
            </div>
          </el-collapse-item>
        </el-collapse>
      </el-card>

      <el-card class="section-card" style="margin-top: 20px">
        <template #header>
          <span class="card-title">{{ t('scoreBacktest.notesTitle') }}</span>
        </template>
        <ul class="notes-list">
          <li v-for="(n, i) in data?.notes || []" :key="i">{{ n }}</li>
        </ul>
        <p class="meta-line">
          {{ t('scoreBacktest.modelVersion') }}: {{ data?.model_version }} ·
          {{ t('scoreBacktest.computedAt') }}: {{ formatTime(data?.computed_at) }}
        </p>
      </el-card>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { DataAnalysis } from '@element-plus/icons-vue'
import { getScoreBacktest } from '@/api/predictions'
import { formatDateTimeInTz } from '@/utils/timezone'

const { t, locale } = useI18n()

const loading = ref(false)
const data = ref(null)
const disclaimer = ref('')
const expandedGroups = ref('')

const metrics = computed(() => {
  if (!data.value) return []
  const d = data.value
  return [
    { label: t('scoreBacktest.primaryHitRate'), value: `${d.primary_hit_rate}%`, color: '#006B54' },
    { label: t('scoreBacktest.tripleHitRate'), value: `${d.triple_hit_rate}%`, color: '#1a237e' },
    { label: t('scoreBacktest.primaryHits'), value: `${d.primary_hits}/${d.matches_evaluated}`, color: '#e65100' },
    { label: t('scoreBacktest.tripleHits'), value: `${d.triple_hits}/${d.matches_evaluated}`, color: '#4527a0' },
  ]
})

const groups = computed(() => data.value?.groups || [])

const emptyHint = computed(() => {
  if (!data.value) return t('scoreBacktest.noDetail')
  if (data.value.matches_evaluated === 0) {
    return t('scoreBacktest.noFinished')
  }
  return t('scoreBacktest.noDetail')
})

function groupSummary(group) {
  return t('scoreBacktest.groupSummary', {
    label: group.label,
    primary: group.primary_hits ?? 0,
    triple: group.triple_hits ?? 0,
    total: group.evaluated ?? 0,
    primaryRate: group.primary_hit_rate ?? 0,
    tripleRate: group.triple_hit_rate ?? 0,
  })
}

function formatTime(iso) {
  if (!iso) return '—'
  return formatDateTimeInTz(iso, 'Asia/Shanghai', locale.value)
}

function formatMatchDate(iso) {
  if (!iso) return '—'
  const d = new Date(String(iso).replace(' ', 'T'))
  if (Number.isNaN(d.getTime())) return String(iso).slice(0, 10)
  return d.toLocaleDateString(locale.value, { month: 'short', day: 'numeric' })
}

watch(groups, (list) => {
  if (list.length && !expandedGroups.value) {
    expandedGroups.value = list[0].group_key
  }
}, { immediate: true })

async function loadData() {
  loading.value = true
  try {
    const res = await getScoreBacktest()
    if (res?.code !== 200 || !res.data) {
      ElMessage.error(res?.message || t('scoreBacktest.loadFailed'))
      data.value = null
      return
    }
    data.value = res.data
    disclaimer.value = data.value?.disclaimer || t('scoreBacktest.disclaimer')
    if (groups.value.length) {
      expandedGroups.value = groups.value[0].group_key
    }
  } catch (e) {
    data.value = null
    ElMessage.error(t('scoreBacktest.loadFailed'))
  } finally {
    loading.value = false
  }
}

onMounted(loadData)
</script>

<style scoped>
.header-row { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }
.header-row h2 { margin: 0; }
.header-row p { margin: 4px 0 0; color: #606266; }
.disclaimer-alert { margin-bottom: 16px; }
.stat-card { display: flex; align-items: center; gap: 16px; margin-bottom: 16px; }
.stat-icon {
  width: 52px; height: 52px; border-radius: 12px;
  display: flex; align-items: center; justify-content: center;
}
.stat-value { font-size: 28px; font-weight: 800; color: #1a237e; display: block; }
.stat-label { font-size: 13px; color: #999; }
.section-card { border-radius: 12px; }
.card-title { font-size: 16px; font-weight: 700; }
.group-title { font-weight: 600; color: #303133; }
.notes-list { margin: 0; padding-left: 20px; line-height: 1.8; color: #606266; }
.meta-line { margin-top: 16px; font-size: 13px; color: #909399; }
</style>
