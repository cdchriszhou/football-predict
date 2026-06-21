import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { STAGE_KEYS, KNOCKOUT_STAGES } from './matchLabels'

const PLAYER_STATUS_CANONICAL = {
  active: 'active',
  minor_injury: 'minor_injury',
  injured: 'injured',
  suspended: 'suspended',
  '正常': 'active',
  '轻伤': 'minor_injury',
  '重伤': 'injured',
  '停赛': 'suspended',
}

export function useModelOptions() {
  const { t } = useI18n()
  return computed(() => [
    { label: t('models.auto'), value: 'auto' },
    { label: t('models.deepseek'), value: 'deepseek' },
    { label: t('models.qwen'), value: 'qwen' },
    { label: t('models.glm'), value: 'glm' }
  ])
}

export function modelLabel(t, name) {
  if (!name) return ''
  if (name === 'rule_engine') return t('models.ruleEngine')
  if (name === 'deepseek') return t('models.deepseek')
  if (name === 'qwen') return t('models.qwen')
  if (name === 'glm') return t('models.glm')
  if (name.includes('+')) return t('models.fusion', { n: name.split('+').length })
  return name
}

export function playerStatusLabel(t, status) {
  const key = PLAYER_STATUS_CANONICAL[status] || status
  return t(`playerStatus.${key}`, status)
}

export function playerStatusTagType(status) {
  const key = PLAYER_STATUS_CANONICAL[status] || status
  if (key === 'active') return 'success'
  if (key === 'minor_injury') return 'warning'
  return 'info'
}

export function bracketStages(t) {
  return KNOCKOUT_STAGES.map((value) => ({
    value,
    label: t(`stage.${STAGE_KEYS[value]}`),
  }))
}

export function formatGroup(t, group) {
  if (!group) return ''
  return t('match.groupSuffix', { g: group })
}
