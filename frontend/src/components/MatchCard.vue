<template>
  <el-card class="match-card" shadow="hover" @click="goDetail">
    <div class="match-header">
      <div class="match-tags">
        <el-tag :type="stageTagType" size="small">{{ stageLabel(t, match.stage) }}</el-tag>
        <span v-if="seasonMeta" class="season-meta">{{ seasonMeta }}</span>
      </div>
      <el-tag
        v-if="isEffectiveMatchStatus(match, 'finished')"
        type="info"
        size="small"
        effect="dark"
        class="match-status-tag"
      >{{ t('status.finished') }}</el-tag>
      <el-tag
        v-else-if="isEffectiveMatchStatus(match, 'live')"
        type="danger"
        size="small"
        effect="dark"
        class="match-status-tag"
      >{{ t('status.live') }}</el-tag>
      <span v-else class="match-status" :class="statusClass">{{ statusLabel(t, effectiveStatus) }}</span>
    </div>

    <div class="match-body">
      <div class="team-col team-a">
        <div class="team-row">
          <TeamBadge :name="match.team_a" :size="32" />
          <span class="team-name">{{ match.team_a }}</span>
        </div>
      </div>

      <div class="score-area">
        <template v-if="hasMatchScore(match) && (isEffectiveMatchStatus(match, 'finished') || isEffectiveMatchStatus(match, 'live'))">
          <span class="score" :class="{ live: isEffectiveMatchStatus(match, 'live') }">
            {{ match.result_a }} - {{ match.result_b }}
          </span>
          <el-tag
            v-if="isEffectiveMatchStatus(match, 'live')"
            type="danger"
            size="small"
            class="live-tag"
          >LIVE</el-tag>
        </template>
        <template v-else-if="isEffectiveMatchStatus(match, 'live')">
          <span class="score live">{{ formatLiveScore(match) }}</span>
          <el-tag type="danger" size="small" class="live-tag">LIVE</el-tag>
        </template>
        <template v-else>
          <span class="vs">VS</span>
          <span class="match-time">{{ formatTime(match.match_time) }}</span>
          <div v-if="displayScores.length || upsetScore" class="predicted-scores">
            <div v-if="displayScores.length" class="likely-scores">
              <span class="likely-label">{{ t('match.likelyScores') }}</span>
              <div class="likely-badges">
                <span
                  v-for="(s, i) in displayScores"
                  :key="s"
                  class="likely-badge"
                  :class="'likely-rank-' + i"
                >{{ s }}</span>
              </div>
            </div>
            <span v-if="upsetScore" class="upset-score">
              {{ t('match.upsetScore') }} {{ upsetScore }}
            </span>
          </div>
        </template>
      </div>

      <div class="team-col team-b">
        <div class="team-row">
          <TeamBadge :name="match.team_b" :size="32" />
          <span class="team-name">{{ match.team_b }}</span>
        </div>
      </div>
    </div>

    <div class="match-footer" v-if="match.location">
      <el-icon :size="14"><Location /></el-icon>
      <span>{{ match.location }}</span>
    </div>

    <!-- market odds -->
    <div v-if="showOdds && hasMarketOdds" class="market-odds" @click.stop>
      <div class="lottery-head">
        <span class="market-badge">{{ t('match.marketBadge') }}</span>
        <span class="lottery-hint">{{ t('match.marketHint') }}</span>
      </div>
      <div class="lottery-row">
        <span class="lottery-label">{{ t('match.wdl') }}</span>
        <span class="lottery-item">{{ t('match.win') }} <b>{{ fmt(marketOdds.win_win) }}</b></span>
        <span class="lottery-item">{{ t('match.draw') }} <b>{{ fmt(marketOdds.draw) }}</b></span>
        <span class="lottery-item">{{ t('match.lose') }} <b>{{ fmt(marketOdds.win_lose) }}</b></span>
      </div>
    </div>

    <!-- sporttery odds -->
    <div v-if="showOdds && canShowSportteryOdds" class="lottery-odds" @click.stop>
      <div class="lottery-head">
        <span class="lottery-badge">{{ t('match.sportteryBadge') }}</span>
        <span class="lottery-hint">{{ t('match.sportteryHint') }}</span>
      </div>
      <div class="lottery-row" v-if="sportteryView.win_win || sportteryView.draw || sportteryView.win_lose">
        <span class="lottery-label">{{ t('match.wdl') }}</span>
        <span class="lottery-item">{{ t('match.win') }} <b>{{ fmt(sportteryView.win_win) }}</b></span>
        <span class="lottery-item">{{ t('match.draw') }} <b>{{ fmt(sportteryView.draw) }}</b></span>
        <span class="lottery-item">{{ t('match.lose') }} <b>{{ fmt(sportteryView.win_lose) }}</b></span>
      </div>
      <div class="lottery-row" v-if="sportteryView.handicap">
        <span class="lottery-label">{{ t('match.handicap', { line: sportteryView.handicap }) }}</span>
        <span class="lottery-item">{{ t('match.win') }} <b>{{ fmt(sportteryView.handicap_win) }}</b></span>
        <span class="lottery-item">{{ t('match.draw') }} <b>{{ fmt(sportteryView.handicap_draw) }}</b></span>
        <span class="lottery-item">{{ t('match.lose') }} <b>{{ fmt(sportteryView.handicap_lose) }}</b></span>
      </div>
      <div v-if="sportteryStatusHint" class="lottery-meta">{{ sportteryStatusHint }}</div>
    </div>
    <div v-else-if="showOdds && !hasMarketOdds && !canShowSportteryOdds" class="lottery-empty" @click.stop>
      <span>{{ t('match.noMarketOdds') }}</span>
    </div>
    <div v-else-if="showOdds && canShowSportteryEmpty" class="lottery-empty" @click.stop>
      <span>{{ t('match.noSporttery') }}</span>
    </div>
  </el-card>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { storeToRefs } from 'pinia'
