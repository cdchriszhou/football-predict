<template>
  <div class="bracket-node">
    <div class="match-slot" :class="{ winner: isWinner(node.team_a) }">
      <span class="team">{{ node.team_a || t('bracket.tbd') }}</span>
      <span class="score" v-if="node.result_a !== undefined">{{ node.result_a }}</span>
    </div>
    <div class="vs-divider">VS</div>
    <div class="match-slot" :class="{ winner: isWinner(node.team_b) }">
      <span class="team">{{ node.team_b || t('bracket.tbd') }}</span>
      <span class="score" v-if="node.result_b !== undefined">{{ node.result_b }}</span>
    </div>
  </div>
</template>

<script setup>
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const props = defineProps({
  node: { type: Object, required: true }
})

function isWinner(team) {
  if (!team || props.node.result_a === undefined || props.node.result_b === undefined) return false
  if (props.node.result_a > props.node.result_b) return team === props.node.team_a
  if (props.node.result_b > props.node.result_a) return team === props.node.team_b
  return false
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

@media (max-width: 767px) {
  .bracket-node { width: 140px; }
  .match-slot { padding: 6px 8px; font-size: 12px; }
  .score { font-size: 12px; }
}
</style>
