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
      <el-tab-pane :label="t('pailie.fc3d')" name="fc3d" />
      <el-tab-pane :label="t('pailie.pl5')" name="pl5" />
      <el-tab-pane :label="t('pailie.qxc')" name="qxc" />
      <el-tab-pane :label="t('pailie.ssq')" name="ssq" />
      <el-tab-pane :label="t('pailie.dlt')" name="dlt" />
    </el-tabs>

    <section class="panel pool-panel">
      <div class="picker-head">
        <div>
          <h3>{{ t('pailie.poolTitle') }}</h3>
          <p class="note">
            {{ t('pailie.poolHint') }}
            <template v-if="poolsUpdatedAt"> · {{ t('pailie.poolUpdated', { time: poolsUpdatedAt }) }}</template>
          </p>
        </div>
        <el-button size="small" :loading="poolsLoading" @click="loadPools">{{ t('pailie.poolRefresh') }}</el-button>
      </div>
      <el-alert
        v-if="poolsMessage"
        type="warning"
        :closable="false"
        show-icon
        class="history-alert"
        :title="poolsMessage"
      />
      <div class="pool-grid">
        <div
          v-for="g in poolGameIds"
          :key="g"
          class="pool-card"
          :class="{ 'pool-card--active': activeGame === g }"
          @click="switchToGame(g)"
        >
          <div class="pool-name">{{ gameName(g) }}</div>
          <div class="pool-amount">{{ poolAmountDisplay(g) }}</div>
          <div class="pool-meta">
            <span>{{ t('pailie.colIssue') }} {{ poolOf(g)?.latest?.issue || '—' }}</span>
            <span>{{ poolOf(g)?.latest?.draw_time || '—' }}</span>
          </div>
          <div class="pool-sale">
            {{ t('pailie.saleAmount') }}：{{ formatPool(poolOf(g)?.latest?.sale_amount_text) }}
          </div>
          <div v-if="g === 'pl3' || g === 'fc3d'" class="pool-fixed">
            {{ t('pailie.pl3FixedPrizes') }}
          </div>
          <p class="pool-note">{{ poolNoteDisplay(g) }}</p>
        </div>
      </div>
    </section>

    <div class="game-body">
      <section class="panel recommend-panel" v-loading="recommendLoading">
        <div class="picker-head">
          <div>
            <h3>{{ t('pailie.recommendTitle') }}</h3>
            <p class="note">
              {{ recommend?.method?.desc || t('pailie.recommendHint') }}
              <template v-if="recommend?.sample_size">
                · {{ t('pailie.sampleSize', { n: recommend.sample_size }) }}
              </template>
            </p>
          </div>
          <el-radio-group v-model="windowSize" size="small" @change="loadRecommend">
            <el-radio-button :value="30">30{{ t('pailie.periods') }}</el-radio-button>
            <el-radio-button :value="60">60{{ t('pailie.periods') }}</el-radio-button>
            <el-radio-button :value="100">100{{ t('pailie.periods') }}</el-radio-button>
          </el-radio-group>
        </div>
        <div class="ai-row">
          <el-switch v-model="useAi" @change="loadRecommend" />
          <span class="ai-label">{{ t('pailie.useAi') }}</span>
          <el-tag v-if="aiEnhancing" size="small" type="warning">{{ t('pailie.aiEnhancing') }}</el-tag>
          <el-tag v-else-if="recommend?.ai_enabled" size="small" type="success">
            {{ recommend.ai_models?.length
              ? t('pailie.aiActiveModels', { models: recommend.ai_models.join('+') })
              : t('pailie.aiActive') }}
          </el-tag>
          <el-tag v-else-if="useAi" size="small" type="info">{{ t('pailie.aiInactive') }}</el-tag>
        </div>

        <el-alert
          v-if="recommend?.disclaimer"
          type="info"
          :closable="false"
          show-icon
          class="history-alert"
          :title="recommend.disclaimer"
        />
        <el-alert
          v-else-if="recommend && !recommend.reachable"
          type="warning"
          :closable="false"
          show-icon
          class="history-alert"
          :title="recommend.message || t('pailie.recommendEmpty')"
        />

        <div v-if="recommendCards.length" class="rec-grid">
          <div
            v-for="(rec, idx) in recommendCards"
            :key="rec.id"
            class="rec-card"
            :class="{ 'rec-card--primary': idx === 0 }"
          >
            <div class="rec-top">
              <span class="rec-label">
                <el-tag v-if="rec.source === 'ai'" size="small" type="warning" effect="plain" class="ai-tag">
                  {{ rec.model_label || 'AI' }}
                </el-tag>
                {{ recLabel(rec) }}
              </span>
              <span class="rec-conf">{{ Math.round((rec.confidence || 0) * 100) }}%</span>
            </div>
            <div
              v-if="activeGame === 'ssq'"
              class="rec-nums rec-nums--ssq"
            >
              <div class="rec-nums-row">
                <span
                  v-for="(d, di) in recDigits(rec).slice(0, 5)"
                  :key="'r' + di"
                  class="rec-ball rec-ball--red"
                >{{ formatBall(d) }}</span>
              </div>
              <div class="rec-nums-row rec-nums-row--second">
                <span class="rec-ball rec-ball--red">{{ formatBall(recDigits(rec)[5]) }}</span>
                <span class="rec-plus">+</span>
                <span class="rec-ball rec-ball--blue">{{ formatBall(recDigits(rec)[6]) }}</span>
              </div>
            </div>
            <div
              v-else-if="activeGame === 'dlt'"
              class="rec-nums rec-nums--dlt"
            >
              <div class="rec-nums-row">
                <span
                  v-for="(d, di) in recDigits(rec).slice(0, 5)"
                  :key="'f' + di"
                  class="rec-ball rec-ball--red"
                >{{ formatBall(d) }}</span>
              </div>
              <div class="rec-nums-row rec-nums-row--second">
                <span class="rec-plus">+</span>
                <span
                  v-for="(d, di) in recDigits(rec).slice(5, 7)"
                  :key="'b' + di"
                  class="rec-ball rec-ball--blue"
                >{{ formatBall(d) }}</span>
              </div>
            </div>
            <div
              v-else-if="activeGame === 'qxc'"
              class="rec-nums rec-nums--qxc-wrap"
            >
              <div class="rec-nums-row">
                <span
                  v-for="(d, di) in recDigits(rec).slice(0, 5)"
                  :key="'q' + di"
                  class="rec-ball"
                >{{ formatBall(d) }}</span>
              </div>
              <div class="rec-nums-row rec-nums-row--second">
                <span class="rec-ball">{{ formatBall(recDigits(rec)[5]) }}</span>
                <span class="rec-plus">+</span>
                <span class="rec-ball rec-ball--special">{{ formatBall(recDigits(rec)[6]) }}</span>
              </div>
            </div>
            <div v-else class="rec-nums">
              <span
                v-for="(d, di) in recDigits(rec)"
                :key="di"
                class="rec-ball"
              >{{ formatBall(d) }}</span>
            </div>
            <p class="rec-reason">{{ rec.reason }}</p>
            <div class="rec-actions">
              <el-button size="small" class="rec-btn" @click="applyRecommend(rec)">{{ t('pailie.applyPick') }}</el-button>
              <el-button size="small" type="primary" class="rec-btn" @click="addRecommendTicket(rec)">
                {{ t('pailie.addTicket') }}
              </el-button>
            </div>
          </div>
        </div>

        <el-collapse v-if="freqRows.length" class="freq-collapse">
          <el-collapse-item :title="t('pailie.freqTitle')" name="freq">
            <div class="freq-block">
              <div v-for="(pos, pi) in freqRows" :key="pi" class="freq-pos">
                <div class="freq-pos-label">{{ positionLabel(pi) }}</div>
                <div class="freq-bars">
                  <div
                    v-for="item in pos"
                    :key="item.digit"
                    class="freq-item"
                    :title="t('pailie.freqTip', { count: item.count, rate: pct(item.rate), miss: item.miss })"
                  >
                    <span class="freq-digit" :class="item.tag">{{ formatBall(item.digit) }}</span>
                    <div class="freq-bar-track">
                      <div class="freq-bar-fill" :style="{ width: barWidth(item.rate) }" />
                    </div>
                    <span class="freq-meta">{{ pct(item.rate) }}</span>
                  </div>
                </div>
              </div>
            </div>
          </el-collapse-item>
        </el-collapse>
      </section>

      <section class="panel rules-panel">
        <h3>{{ t('pailie.rulesTitle') }}</h3>
        <p class="note">{{ currentGame?.note }}</p>
        <div class="play-grid">
          <div v-for="pt in currentGame?.play_types || []" :key="pt.id" class="play-card">
            <div class="play-name">{{ pt.name }}</div>
            <div class="play-prize">
              {{ pt.prize_label || t('pailie.prizeFixed', { n: pt.prize }) }}
            </div>
            <p>{{ pt.desc }}</p>
          </div>
        </div>
      </section>

      <section class="panel picker-panel">
        <div class="picker-head">
          <h3>{{ t('pailie.pickTitle') }}</h3>
          <el-radio-group v-if="isThreeDigitGame" v-model="pl3Mode" size="small">
            <el-radio-button value="direct">{{ t('pailie.modeDirect') }}</el-radio-button>
            <el-radio-button value="group3">{{ t('pailie.modeGroup3') }}</el-radio-button>
            <el-radio-button value="group6">{{ t('pailie.modeGroup6') }}</el-radio-button>
          </el-radio-group>
        </div>

        <template v-if="activeGame === 'ssq'">
          <div class="ssq-zone">
            <div class="ssq-zone-title">{{ t('pailie.ssqRed') }} <span class="ssq-count">{{ ssqRed.length }}/6</span></div>
            <div class="digit-row ssq-row">
              <button
                v-for="n in 33"
                :key="'r' + n"
                type="button"
                class="digit-btn ssq-btn"
                :class="{ active: ssqRed.includes(n), hot: isHot(n), cold: isCold(n) }"
                @click="toggleSsqRed(n)"
              >{{ formatBall(n) }}</button>
            </div>
          </div>
          <div class="ssq-zone">
            <div class="ssq-zone-title">{{ t('pailie.ssqBlue') }} <span class="ssq-count">{{ ssqBlue ? 1 : 0 }}/1</span></div>
            <div class="digit-row ssq-row">
              <button
                v-for="n in 16"
                :key="'b' + n"
                type="button"
                class="digit-btn ssq-btn ssq-btn--blue"
                :class="{ active: ssqBlue === n }"
                @click="toggleSsqBlue(n)"
              >{{ formatBall(n) }}</button>
            </div>
          </div>
        </template>

        <template v-else-if="activeGame === 'dlt'">
          <div class="ssq-zone">
            <div class="ssq-zone-title">{{ t('pailie.dltFront') }} <span class="ssq-count">{{ dltFront.length }}/5</span></div>
            <div class="digit-row ssq-row">
              <button
                v-for="n in 35"
                :key="'df' + n"
                type="button"
                class="digit-btn ssq-btn"
                :class="{ active: dltFront.includes(n), hot: isHot(n), cold: isCold(n) }"
                @click="toggleDltFront(n)"
              >{{ formatBall(n) }}</button>
            </div>
          </div>
          <div class="ssq-zone">
            <div class="ssq-zone-title">{{ t('pailie.dltBack') }} <span class="ssq-count">{{ dltBack.length }}/2</span></div>
            <div class="digit-row ssq-row">
              <button
                v-for="n in 12"
                :key="'db' + n"
                type="button"
                class="digit-btn ssq-btn ssq-btn--blue"
                :class="{ active: dltBack.includes(n) }"
                @click="toggleDltBack(n)"
              >{{ formatBall(n) }}</button>
            </div>
          </div>
        </template>

        <div v-else class="digit-rows">
          <div v-for="(row, ri) in digitRows" :key="ri" class="digit-row">
            <span class="pos-label">{{ positionLabel(ri) }}</span>
            <button
              v-for="n in alphabetSize(ri)"
              :key="n - 1"
              type="button"
              class="digit-btn"
              :class="{ active: row.includes(n - 1), hot: isHot(n - 1), cold: isCold(n - 1) }"
              @click="toggleDigit(ri, n - 1)"
            >
              {{ n - 1 }}
            </button>
          </div>
        </div>

        <div class="picker-actions">
          <el-button type="success" plain :disabled="!recommendCards.length" @click="applyTopRecommend">
            {{ t('pailie.applyTop') }}
          </el-button>
          <el-button @click="machinePick">{{ t('pailie.machinePick') }}</el-button>
          <el-button @click="clearPick">{{ t('pailie.clear') }}</el-button>
          <el-button type="primary" :disabled="!canAdd" @click="addTicket">
            {{ t('pailie.addTicket') }}
          </el-button>
        </div>

        <div class="ticket-meta">
          <span>{{ t('pailie.betCount', { n: betCount }) }}</span>
          <span>{{ t('pailie.stakeAmount', { n: betCount * 2 }) }}</span>
          <span v-if="isThreeDigitGame">{{ modeLabel }}</span>
        </div>

        <div v-if="tickets.length" class="ticket-list">
          <div v-for="(tk, idx) in tickets" :key="idx" class="ticket-item">
            <span class="tk-game">{{ gameName(tk.game) }}</span>
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
        <el-table :data="historyTableRows" stripe size="small" empty-text="—">
          <el-table-column prop="issue" :label="t('pailie.colIssue')" min-width="90" />
          <el-table-column prop="result" :label="t('pailie.colResult')" min-width="180" />
          <el-table-column prop="draw_time" :label="t('pailie.colTime')" min-width="110" />
          <el-table-column :label="t('pailie.colPool')" min-width="140">
            <template #default="{ row }">
              {{ isThreeDigitGame ? t('pailie.noFloatingPool') : formatPool(row.pool_balance_text) }}
            </template>
          </el-table-column>
          <el-table-column :label="t('pailie.colSale')" min-width="120">
            <template #default="{ row }">{{ formatPool(row.sale_amount_text) }}</template>
          </el-table-column>
        </el-table>
      </section>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { getPailieCatalog, getPailieHistory, getPailiePools, getPailieRecommend } from '@/api/pailie'

