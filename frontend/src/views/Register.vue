<template>
  <div class="login-page">
    <div class="login-lang">
      <LanguageSwitcher theme="light" />
    </div>
    <div class="login-card">
      <div class="login-icon">
        <FootballLogo :size="64" />
      </div>

      <!-- Step indicator -->
      <div class="step-indicator">
        <span class="step" :class="{ active: step === 1, done: step > 1 }">
          <span class="step-num">1</span> {{ t('register.stepInvite') }}
        </span>
        <span class="step-line"></span>
        <span class="step" :class="{ active: step === 2 }">
          <span class="step-num">2</span> {{ t('register.stepInfo') }}
        </span>
      </div>

      <!-- Step 1: Invite Code -->
      <template v-if="step === 1">
        <h1 class="login-title">{{ t('register.title') }}</h1>
        <p class="login-subtitle">{{ t('register.subtitleInvite') }}</p>

        <el-form
          ref="inviteFormRef"
          :model="inviteForm"
          :rules="inviteRules"
          class="login-form"
          @submit.prevent="handleVerifyInvite"
        >
          <el-form-item prop="code">
            <el-input
              v-model="inviteForm.code"
              :placeholder="t('register.invitePlaceholder')"
              :prefix-icon="Ticket"
              size="large"
              class="login-input"
              maxlength="6"
              @keyup.enter="handleVerifyInvite"
            />
          </el-form-item>

          <el-form-item>
            <el-button
              type="primary"
              size="large"
              class="login-btn"
              :loading="verifying"
              @click="handleVerifyInvite"
            >
              {{ t('register.verifyInvite') }}
            </el-button>
          </el-form-item>
        </el-form>
      </template>

      <!-- Step 2: Registration Form -->
      <template v-if="step === 2">
        <h1 class="login-title">{{ t('register.stepInfoTitle') }}</h1>
        <p class="login-subtitle">{{ t('register.subtitleInfo', { code: inviteForm.code }) }}</p>

        <el-form
          ref="formRef"
          :model="form"
          :rules="rules"
          class="login-form"
          @submit.prevent="handleRegister"
        >
          <el-form-item prop="username">
            <el-input
              v-model="form.username"
              :placeholder="t('register.usernamePlaceholder')"
              :prefix-icon="User"
              size="large"
              class="login-input"
            />
          </el-form-item>

          <el-form-item prop="email">
            <el-input
              v-model="form.email"
              :placeholder="t('register.emailPlaceholder')"
              :prefix-icon="Message"
              size="large"
              class="login-input"
            />
          </el-form-item>

          <el-form-item prop="password">
            <el-input
              v-model="form.password"
              type="password"
              :placeholder="t('register.passwordPlaceholder')"
              :prefix-icon="Lock"
              size="large"
              class="login-input"
              show-password
              @keyup.enter="handleRegister"
            />
          </el-form-item>

          <el-form-item prop="confirmPassword">
            <el-input
              v-model="form.confirmPassword"
              type="password"
              :placeholder="t('register.confirmPasswordPlaceholder')"
              :prefix-icon="Lock"
              size="large"
              class="login-input"
              show-password
              @keyup.enter="handleRegister"
            />
          </el-form-item>

          <el-form-item>
            <el-button
              type="primary"
              size="large"
              class="login-btn"
              :loading="loading"
              @click="handleRegister"
            >
              {{ t('register.submit') }}
            </el-button>
          </el-form-item>
        </el-form>

        <p class="back-link">
          <el-button text type="primary" size="small" @click="step = 1">
            {{ t('register.changeInvite') }}
          </el-button>
        </p>
      </template>

      <p class="footer-link">
        {{ t('auth.hasAccount') }}<router-link to="/login">{{ t('auth.loginNow') }}</router-link>
      </p>

      <div class="disclaimer">
        <el-icon :size="14"><WarningFilled /></el-icon>
        <span>{{ t('auth.disclaimer') }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { User, Lock, Message, Ticket, WarningFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import FootballLogo from '@/components/FootballLogo.vue'
import LanguageSwitcher from '@/components/LanguageSwitcher.vue'
import { register as apiRegister, verifyInvite as apiVerifyInvite } from '@/api/auth'

const { t } = useI18n()
const router = useRouter()
const authStore = useAuthStore()
const step = ref(1)
const verifying = ref(false)
const loading = ref(false)
const inviteFormRef = ref(null)
const formRef = ref(null)

const inviteForm = reactive({
  code: '',
})

const form = reactive({
  username: '',
  email: '',
  password: '',
  confirmPassword: '',
})

const inviteRules = computed(() => ({
  code: [
    { required: true, message: t('register.inviteRequired'), trigger: 'blur' },
    { len: 6, message: t('register.inviteLen'), trigger: 'blur' },
  ],
}))

const validateConfirm = (_rule, value, callback) => {
  if (value !== form.password) {
    callback(new Error(t('header.passwordMismatch')))
  } else {
    callback()
  }
}

const rules = computed(() => ({
  username: [
    { required: true, message: t('register.usernameRequired'), trigger: 'blur' },
    { min: 3, max: 50, message: t('register.usernameLen'), trigger: 'blur' },
  ],
  email: [
    { required: true, message: t('auth.emailRequired'), trigger: 'blur' },
    { type: 'email', message: t('auth.emailInvalid'), trigger: 'blur' },
  ],
  password: [
    { required: true, message: t('register.passwordRequired'), trigger: 'blur' },
    { min: 6, message: t('header.passwordMinLength'), trigger: 'blur' },
  ],
  confirmPassword: [
    { required: true, message: t('register.confirmRequired'), trigger: 'blur' },
    { validator: validateConfirm, trigger: 'blur' },
  ],
}))

async function handleVerifyInvite() {
  if (!inviteFormRef.value) return
  await inviteFormRef.value.validate(async (valid) => {
    if (!valid) return
    verifying.value = true
    try {
      const res = await apiVerifyInvite(inviteForm.code)
      if (res.code !== 200) {
        throw new Error(res.message || t('register.inviteInvalid'))
      }
      ElMessage.success(t('register.inviteVerified'))
      step.value = 2
    } catch (e) {
      ElMessage.error(e.message || t('register.inviteVerifyFailed'))
    } finally {
      verifying.value = false
    }
  })
}

async function handleRegister() {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    loading.value = true
    try {
      const res = await apiRegister(form.username, form.email, form.password, inviteForm.code)
      if (res.code !== 200) {
        throw new Error(res.message || t('register.registerFailed'))
      }
      const { access_token, username } = res.data
      authStore.token = access_token
      authStore.username = username
      authStore.isAdmin = false
      localStorage.setItem('worldcup_auth_token', access_token)
      localStorage.setItem('worldcup_auth_user', username)
      localStorage.setItem('worldcup_auth_is_admin', 'false')
      ElMessage.success(t('register.registerSuccess'))
      router.push('/')
    } catch (e) {
      ElMessage.error(e.message || t('register.registerFailed'))
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
  padding: 40px 40px 32px;
  background: #fff;
  border-radius: 18px;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.06);
  text-align: center;
}
.login-icon {
  margin-bottom: 12px;
}
.step-indicator {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0;
  margin-bottom: 20px;
}
.step {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #aeaeb2;
  font-weight: 500;
}
.step.active {
  color: #1a237e;
  font-weight: 700;
}
.step.done {
  color: #4caf50;
}
.step-num {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: #e8e8ed;
  font-size: 12px;
  font-weight: 700;
}
.step.active .step-num {
  background: #1a237e;
  color: #fff;
}
.step.done .step-num {
  background: #4caf50;
  color: #fff;
}
.step-line {
  width: 40px;
  height: 2px;
  background: #e8e8ed;
  margin: 0 8px;
}
.login-title {
  font-size: 22px;
  font-weight: 700;
  color: #1d1d1f;
  margin: 0 0 4px;
  letter-spacing: 2px;
}
.login-subtitle {
  font-size: 14px;
  color: #86868b;
  margin: 0 0 24px;
}
.login-subtitle code {
  background: #e8f5e9;
  color: #2e7d32;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 13px;
  letter-spacing: 2px;
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
  margin-top: 4px;
}
.login-btn:hover {
  background: #283593;
}
.login-btn:active {
  background: #0d1b5e;
}
.back-link {
  margin: 8px 0 0;
}
.footer-link {
  margin: 16px 0 0;
  font-size: 13px;
  color: #86868b;
}
.footer-link a {
  color: #1a237e;
  text-decoration: none;
  font-weight: 500;
}
.footer-link a:hover {
  text-decoration: underline;
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
@media (max-width: 767px) {
  .login-card {
    padding: 28px 20px 24px;
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
</style>
