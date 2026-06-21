<template>
  <div class="login-page">
    <div class="login-lang">
      <LanguageSwitcher theme="light" />
    </div>
    <div class="login-card">
      <div class="login-icon">
        <FootballLogo :size="64" />
      </div>
      <h1 class="login-title">{{ t('resetPassword.title') }}</h1>
      <p class="login-subtitle">{{ t('resetPassword.subtitle') }}</p>

      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        class="login-form"
        @submit.prevent="handleSubmit"
      >
        <el-form-item prop="token">
          <el-input
            v-model="form.token"
            :placeholder="t('resetPassword.tokenPlaceholder')"
            :prefix-icon="Key"
            size="large"
            class="login-input"
          />
        </el-form-item>

        <el-form-item prop="newPassword">
          <el-input
            v-model="form.newPassword"
            type="password"
            :placeholder="t('resetPassword.newPasswordPlaceholder')"
            :prefix-icon="Lock"
            size="large"
            class="login-input"
            show-password
            @keyup.enter="handleSubmit"
          />
        </el-form-item>

        <el-form-item prop="confirmPassword">
          <el-input
            v-model="form.confirmPassword"
            type="password"
            :placeholder="t('resetPassword.confirmPlaceholder')"
            :prefix-icon="Lock"
            size="large"
            class="login-input"
            show-password
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
            {{ t('resetPassword.submit') }}
          </el-button>
        </el-form-item>
      </el-form>

      <p class="footer-link">
        <router-link to="/login">{{ t('auth.backToLogin') }}</router-link>
      </p>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter, useRoute } from 'vue-router'
import { Lock, Key } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import FootballLogo from '@/components/FootballLogo.vue'
import LanguageSwitcher from '@/components/LanguageSwitcher.vue'
import { resetPassword } from '@/api/auth'

const { t } = useI18n()
const router = useRouter()
const route = useRoute()
const formRef = ref(null)
const loading = ref(false)

const form = reactive({
  token: '',
  newPassword: '',
  confirmPassword: '',
})

onMounted(() => {
  if (route.query.token) {
    form.token = route.query.token
  }
})

const validateConfirm = (_rule, value, callback) => {
  if (value !== form.newPassword) {
    callback(new Error(t('header.passwordMismatch')))
  } else {
    callback()
  }
}

const rules = computed(() => ({
  token: [
    { required: true, message: t('resetPassword.tokenRequired'), trigger: 'blur' },
  ],
  newPassword: [
    { required: true, message: t('header.newPasswordRequired'), trigger: 'blur' },
    { min: 6, message: t('header.passwordMinLength'), trigger: 'blur' },
  ],
  confirmPassword: [
    { required: true, message: t('header.confirmRequired'), trigger: 'blur' },
    { validator: validateConfirm, trigger: 'blur' },
  ],
}))

async function handleSubmit() {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    loading.value = true
    try {
      const res = await resetPassword(form.token, form.newPassword)
      if (res.code !== 200) {
        throw new Error(res.message || t('resetPassword.failed'))
      }
      ElMessage.success(t('resetPassword.success'))
      router.push('/login')
    } catch (e) {
      ElMessage.error(e.message || t('resetPassword.failed'))
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
