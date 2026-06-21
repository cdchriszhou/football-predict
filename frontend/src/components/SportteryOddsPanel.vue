<template>
  <div class="sporttery-panel">
    <div v-if="!hasOdds" class="empty-odds">
      <el-empty :description="t('sporttery.notOnSale')" :image-size="60" />
    </div>
    <template v-else>
      <div class="sporttery-banner">
        <span class="sporttery-badge">{{ t('sporttery.badge') }}</span>
        <span class="sporttery-title">{{ t('sporttery.title') }}</span>
        <span class="sporttery-tag official">{{ t('sporttery.official') }}</span>
        <span v-if="sportteryMeta?.match_num" class="sporttery-num">
          {{ t('sporttery.matchNum', { n: sportteryMeta.match_num }) }}
        </span>
      </div>

      <div class="odds-section">
        <h4 class="section-title">{{ t('sporttery.wdlHandicap') }}</h4>
        <el-table :data="oddsData" size="small" border stripe>
          <el-table-column prop="type" :label="t('sporttery.playType')" width="130" />
          <el-table-column prop="a" :label="t('sporttery.winCol')" align="center" />
          <el-table-column prop="draw" :label="t('sporttery.drawCol')" align="center" />
          <el-table-column prop="b" :label="t('sporttery.loseCol')" align="center" />
        </el-table>
      </div>

      <div class="odds-section" v-if="scoreList.length">
        <h4 class="section-title">{{ t('sporttery.scoreSection') }}</h4>
        <div class="score-grid">
          <div class="score-col">
            <div class="score-col-title">{{ crsGrid.homeLabel }} {{ t('sporttery.winCol') }}</div>
            <div class="score-row" v-for="item in crsGrid.homeWin" :key="item.score">
              <span class="score-label">{{ item.score }}</span>
              <span class="score-odds">{{ item.odds }}</span>
            </div>
          </div>
          <div class="score-col">
            <div class="score-col-title">{{ t('sporttery.drawCol') }}</div>
            <div class="score-row" v-for="item in crsGrid.draw" :key="item.score">
              <span class="score-label">{{ item.score }}</span>
              <span class="score-odds">{{ item.odds }}</span>
            </div>
          </div>
          <div class="score-col">
            <div class="score-col-title">{{ crsGrid.awayLabel }} {{ t('sporttery.winCol') }}</div>
            <div class="score-row" v-for="item in crsGrid.awayWin" :key="item.score">
              <span class="score-label">{{ item.score }}</span>
              <span class="score-odds">{{ item.odds }}</span>
            </div>
          </div>
        </div>
        <div v-if="crsGrid.others.length" class="score-other-row">
          <div class="score-row" v-for="item in crsGrid.others" :key="item.score">
            <span class="score-label">{{ item.score }}</span>
            <span class="score-odds">{{ item.odds }}</span>
          </div>
        </div>
      </div>

      <div class="odds-section" v-if="halfFullList.length">
        <h4 class="section-title">{{ t('sporttery.halfFull') }}</h4>
        <div class="half-full-grid">
          <div class="hf-row" v-for="item in halfFullList" :key="item.label">
            <span class="hf-label">{{ item.label }}</span>
            <span class="hf-odds">{{ item.odds }}</span>
          </div>
        </div>
      </div>

      <div class="odds-meta">
        <span v-if="sportteryView?.on_sale === false" class="pre-match-hint">{{ t('match.sportteryPreMatch') }}</span>
        <span v-if="sportteryView?.update_time">{{ t('common.updateTime') }}: {{ formatTime(sportteryView.update_time) }}</span>
        <span>{{ t('common.source') }}: {{ formatSource(sportteryView.source) }}</span>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { hasSportteryOdds, isSportteryOfficial, resolveSportteryView } from '@/utils/sporttery'
import { buildCrsGrid } from '@/utils/sportteryCrs'

const props = defineProps({
  odds: { type: Object, default: null },
  teamA: { type: String, default: '' },
  teamB: { type: String, default: '' }
})

const { t, locale } = useI18n()

const sportteryView = computed(() => resolveSportteryView(props.odds))

const hasOdds = computed(() => hasSportteryOdds(props.odds))

const sportteryMeta = computed(() => sportteryView.value?.sporttery_meta || props.odds?.sporttery_meta || null)