import TeamBadge from '@/components/TeamBadge.vue'
import { usePredictionsStore } from '@/stores/predictions'
import { useOddsStore } from '@/stores/odds'
import { useCompetitionStore } from '@/stores/competition'
import { useAuthStore } from '@/stores/auth'
import { hasSportteryOdds, resolveSportteryView } from '@/utils/sporttery'
import { stageLabel, statusLabel } from '@/i18n/matchLabels'
import { effectiveMatchStatus, hasMatchScore, isEffectiveMatchStatus } from '@/utils/matchStatus'
import { parseLikelyScores, parseUpsetScore } from '@/utils/scorePrediction'

const { t } = useI18n()
const router = useRouter()
const compStore = useCompetitionStore()
const authStore = useAuthStore()

const props = defineProps({
  match: { type: Object, required: true },
  showOdds: { type: Boolean, default: false }
})

function goDetail() {
  router.push(`${compStore.basePath}/matches/${props.match.id}`)
}

const predStore = usePredictionsStore()
const oddsStore = useOddsStore()
const { cache: oddsCache } = storeToRefs(oddsStore)
const prediction = computed(() => predStore.getPredictionForMatch(props.match.id))
const lotteryOdds = computed(() => oddsCache.value[Number(props.match.id)] ?? null)

const marketOdds = computed(() => {
  const o = lotteryOdds.value
  if (!o) return null
  const e = o.european
  if (e?.win_win) return e
  if (o.win_win && (o.source || '').includes('the-odds-api')) {
    return { win_win: o.win_win, draw: o.draw, win_lose: o.win_lose }
  }
  return null
})

const hasMarketOdds = computed(() => !!(marketOdds.value?.win_win))

const sportteryView = computed(() => resolveSportteryView(lotteryOdds.value))

const sportteryStatusHint = computed(() => {
  const v = sportteryView.value
  if (!v) return ''
  if (v.on_sale === false) return t('match.sportteryPreMatch')
  if (v.update_time) return t('match.sportteryUpdatedAt', { time: formatTime(v.update_time) })
  return ''
})

const canShowSportteryOdds = computed(() => authStore.canAccessSporttery && hasSportteryOdds(lotteryOdds.value))
const canShowSportteryEmpty = computed(
  () => authStore.canAccessSporttery && !hasSportteryOdds(lotteryOdds.value) && !hasMarketOdds.value
)

function fmt(v) {
  if (v == null || v === '') return '-'
  const n = Number(v)
  return Number.isFinite(n) ? n.toFixed(2) : v
}

const effectiveStatus = computed(() => effectiveMatchStatus(props.match))

const displayScores = computed(() => parseLikelyScores(prediction.value))
const upsetScore = computed(() => parseUpsetScore(prediction.value))

const stageTagType = computed(() => {
  const map = { '小组赛': 'info', '1/8决赛': 'warning', '1/4决赛': 'warning', '半决赛': 'danger', '决赛': 'danger', '季军赛': '' }
  return map[props.match.stage] || 'info'
})

const seasonMeta = computed(() => {
  const parts = []
  if (props.match.season) parts.push(`${props.match.season}${t('match.seasonSuffix')}`)
  if (props.match.matchday) parts.push(t('match.matchdayRound', { n: props.match.matchday }))
  return parts.join(' · ')
})

