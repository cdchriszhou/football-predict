<template>
  <div class="hkjc-horses">
    <div class="page-header">
      <div class="header-row">
        <div>
          <h2>{{ t('hkjc.horsesTitle') }}</h2>
          <p>{{ t('hkjc.horsesSubtitle') }}</p>
        </div>
        <el-button type="primary" :loading="loading" @click="loadData(true)">{{ t('common.refresh') }}</el-button>
      </div>
    </div>

    <el-alert type="warning" :closable="false" show-icon class="disclaimer-alert" :title="disclaimer" />

    <el-alert
      v-if="loadError"
      type="error"
      :closable="false"
      show-icon
      class="disclaimer-alert"
      :title="loadError"
    />
    <el-alert
      v-else-if="!loading && horses.length === 0"
      type="info"
      :closable="false"
      show-icon
      class="disclaimer-alert"
      :title="t('hkjc.horsesEmptyHint')"
    />

    <el-card v-loading="loading" class="section-card">
      <el-table :data="horses" stripe>
        <el-table-column type="index" :label="t('hkjc.colRank')" width="60" />
        <el-table-column prop="name" :label="t('hkjc.colHorseName')" min-width="120" />
        <el-table-column :label="t('hkjc.colRating')" width="80" sortable prop="rating" :sort-method="sortRating">
          <template #default="{ row }">{{ formatRating(row.rating) }}</template>
        </el-table-column>
        <el-table-column :label="t('hkjc.colAge')" width="80">
          <template #default="{ row }">{{ formatAge(row.age) }}</template>
        </el-table-column>
        <el-table-column :label="t('hkjc.colSex')" width="70">
          <template #default="{ row }">{{ formatSex(row.sex) }}</template>
        </el-table-column>
        <el-table-column prop="trainer" :label="t('hkjc.colTrainer')" min-width="100" />
        <el-table-column prop="recent_form" :label="t('hkjc.colRecentForm')" min-width="120" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useHkjcStore } from '@/stores/hkjc'

const { t } = useI18n()
const store = useHkjcStore()

const loading = ref(false)
const horses = ref([])
const disclaimer = ref('')
const loadError = ref('')

function formatAge(age) {
  const n = Number(age)
  if (!n || n <= 0) return '—'
  return t('hkjc.ageYears', { n })
}

function formatSex(sex) {
  if (!sex) return '—'
  const key = `hkjc.sex.${String(sex).toLowerCase()}`
  const label = t(key)
  return label !== key ? label : sex
}

function formatRating(rating) {
  const n = Number(rating)
  if (!n || n <= 0) return '—'
  return String(n)
}

function sortRating(a, b) {
  return Number(a.rating || 0) - Number(b.rating || 0)
}

async function loadData(refresh = false) {
  loading.value = true
  loadError.value = ''
  try {
    const res = await store.fetchHorses(refresh)
    horses.value = res || []
    disclaimer.value = t('hkjc.disclaimer')
  } catch (e) {
    loadError.value = e.response?.data?.message || e.message || t('messages.requestFailed')
    horses.value = []
  } finally {
    loading.value = false
  }
}

onMounted(() => loadData(false))
</script>

<style scoped>
.header-row { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }
.header-row h2 { margin: 0; }
.header-row p { margin: 4px 0 0; }
.disclaimer-alert { margin-bottom: 16px; }
.section-card { border-radius: 12px; }
</style>
