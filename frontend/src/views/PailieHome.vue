<template>
  <div class="pailie-page">
    <div class="page-header">
      <div>
        <h2>{{ t('pailie.title') }}</h2>
        <p>{{ t('pailie.subtitle') }}</p>
      </div>
      <el-button type="primary" :loading="loading" @click="refresh">
        {{ t('pailie.refresh') }}
      </el-button>
    </div>

    <el-alert
      type="warning"
      :closable="false"
      show-icon
      class="disclaimer"
      :title="catalog?.disclaimer || t('pailie.disclaimer')"
    />

    <el-tabs v-model="activeGame" class="game-tabs" @tab-change="onTabChange">
      <el-tab-pane :label="t('pailie.pl3')" name="pl3" />
      <el-tab-pane :label="t('pailie.pl5')" name="pl5" />
    </el-tabs>

    <div v-loading="loading" class="game-body">
      <section class="panel rules-panel">
        <h3>{{ t('pailie.rulesTitle') }}</h3>
        <p class="note">{{ currentGame?.note }}</p>
        <div class="play-grid">
          <div v-for="pt in currentGame?.play_types || []" :key="pt.id" class="play-card">
            <div class="play-name">{{ pt.name }}</div>
            <div class="play-prize">{{ t('pailie.prizeFixed', { n: pt.prize }) }}</div>
            <p>{{ pt.desc }}</p>
          </div>
        </div>
      </section>

      <section class="panel picker-panel">
        <div class="picker-head">
          <h3>{{ t('pailie.pickTitle') }}</h3>
          <el-radio-group v-if="activeGame === 'pl3'" v-model="pl3Mode" size="small">
            <el-radio-button value="direct">{{ t('pailie.modeDirect') }}</el-radio-button>
            <el-radio-button value="group3">{{ t('pailie.modeGroup3') }}</el-radio-button>
            <el-radio-button value="group6">{{ t('pailie.modeGroup6') }}</el-radio-button>
          </el-radio-group>
        </div>

        <div class="digit-rows">
          <div v-for="(row, ri) in digitRows" :key="ri" class="digit-row">
            <span class="pos-label">{{ positionLabel(ri) }}</span>
            <button
              v-for="n in 10"
              :key="n - 1"
              type="button"
              class="digit-btn"
              :class="{ active: row.includes(n - 1) }"
              @click="toggleDigit(ri, n - 1)"
            >
              {{ n - 1 }}
            </button>
          </div>
        </div>

        <div class="picker-actions">
          <el-button @click="machinePick">{{ t('pailie.machinePick') }}</el-button>
          <el-button @click="clearPick">{{ t('pailie.clear') }}</el-button>
          <el-button type="primary" :disabled="!canAdd" @click="addTicket">
            {{ t('pailie.addTicket') }}
          </el-button>
        </div>

        <div class="ticket-meta">
          <span>{{ t('pailie.betCount', { n: betCount }) }}</span>
          <span>{{ t('pailie.stakeAmount', { n: betCount * 2 }) }}</span>
          <span v-if="activeGame === 'pl3'">{{ modeLabel }}</span>
        </div>

        <div v-if="tickets.length" class="ticket-list">
          <div v-for="(tk, idx) in tickets" :key="idx" class="ticket-item">
            <span class="tk-game">{{ tk.game === 'pl3' ? t('pailie.pl3') : t('pailie.pl5') }}</span>
            <span class="tk-mode">{{ ticketModeLabel(tk) }}</span>
            <span class="tk-nums">{{ tk.display }}</span>
            <span class="tk-bets">{{ t('pailie.betCount', { n: tk.bets }) }}</span>
            <el-button link type="danger" @click="removeTicket(idx)">{{ t('pailie.remove') }}</el-button>
          </div>
        </div>
        <el-empty v-else :description="t('pailie.emptyTickets')" :image-size="64" />
      </section>

      <section class="panel history-panel">
        <h3>{{ t('pailie.historyTitle') }}</h3>
        <el-alert
          v-if="historyMessage"
          type="info"
          :closable="false"
          show-icon
          :title="historyMessage"
          class="history-alert"
        />
        <el-table :data="historyRows" stripe size="small" empty-text="—">
          <el-table-column prop="issue" :label="t('pailie.colIssue')" min-width="100" />
          <el-table-column prop="result" :label="t('pailie.colResult')" min-width="120" />
          <el-table-column prop="draw_time" :label="t('pailie.colTime')" min-width="120" />
        </el-table>
      </section>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { getPailieCatalog, getPailieHistory } from '@/api/pailie'

