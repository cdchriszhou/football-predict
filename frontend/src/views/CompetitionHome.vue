<template>
  <div class="competition-home">
    <div class="home-top">
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
      <LanguageSwitcher theme="light" />
    </div>
    <div class="home-header">
      <h1>{{ t('competition.homeTitle') }}</h1>
      <p>{{ t('competition.homeSubtitle') }}</p>
    </div>

    <el-alert
      v-if="loadError"
      type="warning"
      :title="loadError"
      show-icon
      :closable="false"
      class="load-error"
    />

    <div v-loading="loading" class="card-grid">
      <el-empty
        v-if="!loading && !competitions.length"
        :description="t('competition.loadEmpty')"
      >
        <el-button type="primary" @click="loadCompetitions">{{ t('common.retry') }}</el-button>
      </el-empty>

      <div
        v-for="item in competitions"
        :key="item.slug"
        class="comp-card"
        :class="{
          'comp-card--ended': item.season_status === 'ended',
          'comp-card--locked': !authStore.canAccessCompetition(item.slug),
        }"
        :style="{ '--accent': item.theme_color || '#1a237e' }"
        @click="enterCompetition(item.slug)"
      >
        <div class="comp-card-badges">
          <span v-if="item.season_status === 'ended'" class="comp-card-badge comp-card-badge--ended">
            {{ t('competition.statusEnded') }}
          </span>
          <span v-if="item.type === 'international'" class="comp-card-badge comp-card-badge--type">FIFA</span>
          <span v-if="!authStore.canAccessCompetition(item.slug)" class="comp-card-badge comp-card-badge--locked">
            {{ t('competition.locked') }}
          </span>
        </div>
        <div class="comp-card-icon">
          <el-icon :size="36">
            <TrophyBase v-if="item.type === 'international'" />
            <Medal v-else />
          </el-icon>
        </div>
        <h3>{{ t(`competition.names.${item.name_key}`) }}</h3>
        <p class="comp-short">{{ item.short_name }}</p>
        <div class="comp-times">
          <div class="comp-time-row">
            <span class="comp-time-label">{{ t('competition.timeBeijing') }}</span>
            <span class="comp-time-value">{{ cardBeijingTime(item) }}</span>
          </div>
          <div class="comp-time-row">
            <span class="comp-time-label">{{ localTimeLabel(item) }}</span>
            <span class="comp-time-value">{{ cardLocalTime(item) }}</span>
          </div>
        </div>
        <div class="comp-stats">
          <span>{{ t('competition.statMatches', { n: item.stats?.matches ?? 0 }) }}</span>
          <span>{{ t('competition.statTeams', { n: item.stats?.teams ?? 0 }) }}</span>
        </div>
        <el-button type="primary" class="enter-btn">{{ t('competition.enter') }}</el-button>
      </div>
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
        <el-form-item>
          <el-button type="primary" native-type="submit" :loading="pwdLoading" style="width: 100%">
            {{ t('header.confirmChange') }}
          </el-button>
        </el-form-item>
      </el-form>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import {
  TrophyBase, Medal, UserFilled, ArrowDown, Key, SwitchButton, Lock,
} from '@element-plus/icons-vue'
import { useCompetitionStore } from '@/stores/competition'
import { normalizeCompetition } from '@/data/competitions'
import { useAuthStore } from '@/stores/auth'
import { changePassword } from '@/api/auth'
import LanguageSwitcher from '@/components/LanguageSwitcher.vue'
import {
  BEIJING_TZ, formatClock, resolveCompetitionTimezone,
} from '@/utils/timezone'

const { t, locale } = useI18n()
const router = useRouter()
const compStore = useCompetitionStore()
const authStore = useAuthStore()
const loading = ref(false)
const loadError = ref('')
const competitions = ref([])
const clockTick = ref(Date.now())
let clockTimer

const dialogVisible = ref(false)
const pwdLoading = ref(false)
const formRef = ref()
const form = reactive({
  oldPassword: '',
  newPassword: '',
  confirmPassword: '',
})

const rules = computed(() => ({
  oldPassword: [{ required: true, message: t('header.oldPasswordRequired'), trigger: 'blur' }],
  newPassword: [
    { required: true, message: t('header.newPasswordRequired'), trigger: 'blur' },
    { min: 6, message: t('header.passwordMinLength'), trigger: 'blur' },
  ],
  confirmPassword: [
    { required: true, message: t('header.confirmRequired'), trigger: 'blur' },
    {
      validator: (_rule, value, callback) => {
        if (value !== form.newPassword) callback(new Error(t('header.passwordMismatch')))
        else callback()
      },
      trigger: 'blur',
    },
  ],
}))

function localTimeLabel(item) {
  const { labelKey } = resolveCompetitionTimezone(item)
  return t(`competition.timeLocal.${labelKey}`)
}

function cardBeijingTime(item) {
  void clockTick.value
  return formatClock(BEIJING_TZ, locale.value, new Date(clockTick.value))
}

