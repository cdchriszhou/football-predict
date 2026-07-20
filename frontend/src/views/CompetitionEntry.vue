<template>
  <Dashboard v-if="!isRacing" />
  <HkjcDashboard v-else />
</template>

<script setup>
import { computed } from 'vue'
import { useCompetitionStore } from '@/stores/competition'
import Dashboard from './Dashboard.vue'
import HkjcDashboard from './racing/HkjcDashboard.vue'

const compStore = useCompetitionStore()
const isRacing = computed(() => compStore.isRacing)
</script>
