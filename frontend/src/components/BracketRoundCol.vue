<template>
  <section class="round-column" :class="[`side-${side}`, `round-${roundIndex}`]">
    <header class="column-title">{{ label }}</header>
    <div class="round-track" :style="trackStyle">
      <div
        v-for="(pair, pi) in pairGroups"
        :key="`${stage}-${pi}`"
        class="pair-group"
        :style="{ flex: pairSpan }"
      >
        <div
          v-for="no in pair"
          :key="no"
          class="match-cell"
          @click="onClick(no)"
        >
          <BracketNode :node="resolve(no)" compact />
        </div>
        <template v-if="showConnector && pair.length === 2">
          <span class="connector-h" aria-hidden="true" />
          <span class="connector-v" aria-hidden="true" />
        </template>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import BracketNode from '@/components/BracketNode.vue'
import { chunkPairs } from '@/data/worldcupBracketTree'

const LEAF_SLOTS = 8
const SLOT_H = 52

const props = defineProps({
  side: { type: String, required: true, validator: (v) => ['left', 'right'].includes(v) },
  stage: { type: String, required: true },
  label: { type: String, required: true },
  matchNos: { type: Array, required: true },
  roundIndex: { type: Number, required: true },
  showConnector: { type: Boolean, default: true },
  resolve: { type: Function, required: true },
})

const emit = defineEmits(['select'])

const pairSpan = computed(() => 2 ** props.roundIndex)
const pairGroups = computed(() => chunkPairs(props.matchNos))

const trackStyle = computed(() => ({
  '--leaf-slots': LEAF_SLOTS,
  '--slot-h': `${SLOT_H}px`,
  minHeight: `${LEAF_SLOTS * SLOT_H}px`,
}))

function onClick(matchNo) {
  const m = props.resolve(matchNo)
  if (m?.id) emit('select', m)
}
</script>

<style scoped>
.round-column {
  flex: 0 0 auto;
  min-width: 140px;
  display: flex;
  flex-direction: column;
}

.column-title {
  text-align: center;
  font-size: 13px;
  font-weight: 700;
  color: #1a237e;
  margin-bottom: 12px;
  white-space: nowrap;
}

.round-track {
  flex: 1;
  display: flex;
  flex-direction: column;
  position: relative;
}

.pair-group {
  position: relative;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 6px;
  min-height: 0;
}

.match-cell {
  cursor: pointer;
  transition: transform 0.15s ease;
}

.match-cell:hover {
  transform: translateY(-1px);
}

/* ── Left wing: connectors toward center (right edge) ── */
.side-left .pair-group {
  padding-right: 20px;
}

.side-left .connector-h {
  position: absolute;
  right: 0;
  top: 50%;
  width: 20px;
  height: 2px;
  background: #9fa8da;
  transform: translateY(-50%);
}

.side-left .connector-v {
  position: absolute;
  right: 0;
  top: 25%;
  bottom: 25%;
  width: 2px;
  background: #9fa8da;
  transform: translateX(18px);
}

/* ── Right wing: connectors toward center (left edge) ── */
.side-right .pair-group {
  padding-left: 20px;
}

.side-right .connector-h {
  position: absolute;
  left: 0;
  top: 50%;
  width: 20px;
  height: 2px;
  background: #9fa8da;
  transform: translateY(-50%);
}

.side-right .connector-v {
  position: absolute;
  left: 0;
  top: 25%;
  bottom: 25%;
  width: 2px;
  background: #9fa8da;
  transform: translateX(-18px);
}

@media (max-width: 767px) {
  .round-column {
    min-width: 128px;
  }

  .column-title {
    font-size: 12px;
  }
}
</style>
