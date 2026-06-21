<template>
  <div class="header-wrapper">
    <div class="header-left">
      <el-button
        v-if="isMobile"
        :icon="Menu"
        circle
        size="small"
        class="hamburger-btn"
        @click="$emit('toggleSidebar')"
      />
      <WorldCupLogo :size="32" />
      <h1 class="header-title">{{ headerTitle }}</h1>
      <div class="timezones" v-if="!isMobile">
        <span class="tz-item"><span class="tz-flag">🇨🇳</span><span class="tz-label">{{ t('competition.timeBeijing') }}</span>{{ beijingTime }}</span>
        <span class="tz-divider">|</span>
        <span class="tz-item"><span class="tz-flag">{{ localFlag }}</span><span class="tz-label">{{ localTimeLabel }}</span>{{ localTime }}</span>
      </div>
    </div>
    <div class="header-right">
      <el-tag v-if="!isMobile && showCountdownTag" type="warning" effect="dark" round>
        {{ countdownLabel }}
      </el-tag>

      <LanguageSwitcher />

      <el-dropdown trigger="click" @command="handleCommand">
        <span class="user-info">
          <el-icon :size="18"><UserFilled /></el-icon>
          <span class="username">{{ authStore.username || t('header.user') }}</span>
          <el-icon :size="14"><ArrowDown /></el-icon>
        </span>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="changePassword">
              <el-icon><Key /></el-icon>
              {{ t('header.changePassword') }}
            </el-dropdown-item>
            <el-dropdown-item command="logout" divided>
              <el-icon><SwitchButton /></el-icon>
              {{ t('header.logout') }}
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>

    <el-dialog
      v-model="dialogVisible"
      :title="t('header.dialogTitle')"
      width="400px"
      :close-on-click-modal="false"
      center
    >
      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-width="0"
        @submit.prevent="handleChangePassword"
      >
        <el-form-item prop="oldPassword">
          <el-input
            v-model="form.oldPassword"
            type="password"
            :placeholder="t('header.oldPassword')"
            :prefix-icon="Lock"
            size="large"
            show-password
          />
        </el-form-item>
        <el-form-item prop="newPassword">
          <el-input
            v-model="form.newPassword"
            type="password"
            :placeholder="t('header.newPassword')"
            :prefix-icon="Lock"
            size="large"
            show-password
          />
        </el-form-item>
        <el-form-item prop="confirmPassword">
          <el-input
            v-model="form.confirmPassword"
            type="password"
            :placeholder="t('header.confirmPassword')"
            :prefix-icon="Lock"
            size="large"
            show-password
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">{{ t('header.cancel') }}</el-button>
        <el-button type="primary" :loading="loading" @click="handleChangePassword">
          {{ t('header.confirmChange') }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { SwitchButton, Menu, UserFilled, ArrowDown, Lock, Key } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { useCompetitionStore } from '@/stores/competition'
import { changePassword } from '@/api/auth'
import WorldCupLogo from '@/components/WorldCupLogo.vue'
import LanguageSwitcher from '@/components/LanguageSwitcher.vue'
import {
  BEIJING_TZ, formatClock, resolveCompetitionTimezone, TIMEZONE_FLAGS, resolveActiveCompetition,
} from '@/utils/timezone'

defineProps({
  isMobile: Boolean
})

defineEmits(['toggleSidebar'])

const { t, locale } = useI18n()
const authStore = useAuthStore()
const compStore = useCompetitionStore()
const dialogVisible = ref(false)
const loading = ref(false)
const formRef = ref(null)

const form = reactive({
  oldPassword: '',
  newPassword: '',
  confirmPassword: '',
})

const validateConfirm = (_rule, value, callback) => {
  if (value !== form.newPassword) {
    callback(new Error(t('header.passwordMismatch')))
  } else {
    callback()
  }
}

const rules = computed(() => ({
  oldPassword: [{ required: true, message: t('header.oldPasswordRequired'), trigger: 'blur' }],
  newPassword: [
    { required: true, message: t('header.newPasswordRequired'), trigger: 'blur' },
    { min: 6, message: t('header.passwordMinLength'), trigger: 'blur' },
  ],
  confirmPassword: [
    { required: true, message: t('header.confirmRequired'), trigger: 'blur' },
    { validator: validateConfirm, trigger: 'blur' },
  ],
}))

const countdownText = ref('')
const countdownMode = ref('hidden') // hidden | countdown | live | ended
const beijingTime = ref('')
const localTime = ref('')
let countdownTimer
let clockTimer

const activeTimezone = computed(() => (
  resolveCompetitionTimezone(resolveActiveCompetition(compStore))
))

const localTimeLabel = computed(() => t(`competition.timeLocal.${activeTimezone.value.labelKey}`))

const localFlag = computed(() => TIMEZONE_FLAGS[activeTimezone.value.labelKey] || TIMEZONE_FLAGS.local)

function resolveCompetitionDates() {
  const cur = compStore.current
  if (cur?.slug === compStore.slug) {
    return { opening: cur.opening_date, closing: cur.closing_date }
  }
  const fromList = compStore.list.find(c => c.slug === compStore.slug)
  return {
    opening: fromList?.opening_date,
    closing: fromList?.closing_date,
  }
}

const showCountdownTag = computed(() => countdownMode.value !== 'hidden')

const headerTitle = computed(() => {
  if (compStore.current?.name_key) {
    return t(`competition.names.${compStore.current.name_key}`)
  }
  return t('auth.loginTitle')
})

const countdownLabel = computed(() => {
  if (countdownMode.value === 'live') return t('header.inProgress')
  if (countdownMode.value === 'ended') return t('header.tournamentEnded')
  if (countdownMode.value === 'countdown') {
    return t('header.countdown', { time: countdownText.value })
  }
  return ''
})

function updateCountdown() {
  const { opening: openingStr, closing: closingStr } = resolveCompetitionDates()

  if (!openingStr) {
    countdownMode.value = 'hidden'
    countdownText.value = ''
    return
  }

  const now = new Date()
  const opening = new Date(openingStr)
  const closing = closingStr ? new Date(closingStr) : null

  if (closing && now > closing) {
    countdownMode.value = 'ended'
    countdownText.value = ''
    return
  }

  if (now >= opening) {
    countdownMode.value = 'live'
    countdownText.value = ''
    return
  }

  const diff = opening - now
  const days = Math.floor(diff / (1000 * 60 * 60 * 24))
  const hours = Math.floor((diff / (1000 * 60 * 60)) % 24)
  countdownText.value = t('header.daysHours', { days, hours })
  countdownMode.value = 'countdown'
}

function updateClocks() {
  const now = new Date()
  beijingTime.value = formatClock(BEIJING_TZ, locale.value, now)
  localTime.value = formatClock(activeTimezone.value.timezone, locale.value, now)
}

function handleCommand(cmd) {
  if (cmd === 'changePassword') {
    form.oldPassword = ''
    form.newPassword = ''
    form.confirmPassword = ''
    dialogVisible.value = true
  } else if (cmd === 'logout') {
    authStore.logout()
  }
}

async function handleChangePassword() {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    loading.value = true
    try {
      const res = await changePassword(form.oldPassword, form.newPassword)
      if (res.code !== 200) {
        throw new Error(res.message || t('header.changeFailed'))
      }
      ElMessage.success(t('header.changeSuccess'))
      dialogVisible.value = false
      setTimeout(() => authStore.logout(), 1000)
    } catch (e) {
      ElMessage.error(e.message || t('header.changeFailed'))
    } finally {
      loading.value = false
    }
  })
}

