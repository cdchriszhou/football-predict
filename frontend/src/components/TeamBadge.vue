<template>
  <span class="team-badge-wrap" :class="{ inline }">
    <img
      v-if="src && !failed"
      :src="src"
      :alt="name"
      :class="['team-badge', isCrest ? 'team-badge--crest' : 'team-badge--flag']"
      :style="imgStyle"
      @error="failed = true"
    />
    <span v-else class="team-badge-fallback" :style="fallbackStyle">{{ fallback }}</span>
  </span>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useCompetitionStore } from '@/stores/competition'
import { useTeamsStore } from '@/stores/teams'
import { resolveTeamAvatarUrl, isTeamCrest, teamAvatarFallback } from '@/utils/teamAvatar'

const props = defineProps({
  name: { type: String, required: true },
  flagUrl: { type: String, default: '' },
  size: { type: Number, default: 28 },
  inline: { type: Boolean, default: true },
})

const compStore = useCompetitionStore()
const teamsStore = useTeamsStore()
const failed = ref(false)

watch(() => [props.name, props.flagUrl], () => { failed.value = false })

const teamRecord = computed(() => teamsStore.teamsByName?.[props.name])

const avatarOpts = computed(() => ({
  name: props.name,
  flag_url: props.flagUrl || teamRecord.value?.flag_url,
  isWorldCup: compStore.isWorldCup,
}))

const src = computed(() => resolveTeamAvatarUrl(avatarOpts.value))
const isCrest = computed(() => isTeamCrest(avatarOpts.value))
const fallback = computed(() => teamAvatarFallback(props.name, compStore.isWorldCup))

const imgStyle = computed(() => {
  if (isCrest.value) {
    return { width: `${props.size}px`, height: `${props.size}px` }
  }
  const h = Math.round(props.size * 0.75)
  return { width: `${Math.round(props.size * 1.15)}px`, height: `${h}px` }
})

const fallbackStyle = computed(() => ({
  fontSize: `${Math.round(props.size * 0.85)}px`,
  lineHeight: 1,
}))
</script>

<style scoped>
.team-badge-wrap {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.team-badge-wrap.inline {
  vertical-align: middle;
}
.team-badge {
  display: block;
  object-fit: contain;
}
.team-badge--flag {
  border-radius: 3px;
  object-fit: cover;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.08);
}
.team-badge--crest {
  border-radius: 4px;
}
.team-badge-fallback {
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
</style>
