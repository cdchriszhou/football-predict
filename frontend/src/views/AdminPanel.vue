<template>
  <div class="admin-page">
    <div class="page-header">
      <h2>{{ t('admin.title') }}</h2>
      <p>{{ t('admin.subtitle') }}</p>
    </div>

    <el-tabs v-model="activeTab" type="border-card">
      <el-tab-pane :label="t('admin.tabSystem')" name="system">

    <!-- Health check -->
    <el-row :gutter="20">
      <el-col :xs="12" :sm="6" v-for="h in healthItems" :key="h.key">
        <el-card class="health-card">
          <div class="health-indicator">
            <el-icon :size="20" :color="h.ok ? '#4caf50' : '#f44336'">
              <CircleCheck v-if="h.ok" /><CircleClose v-else />
            </el-icon>
            <span>{{ h.label }}</span>
          </div>
          <span class="health-status" :class="{ ok: h.ok, error: !h.ok }">{{ h.ok ? t('admin.statusOk') : h.msg }}</span>
        </el-card>
      </el-col>
    </el-row>

    <!-- API Configuration -->
    <el-card class="admin-card" style="margin-top: 20px">
      <template #header>
        <div class="flex-between">
          <span class="card-title">{{ t('admin.apiConfigTitle') }}</span>
          <el-tag :type="config.active_model === 'rule_engine' ? 'info' : 'success'" size="small">
            {{ t('admin.currentModel') }}: {{ displayModelLabel(config.active_model) }}
          </el-tag>
        </div>
      </template>

      <el-form :model="apiForm" :label-position="isMobile ? 'top' : 'right'" label-width="130px" @submit.prevent>
        <!-- ========== DeepSeek ========== -->
        <div class="model-section">
          <div class="model-header">
            <span class="model-name">🔮 {{ t('models.deepseek') }}</span>
            <span v-if="config.deepseek_configured" class="tag-ok">{{ t('admin.configured') }}</span>
            <span v-else class="tag-no">{{ t('admin.notConfigured') }}</span>
          </div>
          <el-form-item :label="t('admin.apiKey')">
            <el-input v-model="apiForm.deepseek_api_key" type="password" show-password placeholder="sk-xxxxxxxx" clearable />
            <div class="form-hint"><a href="https://platform.deepseek.com/" target="_blank">{{ t('admin.applyKey') }}</a></div>
          </el-form-item>
          <el-form-item :label="t('admin.apiUrl')">
            <el-input v-model="apiForm.deepseek_api_url" placeholder="https://api.deepseek.com/v1/chat/completions" />
          </el-form-item>
        </div>

        <!-- ========== Qwen ========== -->
        <el-divider />
        <div class="model-section">
          <div class="model-header">
            <span class="model-name">☁️ {{ t('models.qwen') }}</span>
            <span v-if="config.qwen_configured" class="tag-ok">{{ t('admin.configured') }}</span>
            <span v-else class="tag-no">{{ t('admin.notConfigured') }}</span>
          </div>
          <el-form-item :label="t('admin.apiKey')">
            <el-input v-model="apiForm.qwen_api_key" type="password" show-password placeholder="sk-xxxxxxxx" clearable />
            <div class="form-hint"><a href="https://dashscope.console.aliyun.com/" target="_blank">{{ t('admin.applyKey') }}</a></div>
          </el-form-item>
          <el-form-item :label="t('admin.apiUrl')">
            <el-input v-model="apiForm.qwen_api_url" placeholder="https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions" />
          </el-form-item>
        </div>

        <!-- ========== GLM ========== -->
        <el-divider />
        <div class="model-section">
          <div class="model-header">
            <span class="model-name">🤖 {{ t('models.glm') }}</span>
            <span v-if="config.glm_configured" class="tag-ok">{{ t('admin.configured') }}</span>
            <span v-else class="tag-no">{{ t('admin.notConfigured') }}</span>
          </div>
          <el-form-item :label="t('admin.apiKey')">
            <el-input v-model="apiForm.glm_api_key" type="password" show-password placeholder="xxxxxxxxxxxxxxxx" clearable />
            <div class="form-hint"><a href="https://open.bigmodel.cn/" target="_blank">{{ t('admin.applyKey') }}</a></div>
          </el-form-item>
          <el-form-item :label="t('admin.apiUrl')">
            <el-input v-model="apiForm.glm_api_url" placeholder="https://open.bigmodel.cn/api/paas/v4/chat/completions" />
          </el-form-item>
        </div>

        <!-- ========== football-data.org ========== -->
        <el-divider />
        <div class="model-section">
          <div class="model-header">
            <span class="model-name">⚽ {{ t('admin.footballDataApiTitle') }}</span>
            <span v-if="config.football_data_configured" class="tag-ok">{{ t('admin.configured') }}</span>
            <span v-else class="tag-no">{{ t('admin.notConfigured') }}</span>
          </div>
          <el-form-item :label="t('admin.apiKey')">
            <el-input v-model="apiForm.football_data_api_key" type="password" show-password placeholder="football-data.org token" clearable />
            <div class="form-hint"><a href="https://www.football-data.org/client/register" target="_blank">{{ t('admin.applyKeyFootballData') }}</a></div>
          </el-form-item>
          <el-form-item :label="t('admin.connectionTest')">
            <el-button type="success" size="small" @click="testFootballDataApi" :loading="testingFootballData" :disabled="!config.football_data_configured">
              {{ t('admin.testFootballDataApi') }}
            </el-button>
          </el-form-item>
        </div>

        <!-- ========== The Odds API ========== -->
        <el-divider />
        <div class="model-section">
          <div class="model-header">
            <span class="model-name">📊 {{ t('admin.oddsApiTitle') }}</span>
            <span v-if="config.odds_api_configured" class="tag-ok">{{ t('admin.configured') }}</span>
            <span v-else class="tag-no">{{ t('admin.notConfigured') }}</span>
          </div>
          <el-form-item :label="t('admin.apiKey')">
            <el-input v-model="apiForm.odds_api_key" type="password" show-password placeholder="the-odds-api key" clearable />
            <div class="form-hint"><a href="https://the-odds-api.com/" target="_blank">{{ t('admin.applyKeyWorldCup') }}</a></div>
          </el-form-item>
          <el-form-item :label="t('admin.connectionTest')">
            <el-button type="success" size="small" @click="testOddsApi" :loading="testingOddsApi" :disabled="!config.odds_api_configured">
              {{ t('admin.testOddsApi') }}
            </el-button>
          </el-form-item>
        </div>

        <el-divider />

        <el-form-item>
          <el-button type="primary" @click="saveApiConfig" :loading="savingConfig">
            <el-icon><Select /></el-icon> {{ t('admin.saveAll') }}
          </el-button>
          <el-button @click="loadConfig">{{ t('common.reset') }}</el-button>
        </el-form-item>

        <el-form-item :label="t('admin.connectionTest')">
          <el-button type="success" size="small" @click="testApi('deepseek')" :loading="testingModels.deepseek" :disabled="!config.deepseek_configured">
            {{ t('admin.testDeepseek') }}
          </el-button>
          <el-button type="success" size="small" @click="testApi('qwen')" :loading="testingModels.qwen" :disabled="!config.qwen_configured">
            {{ t('admin.testQwen') }}
          </el-button>
          <el-button type="success" size="small" @click="testApi('glm')" :loading="testingModels.glm" :disabled="!config.glm_configured">
            {{ t('admin.testGlm') }}
          </el-button>
        </el-form-item>

        <el-form-item v-if="testResult" :label="t('admin.testResult')">
          <el-alert
            :title="testResult.message"
            :type="testResult.ok ? 'success' : 'error'"
            :closable="true"
            show-icon
            @close="testResult = null"
          >
            <template v-if="testResult.ok && testResult.model === 'The Odds API'">
              {{ t('admin.testOddsDetail', {
                s: testResult.latency_seconds,
                events: testResult.events_count,
                matched: testResult.db_matched
              }) }}
              <span v-if="testResult.sample_api_match">{{ t('admin.testOddsSample', { sample: testResult.sample_api_match }) }}</span>
            </template>
            <template v-else-if="testResult.ok">
              {{ t('admin.testLatency', { s: testResult.latency_seconds, code: testResult.status_code }) }}
            </template>
            <template v-else>
              <span v-if="testResult.response">{{ t('admin.testResponse', { text: testResult.response }) }}</span>
            </template>
          </el-alert>
        </el-form-item>

        <el-form-item v-if="configSaved">
          <div class="save-success">
            <el-icon color="#4caf50"><CircleCheck /></el-icon> {{ t('admin.configSaved') }}
          </div>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- Crawler controls -->
    <el-card class="admin-card" style="margin-top: 20px">
      <template #header><span class="card-title">{{ t('admin.crawlerTitle') }}</span></template>
      <div class="crawler-controls">
        <el-button type="primary" @click="runCrawler('all')" :loading="crawlingAll">
          <el-icon><Download /></el-icon> {{ t('admin.crawlAll') }}
        </el-button>
        <el-button @click="runCrawler('schedule')" :loading="crawlingSchedule">{{ t('admin.crawlSchedule') }}</el-button>
        <el-button @click="runCrawler('team')" :loading="crawlingTeam">{{ t('admin.crawlTeam') }}</el-button>
        <el-button @click="runCrawler('odds')" :loading="crawlingOdds">{{ t('admin.crawlOdds') }}</el-button>
        <el-button type="warning" @click="probeSportteryApi" :loading="probingSporttery">{{ t('admin.probeSporttery') }}</el-button>
      </div>
      <p v-if="sportteryProbeMsg" class="sporttery-probe-msg" :class="{ ok: sportteryProbeOk, err: !sportteryProbeOk }">{{ sportteryProbeMsg }}</p>

      <div class="table-responsive" style="margin-top: 16px">
        <el-table :data="crawlerLogs" size="small" stripe>
          <el-table-column prop="crawler_type" :label="t('admin.colType')" width="100" />
          <el-table-column prop="status" :label="t('admin.colStatus')" width="100">
            <template #default="{ row }">
              <el-tag :type="row.status === 'success' ? 'success' : 'danger'" size="small">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="records_count" :label="t('admin.colRecords')" width="80" />
          <el-table-column prop="error_message" :label="t('admin.colError')" min-width="150" show-overflow-tooltip />
          <el-table-column prop="start_time" :label="t('admin.colStartTime')" width="170">
            <template #default="{ row }">{{ formatTime(row.start_time) }}</template>
          </el-table-column>
        </el-table>
      </div>
    </el-card>

    <!-- Invite Codes -->
    <el-card class="admin-card" style="margin-top: 20px">
      <template #header>
        <div class="flex-between">
          <span class="card-title">{{ t('admin.inviteTitle') }}</span>
          <el-button type="primary" size="small" :icon="Plus" @click="generateInvite" :loading="generatingCode">
            {{ t('admin.generateInvite') }}
          </el-button>
        </div>
      </template>
      <div v-if="newCode" class="new-code-box">
        <span class="new-code-label">{{ t('admin.currentInvite') }}</span>
        <code class="new-code-value">{{ newCode }}</code>
        <span class="new-code-expiry">
          {{ newCodeExpiresAt ? t('admin.inviteExpiryUntil', { time: newCodeExpiresAt }) : t('admin.inviteExpiry') }}
        </span>
        <el-button text size="small" @click="copyCode(newCode)">
          <el-icon><CopyDocument /></el-icon> {{ t('admin.copy') }}
        </el-button>
      </div>
      <el-table :data="inviteCodes" style="width:100%" stripe>
        <el-table-column prop="code" :label="t('admin.colInviteCode')" width="140">
          <template #default="{ row }">
            <span :style="{ color: row.is_active ? '#1d1d1f' : '#999' }">{{ row.code }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="t('admin.colInviteStatus')" width="90">
          <template #default="{ row }">
            <el-tag v-if="row.is_active" type="success" size="small">{{ t('admin.inviteActive') }}</el-tag>
            <el-tag v-else type="danger" size="small">{{ t('admin.inviteExpired') }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="use_count" :label="t('admin.colUseCount')" width="80" />
        <el-table-column :label="t('admin.colCreated')" width="160">
          <template #default="{ row }">{{ formatInviteTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column :label="t('admin.colExpires')" width="160">
          <template #default="{ row }">{{ formatInviteTime(row.expires_at) }}</template>
        </el-table-column>
        <el-table-column :label="t('admin.colActions')" width="80">
          <template #default="{ row }">
            <el-popconfirm
              :title="t('admin.confirmDeleteInvite')"
              :confirm-button-text="t('common.confirm')"
              :cancel-button-text="t('common.cancel')"
              @confirm="deleteCode(row.id)"
            >
              <template #reference>
                <el-button text type="danger" size="small">{{ t('admin.delete') }}</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!inviteCodes.length" :description="t('admin.noInvites')" :image-size="60" />
    </el-card>

    <!-- Predict controls -->
    <el-card class="admin-card" style="margin-top: 20px">
      <template #header><span class="card-title">{{ t('admin.predictTaskTitle') }}</span></template>
      <div class="predict-controls">
        <el-select v-model="predictModel" style="width:220px;margin-right:12px">
          <el-option v-for="opt in modelOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
        </el-select>
        <el-button type="warning" @click="runBatchPredict" :loading="batchPredicting">
          {{ t('admin.batchPredict') }}
        </el-button>
        <span class="result-msg" v-if="batchResult">{{ batchResult }}</span>
      </div>
    </el-card>

      </el-tab-pane>

      <!-- Users Tab -->
      <el-tab-pane :label="t('admin.tabUsers')" name="users">
        <el-row :gutter="20">
          <el-col :xs="12" :sm="12">
            <el-card class="user-stat-card">
              <div class="user-stat">
                <el-icon :size="28" color="#409eff"><User /></el-icon>
                <div class="user-stat-info">
                  <span class="user-stat-num">{{ userStats.total }}</span>
                  <span class="user-stat-label">{{ t('admin.userTotal') }}</span>
                </div>
              </div>
            </el-card>
          </el-col>
          <el-col :xs="12" :sm="12">
            <el-card class="user-stat-card">
              <div class="user-stat">
                <el-icon :size="28" color="#67c23a"><UserFilled /></el-icon>
                <div class="user-stat-info">
                  <span class="user-stat-num">{{ userStats.active }}</span>
                  <span class="user-stat-label">{{ t('admin.userActive') }}</span>
                </div>
              </div>
            </el-card>
          </el-col>
        </el-row>

        <el-card class="admin-card" style="margin-top: 20px">
          <template #header>
            <div class="flex-between">
              <span class="card-title">{{ t('admin.userListTitle') }}</span>
              <el-button size="small" @click="loadUsers">
                <el-icon><Refresh /></el-icon> {{ t('common.refresh') }}
              </el-button>
            </div>
          </template>
          <div class="table-responsive">
            <el-table :data="userList" stripe size="small" v-loading="loadingUsers">
              <el-table-column prop="id" label="ID" width="60" />
              <el-table-column prop="username" :label="t('admin.colUsername')" min-width="120" />
              <el-table-column prop="email" :label="t('admin.colEmail')" min-width="160" />
              <el-table-column :label="t('admin.colRole')" width="90">
                <template #default="{ row }">
                  <el-tag :type="row.is_admin ? 'danger' : 'info'" size="small">
                    {{ row.is_admin ? t('admin.roleAdmin') : t('admin.roleUser') }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column :label="t('admin.colUserStatus')" width="90">
                <template #default="{ row }">
                  <el-tag :type="row.is_active ? 'success' : 'danger'" size="small">
                    {{ row.is_active ? t('admin.userActiveStatus') : t('admin.userDisabledStatus') }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column :label="t('admin.colCreated')" width="170">
                <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
              </el-table-column>
              <el-table-column :label="t('admin.colLastLogin')" width="170">
                <template #default="{ row }">
                  {{ row.last_login_at ? formatLastLogin(row.last_login_at) : t('admin.neverLoggedIn') }}
                </template>
              </el-table-column>
              <el-table-column :label="t('admin.colAccessExpires')" min-width="200">
                <template #default="{ row }">
                  <el-date-picker
                    v-if="!row.is_admin"
                    v-model="row._accessExpires"
                    type="datetime"
                    value-format="YYYY-MM-DDTHH:mm:ss"
                    :placeholder="t('admin.accessNeverExpires')"
                    clearable
                    size="small"
                    style="width: 100%"
                    @change="() => saveUserAccess(row)"
                  />
                  <span v-else class="text-muted">{{ t('admin.accessUnlimited') }}</span>
                </template>
              </el-table-column>
              <el-table-column :label="t('admin.colAllowedCompetitions')" min-width="260">
                <template #default="{ row }">
                  <div v-if="!row.is_admin" class="access-comp-cell">
                    <el-checkbox
                      v-model="row._allCompetitions"
                      size="small"
                      @change="() => onAllCompetitionsChange(row)"
                    >
                      {{ t('admin.allCompetitions') }}
                    </el-checkbox>
                    <el-select
                      v-if="!row._allCompetitions"
                      v-model="row._allowedCompetitions"
                      multiple
                      collapse-tags
                      collapse-tags-tooltip
                      size="small"
                      :placeholder="t('admin.selectCompetitions')"
                      style="width: 100%; margin-top: 4px"
                      @change="() => saveUserAccess(row)"
                    >
                      <el-option
                        v-for="opt in competitionOptions"
                        :key="opt.slug"
                        :label="competitionLabel(opt)"
                        :value="opt.slug"
                      />
                    </el-select>
                  </div>
                  <span v-else class="text-muted">{{ t('admin.accessUnlimited') }}</span>
                </template>
              </el-table-column>
              <el-table-column :label="t('admin.colSportteryAccess')" min-width="180">
                <template #default="{ row }">
                  <el-radio-group
                    v-if="!row.is_admin"
                    v-model="row._canAccessSporttery"
                    size="small"
                    @change="() => saveUserAccess(row)"
                  >
                    <el-radio :value="true">{{ t('admin.sportteryVisible') }}</el-radio>
                    <el-radio :value="false">{{ t('admin.sportteryHidden') }}</el-radio>
                  </el-radio-group>
                  <span v-else class="text-muted">{{ t('admin.accessUnlimited') }}</span>
                </template>
              </el-table-column>
              <el-table-column :label="t('admin.colActions')" width="180">
                <template #default="{ row }">
                  <el-button
                    text
                    :type="row.is_active ? 'danger' : 'success'"
                    size="small"
                    @click="handleToggleActive(row)"
                  >
                    {{ row.is_active ? t('admin.disable') : t('admin.enable') }}
                  </el-button>
                  <el-popconfirm
                    :title="t('admin.confirmResetPwd', { name: row.username })"
                    :confirm-button-text="t('common.confirm')"
                    :cancel-button-text="t('common.cancel')"
                    @confirm="handleResetPassword(row)"
                  >
                    <template #reference>
                      <el-button text type="warning" size="small">{{ t('admin.resetPassword') }}</el-button>
                    </template>
                  </el-popconfirm>
                </template>
              </el-table-column>
            </el-table>
          </div>
          <el-empty v-if="!loadingUsers && !userList.length" :description="t('admin.noUsers')" :image-size="60" />
        </el-card>
      </el-tab-pane>

      <!-- Runtime logs -->
      <el-tab-pane :label="t('admin.tabLogs')" name="logs">
        <el-card class="admin-card">
          <template #header>
            <div class="flex-between log-toolbar">
              <span class="card-title">{{ t('admin.runtimeLogsTitle') }}</span>
              <div class="log-actions">
                <el-select v-model="logSource" style="width: 140px" @change="loadRuntimeLogs">
                  <el-option :label="t('admin.logSourceBackend')" value="backend" />
                  <el-option :label="t('admin.logSourceFrontend')" value="frontend" />
                </el-select>
                <el-select v-model="logLines" style="width: 120px" @change="loadRuntimeLogs">
                  <el-option :label="t('admin.logLines', { n: 200 })" :value="200" />
                  <el-option :label="t('admin.logLines', { n: 500 })" :value="500" />
                  <el-option :label="t('admin.logLines', { n: 1000 })" :value="1000" />
                </el-select>
                <el-checkbox v-model="logAutoRefresh" @change="onLogAutoRefreshChange">
                  {{ t('admin.logAutoRefresh') }}
                </el-checkbox>
                <el-button size="small" :loading="loadingRuntimeLogs" @click="loadRuntimeLogs">
                  <el-icon><Refresh /></el-icon> {{ t('common.refresh') }}
                </el-button>
              </div>
            </div>
          </template>
          <p v-if="runtimeLogMeta.path" class="log-meta">
            {{ runtimeLogMeta.path }}
            · {{ formatLogSize(runtimeLogMeta.size_bytes) }}
            · {{ t('admin.logMetaLines', { n: runtimeLogMeta.lines_returned }) }}
            <span v-if="runtimeLogMeta.truncated"> · {{ t('admin.logTruncated') }}</span>
          </p>
          <el-alert
            v-if="runtimeLogMeta.message && !runtimeLogMeta.exists"
            type="warning"
            :closable="false"
            show-icon
            :title="runtimeLogMeta.message"
            style="margin-bottom: 12px"
          />
          <div ref="logViewerRef" class="log-viewer" v-loading="loadingRuntimeLogs">
            <pre v-if="runtimeLogContent" class="log-pre">{{ runtimeLogContent }}</pre>
            <el-empty v-else :description="t('admin.logEmpty')" :image-size="60" />
          </div>
        </el-card>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted, inject, watch, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { healthCheck, triggerCrawler, getCrawlerStatus, triggerBatchPredict, getBatchPredictStatus, getConfig, saveConfig, testApiConnection, testOddsApiConnection, testFootballDataConnection, probeSporttery, generateInviteCode, getInviteCodes, deleteInviteCode, getUsers, resetUserPassword, toggleUserActive, updateUserAccess, getRuntimeLogs } from '@/api/admin'
import { getSystemHealth } from '@/api/system'
import { Plus, CopyDocument, User, UserFilled, Refresh } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { modelLabel, useModelOptions } from '@/i18n/helpers'
import { BEIJING_TZ, formatDateTimeInTz } from '@/utils/timezone'

const { t, locale } = useI18n()
const modelOptions = useModelOptions()
const isMobile = inject('isMobile', ref(false))
const activeTab = ref('system')

const healthState = ref([
  { key: 'healthDatabase', ok: false, msg: '' },
  { key: 'healthRedis', ok: false, msg: '' },
  { key: 'healthAi', ok: false, msg: '' },
  { key: 'healthScheduler', ok: false, msg: '' }
])

const healthItems = computed(() => healthState.value.map(h => ({
  key: h.key,
  label: t(`admin.${h.key}`),
  ok: h.ok,
  msg: h.msg
})))

const crawlerLogs = ref([])
const crawlingAll = ref(false)
const crawlingSchedule = ref(false)
const crawlingTeam = ref(false)
const crawlingOdds = ref(false)
const probingSporttery = ref(false)
const sportteryProbeMsg = ref('')
const sportteryProbeOk = ref(false)

const predictModel = ref('auto')
const batchPredicting = ref(false)
const batchResult = ref('')

const config = reactive({
  deepseek_api_key: '', deepseek_api_url: '',
  deepseek_configured: false,
  qwen_api_key: '', qwen_api_url: '',
  qwen_configured: false,
  glm_api_key: '', glm_api_url: '',
  glm_configured: false,
  fallback_api_key: '', fallback_configured: false,
  odds_api_key: '', odds_api_configured: false,
  football_data_api_key: '', football_data_configured: false,
  active_model: 'rule_engine',
  available_models: []
})

const apiForm = reactive({
  deepseek_api_key: '', deepseek_api_url: '',
  qwen_api_key: '', qwen_api_url: '',
  glm_api_key: '', glm_api_url: '',
  odds_api_key: '',
  football_data_api_key: ''
})
const savingConfig = ref(false)
const configSaved = ref(false)
const testResult = ref(null)
const testingModels = reactive({ deepseek: false, qwen: false, glm: false })
const testingOddsApi = ref(false)
const testingFootballData = ref(false)

function displayModelLabel(m) {
  return modelLabel(t, m === 'fallback' ? 'fallback' : m)
}

async function checkHealth() {
  healthState.value.forEach(h => { h.msg = t('admin.statusChecking') })
  try {
    const res = await getSystemHealth()
    healthState.value[0].ok = res.data.database === 'ok'
    healthState.value[0].msg = res.data.database === 'ok'
      ? (res.data.match_count > 0
        ? t('admin.statusOk')
        : t('admin.statusDbEmpty', { n: res.data.match_count ?? 0 }))
      : t('admin.statusError')
    const redisStatus = res.data.redis
    healthState.value[1].ok = redisStatus === 'ok' || redisStatus === 'memory'
    healthState.value[1].msg = redisStatus === 'ok' ? t('admin.statusOk') : redisStatus === 'memory' ? t('admin.statusMemory') : t('admin.statusUnavailable')
    healthState.value[2].ok = !!res.data.ai_configured
    healthState.value[2].msg = res.data.ai_configured
      ? (res.data.active_model || t('admin.statusOk'))
      : t('admin.noApiKey')
    healthState.value[3].ok = res.data.status === 'running'
    healthState.value[3].msg = res.data.status === 'running' ? t('admin.statusRunning') : t('admin.statusError')
  } catch (e) {
    healthState.value[0].ok = false
    healthState.value[0].msg = t('admin.statusBackendUnreachable')
    healthState.value[1].ok = false
    healthState.value[1].msg = t('admin.statusBackendUnreachable')
    healthState.value[2].ok = false
    healthState.value[2].msg = t('admin.statusBackendUnreachable')
    healthState.value[3].ok = false
    healthState.value[3].msg = e?.message || t('admin.statusConnectFail')
  }
}

async function loadConfig() {
  try {
    const res = await getConfig()
    Object.assign(config, res.data)
    apiForm.deepseek_api_key = ''
    apiForm.deepseek_api_url = config.deepseek_api_url || ''
    apiForm.qwen_api_key = ''
    apiForm.qwen_api_url = config.qwen_api_url || ''
    apiForm.glm_api_key = ''
    apiForm.glm_api_url = config.glm_api_url || ''
    apiForm.odds_api_key = ''
    apiForm.football_data_api_key = ''
    configSaved.value = false

    const anyConfigured = config.deepseek_configured || config.qwen_configured || config.glm_configured || config.fallback_configured
    if (!healthState.value[2].ok) {
      healthState.value[2].ok = anyConfigured
      healthState.value[2].msg = anyConfigured
        ? config.available_models?.map(m => displayModelLabel(m)).join(' / ') || displayModelLabel(config.active_model)
        : t('admin.noApiKey')
    }
    if (!healthState.value[3].ok) {
      healthState.value[3].ok = true
      healthState.value[3].msg = t('admin.statusRunning')
    }
  } catch {
    if (!healthState.value[2].msg || healthState.value[2].msg === t('admin.statusChecking')) {
      healthState.value[2].ok = false
      healthState.value[2].msg = t('admin.statusConnectFail')
    }
  }
}

async function saveApiConfig() {
  savingConfig.value = true
  configSaved.value = false
  try {
    const data = {}
    if (apiForm.deepseek_api_key) data.deepseek_api_key = apiForm.deepseek_api_key
    if (apiForm.deepseek_api_url) data.deepseek_api_url = apiForm.deepseek_api_url
    if (apiForm.qwen_api_key) data.qwen_api_key = apiForm.qwen_api_key
    if (apiForm.qwen_api_url) data.qwen_api_url = apiForm.qwen_api_url
    if (apiForm.glm_api_key) data.glm_api_key = apiForm.glm_api_key
    if (apiForm.glm_api_url) data.glm_api_url = apiForm.glm_api_url
    if (apiForm.odds_api_key) data.odds_api_key = apiForm.odds_api_key
    if (apiForm.football_data_api_key) data.football_data_api_key = apiForm.football_data_api_key

    if (Object.keys(data).length === 0) return

    await saveConfig(data)
    configSaved.value = true
    apiForm.deepseek_api_key = ''
    apiForm.qwen_api_key = ''
    apiForm.glm_api_key = ''
    apiForm.odds_api_key = ''
    apiForm.football_data_api_key = ''
    await loadConfig()

    setTimeout(() => { configSaved.value = false }, 5000)
  } catch {
    configSaved.value = false
  } finally {
    savingConfig.value = false
  }
}

async function testFootballDataApi() {
  testingFootballData.value = true
  testResult.value = null
  try {
    const res = await testFootballDataConnection()
    testResult.value = res.data || { ok: false, message: res.message || t('admin.testUnknown'), model: 'football-data.org' }
  } catch (e) {
    testResult.value = {
      ok: false,
      model: 'football-data.org',
      message: e.response?.data?.message || e.message || t('admin.testConnectFailed'),
      teams_count: e.response?.data?.data?.teams_count,
      matches_count: e.response?.data?.data?.matches_count,
      latency_seconds: e.response?.data?.data?.latency_seconds,
    }
  } finally {
    testingFootballData.value = false
  }
}

async function testOddsApi() {
  testingOddsApi.value = true
  testResult.value = null
  try {
    const res = await testOddsApiConnection()
    testResult.value = res.data || { ok: false, message: res.message || t('admin.testUnknown'), model: 'The Odds API' }
  } catch (e) {
    testResult.value = {
      ok: false,
      model: 'The Odds API',
      message: e.response?.data?.message || e.message || t('admin.testConnectFailed'),
      events_count: e.response?.data?.data?.events_count,
      latency_seconds: e.response?.data?.data?.latency_seconds,
    }
  } finally {
    testingOddsApi.value = false
  }
}

async function testApi(model) {
  testingModels[model] = true
  testResult.value = null
  try {
    const res = await testApiConnection(model)
    testResult.value = res.data || { ok: false, message: res.message || t('admin.testUnknown') }
  } catch (e) {
    testResult.value = {
      ok: false,
      message: e.response?.data?.message || e.message || t('admin.testConnectFailed'),
      status_code: e.response?.status || 0,
      response: e.response?.data?.data?.response || ''
    }
  } finally {
    testingModels[model] = false
  }
}

async function loadLogs() {
  try {
    const res = await getCrawlerStatus()
    crawlerLogs.value = res.data
  } catch {}
}

async function runCrawler(type) {
  const stateMap = { all: crawlingAll, schedule: crawlingSchedule, team: crawlingTeam, odds: crawlingOdds }
  const state = stateMap[type]
  if (!state) return
  state.value = true
  try {
    if (type === 'all') await triggerCrawler()
    else await triggerCrawler(type)
    await loadLogs()
  } finally {
    state.value = false
  }
}

async function probeSportteryApi() {
  probingSporttery.value = true
  sportteryProbeMsg.value = ''
  try {
    const res = await probeSporttery()
    const d = res.data || {}
    sportteryProbeOk.value = !!d.ok
    const pool = d.live_pool_size ?? d.pool_size ?? 0
    const routes = (d.route_results || [])
      .map((r) => `${r.route}:${r.http_status ?? 'err'}${r.ok ? '✓' : '✗'}`)
      .join(' · ')
    if (d.ok) {
      sportteryProbeMsg.value = `${t('admin.probeSportteryOk', { n: pool })}${routes ? ` (${routes})` : ''}`
    } else {
      const base = d.last_error || res.message || t('admin.probeSportteryFail')
      sportteryProbeMsg.value = routes ? `${base} — ${routes}` : base
      if (d.hint) sportteryProbeMsg.value += ` ${d.hint}`
    }
  } catch (e) {
    sportteryProbeOk.value = false
    sportteryProbeMsg.value = e?.response?.data?.message || t('admin.probeSportteryFail')
  } finally {
    probingSporttery.value = false
  }
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

async function pollBatchPredict() {
  const maxPolls = 600
  for (let i = 0; i < maxPolls; i++) {
    const res = await getBatchPredictStatus()
    const s = res.data || {}
    const done = Number(s.done) || 0
    const total = Number(s.total) || 0
    if (s.running) {
      batchResult.value = total > 0
        ? t('admin.batchProgress', { done, total })
        : t('admin.batchPredicting')
      await sleep(4000)
      continue
    }
    if (s.error) {
      throw new Error(s.error)
    }
    const ok = Number(s.success) || done
    batchResult.value = t('admin.batchDone', { n: ok })
    return
  }
  throw new Error(t('admin.batchTimeout'))
}

async function runBatchPredict() {
  batchPredicting.value = true
  batchResult.value = t('admin.batchPredicting')
  try {
    await triggerBatchPredict(predictModel.value, 'worldcup-2026')
    await pollBatchPredict()
  } catch (e) {
    const msg = e.response?.data?.message || e.message || t('messages.unknownError')
    batchResult.value = t('admin.batchFailed', { msg })
  } finally {
    batchPredicting.value = false
  }
}

function formatTime(time) {
  if (!time) return ''
  return new Date(time).toLocaleString(locale.value)
}

function formatLastLogin(time) {
  return formatDateTimeInTz(time, BEIJING_TZ, locale.value)
}

function formatInviteTime(time) {
  return formatDateTimeInTz(time, BEIJING_TZ, locale.value)
}

const inviteCodes = ref([])
const newCode = ref('')
const newCodeExpiresAt = ref('')
const generatingCode = ref(false)

async function generateInvite() {
  generatingCode.value = true
  try {
    const res = await generateInviteCode()
    if (res.code === 200) {
      newCode.value = res.data.code
      newCodeExpiresAt.value = res.data.expires_at ? formatInviteTime(res.data.expires_at) : ''
      ElMessage.success(res.message)
      await loadInviteCodes()
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.message || t('admin.generateFailed'))
  } finally {
    generatingCode.value = false
  }
}

async function loadInviteCodes() {
  try {
    const res = await getInviteCodes()
    inviteCodes.value = res.data || []
  } catch {}
}

async function deleteCode(id) {
  try {
    await deleteInviteCode(id)
    ElMessage.success(t('admin.deleted'))
    await loadInviteCodes()
  } catch {
    ElMessage.error(t('admin.deleteFailed'))
  }
}

function copyCode(code) {
  navigator.clipboard.writeText(code).then(() => {
    ElMessage.success(t('admin.copied'))
  }).catch(() => {})
}

const userList = ref([])
const userStats = reactive({ total: 0, active: 0 })
const loadingUsers = ref(false)
const competitionOptions = ref([])
const savingAccessIds = ref(new Set())

function competitionLabel(opt) {
  if (opt.name_key) {
    return t(`competition.names.${opt.name_key}`)
  }
  return opt.short_name || opt.slug
}

function initUserAccessFields(user) {
  user._accessExpires = user.access_expires_at || null
  user._allCompetitions = user.has_all_competitions !== false
  user._allowedCompetitions = user.allowed_competitions ? [...user.allowed_competitions] : []
  user._canAccessSporttery = !!user.can_access_sporttery
}

async function loadUsers() {
  loadingUsers.value = true
  try {
    const res = await getUsers()
    if (res.data) {
      competitionOptions.value = res.data.competition_options || []
      userList.value = (res.data.users || []).map((u) => {
        initUserAccessFields(u)
        return u
      })
      userStats.total = res.data.total || 0
      userStats.active = res.data.active || 0
    }
  } catch {
    ElMessage.error(t('admin.loadUsersFailed'))
  } finally {
    loadingUsers.value = false
  }
}

function onAllCompetitionsChange(row) {
  if (row._allCompetitions) {
    row._allowedCompetitions = []
  }
  saveUserAccess(row)
}

async function saveUserAccess(row) {
  if (row.is_admin || savingAccessIds.value.has(row.id)) return
  savingAccessIds.value.add(row.id)
  try {
    const payload = {
      clear_access_expires_at: !row._accessExpires,
    }
    if (row._accessExpires) {
      payload.access_expires_at = row._accessExpires
    }
    if (row._allCompetitions) {
      payload.grant_all_competitions = true
    } else {
      payload.allowed_competitions = row._allowedCompetitions || []
    }
    payload.can_access_sporttery = row._canAccessSporttery
    const res = await updateUserAccess(row.id, payload)
    if (res.code === 200 && res.data) {
      row.access_expires_at = res.data.access_expires_at
      row.allowed_competitions = res.data.allowed_competitions
      row.has_all_competitions = res.data.has_all_competitions
      row.can_access_sporttery = res.data.can_access_sporttery
      row._canAccessSporttery = !!res.data.can_access_sporttery
      ElMessage.success(res.message || t('admin.accessSaved'))
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.message || t('admin.accessSaveFailed'))
    await loadUsers()
  } finally {
    savingAccessIds.value.delete(row.id)
  }
}

async function handleToggleActive(row) {
  try {
    const res = await toggleUserActive(row.id)
    if (res.code === 200) {
      row.is_active = res.data.is_active
      const status = row.is_active ? t('admin.toggleEnabled') : t('admin.toggleDisabled')
      ElMessage.success(t('admin.toggleSuccess', { name: row.username, status }))
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.message || t('admin.toggleFailed'))
  }
}

async function handleResetPassword(row) {
  try {
    const { value } = await ElMessageBox.prompt(
      t('admin.resetPwdPrompt', { name: row.username }),
      t('admin.resetPassword'),
      { inputType: 'password', confirmButtonText: t('common.confirm'), cancelButtonText: t('common.cancel') }
    )
    if (!value || value.length < 6) {
      ElMessage.warning(t('admin.resetPwdTooShort'))
      return
    }
    await resetUserPassword(row.id, value)
    ElMessage.success(t('admin.resetPwdSuccess', { name: row.username }))
  } catch (e) {
    if (e === 'cancel' || e?.action === 'cancel') return
    ElMessage.error(e.response?.data?.message || t('admin.resetPwdFailed'))
  }
}

const logSource = ref('backend')
const logLines = ref(500)
const logAutoRefresh = ref(false)
const loadingRuntimeLogs = ref(false)
const runtimeLogContent = ref('')
const runtimeLogMeta = reactive({
  path: '',
  exists: false,
  size_bytes: 0,
  lines_returned: 0,
  truncated: false,
  message: '',
})
const logViewerRef = ref(null)
let logRefreshTimer = null

function formatLogSize(bytes) {
  if (!bytes) return '0 B'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`
}

async function loadRuntimeLogs() {
  loadingRuntimeLogs.value = true
  try {
    const res = await getRuntimeLogs(logSource.value, logLines.value)
    const data = res.data || {}
    runtimeLogContent.value = data.content || ''
    runtimeLogMeta.path = data.path || ''
    runtimeLogMeta.exists = !!data.exists
    runtimeLogMeta.size_bytes = data.size_bytes || 0
    runtimeLogMeta.lines_returned = data.lines_returned || 0
    runtimeLogMeta.truncated = !!data.truncated
    runtimeLogMeta.message = data.message || ''
    await nextTick()
    if (logViewerRef.value) {
      logViewerRef.value.scrollTop = logViewerRef.value.scrollHeight
    }
  } catch (e) {
    runtimeLogContent.value = ''
    runtimeLogMeta.message = e.response?.data?.message || e.message || t('admin.logLoadFailed')
  } finally {
    loadingRuntimeLogs.value = false
  }
}

function stopLogAutoRefresh() {
  if (logRefreshTimer) {
    clearInterval(logRefreshTimer)
    logRefreshTimer = null
  }
}

function startLogAutoRefresh() {
  stopLogAutoRefresh()
  logRefreshTimer = setInterval(() => {
    if (activeTab.value === 'logs') loadRuntimeLogs()
  }, 10000)
}

function onLogAutoRefreshChange(enabled) {
  if (enabled) startLogAutoRefresh()
  else stopLogAutoRefresh()
}

watch(activeTab, (tab) => {
  if (tab === 'logs') {
    loadRuntimeLogs()
    if (logAutoRefresh.value) startLogAutoRefresh()
  } else {
    stopLogAutoRefresh()
  }
})

onMounted(() => {
  checkHealth()
  loadConfig()
  loadLogs()
  loadInviteCodes()
  loadUsers()
})

onUnmounted(() => {
  stopLogAutoRefresh()
})
</script>

<style scoped>
.health-card { text-align: center; border-radius: 12px; }
.health-indicator { display: flex; align-items: center; gap: 8px; justify-content: center; margin-bottom: 8px; }
.health-status { font-size: 14px; }
.health-status.ok { color: #4caf50; }
.health-status.error { color: #f44336; }
.admin-card { border-radius: 12px; }
.card-title { font-size: 16px; font-weight: 700; }
.crawler-controls, .predict-controls { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.sporttery-probe-msg { margin: 10px 0 0; font-size: 13px; line-height: 1.5; }
.sporttery-probe-msg.ok { color: #4caf50; }
.sporttery-probe-msg.err { color: #f44336; }
.result-msg { color: #4caf50; font-size: 14px; margin-left: 12px; }
.form-hint { font-size: 13px; color: #999; margin-top: 4px; }
.form-hint a { color: #1a237e; }
.save-success { display: inline-flex; align-items: center; gap: 4px; color: #4caf50; font-size: 14px; margin-left: 12px; }
.model-section { padding: 4px 0; }
.model-header { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.model-name { font-size: 15px; font-weight: 700; }
.tag-ok { font-size: 13px; color: #4caf50; font-weight: 600; }
.tag-no { font-size: 13px; color: #999; }

.flex-between { display: flex; justify-content: space-between; align-items: center; width: 100%; }
.new-code-box {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  background: #e8f5e9;
  border-radius: 10px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}
.new-code-label { font-size: 14px; color: #2e7d32; font-weight: 600; }
.new-code-value {
  font-size: 22px;
  font-weight: 700;
  color: #1b5e20;
  letter-spacing: 4px;
  background: #fff;
  padding: 4px 12px;
  border-radius: 6px;
  user-select: all;
}
.new-code-expiry { font-size: 12px; color: #66bb6a; margin-left: 4px; }

.user-stat-card { border-radius: 12px; }
.user-stat { display: flex; align-items: center; gap: 16px; }
.user-stat-info { display: flex; flex-direction: column; }
.user-stat-num { font-size: 28px; font-weight: 700; color: #1d1d1f; }
.user-stat-label { font-size: 14px; color: #999; }
.text-muted { color: #909399; font-size: 12px; }
.access-comp-cell { display: flex; flex-direction: column; gap: 4px; }

.log-toolbar { flex-wrap: wrap; gap: 8px; }
.log-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.log-meta { font-size: 12px; color: #909399; margin: 0 0 12px; word-break: break-all; }
.log-viewer {
  background: #1e1e1e;
  border-radius: 8px;
  min-height: 320px;
  max-height: 70vh;
  overflow: auto;
}
.log-pre {
  margin: 0;
  padding: 12px 14px;
  color: #d4d4d4;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
}

@media (max-width: 767px) {
  .health-indicator { font-size: 13px; }
  .crawler-controls, .predict-controls { flex-direction: column; align-items: stretch; }
  .crawler-controls .el-button, .predict-controls .el-button { width: 100%; }
  .predict-controls .el-select { width: 100% !important; margin-right: 0 !important; }
  .model-name { font-size: 14px; }
  .form-hint { font-size: 11px; }
  .log-actions { width: 100%; }
  .log-actions .el-select { flex: 1; min-width: 120px; }
}
</style>