const { t } = useI18n()

const loading = ref(false)
const poolsLoading = ref(false)
const recommendLoading = ref(false)
const aiEnhancing = ref(false)
const catalog = ref(null)
const history = ref({ history: {}, message: null, reachable: false })
const poolsData = ref({ pools: {}, message: null, updated_at: null })
const recommend = ref(null)
const activeGame = ref('pl3')
const pl3Mode = ref('direct')
const windowSize = ref(100)
const useAi = ref(true)
const selections = ref([[], [], []])
const tickets = ref([])
const poolGameIds = ['pl3', 'fc3d', 'pl5', 'qxc', 'ssq', 'dlt']
const ssqRed = ref([])
const ssqBlue = ref(null)
const dltFront = ref([])
const dltBack = ref([])
let poolTimer = null
let recommendSeq = 0
const recommendCache = new Map()
/** 各玩法最近已知期号，用于开奖后自动刷新推荐 */
const knownIssues = ref({})

const isThreeDigitGame = computed(() => activeGame.value === 'pl3' || activeGame.value === 'fc3d')

function recommendCacheKey(game, win, ai) {
  return `${game}:${win}:${ai ? 1 : 0}`
}

function clearRecommendCacheForGames(gameIds) {
  if (!gameIds?.length) return
  for (const key of [...recommendCache.keys()]) {
    if (gameIds.some((g) => key.startsWith(`${g}:`))) {
      recommendCache.delete(key)
    }
  }
}

