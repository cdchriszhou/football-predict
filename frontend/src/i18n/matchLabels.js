/** World Cup / knockout tournament stages only */
export const STAGE_KEYS = {
  '小组赛': 'group',
  '1/8决赛': 'round16',
  '1/4决赛': 'quarter',
  '半决赛': 'semi',
  '季军赛': 'third',
  '决赛': 'final'
}

export const TOURNAMENT_STAGES = Object.keys(STAGE_KEYS)

/** Knockout-only stages for the bracket view (exclude group stage). */
export const KNOCKOUT_STAGES = TOURNAMENT_STAGES.filter((s) => s !== '小组赛')

export const STATUS_KEYS = {
  upcoming: 'upcoming',
  live: 'live',
  finished: 'finished',
  '未开始': 'upcoming',
  '进行中': 'live',
  '已结束': 'finished',
}

const STATUS_ALIASES = {
  upcoming: ['upcoming', '未开始'],
  live: ['live', '进行中'],
  finished: ['finished', '已结束'],
}

export function isMatchStatus(status, kind) {
  return STATUS_ALIASES[kind]?.includes(status) ?? false
}

export function stageLabel(t, stage) {
  const key = STAGE_KEYS[stage]
  if (key) return t(`stage.${key}`)
  const m = stage?.match(/^第(\d+)轮$/)
  if (m) return t('stage.matchday', { n: m[1] })
  if (stage === '联赛') return t('stage.league')
  return stage
}

export function statusLabel(t, status) {
  const key = STATUS_KEYS[status]
  return key ? t(`status.${key}`) : status
}
