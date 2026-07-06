<template>
  <div class="bracket-node" :class="{ compact }">
    <div class="match-slot" :class="{ winner: isWinner(node.team_a) }">
      <span class="team">{{ node.team_a || t('bracket.tbd') }}</span>
      <span class="score" v-if="hasMatchScore(node)">{{ node.result_a }}</span>
    </div>
    <div class="vs-divider">VS</div>
    <div class="match-slot" :class="{ winner: isWinner(node.team_b) }">
      <span class="team">{{ node.team_b || t('bracket.tbd') }}</span>
      <span class="score" v-if="hasMatchScore(node)">{{ node.result_b }}</span>
    </div>
    <div v-if="penaltyLine" class="penalty-line">{{ penaltyLine }}</div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { isMatchWinner } from '@/utils/matchScore'
import { hasMatchScore } from '@/utils/matchStatus'

const { t } = useI18n()

const props = defineProps({
  node: { type: Object, required: true },
  compact: { type: Boolean, default: false },
})

const penaltyLine = computed(() => {
  const n = props.node
  if (n.penalty_a == null || n.penalty_b == null) return ''
  return t('match.penaltyShort', { score: `${n.penalty_a} - ${n.penalty_b}` })
})

function isWinner(team) {
  return isMatchWinner(props.node, team)
}
</script>

<style scoped>
.bracket-node {
  width: 160px;
  border: 2px solid #1a237e;
  border-radius: 8px;
  overflow: hidden;
  background: #fff;
}
.match-slot {
  padding: 8px 10px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
}
.match-slot.winner {
  background: #e8f5e9;
  font-weight: 700;
}
.vs-divider {
  text-align: center;
  font-size: 11px;
  color: #999;
  background: #f5f5f5;
  padding: 2px;
}
.score {
  font-weight: 700;
  color: #1a237e;
}

.penalty-line {
  text-align: center;
  font-size: 10px;
  font-weight: 700;
  color: #5c6bc0;
  background: #eef0fb;
  padding: 2px 4px;
}

.bracket-node.compact {
  width: 136px;
}
.bracket-node.compact .match-slot {
  padding: 5px 8px;
  font-size: 12px;
}
.bracket-node.compact .team {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 88px;
}

@media (max-width: 767px) {
  .bracket-node { width: 140px; }
  .bracket-node.compact { width: 124px; }
  .match-slot { padding: 6px 8px; font-size: 12px; }
  .score { font-size: 12px; }
}
</style>
