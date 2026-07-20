<template>
  <HkjcBacktest v-if="compStore.isRacing" />
  <ScoreBacktest v-else />
</template>

<script setup>
import { useCompetitionStore } from '@/stores/competition'
import HkjcBacktest from '@/views/racing/HkjcBacktest.vue'
import ScoreBacktest from '@/views/ScoreBacktest.vue'

const compStore = useCompetitionStore()
</script>
