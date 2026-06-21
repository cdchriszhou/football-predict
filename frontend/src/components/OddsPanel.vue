<template>
  <div class="odds-panel">
    <div v-if="!hasMarketOdds" class="empty-odds">
      <el-empty :description="t('match.noMarketData')" :image-size="60" />
    </div>
    <template v-else>
      <div class="odds-section" v-if="europeanRows.length">
        <h4 class="section-title">{{ t('match.european') }}</h4>
        <el-table :data="europeanRows" size="small" border stripe>
          <el-table-column prop="type" :label="t('match.wdl')" width="130" />
          <el-table-column prop="a" :label="t('match.win')" align="center" />
          <el-table-column prop="draw" :label="t('match.draw')" align="center" />
          <el-table-column prop="b" :label="t('match.lose')" align="center" />
        </el-table>
      </div>

      <div class="odds-section" v-if="macauRows.length">
        <h4 class="section-title">
          {{ t('match.macau') }}
          <span v-if="macauIsDerived" class="derived-tag">{{ t('match.macauDerived') }}</span>
        </h4>
        <el-table :data="macauRows" size="small" border stripe>
          <el-table-column prop="type" :label="t('match.wdl')" width="130" />
          <el-table-column prop="a" :label="t('match.win')" align="center" />
          <el-table-column prop="draw" :label="t('match.draw')" align="center" />
          <el-table-column prop="b" :label="t('match.lose')" align="center" />
        </el-table>
      </div>

      <div class="odds-hint">{{ t('match.marketHintPanel') }}</div>

      <div class="odds-meta" v-if="odds?.update_time">
        <span>{{ t('common.updateTime') }}: {{ formatTime(odds.update_time) }}</span>
        <span v-if="marketSource">{{ t('common.source') }}: {{ marketSource }}</span>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const props = defineProps({
  odds: { type: Object, default: null }
})

const european = computed(() => {
  const e = props.odds?.european
  if (e?.win_win) return e
  const o = props.odds
  if (!o?.win_win) return null
  return {
    win_win: o.win_win,
    draw: o.draw,
    win_lose: o.win_lose,
    over_under: o.over_under
  }
})

const macau = computed(() => {
  const m = props.odds?.macau
  if (m?.win_win) return m
  const o = props.odds
  if (!o?.win_win || !o?.handicap) return null
  return {
    win_win: o.win_win,
    draw: o.draw,
    win_lose: o.win_lose,
    handicap: o.handicap,
    handicap_win: o.handicap_win,
    handicap_draw: o.handicap_draw,
    handicap_lose: o.handicap_lose
  }
})

const hasMarketOdds = computed(() => {
  return !!(european.value?.win_win || macau.value?.win_win)
})

const europeanRows = computed(() => {
  const e = european.value
  if (!e?.win_win) return []
  const rows = [
    { type: t('match.wdl'), a: e.win_win, draw: e.draw, b: e.win_lose }
  ]
  const ou = e.over_under || props.odds?.over_under
  if (ou) {
    rows.push({
      type: t('match.overUnder', { line: ou }),
      a: `${t('match.big')}(${props.odds?.over_odds ?? '-'})`,
      draw: '-',
      b: `${t('match.small')}(${props.odds?.under_odds ?? '-'})`
    })
  }
  return rows
})

const macauIsDerived = computed(() => {
  const src = macau.value?.source || ''
  return src.includes('derived')
})

const macauRows = computed(() => {
  const m = macau.value
  if (!m?.win_win) return []
  const rows = [
    { type: t('match.wdl'), a: m.win_win, draw: m.draw, b: m.win_lose }
  ]
  if (m.handicap) {
    rows.push({
      type: t('match.handicapRow', { line: m.handicap }),
      a: m.handicap_win,
      draw: m.handicap_draw,
      b: m.handicap_lose
    })
  }
  return rows
})

const marketSource = computed(() => {
  const sources = []
  if (props.odds?.european?.source) sources.push(props.odds.european.source)
  if (props.odds?.macau?.source) sources.push(props.odds.macau.source)
  if (sources.length) return sources.join(' + ')
  const src = props.odds?.source || ''
  if (src.includes('the-odds-api')) return 'the-odds-api'
  return src || ''
})

function formatTime(tVal) {
  if (!tVal) return ''
  return new Date(tVal).toLocaleString()
}
</script>

<style scoped>
.odds-panel { padding: 4px 0; }
.odds-section { margin-bottom: 20px; }
.section-title { font-size: 14px; font-weight: 700; margin: 0 0 10px; color: #333; }
.derived-tag { font-size: 11px; font-weight: 500; color: #e6a23c; margin-left: 6px; }
.odds-hint {
  font-size: 12px;
  color: #999;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 6px;
  line-height: 1.5;
}
.odds-meta { display: flex; gap: 16px; font-size: 12px; color: #999; margin-top: 10px; flex-wrap: wrap; }

@media (max-width: 767px) {
  .odds-section { margin-bottom: 12px; }
  .section-title { font-size: 13px; }
}
</style>
