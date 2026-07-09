<template>
  <div class="bracket-fifa-wrap">
    <p v-if="!loading && hasAnyMatch" class="bracket-hint">{{ t('bracket.pyramidHint') }}</p>
    <div class="bracket-scroll">
      <div v-if="loading" class="loading-box" v-loading="true" />
      <div v-else-if="!hasAnyMatch" class="empty-box">
        <el-empty :description="t('bracket.empty')" />
      </div>
      <div v-else class="fifa-bracket">
        <!-- 左半区：由外向内 -->
        <div class="wing wing-left">
          <BracketRoundCol
            v-for="(round, ri) in leftRounds"
            :key="`l-${round.stage}`"
            :side="'left'"
            :stage="round.stage"
            :label="round.label"
            :match-nos="round.matchNos"
            :round-index="ri"
            :show-connector="ri < leftRounds.length - 1"
            :resolve="resolve"
            @select="goDetail"
          />
        </div>

        <!-- 中心：决赛 + 季军赛 -->
        <div class="center-column">
          <div class="center-spacer" aria-hidden="true" />
          <section class="center-block center-final">
            <header class="column-title">{{ stageLabel(t, '决赛') }}</header>
            <div class="center-match" @click="goDetail(finalMatch)">
              <BracketNode :node="finalMatch" compact />
            </div>
          </section>
          <section class="center-block center-third">
            <header class="column-title column-title-sub">{{ t('bracket.thirdPlace') }}</header>
            <div class="center-match" @click="goDetail(thirdMatch)">
              <BracketNode :node="thirdMatch" compact />
            </div>
          </section>
        </div>

        <!-- 右半区：由内向外（列顺序仍左→右，连线向左汇） -->
        <div class="wing wing-right">
          <BracketRoundCol
            v-for="(round, ri) in rightRounds"
            :key="`r-${round.stage}`"
            :side="'right'"
            :stage="round.stage"
            :label="round.label"
            :match-nos="round.matchNos"
            :round-index="rightRounds.length - 1 - ri"
            :show-connector="ri > 0"
            :resolve="resolve"
            @select="goDetail"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import BracketNode from '@/components/BracketNode.vue'
import BracketRoundCol from '@/components/BracketRoundCol.vue'
import { getKnockoutBracket } from '@/api/matches'
import { KNOCKOUT_STAGES, stageLabel } from '@/i18n/matchLabels'
import { useCompetitionStore } from '@/stores/competition'
import {
  BRACKET_LAYOUT,
  WING_ROUND_STAGES,
  buildMatchIndex,
  resolveBracketMatch,
} from '@/data/worldcupBracketTree'

const { t } = useI18n()
const router = useRouter()
const compStore = useCompetitionStore()

const loading = ref(false)
const byStage = ref({})
const matchIndex = ref({ byTeams: new Map(), byStageSlot: {}, flat: [] })

function buildWingRounds(side) {
  return WING_ROUND_STAGES.map((stage) => ({
    stage,
    label: stageLabel(t, stage),
    matchNos: BRACKET_LAYOUT[side][stage],
  }))
}

const leftRounds = computed(() => buildWingRounds('left'))
const rightRounds = computed(() => {
  const rounds = buildWingRounds('right')
  return [...rounds].reverse()
})

const finalMatch = computed(() =>
  resolveBracketMatch(BRACKET_LAYOUT.center.final, matchIndex.value),
)
const thirdMatch = computed(() =>
  resolveBracketMatch(BRACKET_LAYOUT.center.third, matchIndex.value),
)

const hasAnyMatch = computed(() =>
  compStore.isWorldCup
  || KNOCKOUT_STAGES.some((s) => (byStage.value[s] || []).length > 0),
)

function resolve(matchNo) {
  return resolveBracketMatch(matchNo, matchIndex.value)
}

async function loadAll() {
  loading.value = true
  try {
    const res = await getKnockoutBracket()
    if (res?.data && typeof res.data === 'object') {
      const { slots, ...stages } = res.data
      byStage.value = stages
      matchIndex.value = buildMatchIndex(stages, slots)
    } else {
      byStage.value = {}
      matchIndex.value = buildMatchIndex({})
    }
  } catch (err) {
    console.warn('[bracket] load failed:', err?.message || err)
    byStage.value = {}
    matchIndex.value = buildMatchIndex({})
  } finally {
    loading.value = false
  }
}

function goDetail(match) {
  if (!match?.id) return
  router.push(`${compStore.basePath}/matches/${match.id}`)
}

onMounted(loadAll)
watch(() => compStore.slug, () => {
  if (compStore.slug) loadAll()
})
</script>

<style scoped>
.bracket-fifa-wrap {
  width: 100%;
}

.bracket-hint {
  margin: 0 0 12px;
  font-size: 13px;
  color: #888;
  text-align: center;
}

.bracket-scroll {
  overflow-x: auto;
  overflow-y: hidden;
  padding: 8px 4px 16px;
  -webkit-overflow-scrolling: touch;
}

.fifa-bracket {
  display: flex;
  align-items: stretch;
  justify-content: center;
  gap: 0;
  min-width: min-content;
  padding: 8px 12px 24px;
}

.wing {
  display: flex;
  align-items: stretch;
  flex: 0 0 auto;
}

.wing-left {
  gap: 24px;
}

.wing-right {
  gap: 24px;
}

.center-column {
  flex: 0 0 auto;
  display: flex;
  flex-direction: column;
  align-items: center;
  min-width: 156px;
  padding: 0 20px;
  min-height: calc(var(--leaf-slots, 8) * 52px + 120px);
}

.center-spacer {
  flex: 3 1 0;
  min-height: 0;
}

.center-block {
  flex: 0 0 auto;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.center-final {
  margin-bottom: 20px;
}

.center-third {
  margin-top: auto;
  padding-bottom: 4px;
}

.column-title {
  text-align: center;
  font-size: 13px;
  font-weight: 700;
  color: #1a237e;
  margin-bottom: 10px;
  white-space: nowrap;
}

.column-title-sub {
  font-size: 12px;
  color: #5c6bc0;
}

.center-match {
  cursor: pointer;
  transition: transform 0.15s ease;
}

.center-match:hover {
  transform: translateY(-1px);
}

.loading-box,
.empty-box {
  min-height: 200px;
  display: flex;
  align-items: center;
  justify-content: center;
}

@media (max-width: 767px) {
  .wing-left,
  .wing-right {
    gap: 16px;
  }

  .center-column {
    padding: 0 12px;
    min-width: 140px;
  }

  .column-title {
    font-size: 12px;
  }
}
</style>