const statusClass = computed(() => ({
  'status-upcoming': effectiveStatus.value === 'upcoming',
  'status-live': effectiveStatus.value === 'live',
  'status-finished': effectiveStatus.value === 'finished',
}))

function formatTime(tVal) {
  if (!tVal) return ''
  const d = new Date(tVal)
  return `${(d.getMonth()+1).toString().padStart(2,'0')}/${d.getDate().toString().padStart(2,'0')} ${d.getHours().toString().padStart(2,'0')}:${d.getMinutes().toString().padStart(2,'0')}`
}

function formatLiveScore(m) {
  if (hasMatchScore(m)) return `${m.result_a} - ${m.result_b}`
  return '0 - 0'
}
</script>

<style scoped>
.match-card {
  cursor: pointer;
  border-radius: 12px;
}
.match-card:hover { border-color: #1a237e; }
.match-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.match-tags { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.season-meta { font-size: 11px; color: #888; }
.match-body { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.team-col { display: flex; flex-direction: column; align-items: center; flex: 1; min-width: 0; }
.team-row { display: flex; align-items: center; justify-content: center; gap: 8px; width: 100%; }
.team-name { font-size: 15px; font-weight: 600; text-align: left; line-height: 1.3; word-break: break-word; }
.score-area { flex-shrink: 0; text-align: center; padding: 0 8px; }
.score { font-size: 24px; font-weight: 800; }
.score.live { color: #f44336; animation: pulse 1s infinite; }
.vs { font-size: 18px; font-weight: 700; color: #999; }
.match-time { font-size: 12px; color: #999; display: block; }
.predicted-scores { margin-top: 4px; }
.likely-scores { margin-bottom: 2px; }
.likely-label {
  display: block;
  font-size: 11px;
  color: #888;
  margin-bottom: 3px;
}
.likely-badges {
  display: flex;
  gap: 4px;
  justify-content: center;
  flex-wrap: wrap;
}
.likely-badge {
  display: inline-block;
  padding: 1px 8px;
  border-radius: 10px;
  font-size: 12px;
  font-weight: 700;
  color: #fff;
  line-height: 1.5;
}
.likely-rank-0 { background: #e65100; font-size: 13px; }
.likely-rank-1 { background: #78909c; font-size: 12px; }
.upset-score {
  font-size: 12px;
  color: #c62828;
  font-weight: 700;
  display: block;
  margin-top: 2px;
}
.live-tag { margin-top: 4px; }
.match-footer { margin-top: 10px; font-size: 12px; color: #999; display: flex; align-items: center; gap: 4px; }

.lottery-odds {
  margin-top: 10px;
  padding: 8px 10px;
  background: linear-gradient(135deg, #fff8e1 0%, #fff3e0 100%);
  border: 1px solid #ffe0b2;
  border-radius: 8px;
}
.market-odds {
  margin-top: 10px;
  padding: 8px 10px;
  background: linear-gradient(135deg, #e8eaf6 0%, #e3f2fd 100%);
  border: 1px solid #c5cae9;
  border-radius: 8px;
}
.market-badge {
  background: #1a237e;
  color: #fff;
  font-size: 11px;
  font-weight: 700;
  padding: 1px 6px;
  border-radius: 4px;
  line-height: 1.6;
}
.lottery-head { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; }
.lottery-badge {
  background: #e65100;
  color: #fff;
  font-size: 11px;
  font-weight: 700;
  padding: 1px 6px;
  border-radius: 4px;
  line-height: 1.6;
}
.lottery-hint { font-size: 11px; color: #bf360c; }
.lottery-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 12px;
  color: #666;
  margin-top: 4px;
}
.lottery-label {
  min-width: 42px;
  font-weight: 600;
  color: #e65100;
  flex-shrink: 0;
}
.lottery-item b { color: #1a237e; font-weight: 700; margin-left: 2px; }
.lottery-meta {
  margin-top: 4px;
  font-size: 11px;
  color: #9e9e9e;
}
.lottery-empty {
  margin-top: 8px;
  font-size: 11px;
  color: #bbb;
  text-align: center;
  padding: 4px 0;
}
.match-status-tag { flex-shrink: 0; }
.status-upcoming { color: #409eff; }
.status-live { color: #f44336; font-weight: 600; }
.status-finished { color: #999; }

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

@media (max-width: 767px) {
  .match-card :deep(.el-card__body) { padding: 12px; }
  .team-name { font-size: 13px; }
  .score { font-size: 20px; }
  .vs { font-size: 16px; }
  .match-header { margin-bottom: 8px; }
  .match-body { gap: 4px; }
}
</style>
