<template>
  <el-config-provider :locale="elementPlusLocale">
    <router-view v-if="isPortalPage" />
    <el-container v-else class="app-container">
      <div v-if="isMobile && sidebarOpen" class="sidebar-backdrop" @click="sidebarOpen = false" />
      <LayoutSidebar
        :is-mobile="isMobile"
        :sidebar-open="sidebarOpen"
        @close="sidebarOpen = false"
      />
      <el-container>
        <el-header class="app-header">
          <LayoutHeader
            :is-mobile="isMobile"
            @toggle-sidebar="toggleSidebar"
          />
        </el-header>
        <el-main class="app-main">
          <router-view />
        </el-main>
      </el-container>
    </el-container>
  </el-config-provider>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, provide } from 'vue'
import { useRoute } from 'vue-router'
import LayoutHeader from './components/LayoutHeader.vue'
import LayoutSidebar from './components/LayoutSidebar.vue'
import { elementPlusLocale } from '@/i18n/element-plus-state'

const route = useRoute()
const isPortalPage = computed(() =>
  route.meta.layout === 'portal' ||
  ['/login', '/register', '/forgot-password', '/reset-password'].includes(route.path)
)
const isLoginPage = computed(() =>
  ['/login', '/register', '/forgot-password', '/reset-password'].includes(route.path)
)

const isMobile = ref(false)
const sidebarOpen = ref(false)

function handleResize() {
  isMobile.value = window.innerWidth < 768
  if (!isMobile.value) sidebarOpen.value = false
}

function toggleSidebar() {
  sidebarOpen.value = !sidebarOpen.value
}

provide('isMobile', isMobile)
provide('toggleSidebar', toggleSidebar)

onMounted(() => {
  handleResize()
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
})
</script>

<style scoped>
.app-container {
  height: 100vh;
}
.app-header {
  background: linear-gradient(135deg, #1a237e, #0d47a1);
  padding: 0 20px;
  display: flex;
  align-items: center;
}
.app-main {
  background: #f5f7fa;
  min-height: calc(100vh - 60px);
  padding: 20px;
}

.sidebar-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  z-index: 90;
}

@media (max-width: 767px) {
  .app-header {
    padding: 0 12px;
  }
  .app-main {
    padding: 12px;
    min-height: calc(100vh - 48px);
  }
}
</style>

<style>
html[dir='rtl'] .header-left,
html[dir='rtl'] .header-right,
html[dir='rtl'] .header-wrapper {
  flex-direction: row-reverse;
}
html[dir='rtl'] .sidebar-menu .el-menu-item [class^='el-icon'] {
  margin-left: 8px;
  margin-right: 0;
}
html[dir='rtl'] .algo-list {
  padding-left: 0;
  padding-right: 20px;
}
</style>