const { t } = useI18n()

const loading = ref(false)
const catalog = ref(null)
const history = ref({ history: {}, message: null, reachable: false })
const activeGame = ref('pl3')
const pl3Mode = ref('direct')
const selections = ref([[], [], []])
const tickets = ref([])

const currentGame = computed(() =>
  (catalog.value?.games || []).find((g) => g.id === activeGame.value) || null,
)

const digitRows = computed(() => selections.value)

const historyRows = computed(() => history.value?.history?.[activeGame.value] || [])
const historyMessage = computed(() => history.value?.message || '')

const modeLabel = computed(() => {
  if (activeGame.value !== 'pl3') return t('pailie.modeDirect')
  if (pl3Mode.value === 'group3') return t('pailie.modeGroup3')
  if (pl3Mode.value === 'group6') return t('pailie.modeGroup6')
  return t('pailie.modeDirect')
})

function positionLabel(idx) {
  if (activeGame.value === 'pl3' && pl3Mode.value !== 'direct') {
    return t('pailie.pool')
  }
  if (activeGame.value === 'pl5') {
    return t(`pailie.pos5.${idx}`)
  }
  return t(`pailie.pos3.${idx}`)
}

function ensureRows() {
  if (activeGame.value === 'pl3' && pl3Mode.value !== 'direct') {
    selections.value = [[]]
    return
  }
  const n = activeGame.value === 'pl5' ? 5 : 3
  selections.value = Array.from({ length: n }, () => [])
}

function toggleDigit(rowIdx, digit) {
  const row = [...selections.value[rowIdx]]
  const i = row.indexOf(digit)
  if (i >= 0) row.splice(i, 1)
  else row.push(digit)
  row.sort((a, b) => a - b)
  const next = [...selections.value]
  next[rowIdx] = row
  selections.value = next
}

function uniqueSorted(nums) {
  return [...new Set(nums)].sort((a, b) => a - b)
}

function countBets() {
  const rows = selections.value
  if (rows.some((r) => !r.length)) return 0
  if (activeGame.value === 'pl5' || pl3Mode.value === 'direct') {
    return rows.reduce((p, r) => p * r.length, 1)
  }
  const pool = uniqueSorted(rows[0] || [])
  if (pl3Mode.value === 'group3') {
    if (pool.length < 2) return 0
    return pool.length * (pool.length - 1)
  }
  if (pl3Mode.value === 'group6') {
    const m = pool.length
    if (m < 3) return 0
    return (m * (m - 1) * (m - 2)) / 6
  }
  return 0
}

const betCount = computed(() => countBets())
const canAdd = computed(() => betCount.value > 0)

function displayFromSelection() {
  if (activeGame.value === 'pl3' && pl3Mode.value !== 'direct') {
    return uniqueSorted(selections.value[0] || []).join(' ')
  }
  return selections.value.map((r) => (r.length === 1 ? String(r[0]) : `[${r.join(',')}]`)).join(' · ')
}

function machinePick() {
  if (activeGame.value === 'pl3' && pl3Mode.value !== 'direct') {
    const count = pl3Mode.value === 'group3' ? 2 : 3
    const pool = []
    while (pool.length < count) {
      const d = Math.floor(Math.random() * 10)
      if (!pool.includes(d)) pool.push(d)
    }
    pool.sort((a, b) => a - b)
    selections.value = [pool]
    return
  }
  const n = activeGame.value === 'pl5' ? 5 : 3
  selections.value = Array.from({ length: n }, () => [Math.floor(Math.random() * 10)])
}

