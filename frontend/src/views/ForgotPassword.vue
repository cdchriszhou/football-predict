<template>
  <div class="login-page">
    <div class="login-lang">
      <LanguageSwitcher theme="light" />
    </div>
    <div class="login-card">
      <div class="login-icon">
        <FootballLogo :size="64" />
      </div>
      <h1 class="login-title">{{ t('forgotPassword.title') }}</h1>
      <p class="login-subtitle">{{ t('forgotPassword.subtitle') }}</p>

      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        class="login-form"
        @submit.prevent="handleSubmit"
      >
        <el-form-item prop="email">
          <el-input
            v-model="form.email"
            :placeholder="t('forgotPassword.emailPlaceholder')"
            :prefix-icon="Message"
            size="large"
            class="login-input"
            @keyup.enter="handleSubmit"
          />
        </el-form-item>

        <el-form-item>
          <el-button
            type="primary"
            size="large"
            class="login-btn"
            :loading="loading"
            @click="handleSubmit"
          >
            {{ t('forgotPassword.submit') }}
          </el-button>
        </el-form-item>
      </el-form>

      <div v-if="sent" class="result-box">
        <div class="token-display">
          <p class="token-label">{{ t('forgotPassword.tokenLabel') }}</p>
          <code class="token-value">{{ resetToken }}</code>
          <p class="token-hint">{{ t('forgotPassword.tokenHint') }}</p>
        </div>
        <el-button
          type="success"
          size="large"
          class="reset-link-btn"
          @click="goReset"
        >
          {{ t('forgotPassword.goReset') }}
        </el-button>
      </div>

      <p class="footer-link">
        <router-link to="/login">{{ t('auth.backToLogin') }}</router-link>
      </p>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { Message } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import FootballLogo from '@/components/FootballLogo.vue'
import LanguageSwitcher from '@/components/LanguageSwitcher.vue'
import { forgotPassword } from '@/api/auth'

const { t } = useI18n()
const router = useRouter()
const formRef = ref(null)
const loading = ref(false)
const sent = ref(false)
const resetToken = ref('')

const form = reactive({
  email: '',
})

const rules = computed(() => ({
  email: [
    { required: true, message: t('auth.emailRequired'), trigger: 'blur' },
    { type: 'email', message: t('auth.emailInvalid'), trigger: 'blur' },
  ],
}))

async function handleSubmit() {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    loading.value = true
    try {
      const res = await forgotPassword(form.email)
      if (res.code !== 200) {
        throw new Error(res.message || t('forgotPassword.requestFailed'))
      }
      if (res.data && res.data.reset_token) {
        resetToken.value = res.data.reset_token
        sent.value = true
        ElMessage.success(t('forgotPassword.tokenGenerated'))
      } else {
        ElMessage.success(t('forgotPassword.emailSentHint'))
      }
    } catch (e) {
      ElMessage.error(e.message || t('forgotPassword.requestFailed'))
    } finally {
      loading.value = false
    }
  })
}

function goReset() {
  router.push({ path: '/reset-password', query: { token: resetToken.value } })
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
  margin-bottom: 12px;
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
  margin: 0 0 28px;
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
.login-btn {
  width: 100%;
  border-radius: 12px;
  height: 46px;
  font-size: 16px;
  font-weight: 600;
  letter-spacing: 2px;
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
.result-box {
  margin-top: 16px;
  padding: 16px;
  background: #e8f5e9;
  border-radius: 12px;
  text-align: left;
}
.token-label {
  font-size: 13px;
  color: #388e3c;
  margin: 0 0 8px;
}
.token-value {
  display: block;
  padding: 8px 12px;
  background: #fff;
  border-radius: 8px;
  font-size: 12px;
  color: #1d1d1f;
  word-break: break-all;
  border: 1px solid #c8e6c9;
  margin-bottom: 8px;
  user-select: all;
}
.token-hint {
  font-size: 12px;
  color: #66bb6a;
  margin: 0;
}
.reset-link-btn {
  width: 100%;
  border-radius: 12px;
  margin-top: 8px;
  height: 40px;
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
  }
}
</style>