const currentGame = computed(() =>
  (catalog.value?.games || []).find((g) => g.id === activeGame.value) || null,
)

const digitRows = computed(() => selections.value)
const historyRows = computed(() => history.value?.history?.[activeGame.value] || [])
const historyMessage = computed(() => history.value?.message || '')
const historyTableRows = computed(() => {
  const fromPools = poolsData.value?.pools?.[activeGame.value]?.history
  if (Array.isArray(fromPools) && fromPools.length) return fromPools
  return historyRows.value
})
const poolsMessage = computed(() => poolsData.value?.message || '')
const poolsUpdatedAt = computed(() => {
  const raw = poolsData.value?.updated_at
  if (!raw) return ''
  try {
    return new Date(raw).toLocaleString()
  } catch {
    return raw
  }
})
const recommendCards = computed(() => recommend.value?.recommendations || [])
const hotDigits = computed(() => recommend.value?.hot_digits || [])
const coldDigits = computed(() => recommend.value?.cold_digits || [])
const freqRows = computed(() => {
  const stats = recommend.value?.position_stats || []
  return stats.map((pos) =>
    [...pos].sort((a, b) => a.digit - b.digit),
  )
})

function poolOf(gameId) {
  return poolsData.value?.pools?.[gameId] || null
}

function gameName(gameId) {
  if (gameId === 'pl3') return t('pailie.pl3')
  if (gameId === 'fc3d') return t('pailie.fc3d')
  if (gameId === 'pl5') return t('pailie.pl5')
  if (gameId === 'qxc') return t('pailie.qxc')
  if (gameId === 'ssq') return t('pailie.ssq')
  if (gameId === 'dlt') return t('pailie.dlt')
  return gameId
}