function cardLocalTime(item) {
  void clockTick.value
  const { timezone } = resolveCompetitionTimezone(item)
  return formatClock(timezone, locale.value, new Date(clockTick.value))
}

async function loadCompetitions() {
  loading.value = true
  loadError.value = ''
  try {
    const list = await compStore.fetchList()
    competitions.value = [...list]
    if (compStore.listFromFallback) {
      const detail = compStore.listError ? `（${compStore.listError}）` : ''
      loadError.value = `${t('competition.loadFailed')}${detail}`
    }
    compStore.clearCurrent()
  } catch (err) {
    loadError.value = err?.message || t('competition.loadFailed')
    competitions.value = [...compStore.list]
  } finally {
    loading.value = false
  }
}

function enterCompetition(slug) {
  if (!authStore.canAccessCompetition(slug)) {
    ElMessage.warning(authStore.accessDeniedMessage(slug))
    return
  }
  const item = competitions.value.find((c) => c.slug === slug)
    || compStore.list.find((c) => c.slug === slug)
  if (item) {
    compStore.current = normalizeCompetition(item)
  }
  compStore.setSlug(slug)
  router.push(`/competition/${slug}`)
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
    pwdLoading.value = true
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
      pwdLoading.value = false
    }
  })
}

onMounted(() => {
  authStore.fetchMe().catch(() => null)
  loadCompetitions()
  clockTimer = setInterval(() => { clockTick.value = Date.now() }, 1000)
})

onUnmounted(() => {
  clearInterval(clockTimer)
})
</script>

<style scoped>
.competition-home {
  min-height: 100vh;
  background: linear-gradient(160deg, #f5f7fa 0%, #e8eaf6 100%);
  padding: 24px 20px 48px;
}
.home-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  max-width: 1100px;
  margin-left: auto;
  margin-right: auto;
}
.user-info {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #303133;
  cursor: pointer;
  padding: 6px 10px;
  border-radius: 8px;
  transition: background 0.2s;
  user-select: none;
  background: rgba(255, 255, 255, 0.7);
  border: 1px solid rgba(26, 35, 126, 0.1);
}
.user-info:hover {
  background: #fff;
}
.username {
  font-size: 14px;
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 600;
}
.home-header {
  text-align: center;
  margin-bottom: 32px;
}
.home-header h1 {
  font-size: 28px;
  color: #1a237e;
  margin: 0 0 8px;
}
.home-header p {
  color: #606266;
  margin: 0;
}
.load-error {
  max-width: 1100px;
  margin: 0 auto 16px;
}
.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 20px;
  max-width: 1100px;
  margin: 0 auto;
  min-height: 120px;
}
.comp-card {
  background: #fff;
  border-radius: 16px;
  padding: 24px 20px;
  box-shadow: 0 4px 20px rgba(26, 35, 126, 0.08);
  cursor: pointer;
  transition: transform 0.2s, box-shadow 0.2s;
  border-top: 4px solid var(--accent);
  position: relative;
}
.comp-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 8px 28px rgba(26, 35, 126, 0.15);
}
.comp-card--ended {
  opacity: 0.92;
}
.comp-card--ended:hover {
  opacity: 1;
}
.comp-card--locked {
  opacity: 0.88;
}
.comp-card--locked:hover {
  transform: none;
  box-shadow: 0 4px 20px rgba(26, 35, 126, 0.08);
}
.comp-card-badges {
  position: absolute;
  top: 12px;
  right: 12px;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 6px;
}
.comp-card-badge {
  font-size: 11px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 999px;
  line-height: 1.5;
}
.comp-card-badge--type {
  color: var(--accent);
  background: rgba(26, 35, 126, 0.08);
}
.comp-card-badge--ended {
  color: #fff;
  background: #909399;
}
.comp-card-badge--locked {
  color: #fff;
  background: #e6a23c;
}
.comp-card-icon {
  color: var(--accent);
  margin-bottom: 12px;
}
.comp-card h3 {
  margin: 0 0 4px;
  font-size: 18px;
  color: #303133;
}
.comp-short {
  color: #909399;
  font-size: 13px;
  margin: 0 0 10px;
}
.comp-times {
  background: #f5f7fa;
  border-radius: 8px;
  padding: 8px 10px;
  margin-bottom: 12px;
  font-size: 11px;
  line-height: 1.6;
}
.comp-time-row {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 8px;
}
.comp-time-label {
  color: #909399;
  flex-shrink: 0;
}
.comp-time-value {
  color: #303133;
  font-variant-numeric: tabular-nums;
  font-weight: 500;
  text-align: right;
}
.comp-stats {
  display: flex;
  gap: 12px;
  font-size: 12px;
  color: #606266;
  margin-bottom: 16px;
}
.enter-btn {
  width: 100%;
  background: var(--accent);
  border-color: var(--accent);
}
</style>