const homeName = computed(() => props.teamA || t('team.homeTeam'))
const awayName = computed(() => props.teamB || t('team.awayTeam'))

const oddsData = computed(() => {
  const o = sportteryView.value
  if (!o) return []
  const rows = [
    { type: t('match.wdl'), a: o.win_win, draw: o.draw, b: o.win_lose }
  ]
  if (o.handicap) {
    rows.push({
      type: t('match.handicapRow', { line: o.handicap }),
      a: o.handicap_win,
      draw: o.handicap_draw,
      b: o.handicap_lose
    })
  }
  if (o.over_under) {
    rows.push({
      type: t('sporttery.overUnderRow', { line: o.over_under }),
      a: `${t('sporttery.over')} ${o.over_odds ?? '-'}`,
      draw: '-',
      b: `${t('sporttery.under')} ${o.under_odds ?? '-'}`
    })
  }
  return rows
})

const crsGrid = computed(() =>
  buildCrsGrid(sportteryView.value?.score_odds, homeName.value, awayName.value),
)

const scoreList = computed(() => {
  const g = crsGrid.value
  return [...g.homeWin, ...g.draw, ...g.awayWin, ...g.others]
})

const halfFullList = computed(() => {
  const hf = sportteryView.value?.half_full_odds
  if (!hf) return []
  const order = ['胜胜', '胜平', '胜负', '平胜', '平平', '平负', '负胜', '负平', '负负']
  return order.filter(k => hf[k]).map(k => ({
    label: t(`sporttery.halfFullLabels.${k}`, {
      home: homeName.value,
      away: awayName.value
    }),
    odds: hf[k]
  }))
})

function formatTime(time) {
  if (!time) return ''
  return new Date(time).toLocaleString(locale.value)
}

function formatSource(src) {
  if (!src) return ''
  if (isSportteryOfficial(src)) return t('sporttery.officialSource')
  return ''
}
</script>

<style scoped>
.sporttery-panel { padding: 4px 0; }
.sporttery-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  padding: 10px 12px;
  margin-bottom: 16px;
  background: linear-gradient(135deg, #fff8e1 0%, #fff3e0 100%);
  border: 1px solid #ffe0b2;
  border-radius: 8px;
}
.sporttery-badge {
  background: #e65100;
  color: #fff;
  font-size: 12px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 4px;
}
.sporttery-title { font-size: 15px; font-weight: 700; color: #bf360c; }
.sporttery-tag {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  font-weight: 600;
}
.sporttery-tag.official { background: #e8f5e9; color: #2e7d32; }
.sporttery-tag.reference { background: #fff3e0; color: #e65100; }
.sporttery-num { font-size: 12px; color: #999; margin-left: auto; }

.odds-section { margin-bottom: 20px; }
.section-title { font-size: 14px; font-weight: 700; margin: 0 0 10px; color: #333; }

.score-grid { display: flex; gap: 12px; }
.score-col { flex: 1; background: #fafafa; border-radius: 8px; padding: 8px 12px; }
.score-col-title { font-size: 13px; font-weight: 700; color: #e65100; text-align: center; padding-bottom: 6px; border-bottom: 1px solid #eee; margin-bottom: 6px; }
.score-row { display: flex; justify-content: space-between; padding: 4px 8px; font-size: 13px; }
.score-row:nth-child(odd) { background: #f0f0f0; }
.score-label { color: #555; }
.score-odds { color: #e65100; font-weight: 600; }
.score-other-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
  padding: 8px 12px;
  background: #fafafa;
  border-radius: 8px;
}
.score-other-row .score-row {
  flex: 1 1 120px;
  background: #f0f0f0;
  border-radius: 4px;
}

.half-full-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 4px; }
.hf-row { display: flex; justify-content: space-between; align-items: center; padding: 6px 12px; background: #fafafa; border-radius: 4px; font-size: 13px; }
.hf-label { color: #555; }
.hf-odds { color: #e65100; font-weight: 600; }

.odds-meta { display: flex; gap: 16px; font-size: 12px; color: #999; margin-top: 10px; flex-wrap: wrap; }

@media (max-width: 767px) {
  .score-grid { flex-direction: column; gap: 8px; }
  .half-full-grid { grid-template-columns: repeat(2, 1fr); }
}
</style>
