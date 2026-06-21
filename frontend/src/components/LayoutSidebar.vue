<template>
  <el-aside
    :width="isMobile ? '240px' : '200px'"
    class="app-sidebar"
    :class="{ 'sidebar-mobile': isMobile, 'sidebar-open': sidebarOpen }"
  >
    <div v-if="isMobile" class="sidebar-close-row">
      <el-button :icon="Close" circle size="small" @click="$emit('close')" />
    </div>
    <el-menu
      :default-active="activeMenu"
      router
      background-color="#1a237e"
      text-color="#bbdefb"
      active-text-color="#fff"
      class="sidebar-menu"
    >
      <template v-if="isRacing">
        <el-menu-item :index="basePath">
          <el-icon><HomeFilled /></el-icon>
          <span>{{ t('nav.dashboard') }}</span>
        </el-menu-item>
        <el-menu-item :index="`${basePath}/meetings`">
          <el-icon><Calendar /></el-icon>
          <span>{{ t('nav.hkjcMeetings') }}</span>
        </el-menu-item>
        <el-menu-item :index="`${basePath}/purchase-advice`">
          <el-icon><ShoppingCart /></el-icon>
          <span>{{ t('nav.hkjcPurchaseAdvice') }}</span>
        </el-menu-item>
        <el-menu-item :index="`${basePath}/horses`">
          <el-icon><Flag /></el-icon>
          <span>{{ t('nav.hkjcHorses') }}</span>
        </el-menu-item>
        <el-menu-item :index="`${basePath}/backtest`">
          <el-icon><TrendCharts /></el-icon>
          <span>{{ t('nav.hkjcBacktest') }}</span>
        </el-menu-item>
      </template>
      <template v-else>
        <el-menu-item :index="basePath">
          <el-icon><HomeFilled /></el-icon>
          <span>{{ t('nav.dashboard') }}</span>
        </el-menu-item>
        <el-menu-item :index="`${basePath}/matches`">
          <el-icon><TrophyBase /></el-icon>
          <span>{{ t('nav.matches') }}</span>
        </el-menu-item>
        <el-menu-item v-if="features.sporttery !== false && authStore.canAccessSporttery" :index="`${basePath}/sporttery-plan`">
          <el-icon><ShoppingCart /></el-icon>
          <span>{{ t('nav.sportteryPlan') }}</span>
        </el-menu-item>
        <el-menu-item :index="`${basePath}/teams`">
          <el-icon><Flag /></el-icon>
          <span>{{ t('nav.teams') }}</span>
        </el-menu-item>
        <el-menu-item v-if="features.bracket" :index="`${basePath}/bracket`">
          <el-icon><Share /></el-icon>
          <span>{{ t('nav.bracket') }}</span>
        </el-menu-item>
        <el-menu-item v-if="features.tournament" :index="`${basePath}/tournament`">
          <el-icon><Medal /></el-icon>
          <span>{{ t('nav.tournament') }}</span>
        </el-menu-item>
        <el-menu-item :index="`${basePath}/predictions`">
          <el-icon><TrendCharts /></el-icon>
          <span>{{ t('nav.predictions') }}</span>
        </el-menu-item>
        <el-menu-item :index="`${basePath}/backtest`">
          <el-icon><DataAnalysis /></el-icon>
          <span>{{ t('nav.scoreBacktest') }}</span>
        </el-menu-item>
      </template>
      <el-menu-item index="/">
        <el-icon><Switch /></el-icon>
        <span>{{ t('nav.switchCompetition') }}</span>
      </el-menu-item>
      <el-menu-item v-if="authStore.isAdmin" index="/admin">
        <el-icon><Setting /></el-icon>
        <span>{{ t('nav.admin') }}</span>
      </el-menu-item>
    </el-menu>
  </el-aside>
</template>

<script setup>
import { computed, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Calendar, Close, DataAnalysis, Medal, ShoppingCart, Switch } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { useCompetitionStore } from '@/stores/competition'

const { t } = useI18n()
const authStore = useAuthStore()
const compStore = useCompetitionStore()

const props = defineProps({
  isMobile: Boolean,
  sidebarOpen: Boolean
})

const emit = defineEmits(['close'])

const route = useRoute()
const slug = computed(() => route.params.slug || compStore.slug || 'worldcup-2026')
const basePath = computed(() => `/competition/${slug.value}`)
const features = computed(() => compStore.current?.features || compStore.features || {})
const isRacing = computed(() => compStore.isRacing)

const activeMenu = computed(() => {
  const path = route.path
  if (path === '/admin') return '/admin'
  if (path.startsWith(`${basePath.value}/purchase-advice`)) return `${basePath.value}/purchase-advice`
  if (path.startsWith(`${basePath.value}/meetings`)) return `${basePath.value}/meetings`
  if (path.startsWith(`${basePath.value}/races`)) return `${basePath.value}/meetings`
  if (path.startsWith(`${basePath.value}/horses`)) return `${basePath.value}/horses`
  if (path.startsWith(`${basePath.value}/backtest`)) return `${basePath.value}/backtest`
  if (path.startsWith(`${basePath.value}/matches`)) return `${basePath.value}/matches`
  if (path.startsWith(`${basePath.value}/teams`)) return `${basePath.value}/teams`
  if (path.startsWith(`${basePath.value}/sporttery-plan`)) return `${basePath.value}/sporttery-plan`
  if (path === basePath.value) return basePath.value
  return path
})

watch(() => route.path, () => {
  if (props.isMobile && props.sidebarOpen) {
    emit('close')
  }
})
</script>

<style scoped>
.app-sidebar {
  background: #1a237e;
}
.sidebar-menu {
  border-right: none;
}
.sidebar-menu .el-menu-item.is-active {
  background: rgba(255,255,255,0.12) !important;
}

.sidebar-mobile {
  position: fixed;
  left: 0;
  top: 0;
  bottom: 0;
  z-index: 100;
  transform: translateX(-100%);
  transition: transform 0.3s ease;
  box-shadow: 2px 0 12px rgba(0, 0, 0, 0.15);
}
.sidebar-mobile.sidebar-open {
  transform: translateX(0);
}
.sidebar-close-row {
  display: flex;
  justify-content: flex-end;
  padding: 8px;
}
</style>