function formatBall(n) {
  const num = Number(n)
  if (!Number.isFinite(num)) return n
  return (activeGame.value === 'ssq' || activeGame.value === 'dlt')
    ? String(num).padStart(2, '0')
    : String(num)
}

function formatPool(text) {
  if (text === 0 || text === '0') return '0'
  return text || '—'
}

function poolAmountDisplay(gameId) {
  const latest = poolOf(gameId)?.latest
  if (gameId === 'pl3' || gameId === 'fc3d') {
    // 排列3 / 福彩3D 为固定奖，无浮动奖池
    return t('pailie.noFloatingPool')
  }
  return formatPool(latest?.pool_balance_text)
}

function poolNoteDisplay(gameId) {
  if (gameId === 'pl3') return t('pailie.pl3PoolExplain')
  if (gameId === 'fc3d') return t('pailie.fc3dPoolExplain')
  return poolOf(gameId)?.pool_note || ''
}

function switchToGame(gameId) {
  if (activeGame.value === gameId) return
  activeGame.value = gameId
  onTabChange()
}
const modeLabel = computed(() => {
  if (!isThreeDigitGame.value) return t('pailie.modeDirect')
  if (pl3Mode.value === 'group3') return t('pailie.modeGroup3')
  if (pl3Mode.value === 'group6') return t('pailie.modeGroup6')
  return t('pailie.modeDirect')
})

