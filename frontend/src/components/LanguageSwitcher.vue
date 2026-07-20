<template>
  <el-dropdown trigger="click" @command="onSelect">
    <span class="lang-trigger" :class="{ light: theme === 'light' }">
      <span class="globe-icon">🌐</span>
      <span class="lang-label">{{ currentLabel }}</span>
      <el-icon :size="12"><ArrowDown /></el-icon>
    </span>
    <template #dropdown>
      <el-dropdown-menu>
        <el-dropdown-item
          v-for="item in locales"
          :key="item.value"
          :command="item.value"
          :class="{ 'is-active': item.value === currentLocale }"
        >
          {{ t(item.labelKey) }}
        </el-dropdown-item>
      </el-dropdown-menu>
    </template>
  </el-dropdown>
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { ArrowDown } from '@element-plus/icons-vue'
import { SUPPORTED_LOCALES, setAppLocale, getAppLocale } from '@/i18n'
import { useLocaleStore } from '@/stores/locale'

const props = defineProps({
  theme: { type: String, default: 'dark' }
})

const { t } = useI18n()
const localeStore = useLocaleStore()

const locales = SUPPORTED_LOCALES
const currentLocale = computed(() => getAppLocale())

const currentLabel = computed(() => {
  const item = locales.find(l => l.value === currentLocale.value)
  return item ? t(item.labelKey) : currentLocale.value
})

function onSelect(locale) {
  if (locale === currentLocale.value) return
  setAppLocale(locale)
  localeStore.applyElementPlusLocale(locale)
}
</script>

<style scoped>
.lang-trigger {
  display: flex;
  align-items: center;
  gap: 4px;
  color: rgba(255, 255, 255, 0.9);
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 8px;
  transition: background 0.2s;
  user-select: none;
  font-size: 13px;
}
.lang-trigger:hover {
  background: rgba(255, 255, 255, 0.12);
}
.lang-trigger.light {
  color: #1a237e;
}
.lang-trigger.light:hover {
  background: rgba(26, 35, 126, 0.08);
}
.globe-icon {
  font-size: 14px;
  line-height: 1;
}
.lang-label {
  max-width: 88px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
:deep(.el-dropdown-menu__item.is-active) {
  color: #1a237e;
  font-weight: 600;
}
</style>