function clearPick() {
  ensureRows()
}

function addTicket() {
  if (!canAdd.value) return
  tickets.value.unshift({
    game: activeGame.value,
    mode: activeGame.value === 'pl3' ? pl3Mode.value : 'direct',
    display: displayFromSelection(),
    bets: betCount.value,
    amount: betCount.value * 2,
  })
  ElMessage.success(t('pailie.ticketAdded'))
  clearPick()
}

function removeTicket(idx) {
  tickets.value.splice(idx, 1)
}

function ticketModeLabel(tk) {
  if (tk.mode === 'group3') return t('pailie.modeGroup3')
  if (tk.mode === 'group6') return t('pailie.modeGroup6')
  return t('pailie.modeDirect')
}

function onTabChange() {
  ensureRows()
}

watch(pl3Mode, () => {
  if (activeGame.value === 'pl3') ensureRows()
})

async function refresh() {
  loading.value = true
  try {
    const [catRes, histRes] = await Promise.all([
      getPailieCatalog(),
      getPailieHistory({ limit: 10 }),
    ])
    if (catRes?.code === 200) catalog.value = catRes.data
    if (histRes?.code === 200) history.value = histRes.data
  } catch (e) {
    ElMessage.warning(e?.message || t('pailie.loadFailed'))
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  ensureRows()
  refresh()
})
</script>

<style scoped>
.pailie-page {
  max-width: 1100px;
}
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 16px;
}
.page-header h2 {
  margin: 0 0 6px;
  color: #1a237e;
}
.page-header p {
  margin: 0;
  color: #606266;
}
.disclaimer {
  margin-bottom: 16px;
}
.game-tabs {
  margin-bottom: 8px;
}
.panel {
  background: #fff;
  border-radius: 12px;
  padding: 16px 18px;
  margin-bottom: 16px;
  box-shadow: 0 1px 4px rgba(26, 35, 126, 0.06);
}
.panel h3 {
  margin: 0 0 10px;
  font-size: 16px;
  color: #303133;
}
.note {
  color: #606266;
  margin: 0 0 12px;
  font-size: 13px;
}
.play-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 12px;
}
.play-card {
  border: 1px solid #f0f0f0;
  border-radius: 10px;
  padding: 12px;
  background: #fafafa;
}
.play-name {
  font-weight: 700;
  color: #c62828;
}
.play-prize {
  margin: 4px 0 8px;
  font-size: 13px;
  color: #e65100;
}
.play-card p {
  margin: 0;
  font-size: 12px;
  color: #606266;
  line-height: 1.5;
}
.picker-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}
.digit-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}
.pos-label {
  width: 48px;
  font-size: 13px;
  color: #606266;
  flex-shrink: 0;
}
.digit-btn {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  border: 1px solid #dcdfe6;
  background: #fff;
  cursor: pointer;
  font-weight: 600;
  color: #303133;
  transition: all 0.15s;
}
.digit-btn:hover {
  border-color: #c62828;
  color: #c62828;
}
.digit-btn.active {
  background: #c62828;
  border-color: #c62828;
  color: #fff;
}
.picker-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin: 12px 0 8px;
}
.ticket-meta {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
  font-size: 13px;
  color: #606266;
  margin-bottom: 12px;
}
.ticket-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.ticket-item {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  padding: 10px 12px;
  background: #fff8f6;
  border: 1px solid #ffcdd2;
  border-radius: 8px;
  font-size: 13px;
}
.tk-game, .tk-mode {
  font-weight: 600;
  color: #c62828;
}
.tk-nums {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  letter-spacing: 0.04em;
}
.history-alert {
  margin-bottom: 12px;
}
@media (max-width: 640px) {
  .page-header {
    flex-direction: column;
  }
  .digit-btn {
    width: 32px;
    height: 32px;
  }
}
</style>