function alphabetSize(posIdx) {
  const fromApi = recommend.value?.alphabets?.[posIdx]
  if (fromApi) return fromApi
  const fromCatalog = currentGame.value?.alphabets?.[posIdx]
  if (fromCatalog) return fromCatalog
  if (activeGame.value === 'qxc' && posIdx === 6) return 15
  return 10
}

function pct(rate) {
  return `${Math.round((rate || 0) * 1000) / 10}%`
}

function barWidth(rate) {
  let base = 1 / 10
  if (activeGame.value === 'ssq') base = 6 / 33
  else if (activeGame.value === 'dlt') base = 5 / 35
  const w = Math.max(8, Math.min(100, ((rate || 0) / (base * 2)) * 100))
  return `${w}%`
}

function isHot(d) {
  return hotDigits.value.includes(d)
}

function isCold(d) {
  return coldDigits.value.includes(d)
}

function recLabel(rec) {
  return rec.label || t('pailie.recAlt')
}

function recDigits(rec) {
  if (Array.isArray(rec?.digits) && rec.digits.length) return rec.digits
  const text = String(rec?.display || '').trim()
  if (!text) return []
  return text.split(/\s+/).map((x) => {
    const n = Number(x)
    return Number.isFinite(n) ? n : x
  })
}

function positionLabel(idx) {
  if (activeGame.value === 'ssq') {
    return idx === 0 ? t('pailie.ssqRed') : t('pailie.ssqBlue')
  }
  if (activeGame.value === 'dlt') {
    return idx === 0 ? t('pailie.dltFront') : t('pailie.dltBack')
  }
  if (isThreeDigitGame.value && pl3Mode.value !== 'direct' && digitRows.value.length === 1) {
    return t('pailie.pool')
  }
  if (activeGame.value === 'qxc') {
    return t(`pailie.pos7.${idx}`)
  }
  if (activeGame.value === 'pl5') {
    return t(`pailie.pos5.${idx}`)
  }
  return t(`pailie.pos3.${idx}`)
}

function ensureRows() {
  if (activeGame.value === 'ssq') {
    ssqRed.value = []
    ssqBlue.value = null
    return
  }
  if (activeGame.value === 'dlt') {
    dltFront.value = []
    dltBack.value = []
    return
  }
  if (isThreeDigitGame.value && pl3Mode.value !== 'direct') {
    selections.value = [[]]
    return
  }
  const n = activeGame.value === 'qxc' ? 7 : activeGame.value === 'pl5' ? 5 : 3
  selections.value = Array.from({ length: n }, () => [])
}

function toggleSsqRed(n) {
  const set = new Set(ssqRed.value)
  if (set.has(n)) set.delete(n)
  else if (set.size < 6) set.add(n)
  ssqRed.value = [...set].sort((a, b) => a - b)
}

function toggleSsqBlue(n) {
  ssqBlue.value = ssqBlue.value === n ? null : n
}

function toggleDltFront(n) {
  const set = new Set(dltFront.value)
  if (set.has(n)) set.delete(n)
  else if (set.size < 5) set.add(n)
  dltFront.value = [...set].sort((a, b) => a - b)
}

