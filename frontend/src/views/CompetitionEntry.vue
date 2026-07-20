<template>
  <PailieHome v-if="isDigital" />
  <Dashboard v-else />
</template>

<script setup>
import { computed } from 'vue'
import { useCompetitionStore } from '@/stores/competition'
import Dashboard from './Dashboard.vue'
import PailieHome from './PailieHome.vue'

const compStore = useCompetitionStore()
const isDigital = computed(() =>
  compStore.current?.type === 'digital'
  || compStore.slug === 'pailie'
  || compStore.current?.features?.digital_lottery === true,
)
</script>
