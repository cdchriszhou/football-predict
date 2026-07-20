<template>
  <router-view :key="route.params.slug" />
</template>

<script setup>
import { watch, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useCompetitionStore } from '@/stores/competition'
import { findCompetitionMeta } from '@/data/competitions'
import { useMatchesStore } from '@/stores/matches'
import { useTeamsStore } from '@/stores/teams'
import { usePredictionsStore } from '@/stores/predictions'

const route = useRoute()
const compStore = useCompetitionStore()
const matchesStore = useMatchesStore()
const teamsStore = useTeamsStore()
const predStore = usePredictionsStore()

function resetStores() {
  matchesStore.$reset()
  teamsStore.$reset()
  predStore.$reset()
}

async function syncCompetition(slug) {
  if (!slug) return
  if (compStore.slug === slug && compStore.current?.slug === slug) {
    return
  }
  const slugChanged = Boolean(compStore.slug && compStore.slug !== slug)
  if (slugChanged) {
    resetStores()
  }
  compStore.setSlug(slug)

  // Ensure list is populated so fallback metadata is available for fetchCurrent
  if (!compStore.list.length) {
    await compStore.fetchList().catch(() => {})
  }

  try {
    await compStore.fetchCurrent(slug)
  } catch (err) {
    const meta = findCompetitionMeta(slug, compStore.list)
    if (meta) {
      compStore.current = meta
    }
    console.warn('[competition] fetchCurrent failed:', err?.message || err)
  }
}

onMounted(() => syncCompetition(route.params.slug))

watch(() => route.params.slug, (slug) => syncCompetition(slug))
</script>