function toggleDltBack(n) {
  const set = new Set(dltBack.value)
  if (set.has(n)) set.delete(n)
  else if (set.size < 2) set.add(n)
  dltBack.value = [...set].sort((a, b) => a - b)
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
  if (activeGame.value === 'ssq') {
    return ssqRed.value.length === 6 && ssqBlue.value ? 1 : 0
  }
  if (activeGame.value === 'dlt') {
    return dltFront.value.length === 5 && dltBack.value.length === 2 ? 1 : 0
  }
  const rows = selections.value
  if (rows.some((r) => !r.length)) return 0
  if (activeGame.value === 'pl5' || !isThreeDigitGame.value || pl3Mode.value === 'direct') {
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
  if (activeGame.value === 'ssq') {
    const reds = ssqRed.value.map(formatBall).join(' ')
    return `${reds} + ${formatBall(ssqBlue.value)}`
  }
  if (activeGame.value === 'dlt') {
    const front = dltFront.value.map(formatBall).join(' ')
    const back = dltBack.value.map(formatBall).join(' ')
    return `${front} + ${back}`
  }
  if (isThreeDigitGame.value && pl3Mode.value !== 'direct') {
    return uniqueSorted(selections.value[0] || []).join(' ')
  }
  return selections.value.map((r) => (r.length === 1 ? String(r[0]) : `[${r.join(',')}]`)).join(' · ')
}

function applyRecommend(rec) {
  if (!rec?.digits?.length) return
  if (activeGame.value === 'ssq' || rec.mode === 'ssq') {
    const digits = rec.digits
    ssqRed.value = digits.slice(0, 6).map(Number)
    ssqBlue.value = Number(digits[6])
    ElMessage.success(t('pailie.applied'))
    return
  }
  if (activeGame.value === 'dlt' || rec.mode === 'dlt') {
    const digits = rec.digits
    dltFront.value = digits.slice(0, 5).map(Number)
    dltBack.value = digits.slice(5, 7).map(Number)
    ElMessage.success(t('pailie.applied'))
    return
  }
  if (rec.mode === 'group3' || rec.mode === 'group6') {
    pl3Mode.value = rec.mode
    selections.value = [[...rec.digits].sort((a, b) => a - b)]
  } else {
    pl3Mode.value = 'direct'
    selections.value = rec.digits.map((d) => [d])
  }
  ElMessage.success(t('pailie.applied'))
}

function applyTopRecommend() {
  const top = recommendCards.value[0]
  if (top) applyRecommend(top)
}

function addRecommendTicket(rec) {
  if (!rec?.digits?.length) return
  const mode = rec.mode || 'direct'
  const bets = rec.bets || 1
  tickets.value.unshift({
    game: activeGame.value,
    mode,
    display: rec.display,
    bets,
    amount: bets * 2,
    fromRecommend: true,
  })
  ElMessage.success(t('pailie.ticketAdded'))
}

function machinePick() {
  if (activeGame.value === 'ssq') {
    const pool = []
    while (pool.length < 6) {
      const n = 1 + Math.floor(Math.random() * 33)
      if (!pool.includes(n)) pool.push(n)
    }
    ssqRed.value = pool.sort((a, b) => a - b)
    ssqBlue.value = 1 + Math.floor(Math.random() * 16)
    return
  }
  if (activeGame.value === 'dlt') {
    const front = []
    while (front.length < 5) {
      const n = 1 + Math.floor(Math.random() * 35)
      if (!front.includes(n)) front.push(n)
    }
    const back = []
    while (back.length < 2) {
      const n = 1 + Math.floor(Math.random() * 12)
      if (!back.includes(n)) back.push(n)
    }
    dltFront.value = front.sort((a, b) => a - b)
    dltBack.value = back.sort((a, b) => a - b)
    return
  }
  if (isThreeDigitGame.value && pl3Mode.value !== 'direct') {
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
  const n = activeGame.value === 'qxc' ? 7 : activeGame.value === 'pl5' ? 5 : 3
  selections.value = Array.from({ length: n }, (_, i) => [
    Math.floor(Math.random() * alphabetSize(i)),
  ])
}

function clearPick() {
  ensureRows()
}

function addTicket() {
  if (!canAdd.value) return
  tickets.value.unshift({
    game: activeGame.value,
    mode: activeGame.value === 'ssq'
      ? 'ssq'
      : (activeGame.value === 'dlt'
        ? 'dlt'
        : (isThreeDigitGame.value ? pl3Mode.value : 'direct')),
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
  if (tk.mode === 'ssq' || tk.game === 'ssq') return t('pailie.modeSsq')
  if (tk.mode === 'dlt' || tk.game === 'dlt') return t('pailie.modeDlt')
  if (tk.mode === 'group3') return t('pailie.modeGroup3')
  if (tk.mode === 'group6') return t('pailie.modeGroup6')
  return t('pailie.modeDirect')
}

async function loadPools(opts) {
  const forceRefresh = !!(opts && typeof opts === 'object' && !('isTrusted' in opts) && opts.forceRefresh)
  poolsLoading.value = true
  try {
    const res = await getPailiePools({ limit: 30, refresh: forceRefresh || undefined })
    if (res?.code === 200) {
      const data = res.data
      poolsData.value = data
      const changed = []
      const pools = data?.pools || {}
      for (const g of poolGameIds) {
        const issue = pools[g]?.latest?.issue
        if (!issue) continue
        const prev = knownIssues.value[g]
        if (prev && prev !== issue) changed.push(g)
        knownIssues.value[g] = issue
      }
      const fromApi = data?.refreshed_games || []
      const toRefresh = [...new Set([...changed, ...fromApi])]
      if (toRefresh.length) {
        clearRecommendCacheForGames(toRefresh)
        if (toRefresh.includes(activeGame.value)) {
          await loadRecommend({ forceRefresh: true })
        }
      }
    }
  } catch (e) {
    poolsData.value = {
      pools: {},
      message: e?.message || t('pailie.loadFailed'),
      updated_at: null,
    }
  } finally {
    poolsLoading.value = false
  }
}

async function loadRecommend(opts) {
  const forceRefresh = !!(opts && typeof opts === 'object' && !('isTrusted' in opts) && opts.forceRefresh)
  const game = activeGame.value
  const win = windowSize.value
  const wantAi = useAi.value
  const seq = ++recommendSeq
  const fullKey = recommendCacheKey(game, win, wantAi)
  const freqKey = recommendCacheKey(game, win, false)

  if (forceRefresh) {
    clearRecommendCacheForGames([game])
  }

  // 回访直接用缓存，避免切 Tab 再等 AI
  if (!forceRefresh && recommendCache.has(fullKey)) {
    recommend.value = recommendCache.get(fullKey)
    aiEnhancing.value = false
    recommendLoading.value = false
    return
  }

  // 有频率缓存时先展示，再后台补 AI
  if (!forceRefresh && recommendCache.has(freqKey)) {
    recommend.value = recommendCache.get(freqKey)
  }

  const needPanelLoading = !recommend.value || recommend.value.game !== game
  if (needPanelLoading) recommendLoading.value = true

  try {
    const freqRes = await getPailieRecommend({
      game,
      window: win,
      use_ai: false,
      refresh: forceRefresh || undefined,
    })
    if (seq !== recommendSeq || activeGame.value !== game) return
    if (freqRes?.code === 200) {
      recommend.value = freqRes.data
      recommendCache.set(freqKey, freqRes.data)
      const issue = freqRes.data?.latest?.issue
      if (issue) knownIssues.value[game] = issue
    }
  } catch (e) {
    if (seq !== recommendSeq || activeGame.value !== game) return
    recommend.value = {
      reachable: false,
      message: e?.message || t('pailie.loadFailed'),
      recommendations: [],
      game,
    }
  } finally {
    if (seq === recommendSeq) recommendLoading.value = false
  }

  if (!wantAi || seq !== recommendSeq || activeGame.value !== game) return

  aiEnhancing.value = true
  try {
    const aiRes = await getPailieRecommend({
      game,
      window: win,
      use_ai: true,
      refresh: forceRefresh || undefined,
    })
    if (seq !== recommendSeq || activeGame.value !== game) return
    if (aiRes?.code === 200) {
      recommend.value = aiRes.data
      recommendCache.set(fullKey, aiRes.data)
    }
  } catch {
    // 频率结果已展示，AI 失败可忽略
  } finally {
    if (seq === recommendSeq) aiEnhancing.value = false
  }
}

async function onTabChange() {
  ensureRows()
  // 不阻塞 Tab 切换：频率先出，AI 后台增强
  loadRecommend()
}

watch(pl3Mode, () => {
  if (isThreeDigitGame.value) ensureRows()
})

async function refresh() {
  loading.value = true
  try {
    recommendCache.clear()
    const [catRes, histRes] = await Promise.all([
      getPailieCatalog(),
      getPailieHistory({ limit: 30, refresh: true }),
      loadRecommend({ forceRefresh: true }),
      loadPools({ forceRefresh: true }),
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
  // 约 2 分钟轮询奖池；检测到新期号后自动刷新对应玩法推荐
  poolTimer = setInterval(() => {
    loadPools({ forceRefresh: true })
  }, 2 * 60 * 1000)
})

onUnmounted(() => {
  if (poolTimer) clearInterval(poolTimer)
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
.ssq-zone {
  margin-bottom: 14px;
}
.ssq-zone-title {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 8px;
}
.ssq-count {
  color: #909399;
  font-weight: 500;
  margin-left: 6px;
}
.ssq-row {
  gap: 6px;
}
.ssq-btn {
  width: 34px;
  height: 34px;
  font-size: 12px;
}
.ssq-btn--blue.active {
  background: #1565c0;
  border-color: #1565c0;
}
.pool-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 12px;
}
.pool-card {
  border: 1px solid #ffe0e0;
  border-radius: 12px;
  padding: 14px;
  background: linear-gradient(160deg, #fff8f6, #fff);
  cursor: pointer;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.pool-card:hover,
.pool-card--active {
  border-color: #c62828;
  box-shadow: 0 2px 10px rgba(198, 40, 40, 0.12);
}
.pool-name {
  font-weight: 700;
  color: #c62828;
  margin-bottom: 6px;
}
.pool-amount {
  font-size: 22px;
  font-weight: 800;
  color: #1a237e;
  letter-spacing: 0.02em;
  font-variant-numeric: tabular-nums;
}
.pool-meta {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  margin-top: 8px;
  font-size: 12px;
  color: #909399;
}
.pool-sale {
  margin-top: 6px;
  font-size: 12px;
  color: #606266;
}
.pool-fixed {
  margin-top: 6px;
  font-size: 12px;
  color: #e65100;
  font-weight: 600;
}
.pool-note {
  margin: 8px 0 0;
  font-size: 11px;
  color: #909399;
  line-height: 1.4;
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
.panel h4 {
  margin: 16px 0 10px;
  font-size: 14px;
  color: #606266;
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
.rec-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 12px;
  align-items: stretch;
}
.play-card {
  border: 1px solid #f0f0f0;
  border-radius: 10px;
  padding: 12px;
  background: #fafafa;
}
.rec-card {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 210px;
  border: 1px solid #eceff1;
  border-radius: 12px;
  padding: 14px 12px;
  background: #fff;
  box-sizing: border-box;
}
.rec-card--primary {
  border-color: #ef9a9a;
  background: linear-gradient(165deg, #fff8f6 0%, #ffffff 55%);
  box-shadow: 0 2px 8px rgba(198, 40, 40, 0.08);
}
.play-name,
.rec-label {
  font-weight: 700;
  color: #c62828;
}
.rec-top {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  align-items: center;
  min-height: 24px;
}
.rec-label {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  line-height: 1.2;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.rec-conf {
  flex-shrink: 0;
  font-size: 12px;
  color: #e65100;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}
.rec-nums {
  display: flex;
  flex-wrap: nowrap;
  justify-content: flex-start;
  align-items: center;
  gap: 6px;
  margin: 14px 0 12px;
  min-height: 36px;
}
.rec-nums--qxc {
  gap: 4px;
}
.rec-nums--ssq,
.rec-nums--qxc-wrap,
.rec-nums--dlt {
  flex-direction: column;
  flex-wrap: nowrap;
  align-items: flex-start;
  gap: 8px;
  min-height: 72px;
}
.rec-nums-row {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-start;
  align-items: center;
  gap: 5px;
}
.rec-nums-row--second {
  gap: 6px;
}
.rec-plus {
  font-size: 14px;
  font-weight: 700;
  color: #909399;
  line-height: 1;
}
.rec-ball {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 700;
  color: #fff;
  background: linear-gradient(145deg, #3949ab, #1a237e);
  font-variant-numeric: tabular-nums;
  flex-shrink: 0;
}
.rec-ball--special {
  background: linear-gradient(145deg, #ef5350, #c62828);
  width: 32px;
  height: 32px;
}
.rec-ball--red {
  background: linear-gradient(145deg, #ef5350, #c62828);
}
.rec-ball--blue {
  background: linear-gradient(145deg, #42a5f5, #1565c0);
}
.rec-reason {
  margin: 0;
  font-size: 12px;
  color: #606266;
  line-height: 1.45;
  height: 2.9em;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}
.rec-actions {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  margin-top: auto;
  padding-top: 12px;
}
.rec-btn {
  width: 100%;
  margin: 0 !important;
}
@media (max-width: 1100px) {
  .rec-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}
@media (max-width: 720px) {
  .rec-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .rec-ball {
    width: 28px;
    height: 28px;
    font-size: 13px;
  }
}
@media (max-width: 420px) {
  .rec-grid {
    grid-template-columns: 1fr;
  }
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
.freq-collapse {
  margin-top: 12px;
  border: none;
}
.freq-collapse :deep(.el-collapse-item__header) {
  font-size: 14px;
  color: #606266;
  height: 40px;
  line-height: 40px;
}
.freq-pos {
  margin-bottom: 12px;
}
.freq-pos-label {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 6px;
}
.freq-bars {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 6px 10px;
}
.freq-item {
  display: grid;
  grid-template-columns: 18px 1fr 40px;
  gap: 6px;
  align-items: center;
}
.freq-digit {
  font-size: 12px;
  font-weight: 700;
  text-align: center;
}
.freq-digit.hot { color: #c62828; }
.freq-digit.cold { color: #1565c0; }
.freq-bar-track {
  height: 6px;
  border-radius: 999px;
  background: #eceff1;
  overflow: hidden;
}
.freq-bar-fill {
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(90deg, #ef9a9a, #c62828);
}
.freq-meta {
  font-size: 11px;
  color: #909399;
  text-align: right;
}
.picker-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}
.ai-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 12px;
  flex-wrap: wrap;
}
.ai-label {
  font-size: 13px;
  color: #606266;
}
.ai-tag {
  margin-right: 6px;
  vertical-align: middle;
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
.digit-btn.hot:not(.active) {
  border-color: #ef9a9a;
  color: #c62828;
}
.digit-btn.cold:not(.active) {
  border-color: #90caf9;
  color: #1565c0;
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
  .freq-bars {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