onMounted(() => {
  updateCountdown()
  updateClocks()
  countdownTimer = setInterval(updateCountdown, 60000)
  clockTimer = setInterval(updateClocks, 1000)
})

watch(
  () => [compStore.slug, compStore.current, compStore.list.length],
  () => {
    updateCountdown()
    updateClocks()
  },
)

onUnmounted(() => {
  clearInterval(countdownTimer)
  clearInterval(clockTimer)
})
</script>

<style scoped>
.header-wrapper {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}
.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}
.header-title {
  color: #fff;
  font-size: 20px;
  font-weight: 700;
  letter-spacing: 2px;
}
.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.user-info {
  display: flex;
  align-items: center;
  gap: 6px;
  color: rgba(255, 255, 255, 0.9);
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 8px;
  transition: background 0.2s;
  user-select: none;
}
.user-info:hover {
  background: rgba(255, 255, 255, 0.12);
}
.username {
  font-size: 14px;
  max-width: 100px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.timezones {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: 4px;
}
.tz-item {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.75);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
  letter-spacing: 0.5px;
}
.tz-flag {
  font-size: 14px;
  margin-right: 2px;
}
.tz-label {
  color: rgba(255, 255, 255, 0.5);
  margin-right: 4px;
  font-weight: 600;
}
.tz-divider {
  color: rgba(255, 255, 255, 0.25);
  font-size: 12px;
}

.hamburger-btn {
  background: transparent;
  border-color: rgba(255, 255, 255, 0.3);
  color: #fff;
}

@media (max-width: 767px) {
  .header-title {
    font-size: 16px;
    letter-spacing: 1px;
  }
  .header-right {
    gap: 6px;
  }
  .header-left {
    gap: 8px;
  }
  .username {
    max-width: 60px;
  }
  .lang-label {
    display: none;
  }
}
</style>
