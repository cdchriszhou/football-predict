<template>
  <div class="login-page">
    <div class="login-lang">
      <LanguageSwitcher theme="light" />
    </div>
    <div class="login-card">
      <div class="login-icon">
        <FootballLogo :size="64" />
      </div>
      <h1 class="login-title">{{ t('auth.loginTitle') }}</h1>
      <p class="login-subtitle">{{ t('auth.loginSubtitle') }}</p>

      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        class="login-form"
        @submit.prevent="handleLogin"
      >
        <el-form-item prop="username">
          <el-input
            v-model="form.username"
            :placeholder="t('auth.username')"
            :prefix-icon="User"
            size="large"
            class="login-input"
          />
        </el-form-item>

        <el-form-item prop="password">
          <el-input
            v-model="form.password"
            type="password"
            :placeholder="t('auth.password')"
            :prefix-icon="Lock"
            size="large"
            class="login-input"
            show-password
            @keyup.enter="handleLogin"
          />
        </el-form-item>

        <el-collapse v-model="showAdvanced" class="advanced-section">
          <el-collapse-item :title="t('auth.serverSettings')" name="server">
            <el-form-item prop="serverUrl">
              <el-input
                v-model="form.serverUrl"
                :placeholder="t('auth.serverPlaceholder')"
                :prefix-icon="Monitor"
                size="default"
                class="login-input"
                clearable
                @keyup.enter="handleLogin"
              />
            </el-form-item>
            <p class="server-hint">{{ t('auth.serverHint') }}</p>
          </el-collapse-item>
        </el-collapse>

        <el-form-item>
          <el-button
            type="primary"
            size="large"
            class="login-btn"
            :loading="loading"
            @click="handleLogin"
          >
            {{ t('auth.login') }}
          </el-button>
        </el-form-item>
      </el-form>

      <div class="login-links">
        <router-link to="/register">{{ t('auth.register') }}</router-link>
        <span class="link-sep">|</span>
        <router-link to="/forgot-password">{{ t('auth.forgotPassword') }}</router-link>
      </div>

      <div class="disclaimer">
        <el-icon :size="14"><WarningFilled /></el-icon>
        <span>{{ t('auth.disclaimer') }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { User, Lock, Monitor, WarningFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import FootballLogo from '@/components/FootballLogo.vue'
import LanguageSwitcher from '@/components/LanguageSwitcher.vue'

const { t } = useI18n()
const router = useRouter()
const authStore = useAuthStore()
const formRef = ref(null)
const loading = ref(false)
const showAdvanced = ref([])

const form = reactive({
  username: '',
  password: '',
  serverUrl: '',
})

onMounted(() => {
  const savedServer = localStorage.getItem('worldcup_server_url')
  if (savedServer) {
    form.serverUrl = savedServer
    showAdvanced.value = ['server']
  }
})

const rules = computed(() => ({
  username: [{ required: true, message: t('auth.username'), trigger: 'blur' }],
  password: [{ required: true, message: t('auth.password'), trigger: 'blur' }],
}))

async function handleLogin() {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    loading.value = true
    try {
      // Save server URL before login (so API requests use the right backend)
      if (form.serverUrl) {
        localStorage.setItem('worldcup_server_url', form.serverUrl)
      } else {
        localStorage.removeItem('worldcup_server_url')
      }
      await authStore.login(form.username, form.password)
      ElMessage.success(t('auth.loginSuccess'))
      router.push('/')
    } catch (e) {
      ElMessage.error(e.message || t('auth.loginFailed'))
    } finally {
      loading.value = false
    }
  })
}
</script>

<style scoped>
.login-page {
  width: 100vw;
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f5f5f7;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC',
    'Microsoft YaHei', sans-serif;
  position: relative;
}

.login-lang {
  position: absolute;
  top: 16px;
  right: 20px;
  z-index: 10;
}

.login-card {
  width: 90%;
  max-width: 400px;
  padding: 48px 40px 40px;
  background: #fff;
  border-radius: 18px;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.06);
  text-align: center;
}

.login-icon {
  margin-bottom: 16px;
}

.login-title {
  font-size: 24px;
  font-weight: 700;
  color: #1d1d1f;
  margin: 0 0 4px;
  letter-spacing: 2px;
}

.login-subtitle {
  font-size: 14px;
  color: #86868b;
  margin: 0 0 32px;
}

.login-form {
  text-align: left;
}

.login-input :deep(.el-input__wrapper) {
  border-radius: 12px;
  background: #f5f5f7;
  border: none;
  box-shadow: none;
  transition: background 0.2s, box-shadow 0.2s;
}

.login-input :deep(.el-input__wrapper:hover) {
  background: #eeeef0;
  box-shadow: none;
}

.login-input :deep(.el-input__wrapper.is-focus) {
  background: #fff;
  box-shadow: 0 0 0 3px rgba(26, 35, 126, 0.12);
}

.login-input :deep(.el-input__inner) {
  font-size: 15px;
  color: #1d1d1f;
}

.login-input :deep(.el-input__inner::placeholder) {
  color: #aeaeb2;
}

.login-btn {
  width: 100%;
  border-radius: 12px;
  height: 46px;
  font-size: 16px;
  font-weight: 600;
  letter-spacing: 4px;
  background: #1a237e;
  border: none;
  margin-top: 8px;
}

.login-btn:hover {
  background: #283593;
}

.login-btn:active {
  background: #0d1b5e;
}

.advanced-section {
  border: none;
  margin-top: 4px;
}
.advanced-section :deep(.el-collapse-item__header) {
  font-size: 13px;
  color: #86868b;
  border: none;
  background: transparent;
  padding: 0 4px;
}
.advanced-section :deep(.el-collapse-item__wrap) {
  border: none;
  background: transparent;
}
.advanced-section :deep(.el-collapse-item__content) {
  padding: 8px 4px 0;
}
.server-hint {
  font-size: 12px;
  color: #aeaeb2;
  margin: 4px 0 0;
}

@media (max-width: 767px) {
  .login-card {
    padding: 32px 20px 28px;
  }
  .login-title {
    font-size: 20px;
  }
  .login-btn {
    height: 44px;
    font-size: 15px;
    letter-spacing: 2px;
  }
  .disclaimer {
    font-size: 11px;
  }
}

.login-links {
  margin-top: 16px;
  font-size: 13px;
  color: #86868b;
}
.login-links a {
  color: #1a237e;
  text-decoration: none;
  font-weight: 500;
}
.login-links a:hover {
  text-decoration: underline;
}
.link-sep {
  margin: 0 8px;
  color: #c0c0c4;
}
.disclaimer {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  margin-top: 16px;
  padding: 10px 12px;
  background: #fff3e0;
  border-radius: 8px;
  font-size: 12px;
  color: #e65100;
  line-height: 1.6;
  text-align: left;
}
.disclaimer .el-icon {
  flex-shrink: 0;
  margin-top: 1px;
}
</style>
